# Implementation results — 0.1.0

Revised implementation source commit: `f12ff3ec679a4b69ba67cbbd75a39ff8858efa64`
(`f12ff3e`), branch `feat/agent-dms-v1`. This evidence is finalized in a subsequent
documentation commit on the same branch. The handback reports that exact final
commit. Source and evidence are committed/pushed; no merge, publication,
deployment, visibility change or task-worktree cleanup is authorized/performed.

All required v1 phases are implemented. The frozen plan SHA-256 remains
`eb301573ad4627a96d26baae2eeb6a4b23b5709600f62d530507bc9d223bbacb`.
[Manager amendments M01 and M02](PLAN-AMENDMENTS.md) are recorded separately and
implemented. The authoritative project/message schema remains version 1; only
the independent local watcher ledger gains its versioned migration.
No internal review/planning/implementation subagents were launched; Manager owns
final review. No Qorqut/ACLA runtime import or copied implementation is present.

## Verified checks

Local interpreter: **CPython 3.12.3**. Tests use isolated temporary project state,
SQLite connections, fake domain clocks, loopback ports and fake notification
executables. No operational database, another agent credential, native user
thread, provider API, global client configuration or existing terminal was used.
No local Python 3.11 interpreter was available; CI evidence is recorded separately
from the local CPython 3.12.3 checks.

Baseline focused commands on the original implementation (`935447c`, retained
as historical acceptance evidence):

| Exact command | Result |
|---|---|
| `.venv/bin/pytest -q tests/test_storage_identity.py tests/test_sessions_status.py tests/test_messages_history.py tests/test_inbox_claims.py tests/test_workstreams.py` | **29 passed**, 8.88 s |
| `.venv/bin/pytest -q tests/test_mcp_integration.py tests/test_stdio_bridge.py` | **10 passed**, 15.01 s |
| `.venv/bin/pytest -q tests/test_watch_receipts.py tests/test_cli_backup.py` | **15 passed**, 11.18 s |

**54 baseline focused tests passed.** No unrestricted repository-wide suite was run.
Earlier development failures exposed a directory result-argument collision,
SDK 2.2 callback/client signature differences, and stateless cross-request
cancellation. These were corrected; M01 supplies the approved cancellation
integration. The final commands above contain no failing or skipped tests.

## R01 corrections and focused regression evidence

R01 identified three recovery defects missed by the baseline checks. All three
are corrected in `f12ff3e`; M02 is transcribed from Manager message 1249 in the
separate amendment document. Original scope and M01 remain intact.

1. **Existing directory preservation (A01/A02/A21/A23).** No runtime helper
   chmods existing directories. Read-only init preflight precedes target creation
   and locking, with authoritative checks under the lock. Existing dedicated
   state/credential directories require private permissions; arbitrary ledger
   parents retain their mode. Every missing intermediate directory is private.
   Temporary-directory regressions compare complete contents/modes for rejected
   0755/0700 populated targets and wrong-project state with no new init.lock;
   test unsafe empty/file targets, concurrent init exclusion, credentials,
   nested init/restore/ledger creation, private ledger/lock files and symlinks.
2. **Session-aware local wakeups (M02/A20–A22).** Base targets retain global
   uncertainty quarantine. One local transaction checks uncertainty, retires safe
   old-session intentions as superseded and selects/creates current-session work.
   Receipt uniqueness/acceptance/reconnect suppression are session-specific.
   Supersession preserves original timestamps/fields and adds reason/time.
   Fake-clock/fake-sink regressions cover numeric revision reuse, capped exact-ID
   retries, empty work, all-session dispatching/uncertain blocks, exact delivered
   and retry resolution, restart, captured revision and same-session suppression.
   Legacy mixed-session migration preserves every original ID/field/outcome
   except specified interrupted-dispatch quarantine, retains historical target
   values and reconstructs per-session acceptance. Injected post-DDL failure
   rolls back the complete migration; injected intent insertion failure rolls
   back supersession. Unknown/newer ledger files retain bytes/mode/mtime.
   An actual SDK watcher and subprocess daemon check proves old authority stops,
   the new current session progresses after daemon restart using the same numeric
   revision, watcher restart stays quiet, and the DM remains pending until an
   explicit claim/ACK. No real native target is used.
3. **Saved session-open contact (A04/A05).** Identical saved-key replay touches
   exactly the authenticated current active session in the same transaction and
   returns the unchanged saved result. A fake-clock replay after 900001 ms renews
   last-seen/lease and directory presence; newer status text/revision/timestamp
   and the complete idempotency row stay unchanged. Conflicting input, closed or
   superseded sessions and revoked credentials renew no session.

Directly affected final local commands:

| Exact command | Result |
|---|---|
| `.venv/bin/pytest -q tests/test_storage_identity.py tests/test_sessions_status.py tests/test_cli_backup.py` | **35 passed**, 6.09 s |
| `.venv/bin/pytest -q tests/test_mcp_integration.py tests/test_stdio_bridge.py tests/test_inbox_claims.py` | **15 passed**, 16.94 s |
| `.venv/bin/pytest -q tests/test_watch_receipts.py` | **26 passed**, 8.68 s |

