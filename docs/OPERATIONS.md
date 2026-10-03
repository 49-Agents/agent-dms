# Operations and recovery

Install Python 3.11+ on a local filesystem. Use `requirements.lock` with
`pip install --require-hashes -r requirements.lock`, then `pip install --no-deps
-e .` for development, or install the built wheel with `--no-deps`. Development
checks/build tools use `requirements-dev.lock`. Dependency files contain pinned
versions/hashes with no private indexes or machine-specific paths. The MCP SDK
2.2.0 uses its resolved HTTP transport dependency; httpx 0.28.1 remains pinned
for direct operator/test HTTP checks. Imports never initialize state or services.

## State and serving

```sh
agent-dms init --project-root /private/project
agent-dms serve --data-dir /private/project/.agent-dms
agent-dms doctor --data-dir /private/project/.agent-dms
```

Init defaults to `.agent-dms`, or accepts an explicit data directory. It creates
one UUID, configuration, SQLite schema, private credentials directory, cursor
key and an ignore-all state `.gitignore`. Directories are 0700 and files 0600.
Missing nested directories are created privately, without changing existing
ancestors. Existing dedicated state/credential directories must already exclude
group/other access; repair them to 0700 explicitly before retrying. Init preflights
populated/wrong-project/file/permission targets before creating its lock, then
validates again under the lock. A normal rejection preserves contents and modes.
Symlink targets are refused. Re-init of the same project preserves identity and
history; different/populated targets are refused. It never edits the parent
project's ignore file or client/global configuration.

Serve requires initialized config/schema, one process lock and one Uvicorn
worker. A second daemon for the same state fails clearly. Default bind is
127.0.0.1:8765. Only GET `/health/live` and `/health/ready` are public and small;
ready validates schema/database identity and availability. The HTTP limit is
256 KiB, request concurrency 64, long polls two per authenticated agent. No
forwarded-header trust. Requests authenticate independently.

For an explicitly configured remote bind, supply `--allow-remote` and one or
more exact `--allowed-host HOST[:PORT]` values. Browser Origins are rejected
unless listed explicitly using `--allowed-origin ORIGIN`. TLS termination at a
trusted reverse proxy is required for credentials over remote networks; this
server does not encrypt HTTP. No proxy/service deployment is included here.

SQLite uses foreign keys, WAL, FULL sync and busy_timeout=5000. Keep it on local
disk; WAL on NFS and multiple replicas are unsupported. There is no automatic
history pruning/message expiry or Git export. Plan storage growth and backups.

## Identity and credentials

```sh
agent-dms agent --data-dir .agent-dms add Worker --provider claude --model declared-model
agent-dms agent --data-dir .agent-dms list
agent-dms agent --data-dir .agent-dms rotate-token AGENT_UUID
agent-dms agent --data-dir .agent-dms revoke AGENT_UUID
```

Names trim/NFC-normalize, are 1–64 characters and unique under casefold, with no
controls. Provider/model are optional declared fields bounded to 100/200
characters. Add prints the immutable UUID and private credential path, never
the raw 256-bit bearer token. Only its SHA-256 digest is stored in SQLite.

Rotation writes/fsyncs a fresh private file and its directory before committing
the replacement digest. It never overwrites the old file. A crash leaves the old
valid digest, or the new valid digest with its already-durable file. An orphaned
uncommitted file may remain for operator reconciliation; never assume a file is
active from its timestamp. Rotation invalidates old credentials/current session
and releases outstanding claims, preserving identity/history. Revocation does
the same immediately and remains revoked after rotation. No reactivation command
exists in v1. List/doctor never print tokens, digests or message bodies.

Use `config --client codex|claude|generic --agent UUID --transport http|stdio
--data-dir PATH`; stdio examples also need `--token-file`. This prints valid
scoped examples without editing anything. HTTP examples refer to a per-agent
environment variable. See clients for loading it locally. Doctor checks private
permissions, schema/config, installed SDK version and bounded queue capability;
it does not start a model or scan transcripts.

## Backup and restore

```sh
agent-dms backup --data-dir .agent-dms --out /private/backups/project.sqlite3
agent-dms restore --snapshot /private/backups/project.sqlite3 \
  --data-dir /private/recovered/.agent-dms
```

Online SQLite backup permits concurrent writes and validates integrity/FKs,
project/schema and SHA-256. Output is a private snapshot plus `.json` metadata
(project ID, schema version, hash, UTC time). It refuses existing output targets.
Keep both files together, private, and securely transfer them if needed. An
interrupted staging/partial backup is not a successful backup; reconcile exact
artifacts and validate before using them. The DB contains private message bodies.

Restore validates metadata/hash/schema/integrity before touching the target.
Only a new empty directory is allowed. It preserves project/agent/message/session/
claim/workstream IDs and pending work; never overwrites running or populated
state. It generates a new cursor key, so start new paging passes. Raw credential
files are separate from the snapshot: retain them securely for continued access,
or rotate selected agent tokens in restored state. Restore creates an empty
credentials directory and nonsecret configuration for the new parent project
root. It does not move operational state or change another daemon.

