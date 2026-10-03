# Native Claude Code / Codex acceptance

Status: **not yet executed**. Official SDK transport tests and the temporary demo
pass independently; they do not establish native application behavior. Use this
procedure before claiming a verified native Claude↔Codex integration.

## Test record

Record date, exact package/commit, OS/Python, both native client versions, model
labels, transport per client, sanitized outcome and any issue links. Never
publish token values, private conversation IDs or transcripts. The operator
chooses/authorizes the two model sessions; this procedure does not start them.

## Prepare an isolated project

1. Install the reviewed wheel in a fresh virtual environment. Run the SDK demo.
2. Create a new disposable project directory and initialize a mailbox there.
   Provision `Manager` and `Worker` with separate credentials. Start one loopback
   daemon. Confirm readiness; record no secrets in evidence.
3. Generate a Codex HTTP example and Claude stdio example with `agent-dms config`.
   Follow each client's current project-local trust/config procedure. Configure
   the stdio command's absolute path. Scope all files to this disposable project;
   avoid global configuration. HTTP token variables must be available to the
   intended client process only.
4. Use two operator-selected native sessions. Give each the relevant agent
   protocol fragment from `examples/AGENTS.md` or `examples/CLAUDE.md`. Identify
   via `agent_whoami`; open a session with a stable conversation key and honest
   status. Keep returned IDs locally, then discover the exact peer UUID.

## Prove the user-visible flow

| Step | Action and pass condition |
| --- | --- |
| Discover | Both agents see the peer and its required status; provider labels are merely declared metadata. |
| Status | Change one status to a new task description. The peer sees it. Try a 31-word status: rejected with no silent truncation. |
| Send/receive | Manager sends a synthetic DM using a saved idempotency key. Worker sees it with `inbox_peek`; a second peek still sees it. |
| Claim/reply | Worker calls `inbox_next`, handles the exact message, and replies with explicit parent ACK and that claim token. Manager claims and ACKs the reply. |
| Retry | Repeat the original send with identical arguments/key: the same message ID returns and no duplicate is created. |
| Restart | Leave a new DM unhandled, stop/restart only this demo daemon, reconnect, and reconcile pending work. Message remains available. Preserve stable conversation keys. |
| Review loop | Manager starts a small synthetic workstream. Worker asks a question; Manager answers; Worker completes; Manager requests one revision; Worker completes again; Manager approves. Use exact revisions/message correlations and separately ACK handled inbox messages. |
| Cross transport | Swap to Codex stdio / Claude HTTP and repeat discovery and one complete DM/reply/ACK. Do not reuse one identity in simultaneous native sessions. |
| End | Set truthful completion/idle status, close the exact application sessions, and stop only the disposable daemon. |

If an agent merely narrates that it called a tool, inspect its actual tool result
and the peer's mailbox. A model response is not a delivery receipt. Record errors
as failures or gaps, not waived passes.

## Optional wakeup checks (separate evidence)

First pass the manual inbox flow. If the installed client supports it, configure
one watcher for the exact current application session and a new private ledger.
For Codex, verify the installed `codex queue --help` capability and use an exact
native thread UUID. For Claude, use only an existing operator-configured Monitor
or supervisor. agent-dms does not install or launch either.

Send one synthetic message. Record separately: nudge emitted/accepted, native
client consumed the nudge, actual inbox tool call, and exact ACK. Re-arm according
to the native client's policy. Test a no-work check emits nothing. Never replay
an uncertain native dispatch blindly; inspect the exact target and follow
receipt reconciliation in [OPERATIONS.md](OPERATIONS.md).

## Reporting

Copy this matrix into private release evidence; fill observations rather than
changing the empty template into an assumed pass.

| Combination | Version(s) | Discovery + status | DM/reply/ACK | Retry/restart | Review loop | Wakeup consumption |
| --- | --- | --- | --- | --- | --- | --- |
| Codex HTTP / Claude stdio | pending | pending | pending | pending | pending | separate optional check |
| Codex stdio / Claude HTTP | pending | pending | pending | pending | pending | separate optional check |

A failure blocks the corresponding compatibility claim. A qualified SDK-only
experimental release can still be considered separately by the maintainer.
