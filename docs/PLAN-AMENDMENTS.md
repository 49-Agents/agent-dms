# Manager-authored plan amendments

## M01 — authenticated inbox_wait cancellation

The following decision was received through the bound review workflow on 2026-10-02. The original implementation plan remains unchanged.

> MANAGER_DECISION — amendment M01: authenticated inbox_wait cancellation

Answer to Worker question 1241: use the first option. Keep stateless Streamable HTTP and preserve A15's actual wire cancellation acceptance. The HTTP boundary may use the pinned official SDK's JSONRPC message adapter and cancellation-parameter helper to correlate notifications/cancelled to an active inbox_wait. This is a narrow transport integration amendment to plan sections 4, 6, 10, 12 and A15; it does not permit a replacement MCP/JSON-RPC implementation or an SDK fork/monkey patch.

Implement the following contract:

1. The official SDK remains responsible for protocol validation, dispatch, tool responses, notification semantics and normal errors. Reuse its typed message/parameter parsing. Preserve the bounded body and original bytes for official dispatch; do not hand-parse JSON-RPC shapes, create a competing response layer or swallow SDK errors. Apply the existing authentication, Host/Origin, request-size and capacity boundaries before cancellation lookup. The registry must never be accessible anonymously.

2. Maintain only bounded, in-process active wait registrations. Correlate by this project, the independently authenticated principal, and the exact typed JSON-RPC request ID (integer and string IDs are distinct). Each registration also records its validated application session/generation and a unique in-process registration identity. Register only inbox_wait after normal principal/session validation and before beginning the wait. Do not expose this registry or its content through tools/logs.

3. Cancel only the matching wait's local cancellation scope/task; do not cancel arbitrary requests, the transport manager or another principal's work. A foreign principal with the same request ID must not affect the original wait. Recheck live credential/session authority on ordinary wait completion, and ensure supersession/revocation invalidate the old wait's authority. Cancellation cannot claim, release, acknowledge, mutate messages or advance a durable cursor.

4. Never overwrite an existing live registration with the same principal and request ID or guess between candidates. If concurrent waits collide on that key, reject the newer inbox_wait with the existing retryable CAPACITY_LIMIT domain envelope, using a safe message explaining the active request-ID collision. Preserve the original wait. Document that simultaneous transports sharing one agent identity must use distinct outstanding request IDs; separate independent actors need separate agent credentials as already required. This is an application-level disambiguation requirement, not an assertion that stateless MCP provides a transport session. Do not infer application session identity from arbitrary unauthenticated cancellation parameters.

5. Use try/finally cleanup with registration-identity checks so an older completion cannot remove a newer registration. Success, timeout, cancellation, disconnect/task cancellation, handler error and shutdown must release capacity exactly once and remove the registration. Unknown/already-completed cancellation IDs are harmless no-ops under SDK notification handling. Do not retain an unbounded cancellation/tombstone queue. A cancellation received before registration may harmlessly miss it: this wait is read-only and still bounded by the 25-second deadline. Keep that race limitation honest rather than inventing durable cancellation guarantees.

6. Extend the focused actual-SDK wire acceptance evidence: start a 25-second inbox_wait, send normal SDK cancellation from its client, and prove server capacity is promptly reusable (target within 2 seconds with a reasonable CI scheduling tolerance), without waiting for the original deadline. Verify repeated cancellation/no-op after cleanup; other-principal same-ID isolation; concurrent same-principal ID collision handling; capacity release after timeout/error; and that a message arriving during/after cancellation remains available to inbox_next. Include session takeover/revocation authority tests already required by A14. Do not assert success from the client task returning alone.

Record this Manager-authored amendment verbatim in docs/PLAN-AMENDMENTS.md and link it from IMPLEMENTATION-RESULTS.md, keeping the original frozen IMPLEMENTATION-PLAN.md intact. Record the pinned SDK limitation and the application cancellation integration in the actual architecture/protocol docs. All other scope, implementation/review boundaries, identity/model settings and focused-test restrictions remain unchanged.

Continue the complete assignment after applying this decision; no acknowledgement or interim progress report. Send one completion report after all required work is finished, committed and pushed. Ask a new precise blocker question if official SDK integration cannot implement these constraints; do not silently relax them.

