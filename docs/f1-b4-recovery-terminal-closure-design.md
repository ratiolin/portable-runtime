# F1-B4 design audit: recovery and terminal closure

## Baselines and scope

- F1-B2 semantic baseline: `448e121dcfd9b92de3e85ba2266e23bf0793f6cd`
- F1-B3 implementation baseline: `25d834a174a5e884afcef532d3e5c3bd4f000107`
- This branch is a design/counterexample freeze only. It introduces no recovery, terminal, governance, review-discharge, qualification, activation, or reopen production semantics.
- B3-P4 remains `NOT STARTED` and is not implied by this audit.

## Frozen entry counterexamples

```text
confirmed Outcome(pass)
    != terminal completion

confirmed Outcome(fail)
    != recovery decision

blocking ReviewObligation exists
    != terminal authority
    != recovery authority

provider/execution uncertainty
    != objective failure

reconciliation result exists
    != objective verification
    != recovery closure
    != terminal completion
```

## Audit finding A: terminal and governance authority are independent by default

`CompletionAuthority` validates typed, passing verification evidence bound to the exact Work/Run, scope, version, criteria, and declared proof obligations. It then delegates the paired Work/Run terminal write to `StateStore.commit_terminal()`.

It does not read distinction-governance `ReviewObligation` state. That absence is not by itself a defect. A blocking Q is a governance-use/review fact; it is not a universal Work/Run terminal veto.

Therefore this audit freezes:

```text
unbound blocking Q
    != global terminal veto
```

A future implementation MUST NOT add a blanket rule such as:

```text
any open blocking ReviewObligation
    -> CompletionAuthority denied
```

Such a rule would collapse two authorities without proving applicability.

### If terminal governance applicability is ever required

It must be explicit. A future contract would need to establish something equivalent to:

```text
Work / Run terminal claim
    + exact ReviewObligation / governed target relation
    + compatible context / scope / version
    -> TerminalGovernanceRequirement
```

Only then may an unresolved Q become a terminal prerequisite.

Even in that case, ordinary `EvidenceArtifact` coverage is not Q-discharge authority. String equality between a terminal proof obligation and a `ReviewObligation.id` cannot substitute for the existing governance chain:

```text
ReviewObligation
    -> GovernanceDecision
    -> GovernedApplication
    -> review discharge / governed application fact
```

So the future rule, if product evidence requires it, is:

```text
explicit terminal-governance applicability
    + unresolved Q
    -> terminal fail closed

verification proof that merely names the Q
    != Q discharge
```

This is a conditional future seam, not a current production requirement.

## Audit finding B: current recovery remains execution-level

`dispatch_recovery_mode()` classifies a committed attempt as:

```text
idempotent-retry
reconcile
unknown
```

That classification is not itself recovery authority.

`RealityBoundary.reconcile()` calls the provider's reconciliation operation and returns a `CapabilityResult`. `Runtime.reconcile()` may mark a Step `unknown`, or return an execution-level reconciliation result. Neither path creates a verified `Outcome`, discharges governance, or authorizes terminal completion.

This is the correct non-shortcut behavior, but it exposes the actual B4 capability gap: there is no durable recovery-observation / recovery-judgment / recovery-application chain.

A provider reconciliation result is currently transient execution information:

```text
provider reconcile result
    != durable objective fact
    != recovery decision
    != recovery application
```

If F1-B4 production is later authorized, the default direction should therefore be recovery closure, not terminal-authority redesign.

## Candidate future recovery responsibility chain

This audit freezes only the responsibility shape, not production APIs:

```text
InvocationDispatchCommitted / ambiguous execution
        ↓
reconciliation or independent observation
        ↓
durable RecoveryObservation
        ↓
objective verification where required
        ↓
confirmed Outcome or explicit unresolved/unknown fact
        ↓
RecoveryDisposition
        ↓
RecoveryApplication
```

Required non-substitutions:

```text
reconcile status=succeeded
    != confirmed Outcome

confirmed Outcome(fail)
    != retry decision

RecoveryDisposition
    != RecoveryApplication

blocking Q
    != recovery decision
```

The exact production model is intentionally left open.

## CompletionAuthority decision gate

Current evidence does NOT justify changing `CompletionAuthority` merely because B3 can open a blocking Q.

The terminal side is classified as:

```text
terminal redesign
    NOT REQUIRED BY CURRENT EVIDENCE
```

A terminal-governance extension may only be reopened by a concrete counterexample showing all of the following:

1. an explicit terminal claim is bound to an exact governance obligation;
2. the obligation remains unresolved under the existing Decision/Application chain;
3. `CompletionAuthority` can nevertheless make a terminal claim that the product contract says must be forbidden;
4. the defect cannot be expressed by existing Work verification/revalidation obligations without confusing evidence coverage with governance discharge.

Until then, open Q and terminal authority remain independent responsibilities.

## Recovery decision gate

The audit does identify a real missing capability if the runtime intends to turn reconciliation into durable recovery decisions:

```text
reconciliation observation
    -> no durable recovery authority object today
```

So a later F1-B4 production phase, if authorized, should begin with a durable recovery observation boundary. It must not begin by modifying CompletionAuthority or by making provider reconciliation authoritative.

## Strict design locks

Required-green locks preserve current responsibility separation:

- B4-001: confirmed pass does not complete Work/Run.
- B4-002: confirmed fail does not create recovery action.
- B4-003: opening a blocking Q does not itself mutate terminal/recovery state.
- B4-004: provider reconciliation result remains non-objective and non-terminal.
- B4-005: `CompletionAuthority` does not read governance Q state, and `Runtime.reconcile()` does not own objective/terminal authority.
- B4-006: an unbound blocking Q is not a global terminal veto.
- B4-007: a revalidation-class proof may cover a Work proof obligation but does not discharge an open governance Q.

Strict-xfail future seams intentionally remain unimplemented:

- B4-A01: explicit terminal-governance applicability and unresolved-Q fail-closed semantics.
- B4-A02: durable recovery observation before recovery judgment.
- B4-A03: recovery disposition/application separation.

An XPASS must be treated as a semantic change and graduated explicitly; it must not be hidden by weakening strict mode.

## Stop condition

F1-B4 design freeze stops here:

```text
F1-B3 baseline
25d834a174a5e884afcef532d3e5c3bd4f000107
        ↓
F1-B4 design/counterexample audit
        ↓
STOP

no B3-P4
no recovery production
no CompletionAuthority rewrite
no governance discharge changes
no qualification/activation/reopen changes
```
