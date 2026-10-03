import hmac
import secrets
import sqlite3

from .config import private_dir, private_write, safe_path, validate_directory
from .errors import fail
from .models import agent_name, digest, text


class IdentityMixin:
    def authenticate(self, conn, token):
        if not isinstance(token, str) or not token:
            fail("UNAUTHENTICATED", "A valid project bearer credential is required")
        token_hash = digest(token)
        row = conn.execute("SELECT * FROM agents WHERE token_digest=? AND state='active'", (token_hash,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_digest"], token_hash):
            fail("UNAUTHENTICATED", "A valid project bearer credential is required")
        return row

    def agent_whoami(self, conn, agent, **args):
        return {"project_id": self.store.config.project_id, "agent_id": agent["id"], "name": agent["name"], "provider": agent["provider"], "model": agent["model"]}

    def add_agent(self, name, provider=None, model=None):
        name = agent_name(name)
        provider = None if provider is None else text(provider, "provider", 100, required=False)
        model = None if model is None else text(model, "model", 200, required=False)
        validate_directory(self.store.data_dir)
        private_dir(self.store.data_dir / "credentials")
        agent_id, token = self.store.id_factory(), secrets.token_urlsafe(32)
        path = self.store.data_dir / "credentials" / f"{agent_id}-{self.store.id_factory()}.token"
        private_write(path, token + "\n")
        try:
            with self.store.transaction() as conn:
                conn.execute("INSERT INTO agents(id,name,name_key,provider,model,state,token_digest) VALUES(?,?,?,?,?,'active',?)", (agent_id, name, name.casefold(), provider, model, digest(token)))
        except sqlite3.IntegrityError:
            fail("VALIDATION_ERROR", "Agent name already exists")
        return {"agent_id": agent_id, "credential_file": str(path)}

    def operator_list(self):
        with self.store.transaction() as conn:
            return [dict(r) for r in conn.execute("SELECT id,name,provider,model,state FROM agents ORDER BY name_key")]

    def revoke(self, agent_id):
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
            if row is None:
                fail("NOT_FOUND", "Agent not found")
            self.fence(conn, agent_id)
            conn.execute("UPDATE sessions SET state='closed',lease_until=? WHERE agent_id=? AND state='active'", (self.now, agent_id))
            conn.execute("UPDATE agents SET state='revoked' WHERE id=?", (agent_id,))
        return {"agent_id": agent_id, "state": "revoked"}

    def rotate_token(self, agent_id):
        validate_directory(self.store.data_dir)
        private_dir(self.store.data_dir / "credentials")
        with self.store.transaction() as conn:
            row = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
            if row is None:
                fail("NOT_FOUND", "Agent not found")
            token = secrets.token_urlsafe(32)
            path = self.store.data_dir / "credentials" / f"{agent_id}-{self.store.id_factory()}.token"
            private_write(path, token + "\n")
            self.fence(conn, agent_id)
            conn.execute("UPDATE sessions SET state='closed',lease_until=? WHERE agent_id=? AND state='active'", (self.now, agent_id))
            conn.execute("UPDATE agents SET token_digest=? WHERE id=?", (digest(token), agent_id))
        return {"credential_file": str(path)}
