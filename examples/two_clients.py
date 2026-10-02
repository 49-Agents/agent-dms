"""Local two-credential quickstart through real independent MCP connections."""
import argparse
import asyncio
from uuid import uuid4

from agent_dms.client import call, connect, read_token
from agent_dms.mcp_server import configure_safe_logging


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--manager-token-file", required=True)
    parser.add_argument("--worker-token-file", required=True)
    args = parser.parse_args()
    configure_safe_logging()
    async with connect(args.url, read_token(args.manager_token_file)) as manager, connect(args.url, read_token(args.worker_token_file)) as worker:
        own = await call(manager, "agent_whoami", {})
        peer = await call(worker, "agent_whoami", {})
        sessions = []
        for client in (manager, worker):
            sessions.append(await call(client, "session_open", {"client_session_key": str(uuid4()), "status": "Checking durable messaging with my project peer", "availability": "working", "idempotency_key": str(uuid4())}))
        manager_id, worker_id = [s["session_id"] for s in sessions]
        async def operation(client, session_id, name, **arguments):
            from agent_dms.service import MUTATING
            if name in MUTATING:
                arguments["idempotency_key"] = str(uuid4())
            return await call(client, name, {"session_id": session_id, **arguments})
        try:
            directory = await operation(manager, manager_id, "agents_list")
            print("Directory:", ", ".join(v["name"] + " (" + v["presence"] + ")" for v in directory["items"]))
            print("Status:", directory["items"][0]["status"])
            message = await operation(manager, manager_id, "dm_send", to_agent_id=peer["agent_id"], body="Please verify the implementation.")
            print("Sent:", message["message_id"])
            batch = await operation(worker, worker_id, "inbox_next")
            print("Claimed:", [m["message_id"] for m in batch["items"]])
            reply = await operation(worker, worker_id, "dm_reply", message_id=message["message_id"], body="Verification complete.", acknowledge_parent=True, claim_token=batch["claim_token"])
            print("Reply and explicit parent ACK:", reply["message_id"])
            incoming = await operation(manager, manager_id, "inbox_next")
            await operation(manager, manager_id, "inbox_ack", claim_token=incoming["claim_token"], message_ids=[reply["message_id"]], outcome="Reviewed")
            print("Explicit reply ACK: handled")
        finally:
            await operation(manager, manager_id, "session_close")
            await operation(worker, worker_id, "session_close")


if __name__ == "__main__":
    asyncio.run(main())
