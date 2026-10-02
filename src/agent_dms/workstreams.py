from .errors import fail
from .models import rfc3339, text

TRANSITIONS = {("working", "question"): ("worker_id", "blocked", "question"),
               ("blocked", "answer"): ("manager_id", "working", "answer"),
               ("working", "complete"): ("worker_id", "awaiting_review", "completion"),
               ("awaiting_review", "revise"): ("manager_id", "working", "review"),
               ("awaiting_review", "approve"): ("manager_id", "approved", "approval")}


class WorkstreamsMixin:
    def visible_workstream(self, conn, agent_id, workstream_id):
        row = conn.execute("SELECT * FROM workstreams WHERE id=? AND (manager_id=? OR worker_id=?)", (workstream_id, agent_id, agent_id)).fetchone()
        if row is None:
            fail("NOT_FOUND", "Workstream not found")
        return row

    def workstream_view(self, row):
        result = {k: row[k] for k in ("thread_id", "manager_id", "worker_id", "goal", "plan_message_id", "state", "round", "revision")}
        result.update(workstream_id=row["id"], created_at=rfc3339(row["created_at"]), updated_at=rfc3339(row["updated_at"]))
        return result

    def workstream_start(self, conn, agent, session_id, worker_agent_id, goal, plan, idempotency_key):
        text(goal, "goal", 1000)
        text(plan, "plan", 16000)
        body = f"Goal: {goal}\n\nPlan:\n{plan}"
        text(body, "combined handoff", 16000)
        self.active_peer(conn, agent["id"], worker_agent_id)
        thread_id = self.create_thread(conn, agent["id"], worker_agent_id)
        workstream_id = self.store.id_factory()
        conn.execute("INSERT INTO workstreams(id,thread_id,manager_id,worker_id,goal,state,round,revision,created_at,updated_at) VALUES(?,?,?,?,?,'working',1,1,?,?)", (workstream_id, thread_id, agent["id"], worker_agent_id, goal, self.now, self.now))
        message = self.emit_message(conn, agent["id"], worker_agent_id, thread_id, body, "handoff", workstream_id=workstream_id, round=1)
        conn.execute("UPDATE workstreams SET plan_message_id=? WHERE id=?", (message["message_id"], workstream_id))
        conn.execute("INSERT INTO workstream_events(workstream_id,actor_id,action,old_state,new_state,revision,message_id,created_at) VALUES(?,?,'start',NULL,'working',1,?,?)", (workstream_id, agent["id"], message["message_id"], self.now))
        return {"workstream": self.workstream_view(self.visible_workstream(conn, agent["id"], workstream_id)), "message": message}

    def workstream_transition(self, conn, agent, session_id, workstream_id, action, text, expected_revision, idempotency_key, ack_message_id=None, claim_token=None):
        globals()["text"](text, "transition text", 16000)
        row = self.visible_workstream(conn, agent["id"], workstream_id)
        if row["revision"] != expected_revision:
            fail("REVISION_CONFLICT", "Workstream revision changed", operation="workstream_get")
        transition = TRANSITIONS.get((row["state"], action))
        if transition is None or agent["id"] != row[transition[0]]:
            fail("INVALID_TRANSITION", "Action is not allowed for this role and state")
        peer_id = row["worker_id"] if agent["id"] == row["manager_id"] else row["manager_id"]
        self.active_peer(conn, agent["id"], peer_id)
        if ack_message_id is not None:
            parent = self.visible_message(conn, agent["id"], ack_message_id)
            if parent["workstream_id"] != workstream_id or parent["recipient_id"] != agent["id"]:
                fail("CLAIM_INVALID", "Acknowledged message must be incoming in this workstream")
            self.ack_items(conn, agent, session_id, claim_token, [ack_message_id], None, require_active=True)
        elif claim_token is not None:
            fail("VALIDATION_ERROR", "claim_token requires ack_message_id")
        next_state, kind = transition[1:]
        new_round = row["round"] + (action == "revise")
        revision = row["revision"] + 1
        message = self.emit_message(conn, agent["id"], peer_id, row["thread_id"], text, kind, reply_to=ack_message_id, workstream_id=workstream_id, round=new_round)
        conn.execute("UPDATE workstreams SET state=?,round=?,revision=?,updated_at=? WHERE id=? AND revision=?", (next_state, new_round, revision, self.now, workstream_id, expected_revision))
        conn.execute("INSERT INTO workstream_events(workstream_id,actor_id,action,old_state,new_state,revision,message_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (workstream_id, agent["id"], action, row["state"], next_state, revision, message["message_id"], self.now))
        return {"workstream": self.workstream_view(self.visible_workstream(conn, agent["id"], workstream_id)), "message": message}

    def workstreams_list(self, conn, agent, session_id, limit=20, cursor=None):
        after, upper = self.page_bounds(conn, agent, "workstreams_list", {}, cursor, "workstreams")
        rows = conn.execute("SELECT * FROM workstreams WHERE seq>? AND seq<=? AND (manager_id=? OR worker_id=?) ORDER BY seq LIMIT ?", (after, upper, agent["id"], agent["id"], limit + 1)).fetchall()
        return self.paged(agent, "workstreams_list", {}, upper, [(r["seq"], self.workstream_view(r)) for r in rows], limit)

    def workstream_get(self, conn, agent, session_id, workstream_id, limit=20, cursor=None):
        row = self.visible_workstream(conn, agent["id"], workstream_id)
        filters = {"workstream_id": workstream_id}
        after, upper = self.page_bounds(conn, agent, "workstream_get", filters, cursor, "workstream_events")
        events = conn.execute("SELECT * FROM workstream_events WHERE workstream_id=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?", (workstream_id, after, upper, limit + 1)).fetchall()
        entries = []
        for event in events:
            view = dict(event)
            view["created_at"] = rfc3339(view["created_at"])
            entries.append((event["seq"], view))
        return self.paged(agent, "workstream_get", filters, upper, entries, limit, workstream=self.workstream_view(row))
