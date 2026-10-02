# Source and design provenance

The initial plan was authored on 2026-10-02 for 49Agents' `agent-dms` product.
The product's required behaviors come from the owner's request and inspection
of the current Qorqut inbox and installed ACLA coordination implementation.

## Qorqut behavioral references

The inspected current deployment was `chat-styling-ux-20261002`. Relevant
documentation: Agent inbox, Internal agent messaging, and Agent activity and
task progress. These describe immutable messages, per-recipient acknowledgement,
single-consumer ownership, current-work observations and offline delivery.

Reference file SHA-256 values, for identifying the exact inspected behavior:

| Reference | SHA-256 |
|---|---|
| `bazarlyk/inbox/service.py` | `494823d8703f52b2618382b9ea1e141ad71372af7997ae44c3f8731b4314fca0` |
| `bazarlyk/inbox/messages.py` | `041cba06ba21328e1c75cb80f21267096a4ccede1f989fcd19bb13888bcec65f` |

These are conceptual/behavioral references. No Qorqut source, business data,
configuration or credentials are included or required by this repository.
The new implementation must not depend on a Qorqut installation.

## ACLA behavioral references

Inspected installed plugin version:
`astra-critic-luna-actor/0.1.0+codex.20260930185638`.
Its source license is MIT, copyright 2026 ACLA contributors.

| Reference | SHA-256 |
|---|---|
| `acla/store.py` | `32060eb9c4a3809cdfc251ce0217d84ea77da94cd5a87512031ebc4a7fedeb1d` |
| `acla/delivery.py` | `9aab814bb029be9741f1163acc929fa8a2ecd2b78150e596f2299d65b56082fd` |

The plan carries forward durable full messages, exact claims, coalesced wakeups,
explicit uncertain-delivery recovery, and Manager/Worker handoff/review roles.
It does not port the entire tmux launcher or modify an installed ACLA instance.
If implementation adapts substantial ACLA source, its original MIT notice must
be retained in `THIRD_PARTY_NOTICES.md`.

## External evidence

[Competitor research](COMPETITORS.md) was performed by one GPT-6 Luna research
agent and includes retrieval timestamps, pinned source references where
available, direct competitors, adjacent frameworks and remaining unknowns.
It is a bounded research snapshot, not proof of adoption or an exhaustive list.
No competitor code is approved for copying or executing in this implementation.

The official Python MCP SDK 2.2.0 wheel was inspected before the plan was written:
`mcp-2.2.0-py3-none-any.whl`, SHA-256
`bde982589473a060ae145e3406e9a5333fe538c97229ba841f5a7f92be004f81`.
Use its low-level server and Streamable HTTP session manager.

Codex transport/configuration guidance was checked against the
[official MCP documentation](https://developers.openai.com/codex/mcp/).
The inspected local CLI exposes `codex queue --thread UUID --message TEXT`;
that native wakeup command must remain capability-detected rather than assumed
to be present in every Codex installation.

## Original implementation

The v1 implementation was authored independently against the accepted contract.
No Qorqut, ACLA or competitor implementation code was copied or adapted. The
installed MCP 2.2.0 API/source signatures were read to integrate its low-level
Server callbacks, official clients and StreamableHTTPSessionManager. Manager
amendment M01 authorizes a narrow SDK-typed cancellation integration; it does
not fork or monkey-patch the SDK. Licensing notes are in THIRD_PARTY_NOTICES.md.

Official Codex and Claude MCP configuration pages were fetched on 2026-10-02.
Examples use scoped TOML/JSON, HTTP bearer environment variables, or local private
token-file stdio adapters. Configuration parsing and actual SDK wire acceptance
are distinct from native provider-client verification; see implementation results.
