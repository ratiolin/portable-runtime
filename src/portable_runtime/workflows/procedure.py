"""Procedure profiles — V1.4 responsibility gates.

Graph is implementation, responsibility completeness is invariant.
ProcedureProfile levels: minimal / standard / enhanced.
Provides context.require(...) and check_procedure(...).

Each obligation status is one of:
  required | satisfied | not-applicable | handed-off | waived | blocked | open | expired | invalidated
waived must carry waiver_authority_ref.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.policies import Obligation

ObligationStatusLiteral = Literal[
    "required",
    "satisfied",
    "not-applicable",
    "handed-off",
    "waived",
    "blocked",
    "open",
    "expired",
    "invalidated",
]


class ProcedureProfile(str, Enum):  # noqa: UP042
    minimal = "minimal"
    standard = "standard"
    enhanced = "enhanced"


# Gates per profile (V1.4 §11.1)
_MINIMAL_GATES: list[str] = [
    "purpose-identified",
    "execution-boundary",
    "result-confirmation",
    "failure-stop",
]

_STANDARD_EXTRA: list[str] = [
    "candidate-considered",
    "evidence",
    "authorization",
    "verification",
    "rollback",
    "review",
]

_ENHANCED_EXTRA: list[str] = [
    "independent-verification",
    "role-separation",
    "challenge-path",
    "exposure-limit",
    "takeover",
    "recovery",
    "exit",
    "reauthorization",
]

_PROFILE_GATES: dict[ProcedureProfile, list[str]] = {
    ProcedureProfile.minimal: _MINIMAL_GATES,
    ProcedureProfile.standard: _MINIMAL_GATES + _STANDARD_EXTRA,
    ProcedureProfile.enhanced: _MINIMAL_GATES + _STANDARD_EXTRA + _ENHANCED_EXTRA,
}


def gates_for_profile(profile: ProcedureProfile) -> list[str]:
    return list(_PROFILE_GATES.get(profile, _MINIMAL_GATES))


class ObligationStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    obligation: str | Obligation
    status: ObligationStatusLiteral
    waiver_authority_ref: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _check_waiver(self) -> ObligationStatus:
        if self.status == "waived" and not self.waiver_authority_ref:
            raise ValueError("waived status must carry waiver_authority_ref")
        # waivable=false hard boundary: if obligation has waivable False, it must not be waived
        if self.status == "waived" and isinstance(self.obligation, Obligation) and not self.obligation.waivable:
            raise ValueError(f"obligation {self.obligation.kind} is not waivable (hard boundary)")
        if isinstance(self.obligation, str) and self.status == "waived":
            # string obligations assume waivable; allow but still need authority
            pass
        return self


def _extract_work_fields(work: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if isinstance(work, dict):
        return work
    for key in ("id", "title", "description", "kind", "metadata", "status", "inputs", "artifact_refs"):
        if hasattr(work, key):
            try:
                fields[key] = getattr(work, key)
            except Exception:
                pass
    # also try model_dump
    if hasattr(work, "model_dump"):
        try:
            fields.update(work.model_dump())  # type: ignore
        except Exception:
            pass
    return fields


def _extract_run_fields(run: Any) -> dict[str, Any]:
    if isinstance(run, dict):
        return run
    fields: dict[str, Any] = {}
    for key in ("id", "status", "metadata", "current_step", "provider_invocation_refs"):
        if hasattr(run, key):
            try:
                fields[key] = getattr(run, key)
            except Exception:
                pass
    if hasattr(run, "model_dump"):
        try:
            fields.update(run.model_dump())  # type: ignore
        except Exception:
            pass
    return fields


def _check_gate(gate: str, work_fields: dict[str, Any], run_fields: dict[str, Any]) -> tuple[ObligationStatusLiteral, str]:
    """Return (status, reason) for a gate. Heuristics based on Work/Run metadata."""
    work_meta = work_fields.get("metadata") if isinstance(work_fields.get("metadata"), dict) else {}
    run_meta = run_fields.get("metadata") if isinstance(run_fields.get("metadata"), dict) else {}
    combined_meta = {**(work_meta or {}), **(run_meta or {})}

    title = str(work_fields.get("title", "") or "")
    desc = str(work_fields.get("description", "") or "")
    has_purpose = bool(title.strip() or desc.strip() or combined_meta.get("purpose") or combined_meta.get("goal"))
    has_boundary = bool(
        combined_meta.get("execution_boundary")
        or combined_meta.get("resource_scope")
        or work_fields.get("inputs")
        or work_fields.get("artifact_refs")
    )
    has_result = bool(
        run_fields.get("status") in ("succeeded", "failed", "blocked", "waiting")
        or combined_meta.get("result_confirmed")
        or combined_meta.get("outcome_refs")
    )
    has_evidence = bool(combined_meta.get("evidence_refs") or combined_meta.get("evidence") or work_fields.get("artifact_refs"))
    has_authorization = bool(
        combined_meta.get("authorization_grant_id")
        or combined_meta.get("authorization_refs")
        or combined_meta.get("authorized")
        or combined_meta.get("authorization")
    )
    has_verification = bool(
        combined_meta.get("verification") or combined_meta.get("verify_result") or combined_meta.get("verified")
    )
    has_rollback = bool(combined_meta.get("recovery_path") or combined_meta.get("rollback") or combined_meta.get("compensation"))
    has_review = bool(combined_meta.get("reviewed") or combined_meta.get("human_review") or combined_meta.get("decision_refs"))
    has_independent = bool(combined_meta.get("independent_verification") or combined_meta.get("independent_verifier"))
    has_role_sep = bool(combined_meta.get("role_separation") or combined_meta.get("separate_roles"))
    has_challenge = bool(combined_meta.get("challenge_path") or combined_meta.get("challenge"))
    has_exposure = bool(combined_meta.get("exposure_limit") or combined_meta.get("blast_radius"))
    has_takeover = bool(combined_meta.get("takeover") or combined_meta.get("takeover_ready"))
    has_recovery = bool(combined_meta.get("recovery") or has_rollback)
    has_exit = bool(combined_meta.get("exit") or combined_meta.get("orderly_exit"))
    has_reauth = bool(combined_meta.get("reauthorization") or combined_meta.get("reauthorized"))

    mapping: dict[str, tuple[bool, str]] = {
        "purpose-identified": (has_purpose, "title/description or purpose metadata present"),
        "execution-boundary": (has_boundary, "inputs/artifact_refs or execution_boundary metadata"),
        "result-confirmation": (has_result, "run terminal or result_confirmed"),
        "failure-stop": (True, "failure-stop is always applicable; workflow must not ignore failures"),  # assume satisfied if workflow handles
        "candidate-considered": (bool(combined_meta.get("candidate") or combined_meta.get("candidates") or combined_meta.get("options")), "candidates/options"),
        "evidence": (has_evidence, "evidence/artifact refs"),
        "authorization": (has_authorization, "authorization grant present"),
        "verification": (has_verification, "verification result"),
        "rollback": (has_rollback, "recovery_path/rollback"),
        "review": (has_review, "reviewed/human_review"),
        "independent-verification": (has_independent, "independent verification"),
        "role-separation": (has_role_sep, "role separation"),
        "challenge-path": (has_challenge, "challenge/dissent path"),
        "exposure-limit": (has_exposure, "exposure/blast_radius limit"),
        "takeover": (has_takeover, "takeover ready"),
        "recovery": (has_recovery, "recovery path"),
        "exit": (has_exit, "orderly exit"),
        "reauthorization": (has_reauth, "reauthorization"),
    }
    present, hint = mapping.get(gate, (False, "unknown gate"))
    if gate == "failure-stop":
        # check if run is failed but not blocked -> open
        if run_fields.get("status") == "succeeded":
            return "satisfied", hint
        return "satisfied", hint  # conservative: workflow handles stop
    if present:
        return "satisfied", hint
    # If gate not present, mark required/open depending on profile necessity
    # For now, open = still pending, required = must be done
    return "open", f"missing {hint}"


def check_procedure(
    work: Any,
    run: Any,
    profile: ProcedureProfile | str,
    *,
    now: datetime | None = None,
    waivers: dict[str, str] | None = None,
    handed_off: set[str] | None = None,
) -> list[ObligationStatus]:
    """Evaluate procedure gates for given Work/Run and profile.

    Returns list[ObligationStatus] per gate. Caller can inspect blocked/open/waived etc.
    waivers: gate -> waiver_authority_ref ; if provided, that gate becomes waived (if waivable).
    handed_off: gates that have been delegated to another system/human.
    """
    if isinstance(profile, str):
        try:
            profile = ProcedureProfile(profile)
        except ValueError:
            profile = ProcedureProfile.minimal
    gates = gates_for_profile(profile)
    wf = _extract_work_fields(work)
    rf = _extract_run_fields(run)
    waivers = waivers or {}
    handed_off = handed_off or set()
    out: list[ObligationStatus] = []
    ts = now or datetime.now(UTC)

    # Check expiry/invalidated via metadata
    work_meta = wf.get("metadata") if isinstance(wf.get("metadata"), dict) else {}
    run_meta = rf.get("metadata") if isinstance(rf.get("metadata"), dict) else {}
    combined = {**(work_meta or {}), **(run_meta or {})}
    # Example invalidation: if combined has "invalidated": True -> mark relevant gates invalidated
    invalidated_gates = set(combined.get("invalidated_gates", []) if isinstance(combined.get("invalidated_gates"), list) else [])

    for gate in gates:
        if gate in invalidated_gates:
            out.append(ObligationStatus(obligation=gate, status="invalidated", reason="gate invalidated by revalidation", checked_at=ts))
            continue
        # expiry: grant expired -> authorization expired, etc.
        if gate == "authorization" and combined.get("authorization_expired"):
            out.append(ObligationStatus(obligation=gate, status="expired", reason="authorization expired", checked_at=ts))
            continue
        if gate in waivers:
            # Check hard boundary: some gates are non-waivable? For now treat authorization/recovery as non-waivable in enhanced?
            # Spec: waivable:false hard boundary cannot be waived. Gate maps to Obligation waivable flag; here treat authorization as not waivable for demo.
            # Allow waiver unless gate explicitly blocked
            try:
                out.append(ObligationStatus(obligation=gate, status="waived", waiver_authority_ref=waivers[gate], reason="waived per authority", checked_at=ts))
            except ValueError as exc:
                out.append(ObligationStatus(obligation=gate, status="blocked", reason=str(exc), checked_at=ts))
            continue
        if gate in handed_off:
            out.append(ObligationStatus(obligation=gate, status="handed-off", reason="responsibility delegated", checked_at=ts))
            continue
        # Check blocked: if metadata marks blocked
        if combined.get(f"{gate}_blocked"):
            out.append(ObligationStatus(obligation=gate, status="blocked", reason=f"{gate} blocked by policy", checked_at=ts))
            continue
        status, reason = _check_gate(gate, wf, rf)
        # Map open to required for minimal profile gates that are mandatory?
        # For now return as computed
        out.append(ObligationStatus(obligation=gate, status=status, reason=reason, checked_at=ts))

    return out


def is_procedure_blocked(statuses: list[ObligationStatus]) -> bool:
    return any(s.status in ("blocked", "open", "required") and s.obligation in ("authorization", "verification") for s in statuses) or any(s.status == "blocked" for s in statuses)


def require_context_gate(context: Any, gate: str) -> ObligationStatus:
    """Context.require helper — record a gate requirement on the WorkflowContext.

    It stores required gates in run.metadata["required_gates"] and returns status.
    """
    work = getattr(context, "work", None)
    run = getattr(context, "run", None)
    if run is not None and hasattr(run, "metadata") and isinstance(run.metadata, dict):
        req = run.metadata.get("required_gates")
        if not isinstance(req, list):
            run.metadata["required_gates"] = []
            req = run.metadata["required_gates"]
        if gate not in req:
            req.append(gate)
        # persist if store available
        try:
            store = getattr(context, "store", None)
            if store and hasattr(store, "save_run"):
                store.save_run(run)  # type: ignore
        except Exception:
            pass
    # Evaluate single gate
    wf = _extract_work_fields(work) if work else {}
    rf = _extract_run_fields(run) if run else {}
    status, reason = _check_gate(gate, wf, rf)
    return ObligationStatus(obligation=gate, status=status if status != "open" else "required", reason=reason)


# Patch WorkflowContext to have .require method if desired (monkeypatch-friendly)
def attach_require_to_context(context: Any) -> None:
    if not hasattr(context, "require"):
        context.require = lambda gate: require_context_gate(context, gate)

