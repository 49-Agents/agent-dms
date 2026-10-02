from .errors import fail
from .models import KINDS, rfc3339, text


class MessagingMixin:
    def participant_thread(self, conn, agent_id, thread_id):
        row = conn.execute("SELECT * FROM threads WHERE id=? AND (agent_a=? OR agent_b=?)", (thread_id, agent_id, agent_id)).fetchone()
        if row is None:
            fail("NOT_FOUND", "Thread not found")
        return row

    def visible_message(self, conn, agent_id, message_id):
        row = conn.execute("SELECT * FROM messages WHERE id=? AND (sender_id=? OR recipient_id=?)", (message_id, agent_id, agent_id)).fetchone()
        if row is None:
            fail("NOT_FOUND", "Message not found")
        return row

    def active_peer(self, conn, own_id, peer_id):
        if peer_id == own_id:
            fail("VALIDATION_ERROR", "Self-messages are not supported")
        if conn.execute("SELECT id FROM agents WHERE id=? AND state='active'", (peer_id,)).fetchone() is None:
            fail("NOT_FOUND", "Recipient not found")

    def create_thread(self, conn, own_id, peer_id, subject=None):
        thread_id = self.store.id_factory()
        conn.execute("INSERT INTO threads(id,agent_a,agent_b,created_at,subject) VALUES(?,?,?,?,?)", (thread_id, own_id, peer_id, self.now, subject))
        return thread_id

    def emit_message(self, conn, sender_id, recipient_id, thread_id, body, kind="message", reply_to=None, workstream_id=None, round=None):
        message_id = self.store.id_factory()
        conn.execute("INSERT INTO messages(id,thread_id,sender_id,recipient_id,body,kind,reply_to,created_at,workstream_id,round) VALUES(?,?,?,?,?,?,?,?,?,?)", (message_id, thread_id, sender_id, recipient_id, body, kind, reply_to, self.now, workstream_id, round))
        conn.execute("INSERT INTO deliveries(message_id,recipient_id) VALUES(?,?)", (message_id, recipient_id))
        conn.execute("UPDATE agents SET notification_revision=notification_revision+1 WHERE id=?", (recipient_id,))
        return self.message_view(conn, conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())

    def message_view(self, conn, row):
        delivery = conn.execute("SELECT * FROM deliveries WHERE message_id=?", (row["id"],)).fetchone()
        result = {k: row[k] for k in ("seq", "thread_id", "sender_id", "recipient_id", "body", "kind", "reply_to", "workstream_id", "round")}
        result.update(message_id=row["id"], created_at=rfc3339(row["created_at"]),
                      delivery={"handled_at": rfc3339(delivery["handled_at"]), "outcome": delivery["outcome"]})
        return result

    def dm_send(self, conn, agent, session_id, to_agent_id, body, idempotency_key, thread_id=None, subject=None, kind="message"):
        text(body, "body", 16000)
        if subject is not None:
            text(subject, "subject", 200, required=False)
        if kind not in KINDS:
            fail("VALIDATION_ERROR", "Unsupported message kind")
        self.active_peer(conn, agent["id"], to_agent_id)
        if thread_id is None:
            thread_id = self.create_thread(conn, agent["id"], to_agent_id, subject)
        else:
            thread = self.participant_thread(conn, agent["id"], thread_id)
            if {thread["agent_a"], thread["agent_b"]} != {agent["id"], to_agent_id}:
                fail("NOT_FOUND", "Thread not found")
        return self.emit_message(conn, agent["id"], to_agent_id, thread_id, body, kind)

    def dm_reply(self, conn, agent, session_id, message_id, body, idempotency_key, acknowledge_parent=False, claim_token=None):
        text(body, "body", 16000)
        parent = self.visible_message(conn, agent["id"], message_id)
        if parent["recipient_id"] != agent["id"]:
            fail("NOT_FOUND", "Incoming message not found")
        self.active_peer(conn, agent["id"], parent["sender_id"])
        if acknowledge_parent:
            self.ack_items(conn, agent, session_id, claim_token, [message_id], None)
        elif claim_token is not None:
            fail("VALIDATION_ERROR", "claim_token requires acknowledge_parent=true")
        return self.emit_message(conn, agent["id"], parent["sender_id"], parent["thread_id"], body, reply_to=message_id)

    def thread_view(self, row):
        return {"thread_id": row["id"], "participants": [row["agent_a"], row["agent_b"]], "subject": row["subject"], "created_at": rfc3339(row["created_at"])}

    def threads_list(self, conn, agent, session_id, limit=20, cursor=None):
        after, upper = self.page_bounds(conn, agent, "threads_list", {}, cursor, "threads")
        rows = conn.execute("SELECT * FROM threads WHERE seq>? AND seq<=? AND (agent_a=? OR agent_b=?) ORDER BY seq LIMIT ?", (after, upper, agent["id"], agent["id"], limit + 1)).fetchall()
        return self.paged(agent, "threads_list", {}, upper, [(r["seq"], self.thread_view(r)) for r in rows], limit)

    def thread_read(self, conn, agent, session_id, thread_id, limit=20, cursor=None):
        self.participant_thread(conn, agent["id"], thread_id)
        filters = {"thread_id": thread_id}
        after, upper = self.page_bounds(conn, agent, "thread_read", filters, cursor, "messages")
        rows = conn.execute("SELECT * FROM messages WHERE thread_id=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?", (thread_id, after, upper, limit + 1)).fetchall()
        return self.paged(agent, "thread_read", filters, upper, [(r["seq"], self.message_view(conn, r)) for r in rows], limit, thread_id=thread_id)
