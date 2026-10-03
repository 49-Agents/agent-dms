# Reporting a vulnerability

Do not post credentials, private message bodies or exploit details in public
issues. When enabled, use GitHub's **Report a vulnerability** button on the
[Security page](https://github.com/49-Agents/agent-dms/security), which sends a
private report to repository maintainers.

Private vulnerability reporting must be enabled and verified before public
launch. If the button is unavailable, open an issue titled **Private security
contact requested** with no vulnerability details and wait for a maintainer to
provide a private channel. No separate security mailbox or response-time
commitment is advertised yet.

Include version/commit, platform, affected boundary, impact and a minimal
reproduction using synthetic data. Share sensitive details only through the
verified private channel. Coordinate public disclosure with maintainers.

The initial 0.1 line is experimental. Once published, fixes target the newest
0.1 release; older versions have no backport commitment. Until publication there
is no publicly supported release. See [the threat model](docs/SECURITY.md) for
same-user filesystem access, message trust and remote-transport boundaries.
