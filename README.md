# agent-dms

Connect existing Claude, Codex and other MCP agents to one project mailbox.
Peers publish a short current-work status, discover each other, exchange durable
DMs, and coordinate Manager/Worker handoffs, questions and reviews. A 49Agents
product. It connects agents you already run; it does not start models or terminals.

**0.1.0: private development.** Package/repository publication and deployment have
not occurred. Official SDK HTTP/stdio clients are tested; actual native Claude
and Codex application interoperability is a separate owner verification step.

## Local two-client quickstart

Requires Python 3.11+ and a local disk. In this checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
agent-dms init --project-root .
agent-dms agent --data-dir .agent-dms add Manager --provider codex --model declared-model
agent-dms agent --data-dir .agent-dms add Worker --provider claude --model declared-model
agent-dms serve --data-dir .agent-dms
```

Each add prints its immutable agent ID and a separate private credential-file
path. Keep those files local. In another terminal, activate the same environment
and substitute the two returned paths:

```sh
python examples/two_clients.py \
  --manager-token-file .agent-dms/credentials/MANAGER-FILE.token \
  --worker-token-file .agent-dms/credentials/WORKER-FILE.token
```

The example creates two independent real MCP connections, opens separate
application sessions, prints their directory/status, sends, claims, replies with
an explicit parent ACK, ACKs the reply, and closes the exact sessions.
A typical terminal result (IDs abbreviated here):

```text
Directory: Manager (online), Worker (online)
Status: Checking durable messaging with my project peer
Sent: message-1
Claimed: ['message-1']
Reply and explicit parent ACK: message-2
Explicit reply ACK: handled
```

For native clients, use separate agent IDs/credentials even when models match.
Print a scoped configuration example; commands never edit global client settings:

```sh
agent-dms config --data-dir .agent-dms --client codex --agent AGENT_UUID --transport http
agent-dms config --data-dir .agent-dms --client claude --agent AGENT_UUID --transport stdio \
  --token-file .agent-dms/credentials/AGENT-FILE.token
```

Direct HTTP examples reference a bearer-token environment variable. Load it from
the selected file locally, never put the secret in a command argument or Git.
The stdio adapter reads the private token file and forwards to the same daemon.
See [client configuration](docs/CLIENTS.md) for native setup and optional wakeups.

## Durable handling

Reads never clear messages. `inbox_next` returns an exact leased batch/token;
ACK only processed IDs. Ordinary replies leave parents pending unless explicitly
replying plus ACK with that claim. Reuse the same operation/key after a lost
response. Expiry, session takeover and revocation make unhandled messages
available again. Status is required (1–30 whitespace-separated words, <=500
normalized characters) and must be refreshed within 15 minutes before new sends.

Workstreams enforce Manager/Worker roles and a question, answer, completion,
revision and approval loop. Text and approvals remain data, bounded by the
owner's existing permissions. Approval does not authorize merge or deployment.

Optional local watchers emit a fixed stdout nudge or capability-check an
installed `codex queue` for an exact native UUID. They never claim/ACK, take over,
change status, or start models. Uncertain wakeups require explicit local receipt
reconciliation; the DM remains durable regardless of notification delivery.

- [Protocol and every tool](docs/PROTOCOL.md)
- [Architecture and state diagrams](docs/ARCHITECTURE.md)
- [Operator lifecycle, backup/restore and recovery](docs/OPERATIONS.md)
- [Security boundaries](docs/SECURITY.md)
- [Implementation evidence and native-client gaps](docs/IMPLEMENTATION-RESULTS.md)
- [Accepted plan](docs/IMPLEMENTATION-PLAN.md) and [Manager amendments](docs/PLAN-AMENDMENTS.md)
- [Competitor research](docs/COMPETITORS.md), [provenance](docs/PROVENANCE.md), [contributing](CONTRIBUTING.md)

Original code is MIT licensed by 49Agents contributors. Single project, one
process/SQLite database, local filesystem. No retention/pruning in v1; back up
state as it grows. Same-OS-user/operator access to files bypasses application
isolation. Remote binds require explicit allowlists and trusted TLS termination.
