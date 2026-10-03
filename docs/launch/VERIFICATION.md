# Launch-preparation verification

2026-10-03 UTC. This records preparation evidence, not publication or native
model acceptance. Runtime behavior remains the previously reviewed v1.

## Completed checks

- 14 local focused tests passed: `tests/test_mcp_integration.py`,
  `tests/test_stdio_bridge.py`, `tests/test_cli_backup.py` (18.74 seconds).
- Built wheel/sdist using the hash-locked development environment. The wheel was
  installed into a fresh temporary venv with hash-locked runtime dependencies;
  `pip check`, CLI/version, resources, provisioning and config examples passed.
- `examples/demo.py` passed both from the source environment and from the freshly
  installed wheel: two separate MCP connections, discovery/status, DM, exact
  claim, explicit parent ACK, reply ACK, session close and temporary cleanup.
- Registry metadata validated against the official 2025-12-11 Draft-07 schema.
  Retrieved schema SHA-256:
  `3fba09590c99f61735d234822279f4223fab9e300c0a81e81c91ab62a4114de0`.
- Release metadata guard rejected blank/wrong commit, wrong version and a dirty
  source checkout. It accepted a clean exact checkpoint commit/version.
- GitHub workflow/issue YAML parsed. `actionlint` 1.7.12 reported no errors;
  its official Linux archive hash was verified before use. Publishing workflows
  were linted, not dispatched; no OIDC account or index upload was exercised.
- Checkpoint CI at `b92aeb2` passed both Python versions, all existing named
  feature groups, metadata checks, build and fresh-wheel demo:
  [run 37082629854](https://github.com/49-Agents/agent-dms/actions/runs/37082629854).
  Subsequent preparation refinements require final-commit CI; its URL and exact
  artifact hashes are kept in the release handoff rather than self-referencing
  this document's commit.
- Original nine-commit history: 94 unique blobs scanned for common credential
  patterns. No credential-pattern match; two old workspace paths in AGENTS.md.
  One Git author uses a GitHub noreply address. This bounded scan does not prove
  absence of every kind of secret. No history rewriting was performed.
- Frozen implementation plan SHA-256 is unchanged:
  `eb301573ad4627a96d26baae2eeb6a4b23b5709600f62d530507bc9d223bbacb`.

## Copy gallery

Two text elements, each with eight distinct concepts and four options: 64 unique
candidate IDs. Live HTML/session/export endpoints responded successfully. On an
isolated copy, votes, notes, final selection and round feedback survived a server
restart. The export retained the exact selected text/revision and feedback.
Opening another round preserved the first round read-only; closed-round writes
were rejected and old final selections were not silently inherited.

No synthetic reviews were written to the owner's live gallery. Browser tools
reported no browser available, so visual/mobile rendering and actual clipboard
interaction were not verified. Hostname reachability was verified locally on the
Tailscale interface; no second device was available for an independent check.
The maintained gallery template was reused without UI changes.

## Remaining external checks

Native Claude Code/Codex exchanges, real native wakeup consumption, macOS/WSL,
newer Python versions, PyPI/TestPyPI upload, MCP Registry acceptance and an
independent user's install are unverified. See the readiness and release runbooks
for exact procedures. The repository remains private until explicitly changed;
no package, release or announcement was published by this preparation.