## M02 — session-aware local wakeup recovery

The following Manager decision was received in R01, message 1249, through the
bound review workflow on 2026-10-02. The original implementation plan remains
unchanged. Decision text follows verbatim (original indentation retained).

   MANAGER_DECISION — amendment M02: session-aware local wakeup recovery

   The base target identity remains the current configured sink destination
   (service/agent/sink/native thread/workspace). It excludes the application
   session so unresolved uncertainty continues to quarantine that actual
   destination across session changes. Receipt intent uniqueness and accepted
   revision suppression become scoped to (base target, application session).

   - Add terminal receipt state superseded for a pending or not_started receipt
     whose recorded application session differs from the currently authenticated
     watcher session. It means no dispatch is authorized for that old intent.
     Preserve its ID, original session/target/revision, attempts, timestamps and
     history; record the supersession reason/time without deleting the record.
   - In one local transaction, check the whole base target for uncertain or
     dispatching receipts before retiring old-session safe receipts or creating
     a replacement. Either state blocks every session at that target. On ledger
     restart retain the existing dispatching-to-uncertain rule. Never silently
     resolve, delete, retire, rekey, or bypass an uncertain/dispatching receipt.
   - Once no uncertainty blocks the target, retire old-session pending and
     not_started receipts, and select/create work for the current session. A
     same-session retry retains its exact receipt ID and captured revision and
     respects its existing capped backoff. Do not advance past the captured
     revision when a later arrival occurs during dispatch.
   - Receipt uniqueness is (target, session_id, revision). Accepted watermarks
     are per (target, session_id), including watcher reconnect initialization.
     A new current session with available work can receive a fresh receipt even
     when the numerical revision was accepted for an earlier session. No work
     available still means no new receipt or sink call. Same-session accepted
     revisions remain suppressed.
   - Explicit resolve --delivered on an old uncertain receipt records acceptance
     only for that receipt's original session. Explicit resolve --retry removes
     uncertainty for that exact receipt and returns it to pending. If that
     session is still current, reuse its exact intent/ID as before. If a later
     authenticated watcher owns a different current session, the pending old
     intent is superseded and a fresh current-session receipt may be created.
     Document this exception clearly: resolution never grants authority to
     dispatch using a closed/superseded application session and never ACKs a DM.
   - The watcher still never opens/takes over a session. Keep the authenticated
     heartbeat immediately before dispatch and stop clearly on lost authority.
     Keep existing bounded diagnostics and quiet empty behavior.
   - Version the private local receipt schema. Migrate the current unversioned
     ledger atomically under its exclusive process lock; do not delete/reset the
     ledger or require an operator to discard history. Retain target rows and
     their legacy accepted values as historical data, add per-session accepted
     watermarks reconstructed from that session's accepted/emitted receipt
     rows, and rebuild the receipt uniqueness constraint without losing rows.
     Preserve IDs, fields and terminal/unresolved outcomes (apart from the
     already specified interrupted-dispatch quarantine). A fresh ledger uses
     the new schema; a newer/unknown schema is refused without rewriting it.
     The server's authoritative message database/schema is unaffected.

   Record this M02 decision in docs/PLAN-AMENDMENTS.md; keep the frozen
   IMPLEMENTATION-PLAN.md unchanged. Update the actual watcher/operations
   documentation and implementation evidence to match the recovery semantics.

   Focused acceptance: old pending and not_started rows safely supersede across
   a session change; a new session can dispatch the same numeric revision;
   same-session retry identity/backoff and unchanged-revision suppression are
   preserved; uncertainty survives restart and blocks all sessions on the
   same base target; exact delivered/retry resolutions behave as above; migrated
   legacy mixed-session receipts preserve every ID/field and reconstruct the
   correct per-session acceptance; simulated migration failure rolls back;
   unknown/newer schemas are refused without mutation. Include an actual
   watcher/service session-replacement/restart check proving the current watcher
   makes progress, old authority stops, and DMs remain pending until explicit
   acknowledgement. Use isolated fake sinks, never a user's native thread.
