import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_dms.client import call, connect


async def test_stdio_adapter_direct_http_peer(h, peers, live):
    a, b, _ = peers
    url, app = live
    token_file = h.data_dir / "bridge.token"
    from agent_dms.config import private_write
    private_write(token_file, h.tokens[b])
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent_dms", "stdio", "--url", url, "--token-file", str(token_file)])
    async with stdio_client(params) as streams:
        async with ClientSession(streams[0], streams[1], read_timeout_seconds=5) as bridge:
            await bridge.initialize()
            async with connect(url, h.tokens[a]) as direct:
                assert (await bridge.list_tools()).model_dump() == (await direct.list_tools()).model_dump()
                assert (await bridge.list_prompts()).model_dump() == (await direct.list_prompts()).model_dump()
                assert (await bridge.read_resource("agent-dms://protocol")).contents
                assert (await bridge.get_prompt("agent-dms-acla")).messages
                sent = await call(direct, "dm_send", {"session_id": h.sessions[a], "to_agent_id": b, "body": "through one database", "idempotency_key": "stdio-send"})
                batch = await call(bridge, "inbox_next", {"session_id": h.sessions[b], "idempotency_key": "stdio-claim"})
                assert batch["items"][0]["message_id"] == sent["message_id"]
                reply = await call(bridge, "dm_reply", {"session_id": h.sessions[b], "message_id": sent["message_id"], "body": "stdio reply", "acknowledge_parent": True, "claim_token": batch["claim_token"], "idempotency_key": "stdio-reply"})
                assert (await call(direct, "inbox_peek", {"session_id": h.sessions[a]}))["items"][0]["message_id"] == reply["message_id"]
    # SDK parsing successful stdio replies verifies stdout contained only MCP frames.
    assert h.call(b, "inbox_peek")["counts"]["pending"] == 0


async def test_bridge_transport_fault_preserves_error_envelope():
    import json
    from mcp import types
    from agent_dms.stdio_bridge import forward_tool
    class FailedUpstream:
        async def call_tool(self, *args):
            raise RuntimeError("TOKEN-SENTINEL PRIVATE-MESSAGE-SENTINEL")
    result = await forward_tool(FailedUpstream(), types.CallToolRequestParams(name="dm_send", arguments={}))
    assert result.is_error and result.structured_content["error"]["code"] == "INTERNAL_ERROR"
    assert result.structured_content["request_id"] and not result.structured_content["ok"]
    assert "SENTINEL" not in json.dumps(result.model_dump())
