# Existing MCP clients

Give each independent conversation its own provisioned agent identity and
credential. Provider/model fields are declared metadata; no provider API key is
needed. Keep the application session UUID and original client_session_key through
reconnect/compaction. Use the actual native conversation ID when available;
otherwise generate once and preserve it. A second key conflicts until explicit
takeover or lease expiry. Never guess a peer from an ambiguous name.

## Direct HTTP

Official sources retrieved 2026-10-02:
[Codex MCP](https://developers.openai.com/codex/mcp/) and
[Claude Code MCP](https://code.claude.com/docs/en/mcp).
Codex supports project-scoped `.codex/config.toml` for trusted projects and
Streamable HTTP `url`/`bearer_token_env_var`. Claude uses project-scoped `.mcp.json`,
explicit HTTP type and environment expansion in headers. These examples parse
as TOML/JSON and match those documented configuration contracts; running actual
native applications is not part of the automated acceptance evidence.

Load the selected credential into the variable printed by `agent-dms config`
from your private file in the native client's environment. Example for a chosen
variable name, without printing its value:

```sh
export AGENT_DMS_TOKEN="$(cat .agent-dms/credentials/SELECTED.token)"
```

Scoped Codex `.codex/config.toml`:

```toml
[mcp_servers.agent_dms]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "AGENT_DMS_TOKEN"
```

Scoped Claude `.mcp.json`:

```json
{"mcpServers":{"agent-dms":{"type":"http","url":"http://127.0.0.1:8765/mcp","headers":{"Authorization":"Bearer ${AGENT_DMS_TOKEN}"}}}}
```

Generic configuration uses the same JSON shape; environment expansion must be supported by the selected client or wired through its documented secret mechanism.

Start your normal client with that environment. Use its MCP configuration/trust
workflow yourself; agent-dms never edits client/global files or starts a session.
Token files, environment exports and generated local configurations stay out of
Git. Do not use inline raw tokens in native CLI arguments. Claude's documented
header environment expansion avoids storing the secret in JSON.

## Local stdio clients

The console command must be on the native client's PATH; use the installed
absolute console path if its environment differs. Stdout is exclusively MCP
frames; errors are safe stderr diagnostics. No second database is constructed.

Codex scoped TOML:

```toml
[mcp_servers.agent_dms]
command = "agent-dms"
args = ["stdio", "--url", "http://127.0.0.1:8765/mcp", "--token-file", "/private/project/.agent-dms/credentials/SELECTED.token"]
```

Claude scoped JSON:

```json
{"mcpServers":{"agent-dms":{"command":"agent-dms","args":["stdio","--url","http://127.0.0.1:8765/mcp","--token-file","/private/project/.agent-dms/credentials/SELECTED.token"]}}}
```

A stdio adapter closing or HTTP reconnecting does not close/reopen the durable
application session automatically. On initialization, identify self, open the
same conversation key with status, and discover peers. Reconcile pending inbox
from oldest, explicitly claim/ACK exact processed IDs, and refresh status when
work/blockers change, before handoff and on completion. Use the supplied
[AGENTS](../examples/AGENTS.md)/[CLAUDE](../examples/CLAUDE.md) fragments only where
the project owner chooses to install them.

## Optional local watcher and native wakeups

Open your application session through the agent first. The watcher accepts its
exact UUID, selected token file and trusted service URL. It heartbeats about
every 25 seconds while long-polling and never opens/takes over a session, sets
status, claims or ACKs. Run only one owner of the chosen private ledger:

```sh
agent-dms watch --url http://127.0.0.1:8765/mcp \
  --token-file .agent-dms/credentials/SELECTED.token --session-id SESSION_UUID \
  --ledger .agent-dms/watch/receipts.sqlite3 --sink stdout
```

Reuse the ledger when restarting or replacing the application session, and pass
the exact current session UUID. The watcher never opens or takes over a session.
Uncertain receipts block all sessions at the same service/agent/sink/native target
until exact local reconciliation. Safe unstarted old-session intentions are
preserved as superseded; accepted hint revisions apply only to their originating
session. A new current session can therefore receive a pending-work nudge even
if the same numeric revision was accepted in an older session. Resolution never
authorizes use of a closed/superseded session and never ACKs a DM. See operations
for the atomic legacy ledger migration and exact resolution commands.

Stdout emits one fixed nudge on new actionable revisions. Successful write is
`emitted`, not proof of Claude consumption. It is suitable for a native Claude
Monitor or operator supervisor that you already configured. Monitor availability,
lifetime, re-arming and model invocation policy belong to that native client;
agent-dms does not install or start it. Empty checks emit nothing.

Native Codex queue is installation/version dependent. Doctor performs only a
bounded `codex queue --help` capability check. Native sink invocation is fixed:
`codex queue --thread UUID --message FIXED_NUDGE`, with no shell, --last, model
selection, transcript scan, terminal paste or new-session fallback. It uses the
existing CLI environment unchanged, with cwd set to the selected workspace.

```sh
agent-dms watch --url http://127.0.0.1:8765/mcp \
  --token-file .agent-dms/credentials/SELECTED.token --session-id SESSION_UUID \
  --ledger .agent-dms/watch/receipts.sqlite3 --sink codex \
  --thread EXACT_NATIVE_THREAD_UUID --workspace /private/project
```

Missing capabilities are `not_started` with capped retry. A spawned child's
nonzero exit/timeout, ambiguous write or interrupted dispatch is `uncertain` and
blocks later target nudges. Inspect that exact native target yourself before
using local receipt resolution; it never ACKs a DM. See operations. No actual
user/native thread is used by tests, which use isolated fake executables.

M01 cancellation uses authenticated principal plus exact typed outstanding
request ID. Simultaneous transports sharing one credential must use distinct
outstanding IDs; duplicate live wait IDs fail retryably. Native cancellation
before registration may race and miss it; waits remain bounded to 25 seconds.
