# agent-dms repository instructions

This is a 49Agents product. Its initial development repository is private.

- Read `docs/IMPLEMENTATION-PLAN.md` before implementation. Manager owns design,
  scope and acceptance criteria. Ask Manager about a missing decision rather
  than silently changing the plan. Implementation evidence belongs in
  `docs/IMPLEMENTATION-RESULTS.md`, not retroactive edits to the accepted plan.
- Inspect status and worktree inventory before changes. Work only in the
  dedicated task branch/worktree supplied by the handoff, never the shared
  primary checkout or main/master. Preserve others' work.
- For this workspace, task worktrees belong under
  `/home/alp/qorqut/worktrees/<task>/<repo>` or
  `/home/alp/bazarlyk/worktrees/<task>/<repo>`. Reuse your own task worktree.
- Fetch the intended base before creating a new task branch. Commit all scoped
  code/tests/docs, push after the first meaningful commit and at coherent
  checkpoints, and push before handback. Do not force-push over someone else's
  work. Retain commits and report a push failure.
- Run focused checks for the changed behavior and directly affected interfaces.
  Use the named feature checks in the plan; no broad unrelated test suites.
  Tests use temporary databases/files, fake clocks and isolated local ports.
- Do not import Qorqut/ACLA at runtime, copy private Qorqut implementation,
  access operational databases or another agent's credentials, change global
  client configuration, or control existing terminals during development.
- Do not commit credentials, runtime state, private transcripts, live deployment
  configuration, notification receipts or virtual environments. Use original
  code and preserve notices for any permitted source adaptation.
- No merge, direct default-branch push, deployment, package publication or
  visibility change without explicit owner authorization for that action.
  Review approval and implementation permission do not supply that authority.
- After an explicitly approved merge, verify the remote target, then remove only
  your clean task worktree/local and remote task branches and empty task folder.
  Never delete dirty or unmerged work or unrelated branches/worktrees.
- For Qorqut/Bazarlyk shared releases use the installed `release-worker` and its
  immutable plan/guide; this development task does not authorize any release.
- End reports state branch/short commit; committed yes/no with remaining changes;
  pushed yes/no; merged yes/no and target; cleanup done after merge or retained.

For this initial ACLA implementation: Codex backend, `gpt-6.1-sol`, fixed `xhigh`
effort, normal service speed, self-review loop disabled. Do not spawn internal
reviewer/planning/implementation subagents. Manager reviews after completion.
Send one completion report for the whole assignment; use ACLA ask-question for
blockers and wait for the answer on affected work. Do not send milestone reports.
