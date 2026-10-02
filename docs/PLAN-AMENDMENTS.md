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
