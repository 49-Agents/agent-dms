from .errors import fail
from .models import PRESENCE_MS, STATUS_MS, availability, rfc3339, status_text, text


class StatusMixin:
    def require_fresh(self, conn, agent):
        row = conn.execute("SELECT * FROM statuses WHERE agent_id=?", (agent["id"],)).fetchone()
        if row is None or self.now - row["updated_at"] >= STATUS_MS:
            fail("STATUS_STALE", "Refresh your current-work status before sending", operation="status_set", expected_revision=None if row is None else row["revision"])

    def directory_view(self, conn, agent):
        session = conn.execute("SELECT * FROM sessions WHERE id=?", (agent["current_session_id"],)).fetchone()
        status = conn.execute("SELECT * FROM statuses WHERE agent_id=?", (agent["id"],)).fetchone()
        online = session is not None and session["state"] == "active" and session["lease_until"] > self.now and self.now - session["last_seen_at"] < PRESENCE_MS
        return {"agent_id": agent["id"], "name": agent["name"], "provider": agent["provider"], "model": agent["model"],
                "status": None if status is None else status["text"], "status_word_count": 0 if status is None else status["word_count"],
                "status_updated_at": None if status is None else rfc3339(status["updated_at"]), "status_revision": 0 if status is None else status["revision"],
                "status_fresh": status is not None and self.now - status["updated_at"] < STATUS_MS,
                "status_age_seconds": None if status is None else max(0, (self.now - status["updated_at"]) // 1000),
                "availability": None if status is None else status["availability"], "presence": "online" if online else "offline",
                "last_seen_at": None if session is None else rfc3339(session["last_seen_at"])}

    def status_set(self, conn, agent, session_id, status, availability, expected_revision, idempotency_key):
        normalized, words = status_text(status)
        availability_value = globals()["availability"](availability)
        session = self.current_session(conn, agent, session_id)
        changed = conn.execute("UPDATE statuses SET text=?,word_count=?,availability=?,revision=revision+1,updated_at=? WHERE agent_id=? AND session_id=? AND generation=? AND revision=?", (normalized, words, availability_value, self.now, agent["id"], session_id, session["generation"], expected_revision)).rowcount
        if changed != 1:
            fail("REVISION_CONFLICT", "Status revision changed; read agent_get and retry with a new key", operation="agent_get")
        return self.directory_view(conn, agent)

    def agents_list(self, conn, agent, session_id, limit=20, cursor=None, include_offline=False, query=None):
        if query is not None:
            query = text(query, "query", 100, strip=True, required=False).casefold()
        filters = {"include_offline": include_offline, "query": query}
        after, upper = self.page_bounds(conn, agent, "agents_list", filters, cursor, "agents", "rowid")
        found = []
        # Scan bounded SQL windows; do not materialize the roster to apply presence filters.
        position = after
        while len(found) <= limit:
            rows = conn.execute("SELECT rowid AS seq,* FROM agents WHERE rowid>? AND rowid<=? AND state='active' ORDER BY rowid LIMIT 100", (position, upper)).fetchall()
            if not rows:
                break
            for row in rows:
                position = row["seq"]
                view = self.directory_view(conn, row)
                if row["id"] != agent["id"] and not include_offline and view["presence"] != "online":
                    continue
                if query and query not in row["name"].casefold() and query not in (row["provider"] or "").casefold():
                    continue
                found.append((position, view))
                if len(found) > limit:
                    break
        return self.paged(agent, "agents_list", filters, upper, found, limit, filters=filters)

    def agent_get(self, conn, agent, session_id, agent_id):
        row = conn.execute("SELECT * FROM agents WHERE id=? AND state='active'", (agent_id,)).fetchone()
        if row is None:
            fail("NOT_FOUND", "Agent not found")
        return self.directory_view(conn, row)
