# Contributing

Start with a reproducible bug or a concrete workflow that is difficult today.
For protocol, identity, acknowledgement or lifecycle changes, discuss the design
in an issue before implementation. See [SUPPORT.md](SUPPORT.md); report security
issues through [SECURITY.md](SECURITY.md).

## Development

Use a fork or a permitted branch in this repository. Work in a dedicated Git
worktree and preserve others' changes. From that worktree:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
```

Activate the environment and select focused checks affected by your change:

| Area | Check |
| --- | --- |
| Identity and state | `pytest -q tests/test_storage_identity.py tests/test_sessions_status.py` |
| Durable DMs and acknowledgements | `pytest -q tests/test_messages_history.py tests/test_inbox_claims.py` |
| Workstreams and MCP | `pytest -q tests/test_workstreams.py tests/test_mcp_integration.py` |
| Adapters and wakeups | `pytest -q tests/test_stdio_bridge.py tests/test_watch_receipts.py` |
| Operator lifecycle | `pytest -q tests/test_cli_backup.py` |
| Distribution and onboarding | `python scripts/validate_release.py`, `python -m build --no-isolation`, `python scripts/validate_artifact.py` |

Tests must use temporary state, isolated ports and fake queue executables. They
must not invoke paid models, touch global client settings or depend on a live
mailbox. CI covers Linux on Python 3.11 and 3.12.

## Pull requests

Explain the user-visible problem, resulting behavior and focused validation.
Include failure/retry/restart cases for durability changes. Keep the protocol,
packaged protocol resource and operator docs consistent. Add a changelog entry
for user-visible changes. Do not revise the frozen initial implementation plan;
use a separate design amendment when necessary.

Contributions are under the repository's MIT license. Only submit code you have
the right to contribute and preserve applicable third-party notices. Keep secrets,
runtime state and private transcripts out of commits and issue attachments.

Be considerate, respond to technical disagreement with evidence, and avoid
harassment or personal attacks. Maintainers may remove abusive content and
restrict participation. Support is best effort; no response-time promise is
made. Maintainer review does not by itself authorize a merge or release.
