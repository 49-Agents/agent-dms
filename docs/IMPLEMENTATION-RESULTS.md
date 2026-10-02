# Implementation results

Version 0.1.0. Evidence is recorded separately from the accepted implementation plan.
This document is updated as the authorized implementation is verified.

## Domain checkpoint

Python 3.12.3, isolated temporary SQLite databases and injected clocks.

- `pytest -q tests/test_storage_identity.py tests/test_sessions_status.py`: initial run 15 passed, 2 failed (directory result argument collision). Corrected the collision; `pytest -q tests/test_sessions_status.py`: 13 passed. Storage file: 4 passed in the initial run.
- `pytest -q tests/test_messages_history.py tests/test_inbox_claims.py tests/test_workstreams.py`: 9 passed.

Implemented project identity/private state, credentials, session generations,
status, directory, durable messages/history, signed paging, leased claims,
exact receipts, explicit reply plus ACK, and role-bound workstreams. Tests cover
A01–A12 and domain portions of A17–A18. Transport/client evidence is pending at
this checkpoint. No native provider-client interoperability claim is made.
