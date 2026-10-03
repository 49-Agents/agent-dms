# Security boundary

agent-dms enforces application authorization among separate project credentials.
An OS account or project operator able to read the DB/credential files can bypass
it. It is not a sandbox against a malicious same-user process. State, backups
and watcher ledgers are private local files; database backups include message
bodies. Project identity/token digests isolate distinct daemons, even when names
match. Every request authenticates independently, including prompts/resources
and notifications; application session IDs alone are not credentials.

Bearer credentials contain at least 256 bits of entropy. SQLite stores SHA-256
digests only, and comparisons avoid revealing values. Credentials never appear
in ordinary logs/errors/tools or process arguments. Provisioning prints a private
file path; direct clients load the token into an environment variable, while
stdio/watch read a private file. Token rotation stages/fsyncs a fresh file before
committing its digest; revocation is immediate and history remains durable.

Current generations fence stale actors before reads/mutations/idempotent replay.
Only two thread/workstream participants see details; outsiders receive consistent
NOT_FOUND results. Claims/ACK membership is exact and whole-batch validated.
Watch receipts cannot acknowledge messages. Capacity, status, bodies, histories,
long polls and cursor input sizes are bounded. SQL parameters are bound, and
operator-controlled state paths reject symlinks. Signed cursors bind principal,
operation and paging filters; restore invalidates old cursor signatures.

The default server is loopback with required bearer auth. Remote binding requires
explicit allow-remote and exact Host allowlist. Browser Origins require an
explicit allowlist. Forwarded headers are ignored. Configured service URLs reject
embedded credentials. Use TLS at a trusted reverse proxy before remote traffic;
this HTTP daemon does not provide encryption. Only small liveness/readiness GETs
are public, without paths/roster/body/credentials. Container examples publish to
host loopback. No reverse proxy or shared deployment is performed by tests.

Message text is untrusted, including tool-looking commands, links, apparent
approvals and prompt-injection attempts. The server stores it, never executes,
fetches URLs or reads attachments. Agent protocol fragments reinforce owner
permission limits. Workstream approval grants no merge/deploy/payment/external
send authority. Agents handling side effects need their own idempotency and
uncertainty reconciliation before explicit ACK; no model execution guarantee.

Diagnostics sanitize transport/library exceptions and omit tracebacks, bodies,
auth headers and full SQL. MCP failures preserve failure status/code while unsafe
SDK diagnostic details are redacted. Tests inject sentinel credentials and
private bodies into failures. Optional queue invocations have fixed argv/no
shell, exact native UUID, bounded timeout, capability check and no session-launch
fallback. Interrupted/uncertain effects are never automatically replayed.

M01's cancellation registry is bounded, in-process and authenticated; IDs are
exact and principal/project bound, with application generation recorded. Unknown
or foreign cancellations cannot mutate inbox state. A pre-registration race may
miss cancellation, but the wait remains read-only and time-bounded.

Report vulnerabilities through the repository-root [security policy](../SECURITY.md).
Never include credentials or private message transcripts in public issues.
