"""Isolated persistent test actor; no provider session or model is launched."""
import asyncio
import json
import sys

from agent_dms.client import connect, read_token
from agent_dms.mcp_server import configure_safe_logging


async def main():
    configure_safe_logging()
    token = read_token(sys.argv[2])
    for line in sys.stdin:
        request = json.loads(line)
        try:
            async with connect(sys.argv[1], token) as session:
                result = await session.call_tool(request["tool"], request["arguments"])
                print(json.dumps(result.structured_content), flush=True)
        except Exception:
            print(json.dumps({"ok": False, "error": {"code": "CLIENT_FAILURE"}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
