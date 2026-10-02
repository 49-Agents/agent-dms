"""Transport-only stdio adapter; never constructs project state or claims work."""
import asyncio
import sys

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .client import connect, read_token
from .mcp_server import INSTRUCTIONS, configure_safe_logging


async def bridge(url, token_file):
    configure_safe_logging()
    async with connect(url, read_token(token_file)) as upstream:
        async def forward(awaitable):
            try:
                return await awaitable
            except Exception:
                raise RuntimeError("Daemon request failed; check credentials and session authority") from None
        async def list_tools(ctx, params):
            return await forward(upstream.list_tools(params=params))

        async def call_tool(ctx, params):
            return await forward(upstream.call_tool(params.name, params.arguments or {}))

        async def list_prompts(ctx, params):
            return await forward(upstream.list_prompts(params=params))

        async def get_prompt(ctx, params):
            return await forward(upstream.get_prompt(params.name, params.arguments))

        async def list_resources(ctx, params):
            return await forward(upstream.list_resources(params=params))

        async def read_resource(ctx, params):
            return await forward(upstream.read_resource(params.uri))

        server = Server("agent-dms", version="0.1.0", instructions=INSTRUCTIONS, on_list_tools=list_tools, on_call_tool=call_tool, on_list_prompts=list_prompts, on_get_prompt=get_prompt, on_list_resources=list_resources, on_read_resource=read_resource)
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
