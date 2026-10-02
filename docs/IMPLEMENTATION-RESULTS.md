# Implementation results — 0.1.0

Implementation source commit: `8d3fe536e29506770ac005088cbc733513fd019f`
(`8d3fe53`), branch `feat/agent-dms-v1`. This evidence is finalized in a subsequent
documentation commit on the same branch. The handback reports that exact final
commit. Source and evidence are committed/pushed; no merge, publication,
deployment, visibility change or task-worktree cleanup is authorized/performed.

All required v1 phases are implemented. The frozen plan SHA-256 remains
`eb301573ad4627a96d26baae2eeb6a4b23b5709600f62d530507bc9d223bbacb`.
[Manager amendment M01](PLAN-AMENDMENTS.md) is recorded separately and implemented.
No internal review/planning/implementation subagents were launched; Manager owns
final review. No Qorqut/ACLA runtime import or copied implementation is present.

## Verified checks

Local interpreter: **CPython 3.12.3**. Tests use isolated temporary project state,
SQLite connections, fake domain clocks, loopback ports and fake notification
executables. No operational database, another agent credential, native user
thread, provider API, global client configuration or existing terminal was used.
Python 3.11 is configured in the explicit CI matrix; no local 3.11 interpreter
was available and its CI result is not asserted here.

Final focused commands on the complete implementation:

| Exact command | Result |
|---|---|
| `.venv/bin/pytest -q tests/test_storage_identity.py tests/test_sessions_status.py tests/test_messages_history.py tests/test_inbox_claims.py tests/test_workstreams.py` | **29 passed**, 8.88 s |
| `.venv/bin/pytest -q tests/test_mcp_integration.py tests/test_stdio_bridge.py` | **9 passed**, 18.07 s |
| `.venv/bin/pytest -q tests/test_watch_receipts.py tests/test_cli_backup.py` | **15 passed**, 11.18 s |

**53 focused tests passed.** No unrestricted repository-wide suite was run.
Earlier development failures exposed a directory result-argument collision,
SDK 2.2 callback/client signature differences, and stateless cross-request
cancellation. These were corrected; M01 supplies the approved cancellation
integration. The final commands above contain no failing or skipped tests.

Additional focused validation:

- `.venv/bin/pip install --require-hashes -r requirements-dev.lock` and
  `.venv/bin/pip check`: succeeded, no broken requirements. Runtime/dev lockfiles
  resolve versions/hashes without private indexes or machine-specific paths.
- `SOURCE_DATE_EPOCH=1790980810 .venv/bin/python -m build`: wheel and source
  archive built (timestamp is the implementation source commit's Unix time).
- `.venv/bin/python scripts/validate_artifact.py`: fresh temporary venv installed
  hash-locked runtime dependencies and the wheel; dependency check, import without
  state creation, packaged SQL/protocol, MIT/third-party notices, entry point,
  CLI help/version, actual wheel init/add/list, and JSON/TOML examples all passed.
- `docker build -t agent-dms:local .`: succeeded. Built image
  `sha256:543f6a2faf5878c11f5b35e93771bca98c1a7e31d4be259ab60d702cfa53d209`,
  configured user `10001:10001`. No persistent service/container was deployed.
- `docker compose config --quiet`: passed; host port is loopback-bound and state
  has a persistent volume. No registry/package publication occurred.
- `.venv/bin/python -m compileall -q src examples tests scripts`: passed.
- `git diff --check` and `git diff --cached --check`: passed. Final scope/secret
  inspection found no runtime state, bearer credentials, receipts, transcripts,
  virtual environments or private machine paths in authored runtime/docs/examples.

Validated wheel: `dist/agent_dms-0.1.0-py3-none-any.whl`, SHA-256
`e49ec1ea84460036b7f822b40c9168b66dd6d59270842865e69a66a87dd44eb3`.
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
| A01 | Private init/re-init, UUID stability, symlink/populated-target refusal, newer-schema rejection, process locks; storage/identity and CLI second-daemon tests |
| A02 | Exact token principal, casefold/NFC names, bounded metadata, durable rotation failure handling, revocation, cross-project rejection; storage/identity tests |
| A03 | 1/30/31 words, empty/Unicode/control/500-character boundaries and normalization; session/status tests |
| A04 | Separate-connection concurrent status revisions, age/heartbeat independence and stale-send repair; session/status tests |
| A05 | Stable reconnect, explicit takeover, expired lease renewal, permanent closed/superseded key fencing, stale close/ACK rejection; session/status, inbox and wire tests |
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
| A19 | Real stdio SDK subprocess and direct HTTP peer share one daemon/database and contract; successful SDK parsing verifies protocol-only stdout |
| A20 | Empty/unchanged/all-claimed hints cause no sink/receipt, 105 pending messages counted beyond the first page, captured revision coalescing; watcher tests |
| A21 | Missing capability no-start retry, actual fake subprocess success/nonzero/timeout, parent process killed after child spawn then restart quarantines uncertainty, exact explicit resolution; watcher tests |
| A22 | Exact fixed argv and UUID/workspace, real DM arrival during sink preserves next revision, actual watcher stops on takeover, safe outage diagnostics; watcher tests |
| A23 | Online backup concurrent with writes, integrity/hash/FK validation, new-directory restore retains IDs/pending work, occupied/tampered target refusal; CLI/backup tests |
| A24 | Locked wheel/source build, fresh wheel install/CLI/operator smoke, notices/resources, JSON/TOML configuration parse, non-root Docker build/Compose parse; artifact script and package checks |
| A25 | Two isolated persistent SDK client processes establish sessions over HTTP, send/reply/ACK across daemon restart and complete the full ACLA revision loop through another restart; MCP integration process test |

Meaningful fault injection demonstrates rollback of send message/delivery/thread,
ACK receipt/delivery updates, and workstream transition plus optional ACK/message.
Discarded committed-response retries use the exact saved keys and preserve one
intended effect. Injected transport/tool exceptions include sentinel credentials
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
