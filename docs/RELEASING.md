# Releasing agent-dms

This is a preparation runbook, not authorization to publish. Current candidate:
0.1.0, experimental Linux release. Source, package publication, repository
visibility and promotional posts are separate effects. No runtime deployment is
needed to release this standalone library/CLI.

## 1. Freeze the source and resolve readiness

- Finish the checklist in [LAUNCH-READINESS.md](LAUNCH-READINESS.md). Keep the
  original implementation plan unchanged and retain implementation evidence.
- Review the launch PR, exact source commit, target/base commit and focused CI.
  Maintainers using the Qorqut workspace use its installed `release-worker`
  `source-library` plan/check/merge lifecycle. It does not publish to PyPI.
- Get explicit authorization before merge. After merging, verify the remote
  main tree and its CI, then freeze that full main SHA for publication. A changed
  source/base requires a new release plan/review. Never publish a moving ref.
- Review all refs/history, author metadata, issue/PR text and attached logs before
  visibility change. Deleting a current file does not remove old Git history.
- Resolve native-client acceptance or preserve the explicit SDK-only limitation.
  Replace README's preparation paragraph and the changelog's unreleased label
  with the actual release state in the reviewed release commit; never imply a
  PyPI package exists before it does.

Version 0.1.0 is the initial experimental version, not an API-stability promise.
A GitHub prerelease flag does not make a `0.1.0` PyPI version a PEP 440 prerelease.
If the maintainer wants `0.1.0a1`, update package/CLI/server versions together,
refresh locks as needed, and rerun the artifact checks before freezing source.

## 2. Establish repository and publisher controls

Before public visibility, review the current
[GitHub visibility effects](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).
The public history and forks may persist after a later visibility reversal.

After explicit authorization, configure:

- Repository `49-Agents/agent-dms`, default branch `main`, MIT license detected.
- Protect `main` with PR review and both `features (3.11)` / `features (3.12)`
  required checks. Verify exact check names in GitHub before saving the rule.
- Enable and verify private vulnerability reporting. Test the report route with
  the maintainer account without filing a fake vulnerability. Keep SECURITY.md
  honest if the route is unavailable.
- Suggested topics: `mcp`, `multi-agent`, `agent-communication`, `python`,
  `developer-tools`. Homepage can point to the README; no landing site is needed.
- Create GitHub environments `testpypi` and `pypi`, restrict deployment branches
  to `main`, require maintainer review and prevent self-review where available.
  If the account plan cannot enforce these protections, document an equivalent
  manual publisher review before enabling the workflow.
- Configure repository variable `AGENT_DMS_PUBLISH_ENABLED=true` only when
  publisher setup and the authorized release are ready. It is intentionally
  absent during preparation. The workflow also rejects non-main dispatches.

The maintainer needs a PyPI account with 2FA and an explicitly selected project
owner. A 404 for `agent-dms` is not a name reservation. Recheck before setup;
never publish into a similarly named third-party project or silently rename.

For the first release, add a **pending trusted publisher** on PyPI:

| Field | Value |
| --- | --- |
| PyPI project | `agent-dms` |
| GitHub owner | `49-Agents` |
| Repository | `agent-dms` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

Repeat separately on TestPyPI with environment `testpypi` and its separate
account. Both indexes are public. No long-lived API token is required: the
publishing job uses GitHub OIDC, and only that job has `id-token: write`.

## 3. Build and inspect without publishing

```sh
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python scripts/validate_release.py --expected-commit FULL_APPROVED_SHA --expected-version 0.1.0
SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)" python -m build --no-isolation
python scripts/validate_artifact.py
sha256sum dist/*.whl dist/*.tar.gz > SHA256SUMS
```

Use a clean worktree and empty build-output directory for each candidate. The
validator installs the wheel into a fresh temporary environment, checks resources
and CLI/config behavior, and runs the real two-client DM/ACK demo. Inspect wheel
and sdist inventories, metadata, rendered README and dependency/license notices.
Keep hashes, exact source SHA, test/CI URLs and review outcome in release evidence.

