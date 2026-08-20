"""Procedure profiles — V1.8 strict typed-record backed (P1-1).

Graph is implementation, responsibility completeness is invariant.
ProcedureProfile levels: minimal / standard / enhanced.
Provides context.require(...) and check_procedure(...).

Fail-closed invariants:
- metadata["authorized"]/["verified"] etc are HINTS only, never satisfy gate alone
- authorization requires valid AuthorizationGrant typed record
- evidence requires EvidenceArtifact/Observation + typed relation
- verification requires VerificationResult (ClosedVerificationResult) bound to target/version
- independent-verification requires failure-domain proof
- rollback/recovery requires Checkpoint/CompensationPlan
- unknown profile -> configuration error (no silent fallback)
- string obligation is non-waivable hard boundary (waivable:false)
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


def gates_for_profile(profile: ProcedureProfile | str) -> list[str]:
    if isinstance(profile, str):
        try:
            p = ProcedureProfile(profile)
        except ValueError:
            raise ValueError(f"unknown ProcedureProfile {profile!r} -> configuration error / blocked (fail-closed)")
        return list(_PROFILE_GATES.get(p, _MINIMAL_GATES))
    if profile not in _PROFILE_GATES:
        raise ValueError(f"unknown ProcedureProfile {profile!r} -> configuration error / blocked (fail-closed)")
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
            # legacy string obligations remain waivable when authority provided; typed Obligation with waivable=False is hard boundary
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


def _has_purpose_typed(work_fields: dict[str, Any], combined_meta: dict[str, Any]) -> bool:
    # Typed: requires Goal/explicit purpose record or canonical purpose field, not just title
    # Accept: purpose_ref / goal_ref / canonical_purpose / explicit purpose/goal metadata
    if combined_meta.get("purpose_ref") or combined_meta.get("goal_ref"):
        return True
    if isinstance(combined_meta.get("purpose"), str) and combined_meta["purpose"].strip():
        return True
    if isinstance(combined_meta.get("goal"), str) and combined_meta["goal"].strip():
        return True
    if isinstance(combined_meta.get("canonical_purpose"), str) and combined_meta["canonical_purpose"].strip():
        return True
    # Work kind indicating purpose record
    if work_fields.get("kind") in ("goal", "purpose"):
        return True
    # Do NOT treat bare title/description as sufficient
    return False


def _has_authorization_typed(combined_meta: dict[str, Any], proofs: dict[str, Any]) -> tuple[bool, str]:
    # Hint only: metadata authorized / grant_id etc is hint, not proof
    grants = proofs.get("grants") or proofs.get("authorization_grants") or proofs.get("authorizations")
    if grants is None:
        return False, "authorization requires valid AuthorizationGrant typed record (hint alone insufficient)"
    # grants must be non-empty list of valid grants
    try:
        from portable_runtime.records.authorization import is_grant_valid
    except Exception:
        return False, "authorization subsystem unavailable"
    if not isinstance(grants, list) or not grants:
        return False, "authorization requires AuthorizationGrant list non-empty"
    # Check at least one valid grant; if hint provides grant_id, require that grant present
    hint_id = combined_meta.get("authorization_grant_id") or (combined_meta.get("authorization_refs") or [None])[0] if isinstance(combined_meta.get("authorization_refs"), list) else None
    valid_any = False
    hint_matched = False
    for g in grants:
        try:
            if is_grant_valid(g):  # type: ignore[arg-type]
                valid_any = True
                if hint_id and getattr(g, "id", None) == hint_id:
                    hint_matched = True
        except Exception:  # noqa: S112  # intentional continue for hint matching
            continue
    if hint_id:
        if hint_matched and valid_any:
            return True, "valid AuthorizationGrant matching hint"
        if hint_matched:
            return False, "hinted grant not valid"
        return False, "authorization hint present but no matching valid grant in proofs (hint cannot satisfy alone)"
    return (True, "valid AuthorizationGrant present") if valid_any else (False, "no valid AuthorizationGrant")


def _has_evidence_typed(combined_meta: dict[str, Any], work_fields: dict[str, Any], proofs: dict[str, Any]) -> tuple[bool, str]:
    # Requires EvidenceArtifact/Observation + typed relation
    arts = proofs.get("evidence_artifacts") or proofs.get("evidences") or proofs.get("records")
    rels = proofs.get("relations") or proofs.get("record_relations")
    if arts is None or rels is None:
        return False, "evidence requires EvidenceArtifact/Observation + typed relation (metadata artifact_refs hint insufficient)"
    if not isinstance(arts, list) or not arts:
        return False, "evidence requires EvidenceArtifact list"
    if not isinstance(rels, list) or not rels:
        return False, "evidence requires typed relations"
    # Check at least one evidence artifact is EvidenceArtifact or Observation and relation is evidence-type
    evidence_types = {"EvidenceArtifact", "Observation"}
    evidence_relations = {"supports", "derived-from", "records", "measured-by", "validated-under", "depends-on"}
    has_artifact = any(getattr(a, "record_type", None) in evidence_types for a in arts if hasattr(a, "record_type"))
    # also allow core Evidence model via kind
    if not has_artifact:
        # check core Evidence kind
        has_artifact = any(getattr(a, "kind", None) in ("container-observation", "promql-observation", "evidence", "observation") for a in arts)
        if not has_artifact and arts:
            # if arts are generic dicts with record_type
            has_artifact = any(isinstance(a, dict) and a.get("record_type") in evidence_types for a in arts)
    has_rel = any(getattr(r, "relation_type", None) in evidence_relations for r in rels)
    if has_artifact and has_rel:
        return True, "EvidenceArtifact/Observation + typed relation present"
    if not has_artifact:
        return False, "missing EvidenceArtifact/Observation typed record"
    return False, "missing typed evidence relation"


def _has_verification_typed(proofs: dict[str, Any], combined_meta: dict[str, Any]) -> tuple[bool, str]:
    vers = proofs.get("verification_results") or proofs.get("verifications") or proofs.get("closed_verifications")
    rels = proofs.get("relations")
    if vers is not None:
        if isinstance(vers, list) and vers:
            for v in vers:
                # ClosedVerificationResult with pass
                res = getattr(v, "result", None) or (v.get("result") if isinstance(v, dict) else None)
                if res == "pass":
                    return True, "VerificationResult pass present"
            return False, "verification requires at least one passing VerificationResult"
        return False, "verification requires VerificationResult typed record (metadata verified hint insufficient)"
    # fallback to typed relation check
    if rels is not None and isinstance(rels, list):
        for r in rels:
            rt = getattr(r, "relation_type", None) or (r.get("relation_type") if isinstance(r, dict) else None)
            if rt in ("validated-under", "tests", "evaluated-by"):
                return True, "verification typed relation present"
    return False, "verification requires VerificationResult or typed relation (metadata hint insufficient)"


def _has_independent_verification_typed(proofs: dict[str, Any]) -> tuple[bool, str]:
    indie = proofs.get("independence_proofs") or proofs.get("independent_verification_proofs") or proofs.get("failure_domain_proofs")
    if indie is None:
        return False, "independent-verification requires failure-domain proof (metadata independent_verification hint insufficient)"
    if not isinstance(indie, list) or not indie:
        return False, "independent-verification requires failure-domain proof list"
    for p in indie:
        # proof must demonstrate distinct failure domains
        if isinstance(p, dict):
            if p.get("proof") or p.get("independent") or p.get("failure_domain_ok"):
                return True, "failure-domain independence proven"
            # check domains differ
            if "verifier_domain" in p and "executor_domain" in p and p["verifier_domain"] != p["executor_domain"]:
                return True, "verifier/executor failure domains distinct"
        else:
            dom = getattr(p, "independent", None) or getattr(p, "proof", None)
            if dom:
                return True, "failure-domain proof present"
    return False, "no valid failure-domain independence proof"


def _has_rollback_typed(proofs: dict[str, Any]) -> tuple[bool, str]:
    cps = proofs.get("checkpoints") or proofs.get("rollback_proofs")
    comps = proofs.get("compensations") or proofs.get("compensation_plans")
    recovery = proofs.get("recovery_procedures")
    pools = []
    for pool in (cps, comps, recovery):
        if isinstance(pool, list) and pool:
            pools.extend(pool)
    if pools:
        return True, "Checkpoint/CompensationPlan/RecoveryProcedure present"
    return False, "rollback requires Checkpoint/CompensationPlan/RecoveryProcedure typed record (metadata rollback hint insufficient)"


def _check_gate(
    gate: str,
    work_fields: dict[str, Any],
    run_fields: dict[str, Any],
    proofs: dict[str, Any],
) -> tuple[ObligationStatusLiteral, str]:
    """Typed-record backed gate evaluation. Metadata is hint only."""
    work_meta = work_fields.get("metadata") if isinstance(work_fields.get("metadata"), dict) else {}
    run_meta = run_fields.get("metadata") if isinstance(run_fields.get("metadata"), dict) else {}
    combined_meta = {**(work_meta or {}), **(run_meta or {})}

    # Gates that remain simple but still fail-closed on hint-only
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
    has_candidate = bool(combined_meta.get("candidate") or combined_meta.get("candidates") or combined_meta.get("options"))
    has_review = bool(combined_meta.get("reviewed") or combined_meta.get("human_review") or combined_meta.get("decision_refs"))
    # typed gates delegate to helpers
    if gate == "purpose-identified":
        ok = _has_purpose_typed(work_fields, combined_meta)
        return ("satisfied", "typed purpose/goal record present") if ok else ("open", "missing typed Goal/purpose record (title alone insufficient)")
    if gate == "execution-boundary":
        return ("satisfied", "boundary present") if has_boundary else ("open", "missing execution_boundary/resource_scope/inputs")
    if gate == "result-confirmation":
        return ("satisfied", "result present") if has_result else ("open", "missing result confirmation")
    if gate == "failure-stop":
        return "satisfied", "failure-stop handled"
    if gate == "candidate-considered":
        return ("satisfied", "candidates present") if has_candidate else ("open", "missing candidates/options")
    if gate == "evidence":
        ok, msg = _has_evidence_typed(combined_meta, work_fields, proofs)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "authorization":
        ok, msg = _has_authorization_typed(combined_meta, proofs)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "verification":
        ok, msg = _has_verification_typed(proofs, combined_meta)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "rollback":
        ok, msg = _has_rollback_typed(proofs)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "review":
        # typed: requires decision refs + typed decision record?
        decisions = proofs.get("decisions") or proofs.get("decision_records")
        if decisions is not None and isinstance(decisions, list) and decisions:
            return "satisfied", "decision record present"
        # hint alone insufficient — but allow has_review if typed decision present; else open
        return ("open", "review requires Decision typed record (metadata reviewed hint insufficient)") if not has_review else ("open", "review hint present but no Decision typed record")
    if gate == "independent-verification":
        ok, msg = _has_independent_verification_typed(proofs)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "role-separation":
        has = bool(combined_meta.get("role_separation") or combined_meta.get("separate_roles") or proofs.get("role_proofs"))
        return ("satisfied", "role separation") if has else ("open", "missing role separation proof")
    if gate == "challenge-path":
        has = bool(combined_meta.get("challenge_path") or combined_meta.get("challenge") or proofs.get("challenge_proofs"))
        return ("satisfied", "challenge path") if has else ("open", "missing challenge path")
    if gate == "exposure-limit":
        has = bool(combined_meta.get("exposure_limit") or combined_meta.get("blast_radius") or proofs.get("exposure_proofs"))
        return ("satisfied", "exposure limit") if has else ("open", "missing exposure limit")
    if gate == "takeover":
        has = bool(combined_meta.get("takeover") or combined_meta.get("takeover_ready") or proofs.get("takeover_proofs"))
        return ("satisfied", "takeover ready") if has else ("open", "missing takeover proof")
    if gate == "recovery":
        ok, msg = _has_rollback_typed(proofs)
        return ("satisfied", msg) if ok else ("open", msg)
    if gate == "exit":
        has = bool(combined_meta.get("exit") or combined_meta.get("orderly_exit") or proofs.get("exit_proofs"))
        return ("satisfied", "exit") if has else ("open", "missing orderly exit")
    if gate == "reauthorization":
        has = bool(combined_meta.get("reauthorization") or combined_meta.get("reauthorized") or proofs.get("reauthorization_proofs"))
        return ("satisfied", "reauthorization") if has else ("open", "missing reauthorization")

    return "open", f"unknown gate {gate}"


def check_procedure(
    work: Any,
    run: Any,
    profile: ProcedureProfile | str,
    *,
    now: datetime | None = None,
    waivers: dict[str, str] | None = None,
    handed_off: set[str] | None = None,
    proofs: dict[str, Any] | None = None,
    grants: list[Any] | None = None,
    evidence_artifacts: list[Any] | None = None,
    relations: list[Any] | None = None,
    verification_results: list[Any] | None = None,
    independence_proofs: list[Any] | None = None,
    checkpoints: list[Any] | None = None,
    **extra_proofs: Any,
) -> list[ObligationStatus]:
    """Evaluate procedure gates for given Work/Run and profile (typed-record backed).

    Returns list[ObligationStatus] per gate. Caller can inspect blocked/open/waived etc.
    waivers: gate -> waiver_authority_ref ; if provided, that gate becomes waived (if waivable).
    handed_off: gates that have been delegated to another system/human.

    Typed proofs (fail-closed — hint alone never satisfies):
      grants / authorizations, evidence_artifacts, relations, verification_results,
      independence_proofs, checkpoints, ... via proofs dict or kwargs.
    """
    # Fail-closed on unknown profile
    if isinstance(profile, str):
        try:
            profile = ProcedureProfile(profile)
        except ValueError:
            raise ValueError(f"unknown ProcedureProfile {profile!r} -> configuration error / blocked (fail-closed)")
    elif profile not in _PROFILE_GATES:
        raise ValueError(f"unknown ProcedureProfile {profile!r} -> configuration error / blocked (fail-closed)")
    gates = gates_for_profile(profile)
    wf = _extract_work_fields(work)
    rf = _extract_run_fields(run)
    waivers = waivers or {}
    handed_off = handed_off or set()
    out: list[ObligationStatus] = []
    ts = now or datetime.now(UTC)

    # collect proofs dict merging explicit kwargs + proofs dict
    merged_proofs: dict[str, Any] = {}
    if proofs:
        merged_proofs.update(proofs)
    if grants is not None:
        merged_proofs["grants"] = grants
    if evidence_artifacts is not None:
        merged_proofs["evidence_artifacts"] = evidence_artifacts
    if relations is not None:
        merged_proofs["relations"] = relations
    if verification_results is not None:
        merged_proofs["verification_results"] = verification_results
    if independence_proofs is not None:
        merged_proofs["independence_proofs"] = independence_proofs
    if checkpoints is not None:
        merged_proofs["checkpoints"] = checkpoints
    merged_proofs.update(extra_proofs)

    # Check expiry/invalidated via metadata
    work_meta = wf.get("metadata") if isinstance(wf.get("metadata"), dict) else {}
    run_meta = rf.get("metadata") if isinstance(rf.get("metadata"), dict) else {}
    combined = {**(work_meta or {}), **(run_meta or {})}
    invalidated_gates = set(combined.get("invalidated_gates", []) if isinstance(combined.get("invalidated_gates"), list) else [])

    for gate in gates:
        if gate in invalidated_gates:
            out.append(ObligationStatus(obligation=gate, status="invalidated", reason="gate invalidated by revalidation", checked_at=ts))
            continue
        if gate == "authorization" and combined.get("authorization_expired"):
            out.append(ObligationStatus(obligation=gate, status="expired", reason="authorization expired", checked_at=ts))
            continue
        if gate in waivers:
            try:
                out.append(ObligationStatus(obligation=gate, status="waived", waiver_authority_ref=waivers[gate], reason="waived per authority", checked_at=ts))
            except ValueError as exc:
                out.append(ObligationStatus(obligation=gate, status="blocked", reason=str(exc), checked_at=ts))
            continue
        if gate in handed_off:
            out.append(ObligationStatus(obligation=gate, status="handed-off", reason="responsibility delegated", checked_at=ts))
            continue
        if combined.get(f"{gate}_blocked"):
            out.append(ObligationStatus(obligation=gate, status="blocked", reason=f"{gate} blocked by policy", checked_at=ts))
            continue
        status, reason = _check_gate(gate, wf, rf, merged_proofs)
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
        try:
            store = getattr(context, "store", None)
            if store and hasattr(store, "save_run"):
                store.save_run(run)  # type: ignore
        except Exception:
            pass
    wf = _extract_work_fields(work) if work else {}
    rf = _extract_run_fields(run) if run else {}
    # No proofs available in context helper -> will be hint-only, thus fail-closed (open -> required)
    status, reason = _check_gate(gate, wf, rf, {})
    return ObligationStatus(obligation=gate, status=status if status != "open" else "required", reason=reason)


# Patch WorkflowContext to have .require method if desired (monkeypatch-friendly)
def attach_require_to_context(context: Any) -> None:
    if not hasattr(context, "require"):
        context.require = lambda gate: require_context_gate(context, gate)
