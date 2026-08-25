# F0 — Physical Effect Boundary Audit

Status: audit only. No production protocol mutation.

Baseline: Phase E is closed. The semantic rollback point remains `2f47395a41e4e508eca5ad5af167f10bf5442fd3`; the closure contract is documented in `docs/phase-e-closure.md`.

## Purpose

F0 asks a narrower question than Phase E:

```text
runtime durable dispatch commitment
        ↓
provider invocation
        ↓
where does this carrier actually begin the physical effect?
```

This audit does **not** redefine `InvocationDispatchCommitted` and does not add a transport fence, generation, reservation state, provider capability, or execution status.

The frozen Phase E rule remains:

```text
InvocationDispatchCommitted COMMIT
    <
later blocking governance mutation COMMIT

=> the existing attempt retains the runtime execution authority already committed to it
=> the later blocker does not retroactively revoke that attempt
```

Any future requirement to revoke an already dispatch-committed attempt before a lower-level physical effect would require a new semantic responsibility. It cannot be implemented by silently moving the E2b fence.

## Audit vocabulary

`runtime dispatch commitment`
: The durable `InvocationDispatchCommitted` fact established by `GovernanceDispatchCommitter` before `RealityBoundary` invokes the provider.

`provider invocation entry`
: Entry into `CapabilityProvider.invoke(request, context)`. This is a software call boundary, not necessarily a physical-effect commitment point.

`physical carrier commitment point`
: The first carrier-specific operation after which the external/local effect attempt has actually begun at the transport/process layer. This is not assumed to be atomic with runtime governance state.

`cancellation window`
: The interval in which a carrier could theoretically be stopped before its physical commitment point. A window is useful only if the protocol exposes a request-bound cancellation/fencing responsibility in that interval.

`reconciliation mechanism`
: A durable or authoritative mechanism capable of determining the state of an ambiguous committed attempt after a crash or communication loss. Process termination is not reconciliation, and cancellation is not rollback.

## Carrier matrix

| Carrier | Runtime dispatch commitment | Provider invocation entry | Physical carrier commitment point | Pre-commit cancellation/fence | Post-commit cancellation | Idempotency / reconciliation | Audit conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `StdioJsonlProvider` one-shot subprocess | `InvocationDispatchCommitted` before `RealityBoundary -> provider.invoke` for governed invocations | `StdioJsonlProvider.invoke()` | `await asyncio.create_subprocess_exec(*cmd, ...)` inside `invoke()` | None. The provider exposes no request-bound process or fence before spawn; `cancel(request_id)` is a no-op. | Timeout path can `process.kill()` after spawn. This is best-effort termination, not rollback of effects already produced by the child. | No generic reconciliation ledger in the stdio-jsonl protocol. The request has an ID, but protocol v1 does not define a durable effect identity or reconcile operation. Carrier-specific idempotency must be supplied by the invoked implementation. | There is a real scheduling interval between E2b commitment and process spawn, but no protocol responsibility exists that could safely make it revocable. |
| Codex requested execution through `ProcessExecutor` | `InvocationDispatchCommitted` before `RealityBoundary -> CodexProvider.invoke` for governed invocations | `CodexProvider.invoke()` | `await asyncio.create_subprocess_exec(*spec.argv, ...)` inside core `_run_subprocess()`, reached via `ProcessExecutor.run(spec)` | None. `ProcessSpec` / `ProcessExecutor.run()` has no dispatch token, reservation, or final-fence callback. `CodexProvider.cancel()` is a no-op. | Timeout invokes executor termination (`taskkill /T /F` or `os.kill(pid, 9)` best-effort). A workspace-writing process may already have produced local effects; termination is not rollback. | `CodexProvider.reconcile()` returns `None`; there is no remote operation ledger. Any recovery of workspace effects must use independent state/effect verification rather than provider acknowledgement alone. | The physical point is one abstraction layer below the provider. A generic provider-level fence would still not identify the actual spawn without ProcessExecutor participation. |
| Codex health probe | Not a governed attempt dispatch commitment | `CodexProvider.health()` | `asyncio.create_subprocess_exec(codex, "--version", ...)` | Not applicable to governed effect admission. | Probe timeout may kill the health subprocess. | Not an execution-attempt recovery mechanism. | Must not be mistaken for the requested effect commitment point merely because it also spawns a process. |

## Findings

### F0-1 — There is no uniform physical-effect commitment abstraction

The two audited subprocess carriers already place their physical points at different abstraction layers:

```text
StdioJsonlProvider
RealityBoundary
    -> StdioJsonlProvider.invoke
        -> asyncio.create_subprocess_exec

Codex
RealityBoundary
    -> CodexProvider.invoke
        -> ProcessExecutor.run
            -> _run_subprocess
                -> asyncio.create_subprocess_exec
```

A future HTTP request, queue publication, remote RPC, database write, or other carrier will have a different commitment point again. `CapabilityProvider.invoke()` is therefore too opaque to support a truthful global claim that its entry or return is the physical-effect commitment point.

### F0-2 — Existing cancellation is not a pre-effect fencing protocol

