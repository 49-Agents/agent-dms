# Working on agent-dms

- Read README.md, CONTRIBUTING.md and the relevant protocol/architecture section
  before changing behavior. Preserve project identity, exact leased inbox claims,
  explicit acknowledgements and idempotent retry semantics.
- Work on a dedicated branch and isolated worktree. Inspect Git status and the
  worktree inventory first; preserve other contributors' changes. Maintainer
  workspace instructions determine worktree locations.
- Run focused tests for the behavior and integrations you change. Use temporary
  databases, local ports and fake notification executables. Do not use real
  provider sessions, operational data, global client settings or private tokens.
- Commit scoped source, tests and docs, and push the review branch. Do not merge,
  publish packages, change repository visibility, deploy or post announcements
  without explicit maintainer authorization for that action.
- Keep credentials, runtime state, backups, notification receipts, private
  transcripts and virtual environments out of Git. Do not copy private source
  or competitor implementations; retain notices for permitted adaptations.
- The initial design record in docs/IMPLEMENTATION-PLAN.md is frozen. Explain
  later design changes in a separate amendment or change record, and record
  verification honestly. Transport tests do not prove native model behavior.
- Report branch/commit, focused checks, and committed/pushed/merged status.
  Retain an unmerged worktree for review. Never delete someone else's work.

See docs/RELEASING.md for publication. This repository supplies messaging for
existing agents, not a model/process launcher.
