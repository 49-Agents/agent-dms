import secrets

from .errors import fail
from .models import LEASE_MS, digest, rfc3339, text


class InboxMixin:
    def notification_bump(self, conn, agent_id):
        conn.execute("UPDATE agents SET notification_revision=notification_revision+1 WHERE id=?", (agent_id,))

    def fence(self, conn, agent_id):
        changed = conn.execute("UPDATE deliveries SET claim_digest=NULL WHERE recipient_id=? AND handled_at IS NULL AND claim_digest IS NOT NULL", (agent_id,)).rowcount
        conn.execute("UPDATE claims SET state='fenced' WHERE recipient_id=? AND state='active'", (agent_id,))
        if changed:
            self.notification_bump(conn, agent_id)

    def recover_expired(self, conn, agent_id):
        changed = conn.execute("UPDATE deliveries SET claim_digest=NULL WHERE recipient_id=? AND handled_at IS NULL AND claim_digest IN (SELECT token_digest FROM claims WHERE recipient_id=? AND state='active' AND expires_at<=?)", (agent_id, agent_id, self.now)).rowcount
        conn.execute("UPDATE claims SET state='expired' WHERE recipient_id=? AND state='active' AND expires_at<=?", (agent_id, self.now))
        if changed:
            self.notification_bump(conn, agent_id)

    def counts(self, conn, agent_id):
        row = conn.execute("SELECT count(*) AS pending,coalesce(sum(claim_digest IS NULL),0) AS available,coalesce(sum(claim_digest IS NOT NULL),0) AS claimed FROM deliveries WHERE recipient_id=? AND handled_at IS NULL", (agent_id,)).fetchone()
        return dict(row)

    def inbox_peek(self, conn, agent, session_id, limit=20, cursor=None):
        self.recover_expired(conn, agent["id"])
        after, upper = self.page_bounds(conn, agent, "inbox_peek", {}, cursor, "messages")
        rows = conn.execute("SELECT m.*,d.claim_digest FROM messages m JOIN deliveries d ON d.message_id=m.id WHERE d.recipient_id=? AND d.handled_at IS NULL AND m.seq>? AND m.seq<=? ORDER BY m.seq LIMIT ?", (agent["id"], after, upper, limit + 1)).fetchall()
        entries = [(r["seq"], {**self.message_view(conn, r), "claim_state": "available" if r["claim_digest"] is None else "claimed"}) for r in rows]
        return self.paged(agent, "inbox_peek", {}, upper, entries, limit, counts=self.counts(conn, agent["id"]))

    def inbox_next(self, conn, agent, session_id, idempotency_key, limit=20):
        self.recover_expired(conn, agent["id"])
        rows = conn.execute("SELECT m.* FROM messages m JOIN deliveries d ON d.message_id=m.id WHERE d.recipient_id=? AND d.handled_at IS NULL AND d.claim_digest IS NULL ORDER BY m.seq LIMIT ?", (agent["id"], limit)).fetchall()
        token, expires = None, None
        if rows:
            token = secrets.token_urlsafe(32)
            token_hash = digest(token)
            session = self.current_session(conn, agent, session_id)
            expires = self.now + LEASE_MS
            conn.execute("INSERT INTO claims VALUES(?,?,?,?,?,'active')", (token_hash, agent["id"], session_id, session["generation"], expires))
            for row in rows:
                conn.execute("INSERT INTO claim_items(token_digest,message_id) VALUES(?,?)", (token_hash, row["id"]))
                conn.execute("UPDATE deliveries SET claim_digest=? WHERE message_id=?", (token_hash, row["id"]))
        return {"items": [self.message_view(conn, r) for r in rows], "claim_token": token, "expires_at": rfc3339(expires), "claim_active": bool(rows), "counts": self.counts(conn, agent["id"])}

    def owned_claim(self, conn, agent, session_id, claim_token):
        if not isinstance(claim_token, str) or not claim_token or len(claim_token) > 200:
            fail("CLAIM_INVALID", "An exact claim token is required")
        token_hash = digest(claim_token)
        row = conn.execute("SELECT * FROM claims WHERE token_digest=? AND recipient_id=? AND session_id=?", (token_hash, agent["id"], session_id)).fetchone()
        session = self.current_session(conn, agent, session_id)
        if row is None or row["generation"] != session["generation"]:
            fail("CLAIM_INVALID", "Claim does not belong to this session")
        return row

    def active_claim(self, conn, claim):
        if claim["expires_at"] <= self.now or claim["state"] == "expired":
            fail("CLAIM_EXPIRED", "Claim has expired; reconcile from the oldest pending message", operation="inbox_next")
        if claim["state"] != "active":
            fail("CLAIM_INVALID", "Claim is no longer active")

    def distinct_ids(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            fail("VALIDATION_ERROR", "message_ids requires 1–100 distinct IDs")

    def ack_items(self, conn, agent, session_id, claim_token, message_ids, outcome, *, require_active=False):
        self.distinct_ids(message_ids)
        if outcome is not None:
            text(outcome, "outcome", 2000, required=False)
        claim = self.owned_claim(conn, agent, session_id, claim_token)
        if require_active:
            self.active_claim(conn, claim)
        token_hash = claim["token_digest"]
        validated = []
        for message_id in message_ids:
            row = conn.execute("SELECT d.*,i.released_at FROM deliveries d JOIN claim_items i ON i.message_id=d.message_id AND i.token_digest=? WHERE d.message_id=? AND d.recipient_id=?", (token_hash, message_id, agent["id"])).fetchone()
            if row is None:
                fail("CLAIM_INVALID", "Every ID must belong to the exact claim")
            if row["handled_at"] is not None:
                if require_active:
                    fail("CLAIM_INVALID", "Reply/transition ACK requires a currently leased parent")
                if row["ack_claim_digest"] != token_hash or row["outcome"] != outcome:
                    fail("CLAIM_INVALID", "Acknowledgement conflicts with the first receipt")
            else:
                self.active_claim(conn, claim)
                if row["claim_digest"] != token_hash or row["released_at"] is not None:
                    fail("CLAIM_INVALID", "Message is no longer leased by this claim")
            validated.append(row)
        receipts = []
        for row in validated:
            handled_at = row["handled_at"] if row["handled_at"] is not None else self.now
            if row["handled_at"] is None:
                conn.execute("UPDATE deliveries SET handled_at=?,outcome=?,ack_claim_digest=?,claim_digest=NULL WHERE message_id=?", (handled_at, outcome, token_hash, row["message_id"]))
                conn.execute("INSERT INTO ack_receipts VALUES(?,?,?,?)", (token_hash, row["message_id"], handled_at, outcome))
            receipts.append({"message_id": row["message_id"], "handled_at": rfc3339(handled_at), "outcome": row["outcome"] if row["handled_at"] is not None else outcome})
        self.finish_claim(conn, token_hash)
        return {"receipts": receipts}

    def finish_claim(self, conn, token_hash):
        if conn.execute("SELECT 1 FROM deliveries WHERE claim_digest=? AND handled_at IS NULL LIMIT 1", (token_hash,)).fetchone() is None:
            conn.execute("UPDATE claims SET state='handled' WHERE token_digest=? AND state='active'", (token_hash,))

    def inbox_ack(self, conn, agent, session_id, claim_token, message_ids, idempotency_key, outcome=None):
        return self.ack_items(conn, agent, session_id, claim_token, message_ids, outcome)

    def inbox_release(self, conn, agent, session_id, claim_token, idempotency_key, message_ids=None):
        claim = self.owned_claim(conn, agent, session_id, claim_token)
        self.active_claim(conn, claim)
        token_hash = claim["token_digest"]
        if message_ids is None:
            message_ids = [r[0] for r in conn.execute("SELECT message_id FROM deliveries WHERE claim_digest=? AND handled_at IS NULL", (token_hash,))]
        else:
            self.distinct_ids(message_ids)
            for message_id in message_ids:
                if conn.execute("SELECT 1 FROM deliveries WHERE message_id=? AND claim_digest=? AND handled_at IS NULL", (message_id, token_hash)).fetchone() is None:
                    fail("CLAIM_INVALID", "Every ID must currently belong to this claim")
        for message_id in message_ids:
            conn.execute("UPDATE deliveries SET claim_digest=NULL WHERE message_id=?", (message_id,))
            conn.execute("UPDATE claim_items SET released_at=? WHERE token_digest=? AND message_id=?", (self.now, token_hash, message_id))
        if message_ids:
            self.notification_bump(conn, agent["id"])
        if conn.execute("SELECT 1 FROM deliveries WHERE claim_digest=? LIMIT 1", (token_hash,)).fetchone() is None:
            conn.execute("UPDATE claims SET state='released' WHERE token_digest=?", (token_hash,))
        return {"released_message_ids": message_ids, "counts": self.counts(conn, agent["id"])}

    def inbox_renew(self, conn, agent, session_id, claim_token, idempotency_key):
        claim = self.owned_claim(conn, agent, session_id, claim_token)
        self.active_claim(conn, claim)
        expires = self.now + LEASE_MS
        conn.execute("UPDATE claims SET expires_at=? WHERE token_digest=?", (expires, claim["token_digest"]))
        return {"expires_at": rfc3339(expires)}

    def inbox_hint(self, conn, agent, session_id, after_revision):
        self.recover_expired(conn, agent["id"])
        revision = conn.execute("SELECT notification_revision FROM agents WHERE id=?", (agent["id"],)).fetchone()[0]
        return {"notification_revision": revision, "available": self.counts(conn, agent["id"])["available"], "changed": revision != after_revision}
