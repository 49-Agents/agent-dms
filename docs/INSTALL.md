# Installation

The first release is being prepared. PyPI installation below becomes usable only
after the package is published and its owner/version have been verified. The
source-checkout route works now for authorized repository readers.

## Requirements

- Linux, Python 3.11 or 3.12, and a local filesystem for state.
- One long-running daemon per project; clients use HTTP or its stdio bridge.
- Each independent conversation gets a separate identity/token file.
- Your own MCP-capable agent clients if you want model-driven conversations.
  The SDK demo needs no model subscription or provider API key.

Native Windows is unsupported because the server uses POSIX `fcntl` locks.
macOS/WSL are not in the verified matrix. Do not place SQLite state on NFS,
Dropbox or another synchronized/network filesystem. See [operations](OPERATIONS.md).

## From source, before publication

In an authorized checkout of the reviewed branch:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python examples/demo.py
```

The development lock includes the build backend, so this route is reproducible
without fetching an unconstrained backend. Use the release tag/commit rather
than a moving branch for a persistent installation once available.

## From PyPI, after publication

First confirm the maintainer's release links to `agent-dms` on PyPI and the
expected version. A name-availability check does not reserve a package name.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'agent-dms==0.1.0'
agent-dms --version
```

This resolves transitive dependencies from PyPI. For the hash-locked equivalent,
use `requirements.lock` from the exact release, download its wheel, verify the
published SHA256SUMS, then:

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps ./dist/agent_dms-0.1.0-py3-none-any.whl
python -m pip check
```

The wheel contains runtime resources and the console command. Examples and docs
are in the source distribution/repository; run `examples/demo.py` from the same
release source using this environment to verify the installed wheel.

## Connect a real project

Run `agent-dms init --project-root /absolute/project` once. The default state is
`/absolute/project/.agent-dms`; exclude it from Git and backups that are public.
Provision two identities with `agent-dms agent --data-dir ... add NAME`, then
start `agent-dms serve --data-dir ...`. Store each returned credential-file path
privately and follow [CLIENTS.md](CLIENTS.md).

The `stdio` command needs `--url` and `--token-file`. Installing the package or
an MCP registry entry does not initialize the mailbox, provision identities or
start the daemon. A registry consumer needs access to its own local token file.
An HTTP connection needs its own bearer-token environment variable.

## Common setup failures

| Symptom | First check |
| --- | --- |
| `agent-dms` not found in a native client | Use the installed absolute console path; client PATH may differ from your shell. |
| Connection refused | Start the same project's daemon and check `http://127.0.0.1:8765/health/ready`. |
| `UNAUTHENTICATED` | Correct per-agent token, same daemon/project, no revoked/rotated credential. |
| `SESSION_REQUIRED` | MCP initialization is separate from `session_open`. |
| `SESSION_CONFLICT` | Preserve the conversation key; do not share one identity between concurrent conversations. |
| `STATUS_STALE` | Refresh the honest status with its current revision; heartbeat is insufficient. |
| Message remains pending | Reads and ordinary replies do not ACK; use the exact active claim and handled IDs. |
| No native wakeup | First verify mailbox delivery manually; wakeups are optional and client/version dependent. |

Uninstalling the Python package does not remove your mailbox. Stop your own
daemon, retain a backup if needed, and manage its private state explicitly. Do
not delete state to troubleshoot a delivery problem without reviewing recovery.
