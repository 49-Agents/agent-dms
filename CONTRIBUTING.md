# Contributing

Work only in an isolated dedicated branch/worktree, preserve others' changes,
and read AGENTS.md plus the accepted implementation plan and amendments. Do not
develop on the default branch or shared primary checkout. Commit scoped code,
focused checks and evidence; push before review. Review is not merge/release
permission. Never auto-merge, deploy, publish packages or change visibility.

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.lock
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest -q tests/test_storage_identity.py tests/test_sessions_status.py
.venv/bin/pytest -q tests/test_messages_history.py tests/test_inbox_claims.py
.venv/bin/pytest -q tests/test_workstreams.py tests/test_mcp_integration.py
.venv/bin/pytest -q tests/test_stdio_bridge.py tests/test_watch_receipts.py
.venv/bin/pytest -q tests/test_cli_backup.py
.venv/bin/python -m build
```

Select only files/cases covering changed behavior; these are the named acceptance
feature groups, not authorization for unrestricted all-suite testing. Tests use
temporary state, clocks, ports and fake queue executables, never operational DBs,
real native threads, provider API calls or global client settings. CI explicitly
names these files on Python 3.11/3.12. Do not invent tests that merely mirror code.

Runtime state, tokens, backups, receipts, transcripts and virtual environments
must stay outside commits. Original code is MIT; retain notices for permitted
adaptations, and do not copy private Qorqut or competitor implementations.
Record evidence in IMPLEMENTATION-RESULTS, never retroactively change the frozen
plan. Architecture/scope/acceptance decisions belong to Manager; ask blockers.