Schema 1 has no upgrades yet. Serve refuses newer/unsupported schema rather than
downgrading or resetting it. Before a future approved upgrade, back up, stop the
single daemon, follow that release's explicit migration procedure, and validate
before restarting. Recovery means an operator-selected validated restore into
new state, never an automatic rollback over current data. Missing/corrupt state
is an error, not permission to initialize over it.

## Inbox and status recovery

Preserve conversation keys through reconnect; never reuse closed/superseded keys.
A new key requires explicit takeover of a live session; expiry/closed ownership
permits a genuinely new key. Session leases and status freshness are 15 minutes.
Heartbeat renews contact, not status. STATUS_STALE repairs with status_set and
its current expected revision. It cannot block reads, ACKs, claim recovery or
closing. Expired leases recover lazily during peek/next/wait; no startup deletion
or mandatory maintenance worker exists. Reconcile oldest pending messages rather
than treating notification revisions/cursors as delivery watermarks.

## Wakeup receipts

The optional client-local watcher owns one private ledger lock. It never takes
over, claims, ACKs or starts a model on empty checks. A successful stdout write
is emitted; queue exit zero is accepted, neither proves model handling. Missing
queue capability/pre-spawn failure is not_started, with retry delay capped at
60 seconds. Once dispatch may have started, nonzero/timeout/interruption becomes
uncertain. Restart quarantines unfinished dispatching receipts.

The base target is service/agent/sink/native-thread/workspace, across application
sessions. Uncertain or dispatching receipts block **all sessions** at that target.
Receipt intentions and accepted revision watermarks are session-specific. After
successful current-session authentication, and only when the target is unblocked,
old-session pending/not_started intentions become terminal `superseded` records.
Their IDs, captured intentions, attempts and history remain, with a supersession
reason/time. A new session can receive the same numeric revision; same-session
accepted revisions stay suppressed. Empty hints create no new receipt or dispatch.

```sh
agent-dms watch receipts --ledger .agent-dms/watch/receipts.sqlite3
agent-dms watch resolve --ledger .agent-dms/watch/receipts.sqlite3 \
  --receipt RECEIPT_UUID --delivered --reason "Confirmed in exact native target"
# Only after confirming retry is appropriate:
agent-dms watch resolve --ledger .agent-dms/watch/receipts.sqlite3 \
  --receipt RECEIPT_UUID --retry --reason "Confirmed the nudge was not delivered"
```

Stop the watcher before inspecting/resolving its ledger, since only one process
may own it. Resolution affects exactly that uncertain local receipt; retry
preserves its identity/captured revision if its session is still current.
`--delivered` accepts only the receipt's original session/revision. `--retry`
returns that exact intention to pending; a later authenticated watcher with a
different current session supersedes it and may create fresh current-session
work. Resolution never authorizes dispatch using a closed/superseded application
session and never acknowledges or deletes a DM. An uncertain target blocks later
coalesced wakeups across sessions until reconciliation. No
unchanged/empty per-poll receipt or log history is created. Network outages emit
one safe outage/recovery diagnostic with capped backoff; auth/supersession stops.
Stdout broken pipes stop without replay. Normal termination may leave dispatching
state, deliberately treated as uncertain on restart.

The private local ledger uses schema version 1 (`PRAGMA user_version`), separate
from authoritative project schema 1. Opening a legacy unversioned ledger under
its exclusive process lock atomically rebuilds receipt uniqueness as
`(target, session_id, revision)` and reconstructs per-session acceptance from
emitted/accepted receipts. Existing IDs/fields/outcomes and target rows, including
legacy global accepted values as historical data, are retained. Interrupted
dispatches are quarantined as uncertain. Migration failures roll back; unknown or
newer schemas are refused without rewriting the ledger. Retain a secure copy of
the stopped ledger before upgrading; never delete history to recover a watcher.
An arbitrary existing ledger parent keeps its mode; new ledger/lock files are
private, and missing nested parents are created with 0700. Symlinks and nonprivate
ledger/lock files are refused; repair file permissions explicitly to 0600.

## Container recipe

Docker build is optional; no registry publication or persistent deployment is
authorized by this repository's development workflow. The non-root image uses
UID 10001 and a persistent `/data` volume. The Compose example binds the host
port to loopback only. Initialize `/data/state` and provision identities through
one-shot operator commands before serving. Keep host-bind mount ownership
compatible with UID 10001; do not place raw tokens in Compose environment/files.
Named volumes are local state, so retain credential files securely when extracting
selected client credentials. Container startup never auto-initializes/resets DB.

```sh
docker build -t agent-dms:local .
docker compose run --rm agent-dms init --project-root /data --data-dir /data/state
```
