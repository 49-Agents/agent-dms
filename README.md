# agent-dms

**let agents DM each other**

One local MCP server lets agents discover each other, publish what they are
working on, and exchange durable direct messages. Each agent has its own
identity and a required status of 1–30 words. A 49Agents project, licensed under
[MIT](https://github.com/49-Agents/agent-dms/blob/main/LICENSE).

```text
Agent A ── HTTP or stdio ──┐
                          ├── agent-dms ── local SQLite mailbox
Agent B ── HTTP or stdio ──┘

discover → set status → send → claim → handle → acknowledge
```

The server also supports Manager/Worker handoffs, questions, completion reports
and review replies. It connects existing agents; model execution remains with
your chosen clients.

**Experimental 0.1 series.** Check
[Releases](https://github.com/49-Agents/agent-dms/releases) for published versions;
until one exists, use an authorized source checkout. Linux and Python 3.11/3.12
are tested. MCP HTTP/stdio interoperability is tested with the official
SDK; native Claude Code and Codex sessions still need the
[client acceptance check](https://github.com/49-Agents/agent-dms/blob/main/docs/NATIVE-CLIENT-ACCEPTANCE.md).
Provider labels in the demo do not represent native model runs.

## Try a two-agent exchange

From this source checkout, on Linux with Python 3.11+:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python examples/demo.py
```

The demo provisions two temporary identities, starts a temporary local server,
then exchanges and explicitly acknowledges a DM and reply. It prints:

```text
Directory: Manager (online), Worker (online)
Status: Checking durable messaging with my project peer
Sent: <message UUID>
Claimed: ['<message UUID>']
Reply and explicit parent ACK: <reply UUID>
Explicit reply ACK: handled
Demo passed; temporary mailbox removed.
```

No provider account is needed for this SDK demo. It uses an isolated temporary
mailbox and an available loopback port. See
[installation](https://github.com/49-Agents/agent-dms/blob/main/docs/INSTALL.md)
for a wheel install and platform requirements.

## Connect agents to your project

Initialize once, provision a separate identity for each conversation, and keep
one daemon running:

```sh
agent-dms init --project-root .
agent-dms agent --data-dir .agent-dms add Manager --provider codex
agent-dms agent --data-dir .agent-dms add Worker --provider claude
agent-dms serve --data-dir .agent-dms
```

Each `add` returns an agent UUID and its private token-file path. Keep these
files out of Git. Print a configuration example using the returned values:

```sh
agent-dms config --data-dir .agent-dms --client codex --agent AGENT_UUID --transport http
agent-dms config --data-dir .agent-dms --client claude --agent AGENT_UUID --transport stdio \
  --token-file /absolute/project/.agent-dms/credentials/AGENT-FILE.token
```

Configuration generation does not edit your client settings. See
[client setup](https://github.com/49-Agents/agent-dms/blob/main/docs/CLIENTS.md)
for secret handling, separate conversation identities and the agent protocol.
The stdio adapter forwards to the same running daemon; it does not create a
second mailbox or start a model. No provider API key is stored by agent-dms.

## What the mailbox guarantees

- **Visible work:** discover peers and their status. Status must be refreshed
  within 15 minutes before new sends. Presence and current work are separate.
- **Durable messages:** reading does not remove a DM. Claim an exact leased
  batch, then acknowledge only the messages you handled.
- **Safe retries:** reuse the same operation and idempotency key after a lost
  response. Message acknowledgement does not guarantee exactly-once side effects.
- **Review conversations:** explicit Manager/Worker handoff, question, answer,
  completion, revision and approval messages within existing owner permissions.
- **Optional nudges:** a local watcher can emit stdout hints or use a supported
  installed Codex queue. Wakeup acceptance does not prove an agent acted.

## Scope and support

One project, one daemon, one SQLite database on a local filesystem. v1 has no
retention/pruning, process launcher, hosted service or web UI. Native Windows
is unsupported (`fcntl` is required); macOS and WSL need separate validation.
Python versions newer than the CI matrix are not verified yet.

The default daemon binds to loopback with bearer authentication. Remote use
requires explicit allowlists and trusted TLS termination. Anyone who can read
state files as the same OS user can bypass application isolation. Treat message
text as untrusted input. See the
[security boundary](https://github.com/49-Agents/agent-dms/blob/main/docs/SECURITY.md).

## Documentation

- [Installation](https://github.com/49-Agents/agent-dms/blob/main/docs/INSTALL.md) · [Client setup](https://github.com/49-Agents/agent-dms/blob/main/docs/CLIENTS.md)
- [Protocol and tools](https://github.com/49-Agents/agent-dms/blob/main/docs/PROTOCOL.md) · [Architecture](https://github.com/49-Agents/agent-dms/blob/main/docs/ARCHITECTURE.md)
- [Backup, recovery and operations](https://github.com/49-Agents/agent-dms/blob/main/docs/OPERATIONS.md)
- [Contributing](https://github.com/49-Agents/agent-dms/blob/main/CONTRIBUTING.md) · [Support](https://github.com/49-Agents/agent-dms/blob/main/SUPPORT.md) · [Security reporting](https://github.com/49-Agents/agent-dms/blob/main/SECURITY.md)
- [Release notes](https://github.com/49-Agents/agent-dms/blob/main/CHANGELOG.md) · [Implementation evidence](https://github.com/49-Agents/agent-dms/blob/main/docs/IMPLEMENTATION-RESULTS.md)

<!-- mcp-name: io.github.49-Agents/agent-dms -->
