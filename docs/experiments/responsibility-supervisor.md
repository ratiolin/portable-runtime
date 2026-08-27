# Responsibility Supervisor experiment

Status: **experimental / non-canonical / non-authority-bearing**.

`ResponsibilitySupervisor` is the coordination layer for the persistent-responsibility experiment. It is intentionally not an `AgentLoop`: it does not own external facts, decide what is true, or mint effect authority. It preserves ordering between responsibility positions that other providers may fill.

```text
StandingResponsibility
  -> SituationAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> Commitment
  -> Work
  -> bounded ResourceConsumption
  -> completion
  -> StandingResponsibility remains active
```

The supervisor currently enforces three additional experimental invariants:

1. A `WorkProposal` cannot be registered unless its referenced `SituationAssessment` has already been registered under the same standing responsibility. This prevents an event/trigger from silently becoming committed work.
2. Resource consumption is accumulated against the exact `Commitment` allocation. A budget grants resource use only; it does not grant permission for an external effect.
3. Completing bounded Work does not discharge the standing responsibility. Discharge remains an explicit, separate lifecycle operation.

The supervisor can also register a missing expected signal through the existing `ExpectedSignal -> SituationAssessment` path. A missing event becomes meaningful only because an explicit expectation existed first.

This layer should remain outside the canonical package until at least two independent domains demonstrate that these responsibility positions cannot be safely collapsed.
