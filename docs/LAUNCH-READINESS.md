# Open-source launch readiness

Prepared 2026-10-03 UTC. This checklist distinguishes preparation from actual
release. The accepted implementation is commit `d75282e`; launch changes are on
`prep/agent-dms-open-source-launch`. The repo remains private and main still has
only the initial README at the start of this preparation.

## Prepared artifacts

- Public-facing README, reproducible source installation and disposable demo.
- Package metadata/URLs/classifiers, MIT license/notices, changelog, contributor,
  support and private-security-reporting instructions; issue and PR templates.
- Manual PyPI/TestPyPI OIDC workflow with pinned actions, clean exact-commit
  checks, explicit enable variable and separate protected publisher job.
- MCP Registry `server.json` with the PyPI README ownership marker, named daemon
  URL and required private token-file path. No hosted server is advertised.
- [Release runbook](RELEASING.md), [native-client acceptance](NATIVE-CLIENT-ACCEPTANCE.md),
  [launch strategy/copy](launch/PLAN.md) and an owner review gallery outside source.

## Publication gates

| Gate | Current state | Evidence/action needed |
| --- | --- | --- |
| v1 runtime review | Passed | Accepted d75282e; original CI: 81 checks per Python 3.11/3.12 interpreter. |
| Candidate packaging/demo | Prepared for focused verification | Final results recorded in launch evidence after checks. |
| Linux Python 3.11/3.12 | Supported test baseline | Keep exact candidate CI green. |
| Native Claude↔Codex | Unverified | Run the acceptance procedure or keep an explicit SDK-only compatibility qualification. |
| Native wakeup consumption | Unverified | Separate optional native-client check; never advertise delivery as model handling. |
| Source merge | Pending owner authorization | Review exact launch branch/source and main base; no default-branch write yet. |
| History/public metadata review | Bounded scan completed | Nine initial commits/94 unique blobs: no matched credential patterns; old AGENTS.md contains two local workspace paths. Review author metadata/PRs/actions before public visibility. No history rewrite performed. |
| License/provenance | MIT declared | Original code; existing notices and behavioral provenance retained. Not a third-party legal certification. |
| Package name | PyPI API returned 404 | Snapshot at 2026-10-03 00:23 UTC, not a reservation. Recheck and establish project owner. |
| Publisher accounts/environments | Pending | PyPI/TestPyPI accounts, OIDC bindings, review protections and enable variable. |
| Vulnerability reporting | Policy prepared | Enable and verify the private GitHub reporting route before public launch. |
| Public repository / release | Pending authorization | Public history implications reviewed; exact main/tag/artifact hashes bound to approval. |
| MCP Registry | Manifest prepared | Validate against official schema; org Owner authentication and real PyPI package still required. |
| Marketing posts | Drafts only | Destination live, exact copy/channel chosen and posting authorized separately. |
| Customer demand | Hypothesis | Observe independent installation and a useful exchange on a real project. Stars do not establish demand. |

The bounded history scan checked private-key, GitHub/provider/AWS credential and
literal bearer-token patterns, plus local host/path references, without printing
matches. It is not proof that secrets are absent. The two historical local paths
are workspace instructions, not credentials. The current instructions are now
portable; those older blobs remain part of a visibility change. The frozen
implementation plan has not been modified.

## Recommended release shape

Use an experimental MIT 0.1 release for developers already running multiple
agents on one Linux project. Lead with peer discovery/status and durable DMs;
explain review conversations as an optional coordination pattern. Use GitHub
and PyPI as the primary destination. Registry listing and a Show HN post follow
working installation evidence. Keep 49Agents IDE's distinct license and product
claims separate from agent-dms.

No demand, customer, adoption, speed, cost-saving, security-audit or universal
client-compatibility claim has been established. Launch preparation does not
change those facts. No site, model, production daemon, paid campaign or outreach
is required to finish these preparations.
