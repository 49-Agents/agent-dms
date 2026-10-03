"""One official SDK HTTP call. Credentials are read from a private file.

python examples/client_call.py --url URL --token-file FILE TOOL < arguments.json
Preserve session IDs and retry keys between invocations. Each invocation is an
independent MCP connection, never a new application session unless explicitly asked.
"""
import argparse
import asyncio
import json
import sys

from agent_dms.client import connect, read_token
from agent_dms.mcp_server import configure_safe_logging


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("tool")
    args = parser.parse_args()
    configure_safe_logging()
    arguments = json.load(sys.stdin)
    try:
        async with connect(args.url, read_token(args.token_file)) as session:
            result = await session.call_tool(args.tool, arguments)
            print(json.dumps(result.structured_content))
            return 1 if result.is_error else 0
    except Exception:
        print("MCP call failed; reconcile the same operation/key", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
