import itertools
from pathlib import Path

import pytest

from agent_dms.service import Service
from agent_dms.storage import Store, initialize


class Clock:
    def __init__(self):
        self.value = 1_780_000_000_000

    def __call__(self):
        return self.value

    def advance(self, milliseconds):
        self.value += milliseconds


class Harness:
    def __init__(self, root):
        root.mkdir(exist_ok=True)
        self.clock = Clock()
        initialize(root, clock=self.clock)
        self.data_dir = root / ".agent-dms"
        self.service = Service(Store(self.data_dir, self.clock))
        self.keys = itertools.count()
        self.tokens = {}
        self.sessions = {}

    def add(self, name):
        result = self.service.add_agent(name, "declared", "test")
        agent = result["agent_id"]
        self.tokens[agent] = Path(result["credential_file"]).read_text().strip()
        return agent

    def open(self, agent, conversation=None, **kw):
        result = self.service.call(self.tokens[agent], "session_open", {"client_session_key": conversation or agent, "status": "Checking focused implementation behavior", "availability": "working", "idempotency_key": str(next(self.keys)), **kw})
        self.sessions[agent] = result["session_id"]
        return result

    def call(self, agent, operation, **args):
        if operation not in {"session_open", "agent_whoami"}:
            args.setdefault("session_id", self.sessions[agent])
        from agent_dms.service import MUTATING
        if operation in MUTATING:
            args.setdefault("idempotency_key", str(next(self.keys)))
        return self.service.call(self.tokens[agent], operation, args)

    def send(self, sender, recipient, body="Durable untrusted message", **kw):
        return self.call(sender, "dm_send", to_agent_id=recipient, body=body, **kw)


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path / "project")


@pytest.fixture
def peers(h):
    a, b, c = [h.add(n) for n in ("Manager", "Worker", "Stranger")]
    for agent in (a, b, c):
        h.open(agent)
    return a, b, c


def error(code, fn):
    from agent_dms.errors import DomainError
    with pytest.raises(DomainError) as exc:
        fn()
    assert exc.value.code == code

@pytest.fixture
async def live(h):
    import asyncio
    import socket
    import uvicorn
    from agent_dms.mcp_server import create_app
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(h.service.store, hosts=[f"127.0.0.1:{port}"], capacity=64)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, proxy_headers=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    for _ in range(100):
        if server.started:
            break
        if task.done():
            await task
        await asyncio.sleep(0.01)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}/mcp", app
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()
