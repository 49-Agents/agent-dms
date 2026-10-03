# Changelog

## 0.1.0 — prepared, not yet released

Initial experimental release of agent-dms, a project-local MCP mailbox for
existing agents.

- Peer discovery and separate per-agent credentials.
- Required current-work status of 1–30 words, with freshness and presence.
- Durable DMs, exact leased claims, explicit acknowledgements, history and
  idempotent mutation retries.
- Manager/Worker handoffs, questions, answers, completion reports, revisions
  and approvals within existing owner permissions.
- Shared HTTP daemon and local stdio adapters; optional local wakeup receipts.
- CLI provisioning, token rotation/revocation, backup/restore and diagnostics.
- MIT license, hash-locked dependencies, wheel/sdist and local container recipes.

Linux Python 3.11/3.12 and official SDK HTTP/stdio clients are tested. Native
Claude/Codex sessions and real native wakeup consumption remain unverified.
v1 does not launch models/processes, prune history or provide a hosted service.
Review [installation](docs/INSTALL.md) and [security boundaries](docs/SECURITY.md).