`StdioJsonlProvider.cancel(request_id)` and `CodexProvider.cancel(request_id)` are no-ops. Existing process termination paths happen only after a process exists and are timeout/recovery controls. They do not create a request-bound pre-spawn reservation and cannot prove:

```text
later blocker before spawn
=> previously dispatch-committed attempt cannot spawn
```

Nor can process kill prove rollback of effects already produced after spawn.

### F0-3 — Process spawn is not equivalent to objective effect completion

For a workspace-writing Codex invocation, subprocess creation means the effect carrier has begun. It does not prove that the requested repository mutation was produced, that the mutation is correct, or that the target objective is satisfied.

For stdio-jsonl, spawning the subprocess is even earlier than sending the invocation JSON line to the child. The child process exists before the runtime has finished writing and draining the request message. Therefore neither process spawn nor provider return alone supplies objective effect verification.

### F0-4 — Effect semantics cannot currently be inferred uniformly from the stdio transport descriptor

`ProviderDescriptor` defaults `effect_semantics="pure"`, `side_effect_class="pure"`, and `reversibility="unknown"`. `StdioJsonlProvider` constructs its descriptor from the manifest without explicitly supplying these typed fields, while `ProviderManifest` protocol v1 contains no typed effect-semantics/reversibility fields.

This is an audit finding, not an F0 production change. It means transport implementation alone is not an authoritative classifier for whether a spawned child is physically mutating. Runtime capability/effect contracts remain the action authority. A future transport protocol must not infer physical safety from the stdio descriptor defaults.

### F0-5 — The current crash/recovery model is consistent with Phase E, but not a physical-effect ledger

Phase E correctly preserves a durable committed-attempt fact after `InvocationDispatchCommitted`. F0 finds no carrier-level durable ledger for the two audited subprocess implementations that could establish exactly what happened after a crash between dispatch commitment and authoritative result projection.

This strengthens the case for independent effect verification/recovery semantics; it does not by itself establish a need for revocable transport reservation.

## Decision gate

### F1-A — Transport commitment protocol

Decision: **DEFERRED / NOT REQUIRED BY CURRENT EVIDENCE**.

F0 has not established a product threat model requiring this stronger rule:

```text
InvocationDispatchCommitted COMMIT
    <
later blocker COMMIT
    <
physical effect commitment

=> stop the already dispatch-committed attempt
```

That rule would contradict the frozen E2b meaning unless a new responsibility is introduced. If the product later requires it, the minimum honest model is two-stage:

```text
RevocableDispatchReservation
        ↓
carrier-specific final fence
        ↓
PhysicalEffectCommitted
```

Such a phase would require, at minimum:

1. a new durable reservation identity distinct from `InvocationDispatchCommitted`;
2. explicit carrier participation at the actual commit point;
3. a transport/process API capable of consuming the reservation/fence;
4. recovery rules for reservation-without-physical-commit and physical-commit-without-result;
5. carrier-specific idempotency/reconciliation evidence;
6. conformance proving both linearization orders without redefining Phase E.

It must not be called an E2c governance generation, and it must not silently reinterpret `InvocationDispatchCommitted` as revocable.

### F1-B — Effect verification / recovery closure

Decision: **RECOMMENDED DEFAULT NEXT SEMANTIC PHASE**.

The stronger product gap visible in current code is downstream of legal execution authority:

```text
legal dispatch authority
        ↓
provider execution
        ↓
what effect actually exists?
        ↓
who verifies that effect?
        ↓
what does that verification authorize the runtime to conclude?
```

The entry counterexample for F1-B should be frozen as:

```text
CapabilityResult.status == "succeeded"
    != objective effect verified
    != governance responsibility discharged
    != terminal completion authorized
```

A provider success means the provider reported successful execution. It must not, by itself:

- prove that the intended external/local objective became true;
- close a review obligation;
- discharge independent responsibility;
- prove continued qualification;
- authorize terminal completion.

F1-B should therefore examine objective verification, authoritative Outcome formation, continued qualification/revalidation, and recovery/reopen after ambiguous or failed effects.

## Reopen condition for F1-A

F1-A should be reconsidered only when at least one concrete carrier has a product requirement equivalent to:

```text
A dispatch-committed attempt must remain revocable until carrier-specific physical commitment,
and a blocker linearized before that physical commitment must prevent the effect.
```

The decision must name:

- the exact carrier;
- the exact physical commitment operation;
- the threat/failure scenario that E2b cannot tolerate;
- the required cancellation guarantee;
- the idempotency/reconciliation mechanism;
- why F1-B verification/recovery is insufficient for that scenario.

Absent that evidence, Phase E remains sufficient for execution-authority linearization and F1-A remains deferred.

## F0 exit

F0 is complete when this audit is accepted without production protocol mutation.

Recommended roadmap after acceptance:

```text
Phase E     CLOSED
E1          admission
E2a         permit binding
E2b         durable dispatch linearization

Persistence determinism repair
            COMPLETE (independent maintenance)

F0          physical-effect boundary audit
            COMPLETE on acceptance of this document

F1-A        transport commitment protocol
            DEFERRED unless reopen condition is met

F1-B        effect verification / recovery closure
            DEFAULT next semantic phase
```