**76 directly affected local checks passed**, no failures/skips. The watcher file
was repeated only after affected schema-validation and timestamp-preservation
edits. Its additional rollback case first passed in isolation (1 passed, 0.83 s)
and is included in the final 26. Unchanged messages/history and workstream files
retain baseline evidence; the explicitly named CI groups cover them separately.

Observed revised-source CI: [run 37077075192](https://github.com/49-Agents/agent-dms/actions/runs/37077075192)
for exact source HEAD `f12ff3ec679a4b69ba67cbbd75a39ff8858efa64` completed
successfully on Python **3.11 and 3.12**, including locked install, build and
fresh-wheel artifact validation. Each matrix job ran the following explicit
feature groups (81 tests per interpreter):

| CI command | Python 3.11 | Python 3.12 |
|---|---|---|
| `pytest -q tests/test_storage_identity.py tests/test_sessions_status.py` | 31 passed, 0.50 s | 31 passed, 1.00 s |
| `pytest -q tests/test_messages_history.py tests/test_inbox_claims.py` | 8 passed, 0.47 s | 8 passed, 0.42 s |
| `pytest -q tests/test_workstreams.py tests/test_mcp_integration.py` | 10 passed, 10.92 s | 10 passed, 10.38 s |
| `pytest -q tests/test_stdio_bridge.py tests/test_watch_receipts.py` | 28 passed, 6.72 s | 28 passed, 6.29 s |
| `pytest -q tests/test_cli_backup.py` | 4 passed, 1.82 s | 4 passed, 1.76 s |

This CI result applies to the implementation source commit; the later evidence
commit changes only this report. No native provider-client acceptance is inferred
from SDK tests or CI.

Additional focused validation of revised packaged source:

- `.venv/bin/pip install --require-hashes -r requirements-dev.lock` and
  `.venv/bin/pip check`: succeeded, no broken requirements. Runtime/dev lockfiles
  resolve versions/hashes without private indexes or machine-specific paths.
- `SOURCE_DATE_EPOCH=1790983206 .venv/bin/python -m build`: wheel and source
  archive built (timestamp is the implementation source commit's Unix time).
- `.venv/bin/python scripts/validate_artifact.py`: fresh temporary venv installed
  hash-locked runtime dependencies and the wheel; dependency check, import without
  state creation, packaged SQL/protocol, MIT/third-party notices, entry point,
  CLI help/version, actual wheel init/add/list, and JSON/TOML examples all passed.
- `docker build -t agent-dms:local .`: succeeded. Built image
  `sha256:4e58a78f6585d10b8d384af5749ac2dea122a5cc13e0a0ed9ab95006a2e743c4`,
  configured user `10001:10001`. No persistent service/container was deployed.
- `docker compose config --quiet`: passed; host port is loopback-bound and state
  has a persistent volume. No registry/package publication occurred.
- `.venv/bin/python -m compileall -q src examples tests scripts`: passed.
- `git diff --check` and `git diff --cached --check`: passed. Final scope/secret
  inspection found no runtime state, bearer credentials, receipts, transcripts,
  virtual environments or private machine paths in authored runtime/docs/examples.

Validated wheel: `dist/agent_dms-0.1.0-py3-none-any.whl`, SHA-256
`97c77abf69412ca6397e84d8e28586eeced23ca7717167b9f62a10e436aa781f`.
Artifacts are local ignored outputs, not published or committed binaries.
The source archive includes docs/examples/locked requirements and validation
scripts; it is rebuilt after this evidence update to include the finalized text.

Installed core versions: mcp/mcp-types 2.2.0, httpx 0.28.1, uvicorn 0.54.0,
Pydantic 2.13.5; SDK transport dependency httpx2 2.13.1. Test/build tools:
pytest 8.4.2, pytest-asyncio 1.2.0, build 1.3.0, pip-tools 7.5.1,
setuptools 80.9.0. The package uses the official SDK low-level API, not FastMCP
or a handcrafted JSON-RPC implementation.

## Acceptance traceability

Each row distinguishes implemented behavior from its focused verification.
Native application consumption is separately unverified below.

| ID | Implemented behavior / focused evidence |
|---|---|
| A01 | Private init/re-init, preserved rejected-target contents/modes with no lock creation, nested private creation, UUID stability, symlink/populated-target refusal, newer-schema rejection, concurrent process locks; storage/identity and CLI second-daemon tests |
| A02 | Exact token principal, casefold/NFC names, bounded metadata, durable rotation failure handling, revocation, cross-project rejection; storage/identity tests |
| A03 | 1/30/31 words, empty/Unicode/control/500-character boundaries and normalization; session/status tests |
| A04 | Separate-connection concurrent status revisions, age/heartbeat independence and stale-send repair; session/status tests |
| A05 | Stable reconnect including saved-key contact renewal with unchanged status/receipt, explicit takeover, expired lease renewal, permanent closed/superseded key fencing, stale close/ACK rejection; session/status, inbox and wire tests |
| A06 | Atomic immutable send/delivery, saved-key replay/conflict, ordinary correlated reply, offline/restart persistence; messages/history tests |
| A07 | Participant-only reads/writes, foreign message/thread rejection, signed cursor tamper/principal/filter checks; messages/history tests |
| A08 | Multi-page stable upper sequence excludes arrivals until a fresh pass, no duplicates/skips; messages/history tests |
| A09 | Peek/history/hints leave deliveries pending, concurrent FIFO disjoint claims over separate connections; inbox tests |
| A10 | Mixed valid/foreign ACK fails wholly, selected ACK only, expired pending tokens rejected; inbox tests |
| A11 | Immutable first outcome/time, compatible new-key re-ACK, renew/release/expiry/restart recovery, inactive saved claim receipt; inbox tests |
| A12 | Reply plus explicit parent ACK commits both/neither, failure rollback and stable retry, new sends require a currently leased parent; inbox tests |
| A13 | Actual official SDK initialize, exact 21 tools, annotations, prompts/resources and independent authenticated clients; MCP integration tests |
| A14 | Per-request auth after initialize, foreign application-session rejection, revoked wait stop, takeover fencing; MCP integration tests |
| A15 | Stale sends fail while inbox recovery works, quiet bounded waits, arrival hints, actual SDK cancellation promptly frees server capacity; MCP/M01 tests |
| A16 | 401/403 auth/Host/Origin checks, 256 KiB refusal, actual 64 concurrent requests plus retryable capacity rejection, two waits/principal, sanitized failures; MCP tests |
| A17 | Full start/question/answer/complete/revise/complete/approve loop with exact state/round/revision and one DM/event per step; workstream and SDK-wire tests |
| A18 | Wrong role/stale revision/blocked completion/terminal reopening reject, approval replay stable, ordinary DM kind does not change state, combined handoff bounds; workstream tests |
| A19 | Real stdio SDK subprocess and direct HTTP peer share one daemon/database and contract; successful SDK parsing verifies protocol-only stdout; injected bridge transport faults preserve isError/structured INTERNAL_ERROR/request ID and redact sentinels |
| A20 | Empty/unchanged/all-claimed hints cause no sink/receipt, 105 pending messages counted beyond the first page, captured revision coalescing; watcher tests |
| A21 | Missing capability no-start retry, actual fake subprocess success/nonzero/timeout, parent process killed after child spawn then restart quarantines uncertainty, exact explicit resolution; watcher tests |
| A22 | Exact fixed argv and UUID/workspace, real DM arrival during sink preserves next revision, actual watcher stops on takeover and current-session progress through daemon/watcher restart, session-scoped acceptance with global uncertainty quarantine and atomic legacy migration, safe outage diagnostics; watcher tests |
| A23 | Online backup concurrent with writes, integrity/hash/FK validation, new-directory restore retains IDs/pending work, occupied/tampered target refusal; CLI/backup tests |
| A24 | Locked wheel/source build, fresh wheel install/CLI/operator smoke, notices/resources, JSON/TOML configuration parse, non-root Docker build/Compose parse; artifact script and package checks |
| A25 | Two isolated persistent SDK client processes establish sessions over HTTP, send/reply/ACK across daemon restart and complete the full ACLA revision loop through another restart; MCP integration process test |

Meaningful fault injection demonstrates rollback of send message/delivery/thread,
ACK receipt/delivery updates, and workstream transition plus optional ACK/message.
Discarded committed-response retries use the exact saved keys and preserve one
intended effect. The final stdio transport fault check also verifies that unexpected
upstream exceptions retain a structured failure envelope rather than becoming a
success-looking result or leaking exception details. Injected transport/tool exceptions include sentinel credentials
and private body text; sanitized outputs/diagnostics omit them.

M01 additionally verifies other-principal same-ID cancellation isolation,
integer/string-ID distinction, same-principal active-ID collision rejection,
unknown/repeated cancellation no-ops, timeout/error/disconnect cleanup, and
post-cancellation DM availability. Server capacity is asserted reusable within
a 2-second budget rather than inferred from the client task returning.

## Remaining verification limits

Actual native Claude Code/Codex applications and Claude Monitor consumption were
**not live-tested**. No paid/native provider session was launched for acceptance.
Automated interoperability evidence uses real official SDK HTTP/stdio connections,
not actual model execution. Native client configuration was checked against the
fetched official Codex/Claude MCP pages on 2026-10-02 and parsed locally.

The installed queue capability can be checked by doctor using bounded help only;
no real queue command targeted any user's thread. Fixed sink behavior and crash
uncertainty were verified with isolated fake executables. A queue acceptance or
stdout write does not prove a model handled a message. Monitor lifetime/re-arming
and availability remain client concerns.

Cancellation before handler registration may race and miss it; its read-only
wait still ends within 25 seconds. Simultaneous transports sharing an agent
credential need distinct outstanding request IDs. External/model effects require
client idempotency and reconciliation before ACK. These are documented protocol
limits, not omitted message durability requirements.

Single local process/database, no WAL on NFS/replicas, same-OS-user/operator trust,
no automatic retention/pruning and status assertions that cannot be truth-verified
remain the accepted v1 boundaries. No required v1 behavior is marked future work.
The task branch/worktree and local build artifacts are retained for Manager review.