## 4. Rehearse on TestPyPI, then publish the reviewed version

Only after explicit publication authorization, manually dispatch `publish.yml`
on `main`, supplying the **full approved main commit**, version and target.
Start with `testpypi`. Review the protected-environment job before permitting it.
The workflow builds, checks and uploads the wheel/sdist; it does not create a
GitHub release, change visibility or post announcements.

Download the exact TestPyPI artifact and inspect its hashes. Test it in a fresh
venv: install production dependencies from the reviewed hash lock, then install
only the downloaded agent-dms wheel with `--no-deps`. Avoid mixing TestPyPI and
PyPI with `--extra-index-url`, which can select unintended dependency sources.
Run the demo from the matching source release and verify the README/metadata.

For production, dispatch the same reviewed source with target `pypi`. Each run
rebuilds from the frozen commit using its timestamp and the locked backend; check
hashes against rehearsal and stop on an unexplained difference. Do not assume
reproducibility just because the version matches. The PyPA action verifies the
artifacts and supplies digital attestations. Retain the run URL and downloaded
package hashes. Verify the public PyPI JSON, project ownership, version, files
and a fresh installed-package demo before promotion.

If upload fails or times out, inspect the index's exact version/file hashes
first. Never overwrite a version, use `skip-existing` to hide a mismatch, or
blindly upload again after an uncertain result. A broken published release is
fixed with a new reviewed version; consider yanking the broken version after
explicit authorization. Keep existing users' local databases untouched.

## 5. GitHub release and MCP Registry

Prepare a GitHub **draft** release for `v0.1.0` at the approved main SHA, attach
the same wheel/sdist and SHA256SUMS, and use CHANGELOG.md as release-note source.
Check package URLs and native-client qualifications. Publishing the release or
making the repository public each requires authorization. No production service
is started by these steps.

`server.json` describes the local stdio adapter. It requires an already-provisioned
mailbox, running daemon and private token-file path. It is not a hosted endpoint
or a one-click daemon bootstrap. Do not add a fake `remotes` URL.

After the real PyPI version is available:

1. Obtain a reviewed, pinned official `mcp-publisher` CLI. Check its release
   checksum and record version/hash; avoid piping a moving download into a shell.
2. Validate `server.json` with the current official schema/CLI. The saved schema
   version is `2025-12-11`. The registry is in preview; recheck its current rules.
3. Authenticate using the owner's GitHub account. The proposed namespace is
   `io.github.49-Agents/agent-dms`; current registry docs require **organization
   Owner** status, not ordinary membership. Namespace access remains unverified.
4. Confirm the published PyPI description contains the exact `mcp-name` marker.
   TestPyPI is not supported by the official registry.
5. With separate authorization, run `mcp-publisher publish`. Verify the registry
   record's namespace, version, package identity and arguments using its API.
6. Test the consumer-generated invocation in an isolated project. `uvx` is a
   consumer runtime hint, not an added runtime dependency of agent-dms.

Do not treat local JSON-schema validation as registry publication acceptance.
Registry publication can follow the initial source/package launch if account
or consumer validation is unfinished.

## 6. Promotion and follow-through

Use the reviewed launch copy only after the destination is public and installable.
Read channel rules again; publishing the code does not authorize posting from
social accounts. Use one useful demo, answer setup questions, and record actual
install/DM completion feedback. Do not promise native compatibility, response
speed, cost savings, popularity or performance without evidence.

## Authoritative references (retrieved 2026-10-03 UTC)

- [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/) ([source](https://github.com/pypi/warehouse/blob/main/docs/user/trusted-publishers/using-a-publisher.md))
- [First project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [MCP publishing](https://modelcontextprotocol.io/registry/quickstart) · [Package types](https://modelcontextprotocol.io/registry/package-types) · [Authentication](https://modelcontextprotocol.io/registry/authentication)
- [Exact registry schema](https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json)
- [Show HN rules](https://news.ycombinator.com/showhn.html)
