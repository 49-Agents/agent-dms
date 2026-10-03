import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import safe_path
from .errors import DomainError, fail


def service_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query or parsed.path != "/mcp":
        fail("VALIDATION_ERROR", "Service URL must be HTTP(S) /mcp without embedded credentials, query or fragment")
    return value


def read_token(path):
    path = safe_path(path)
    if not path.is_file() or path.stat().st_mode & 0o077:
        fail("VALIDATION_ERROR", "Credential file must be private (0600)")
    token = path.read_text().strip()
    if not token:
        fail("UNAUTHENTICATED", "Credential file is empty")
    return token


@asynccontextmanager
async def connect(url, token):
    service_url(url)
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}, timeout=35, follow_redirects=False) as http:
        async with streamable_http_client(url, http_client=http, terminate_on_close=False) as streams:
            async with ClientSession(streams[0], streams[1], read_timeout_seconds=35) as session:
                await session.initialize()
                yield session


async def call(session, name, arguments):
    result = await session.call_tool(name, arguments)
    envelope = result.structured_content
    if not isinstance(envelope, dict) or envelope.get("version") != 1:
        fail("INTERNAL_ERROR", "Server returned an invalid result")
    if not envelope.get("ok"):
        error = envelope["error"]
        raise DomainError(error["code"], error["message"], error.get("retryable", False), error.get("repair", {}))
    return envelope["data"]
