from .errors import fail
from .models import LEASE_MS, availability, key, rfc3339, status_text, text


class SessionsMixin:
    def current_session(self, conn, agent, session_id, *, allow_closed=False):
        if not session_id:
            fail("SESSION_REQUIRED", "Open an application session first", operation="session_open")
        session = conn.execute("SELECT * FROM sessions WHERE id=? AND agent_id=?", (session_id, agent["id"])).fetchone()
        if session is None:
            fail("SESSION_REQUIRED", "Session does not belong to this principal", operation="session_open")
        if agent["current_session_id"] != session_id or session["state"] == "superseded":
            fail("SESSION_SUPERSEDED", "This conversation no longer owns the inbox")
        if session["state"] != "active" and not allow_closed:
            fail("SESSION_REQUIRED", "Application session is closed", operation="session_open")
        return session

    def touch(self, conn, session):
        conn.execute("UPDATE sessions SET last_seen_at=?,lease_until=? WHERE id=? AND state='active'", (self.now, self.now + LEASE_MS, session["id"]))

    def session_view(self, row):
        return {"session_id": row["id"], "generation": row["generation"], "state": row["state"],
                "opened_at": rfc3339(row["opened_at"]), "last_seen_at": rfc3339(row["last_seen_at"]), "lease_until": rfc3339(row["lease_until"])}

    def session_open(self, conn, agent, client_session_key, status, availability, takeover=False, idempotency_key=None):
        client_session_key = text(client_session_key, "client_session_key", 128)
        key(idempotency_key)
        old = conn.execute("SELECT * FROM sessions WHERE agent_id=? AND client_session_key=?", (agent["id"], client_session_key)).fetchone()
        current = conn.execute("SELECT * FROM sessions WHERE id=?", (agent["current_session_id"],)).fetchone()
        if old is not None:
            if old["state"] != "active" or old["id"] != agent["current_session_id"]:
                fail("SESSION_SUPERSEDED", "A closed or superseded conversation key cannot reopen")
            self.touch(conn, old)
            return self.session_view(conn.execute("SELECT * FROM sessions WHERE id=?", (old["id"],)).fetchone())
        if current is not None and current["state"] == "active" and current["lease_until"] > self.now and not takeover:
            fail("SESSION_CONFLICT", "Another conversation owns a live session; explicit takeover is required")
        normalized, words = status_text(status)
        availability_value = globals()["availability"](availability)
        generation = 1 + conn.execute("SELECT coalesce(max(generation),0) FROM sessions WHERE agent_id=?", (agent["id"],)).fetchone()[0]
        session_id = self.store.id_factory()
        if current is not None:
            conn.execute("UPDATE sessions SET state='superseded',lease_until=? WHERE id=?", (self.now, current["id"]))
        self.fence(conn, agent["id"])
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,'active',?,?,?)", (session_id, agent["id"], client_session_key, generation, self.now, self.now, self.now + LEASE_MS))
        conn.execute("UPDATE agents SET current_session_id=? WHERE id=?", (session_id, agent["id"]))
        conn.execute("INSERT INTO statuses VALUES(?,?,?,?,?,?,1,?) ON CONFLICT(agent_id) DO UPDATE SET session_id=excluded.session_id,generation=excluded.generation,text=excluded.text,word_count=excluded.word_count,availability=excluded.availability,revision=statuses.revision+1,updated_at=excluded.updated_at", (agent["id"], session_id, generation, normalized, words, availability_value, self.now))
        return self.session_view(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())

    def session_heartbeat(self, conn, agent, session_id):
        return self.session_view(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())

    def session_close(self, conn, agent, session_id):
        self.fence(conn, agent["id"])
        conn.execute("UPDATE sessions SET state='closed',lease_until=? WHERE id=?", (self.now, session_id))
        return {"session_id": session_id, "state": "closed"}
