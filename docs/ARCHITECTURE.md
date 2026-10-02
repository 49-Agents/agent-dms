# Architecture

A Python 3.11+ package connects independently running MCP clients to one
project-local daemon. It never launches agents/models or owns terminals. Each
project has one local SQLite database and one daemon, protected by a process
lock. HTTP and the transport-only stdio bridge share the same application rules.

| Module | Actual responsibility |
|---|---|
| config / models / errors | Pydantic project config, private filesystem writes, deterministic validation, clock/UUID helpers and safe domain errors |
| storage / migrations | Schema 1, local WAL/FULL, FK enforcement, 5-second busy timeout, explicit transactions, process lock |
| identity / sessions / status | Digest credentials, operator lifecycle, current generation, status revisions and directory observations |
| messaging / inbox | Immutable DMs, signed stable paging, claims/membership, exact receipts and recovery |
| workstreams | Fixed role/state table, transactional full DMs and append-only events |
| service | Shared operations, authority-before-replay, atomic idempotency and bounded waits |
| mcp_server | Official SDK low-level Server callbacks, stateless Streamable HTTP manager, boundary validation and M01 cancellation integration |
| client / stdio_bridge | Official SDK client using its HTTP transport dependency; proxy tools/prompts/resources without a second store |
| watch / notification_receipts | Optional local stdout/queue wakeups and independent private receipt ledger |
| operations / cli | Online backup/new-directory restore, examples, doctor and console entry point |

```mermaid
flowchart LR
  C[Existing MCP agents] --> H[Authenticated /mcp]
  S[stdio clients] --> B[Transport bridge] --> H
  H --> A[Shared Service] --> D[(Project SQLite)]
  O[Local operator CLI] --> D
  W[Optional local watcher] --> H
  W --> N[stdout or capability-checked queue]
  W --> R[(Local receipt ledger)]
```

Credentials authenticate every HTTP method and every callback; transport session
IDs confer no authority. A supplied application session must be the authenticated
agent's current generation. Directory visibility is project-wide for active
credentials, while history/workstreams are two-participant only. Operators and
same-OS-user processes able to read state can bypass application authorization.
Message bodies remain untrusted opaque data; no execution/URL/file attachment
surface exists.

Every domain operation opens a short connection/BEGIN IMMEDIATE transaction.
Sends commit message/delivery/revision/idempotency together. Workstream mutations
also commit event/state; optional reply/transition ACK belongs to that same
transaction. Full-batch validation precedes ACK writes. No transaction awaits a
network call, long poll or child. Claims recover lazily; history is never pruned.
Clock and identity factories are injected for deterministic checks.

```mermaid
stateDiagram-v2
  [*] --> active: New key with status
  active --> active: Same key reconnect or heartbeat
  active --> superseded: New key after expiry or explicit takeover
  active --> closed: Exact close, rotation or revocation
  superseded --> [*]: Permanent key tombstone
  closed --> [*]: Permanent key tombstone
```

```mermaid
stateDiagram-v2
  available --> claimed: inbox_next exact leased batch
  claimed --> available: release / expiry / takeover / revoke
  claimed --> handled: Exact explicit ACK
  handled --> handled: Compatible receipt retry
```

```mermaid
stateDiagram-v2
  pending --> dispatching: Persist before external effect
  dispatching --> emitted: stdout write accepted
  dispatching --> accepted: Queue child exits zero
  dispatching --> not_started: Known pre-spawn failure
  dispatching --> uncertain: Timeout / nonzero / interrupted / restart
  not_started --> dispatching: Capped retry, same receipt
  uncertain --> pending: Explicit exact receipt retry resolution
  uncertain --> accepted: Explicit delivered resolution
```

Notification revisions are hints, independent of delivery authority. All pending
pages contribute to counts. Only captured revision is accepted after dispatch;
new arrivals remain observable. Uncertain receipts block subsequent wakeups for
the target until explicit reconciliation. No empty-poll receipt/log history.

The SDK's stateless HTTP dispatcher is per-request, so native cancellation POSTs
cannot reach earlier requests by themselves. Manager amendment M01 permits a
bounded principal/project/exact-typed-ID registry for active validated inbox_wait
handlers. It cancels that local task and preserves official SDK validation,
dispatch and responses. Registry cleanup is identity-guarded in finally; HTTP
disconnect also cancels the request task. IDs are not guessed across principals,
and concurrent same-principal collisions fail retryably. Pre-registration races
may miss cancellation, bounded by the original 25-second deadline. No durable
cancellation state or invented transport session is introduced.
