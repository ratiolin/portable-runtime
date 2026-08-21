"""Authoritative qualification provenance for the RealityBoundary.

The workflow/request metadata boundary carries references only.  Qualification
facts (authorization grants, evidence, relations, procedure proofs and
verification results) are resolved from the configured state store into one
immutable, deep-copied assessment snapshot.  The boundary can then compare the
snapshot digest immediately before creating an execution permit, preventing a
checker from evaluating one set of facts while the provider is invoked with a
different set.

This module deliberately does not introduce a new semantic record type.  A
stored ``BaseRecord`` may carry a small ``metadata.qualification_kind`` marker
for procedure-specific facts; the semantic record remains owned by the
existing Control Plane model.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualificationResolutionError(ValueError):
    """A qualification reference cannot be trusted for this invocation."""


class QualificationRef(BaseModel):
    """Reference crossing the request/work metadata boundary.

    ``version`` is optional for immutable/non-versioned runtime objects.  When
    supplied, the referenced object must expose the same version in its
    canonical field or metadata.  ``kind`` is an optional type discriminator
    used to avoid resolving an evidence id as an authorization grant.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_id: str = Field(min_length=1, alias="id")
    kind: str | None = None
    version: int | str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> QualificationRef:
        if not self.ref_id.strip():
            raise ValueError("qualification reference id must be non-empty")
        if self.kind is not None and not self.kind.strip():
            raise ValueError("qualification reference kind must be non-empty")
        return self

    @classmethod
    def parse(cls, value: Any, *, default_kind: str | None = None) -> QualificationRef:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(id=value, kind=default_kind)
        if isinstance(value, dict):
            raw = dict(value)
            if "ref_id" in raw and "id" not in raw:
                raw["id"] = raw.pop("ref_id")
            if "ref" in raw and "id" not in raw:
                raw["id"] = raw.pop("ref")
            if "record_id" in raw and "id" not in raw:
                raw["id"] = raw.pop("record_id")
            raw.setdefault("kind", default_kind)
            try:
                return cls.model_validate(raw)
            except Exception as exc:  # noqa: BLE001
                raise QualificationResolutionError(f"invalid qualification reference: {exc}") from exc
        raise QualificationResolutionError(
            "qualification metadata must contain string refs or {id, kind?, version?} descriptors"
        )


@dataclass(frozen=True)
class InvocationPermit:
    """One-use internal capability bound to an immutable request snapshot.

    The provider-facing request is materialized from ``request_snapshot``;
    precommit and invocation must not continue consuming a mutable caller
    object after this permit is issued.
    """

    request_digest: str
    qualification_digest: str
    provider_id: str
    lease_generation: int
    request_snapshot: str
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def issue(
        cls,
        request: Any,
        *,
        provider_id: str,
        qualification_digest: str,
        lease_generation: int,
    ) -> InvocationPermit:
        request_payload = (
            request.model_dump(mode="json")
            if hasattr(request, "model_dump")
            else dict(request)
        )
        authority_payload = {
            "request_id": request_payload.get("id"),
            "capability": request_payload.get("capability"),
            "actor": request_payload.get("actor_ref"),
            "resource": request_payload.get("resource_ref"),
            "subject_version_refs": list(request_payload.get("subject_version_refs") or []),
            "effect_class": request_payload.get("effect_class"),
            "constraints": request_payload.get("constraints") or {},
            "provider": provider_id,
            "lease_generation": lease_generation,
            "idempotency_key": request_payload.get("idempotency_key"),
            "qualification_digest": qualification_digest,
        }
        snapshot_payload = {
            "request": request_payload,
            "authority": authority_payload,
        }
        snapshot = json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(snapshot.encode()).hexdigest()
        return cls(
            request_digest=digest,
            qualification_digest=qualification_digest,
            provider_id=provider_id,
            lease_generation=lease_generation,
            request_snapshot=snapshot,
        )

    def snapshot_payload(self) -> dict[str, Any]:
        value = json.loads(self.request_snapshot)
        if not isinstance(value, dict) or not isinstance(value.get("request"), dict):
            raise QualificationResolutionError("invocation permit contains an invalid request snapshot")
        return value

    def materialize_request(self) -> Any:
        """Return a fresh provider-facing request reconstructed from the permit."""

        from portable_runtime.core.capabilities import CapabilityRequest

        return CapabilityRequest.model_validate(self.snapshot_payload()["request"])


_INLINE_FACT_KEYS = frozenset(
    {
        "procedure_proofs",
        "obligation_proofs",
        "policy_obligations",
        "obligations",
        "verification_results",
        "verifications",
        "closed_verifications",
        "evidence_artifacts",
        "evidences",
        "records",
        "relations",
        "record_relations",
        "grants",
        "authorization_grants",
        "authorizations",
        "checkpoints",
        "rollback_proofs",
        "compensations",
        "compensation_plans",
        "failure_stop_proofs",
        "stop_conditions",
        "failure_policies",
        "circuit_breaker_policies",
        "human_stop_authorities",
        "recovery_abort_paths",
        "stop_authorities",
        "independence_proofs",
        "independent_verification_proofs",
        "failure_domain_proofs",
        "role_proofs",
        "role_separation_proofs",
        "separation_proofs",
        "challenge_proofs",
        "challenge_capabilities",
        "escalation_routes",
        "dissent_channels",
        "challenge_paths",
        "exposure_proofs",
        "blast_radius_proofs",
        "exposure_limits",
        "takeover_proofs",
        "takeover_procedures",
        "recovery_authorities",
        "alternative_operators",
        "takeover_ready_proofs",
        "exit_proofs",
        "stop_procedures",
        "migration_paths",
        "shutdown_capabilities",
        "orderly_exit_proofs",
        "reauthorization_proofs",
        "reauthorization_grants",
        "reapproved_grants",
        "decisions",
        "decision_records",
    }
)

_REF_KEYS: dict[str, str] = {
    "authorization_refs": "grants",
    "authorization_grant_refs": "grants",
    "evidence_refs": "evidence_artifacts",
    "evidence_artifact_refs": "evidence_artifacts",
    "verification_refs": "verification_results",
    "verification_result_refs": "verification_results",
    "relation_refs": "relations",
    "record_relation_refs": "relations",
    "checkpoint_refs": "checkpoints",
    "decision_refs": "decisions",
    "obligation_refs": "obligation_proofs",
    "policy_obligation_refs": "obligation_proofs",
    "procedure_proof_refs": "procedure_proofs",
    "qualification_refs": "procedure_proofs",
}

_KIND_TO_PROOF: dict[str, str] = {
    "authorization": "grants",
    "authorizationgrant": "grants",
    "grant": "grants",
    "evidence": "evidence_artifacts",
    "evidenceartifact": "evidence_artifacts",
    "observation": "evidence_artifacts",
    "verification": "verification_results",
    "verificationresult": "verification_results",
    "closedverification": "verification_results",
    "relation": "relations",
    "recordrelation": "relations",
    "checkpoint": "checkpoints",
    "decision": "decisions",
    "obligation": "obligation_proofs",
    "policyobligation": "obligation_proofs",
    "failurestop": "failure_stop_proofs",
    "stopcondition": "failure_stop_proofs",
    "failurepolicy": "failure_stop_proofs",
    "circuitbreaker": "failure_stop_proofs",
    "humanstopauthority": "failure_stop_proofs",
    "recoveryabortpath": "failure_stop_proofs",
    "rollback": "checkpoints",
    "recovery": "recovery_procedures",
    "independence": "independence_proofs",
    "independentverification": "independence_proofs",
    "failuredomain": "independence_proofs",
    "roleseparation": "role_separation_proofs",
    "role": "role_separation_proofs",
    "challenge": "challenge_paths",
    "challengepath": "challenge_paths",
    "exposure": "exposure_proofs",
    "exposurelimit": "exposure_proofs",
    "takeover": "takeover_proofs",
    "exit": "exit_proofs",
    "reauthorization": "reauthorization_proofs",
}

_STALE_LIFECYCLES = {"superseded", "archived", "deprecated", "rejected", "rolled-back"}


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except Exception:  # noqa: S110 - serialization fallback
            return value
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_dump(v) for v in value]
    return value


def _clone(value: Any) -> Any:
    """Freeze Pydantic/runtime values against in-process mutation."""

    try:
        if isinstance(value, BaseModel):
            return value.model_copy(deep=True)
    except Exception:  # noqa: S110 - deepcopy fallback below
        return copy.deepcopy(value)
    return copy.deepcopy(value)


def _version(value: Any) -> int | str | None:
    candidate = getattr(value, "version", None)
    if candidate is not None:
        return candidate
    metadata = getattr(value, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("version", "record_version", "qualification_version"):
            if metadata.get(key) is not None:
                return metadata[key]
    return None


def _record_kind(value: Any) -> str | None:
    if value is None:
        return None
    if value.__class__.__name__ == "AuthorizationGrant":
        return "authorization"
    if value.__class__.__name__ == "RecordRelation":
        return "relation"
    if value.__class__.__name__ == "Checkpoint":
        return "checkpoint"
    record_type = getattr(value, "record_type", None)
    if isinstance(record_type, str):
        return record_type
    if value.__class__.__name__ == "Evidence":
        return "evidence"
    return value.__class__.__name__.lower()


def _metadata(value: Any) -> dict[str, Any]:
    md = getattr(value, "metadata", None)
    return md if isinstance(md, dict) else {}


def _kind_bucket(ref: QualificationRef, value: Any, default: str | None = None) -> str:
    for candidate in (ref.kind, _metadata(value).get("qualification_kind"), _record_kind(value), default):
        if isinstance(candidate, str):
            normalized = candidate.replace("_", "").replace("-", "").lower()
            if normalized in _KIND_TO_PROOF:
                return _KIND_TO_PROOF[normalized]
    return default or "procedure_proofs"


def _assert_ref_valid(ref: QualificationRef, value: Any, *, now: datetime) -> None:
    if value is None:
        raise QualificationResolutionError(f"qualification reference {ref.ref_id!r} not found")
    current_version = _version(value)
    if ref.version is not None:
        if current_version is None:
            raise QualificationResolutionError(
                f"qualification reference {ref.ref_id!r} requires version {ref.version!r}, but record is not versioned"
            )
        if str(current_version) != str(ref.version):
            raise QualificationResolutionError(
                "qualification reference "
                f"{ref.ref_id!r} version mismatch: requested {ref.version!r}, "
                f"current {current_version!r}"
            )
    lifecycle = getattr(value, "lifecycle_status", None)
    if isinstance(lifecycle, str) and lifecycle in _STALE_LIFECYCLES:
        raise QualificationResolutionError(
            f"qualification reference {ref.ref_id!r} points to stale lifecycle {lifecycle!r}"
        )
    expires_at = getattr(value, "expires_at", None) or _metadata(value).get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QualificationResolutionError(
                f"qualification reference {ref.ref_id!r} has malformed expiry"
            ) from exc
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if isinstance(expires_at, datetime) and now >= expires_at:
        raise QualificationResolutionError(f"qualification reference {ref.ref_id!r} is expired")


def _lookup(store: Any, ref: QualificationRef) -> Any | None:
    kind = (ref.kind or "").replace("_", "").replace("-", "").lower()
    getters: list[str]
    if kind in {"authorization", "authorizationgrant", "grant"}:
        getters = ["get_authorization"]
    elif kind in {"relation", "recordrelation"}:
        getters = ["get_relation"]
    elif kind in {"checkpoint"}:
        getters = ["get_checkpoint"]
    elif kind in {"evidence", "evidenceartifact", "observation"}:
        getters = ["get_record", "get_evidence"]
    else:
        getters = ["get_record", "get_authorization", "get_relation", "get_checkpoint", "get_evidence"]
    for getter_name in getters:
        getter = getattr(store, getter_name, None)
        if not callable(getter):
            continue
        try:
            value = getter(ref.ref_id)
        except Exception as exc:  # noqa: BLE001
            raise QualificationResolutionError(
                f"authoritative store lookup failed for {ref.ref_id!r}: {exc}"
            ) from exc
        if value is not None:
            return value
    return None


def _verification_from_record(value: Any) -> Any:
    """Adapt a stored record marker to the procedure helper's typed shape."""

    if getattr(value, "result", None) in {"pass", "fail"}:
        return value
    md = _metadata(value)
    result = md.get("result") or md.get("verification_result")
    if result not in {"pass", "fail"}:
        return value
    payload = {
        "id": getattr(value, "id", None),
        "result": result,
        "target_refs": md.get("target_refs") or md.get("subject_refs") or [],
        "subject_version_refs": md.get("subject_version_refs") or [],
        "version": _version(value),
    }
    return SimpleNamespace(**payload)


def _as_procedure_item(value: Any, bucket: str) -> Any:
    if bucket == "verification_results":
        return _verification_from_record(value)
    if bucket == "obligation_proofs":
        md = _metadata(value)
        payload = dict(md)
        payload.setdefault("id", getattr(value, "id", None))
        payload.setdefault("kind", md.get("obligation") or md.get("qualification_kind"))
        return payload
    if bucket == "procedure_proofs":
        md = _metadata(value)
        if isinstance(md.get("qualification_kind"), str):
            payload = dict(md)
            payload.setdefault("id", getattr(value, "id", None))
            return payload
    return value


@dataclass(frozen=True)
class AssessmentContext:
    """Immutable qualification snapshot shared by all boundary gate checks."""

    work: Any | None
    run: Any | None
    proofs: dict[str, list[Any]]
    refs: tuple[QualificationRef, ...]
    digest: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_authorization_refs(self) -> bool:
        return any(bucket == "grants" for bucket in self.proofs if self.proofs[bucket])

    def procedure_proofs(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for bucket, values in self.proofs.items():
            if bucket == "procedure_proofs":
                for value in values:
                    if isinstance(value, dict) and any(key in _REF_KEYS.values() for key in value):
                        for key, nested in value.items():
                            if key in _REF_KEYS.values() and isinstance(nested, list):
                                result.setdefault(key, []).extend(nested)
                    elif isinstance(value, dict) and isinstance(value.get("qualification_kind"), str):
                        kind = value["qualification_kind"].replace("_", "").replace("-", "").lower()
                        target = _KIND_TO_PROOF.get(kind)
                        if target:
                            result.setdefault(target, []).append(value)
                    else:
                        result.setdefault("procedure_proofs", []).append(value)
            else:
                result[bucket] = list(values)
        return result

    def _payload(self) -> dict[str, Any]:
        return {
            "refs": [ref.model_dump(mode="json", by_alias=True) for ref in self.refs],
            "proofs": {key: [_dump(value) for value in values] for key, values in sorted(self.proofs.items())},
        }

    @classmethod
    def resolve(
        cls,
        store: Any,
        request: Any,
        *,
        work: Any | None = None,
        run: Any | None = None,
    ) -> AssessmentContext:
        if store is None:
            raise QualificationResolutionError("authoritative qualification store unavailable")
        if work is None and getattr(request, "work_id", None) and hasattr(store, "get_work"):
            work = store.get_work(request.work_id)
        if run is None and getattr(request, "run_id", None) and hasattr(store, "get_run"):
            run = store.get_run(request.run_id)

        sources: list[dict[str, Any]] = []
        for candidate in (
            getattr(work, "metadata", None),
            getattr(run, "metadata", None),
            getattr(request, "metadata", None),
        ):
            if isinstance(candidate, dict):
                sources.append(candidate)

        merged: dict[str, Any] = {}
        for source in sources:
            for key, value in source.items():
                if key in _INLINE_FACT_KEYS:
                    raise QualificationResolutionError(
                        f"inline qualification facts are forbidden in metadata: {key!r}; use authoritative refs"
                    )
                if (
                    key in _INLINE_FACT_KEYS
                    and (
                        key.endswith("_proofs")
                        or key.endswith("_results")
                        or key in {"grants", "relations", "checkpoints", "decisions"}
                    )
                ):
                    raise QualificationResolutionError(
                        f"inline qualification facts are forbidden in metadata: {key!r}; use authoritative refs"
                    )
                merged[key] = value

        refs_by_bucket: dict[str, list[QualificationRef]] = {bucket: [] for bucket in set(_REF_KEYS.values())}
        for key, bucket in _REF_KEYS.items():
            value = merged.get(key)
            if value is None:
                continue
            values: Iterable[Any]
            if isinstance(value, (str, dict, QualificationRef)):
                values = [value]
            elif isinstance(value, list):
                values = value
            else:
                raise QualificationResolutionError(f"qualification refs {key!r} must be a list or a single ref")
            for item in values:
                refs_by_bucket[bucket].append(QualificationRef.parse(item))

        # Legacy singular id is still a reference, never an inline grant.
        if isinstance(merged.get("authorization_grant_id"), str):
            refs_by_bucket["grants"].append(
                QualificationRef(id=merged["authorization_grant_id"], kind="authorization")
            )

        refs: list[QualificationRef] = []
        proofs: dict[str, list[Any]] = {bucket: [] for bucket in refs_by_bucket}
        now = datetime.now(UTC)
        seen: set[tuple[str, str | None, str | None]] = set()
        for bucket, bucket_refs in refs_by_bucket.items():
            for ref in bucket_refs:
                dedupe_key = (
                    ref.ref_id,
                    ref.kind,
                    str(ref.version) if ref.version is not None else None,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                value = _lookup(store, ref)
                _assert_ref_valid(ref, value, now=now)
                # Optional type discriminator is authoritative, not advisory.
                if ref.kind:
                    expected = ref.kind.replace("_", "").replace("-", "").lower()
                    actual = (_record_kind(value) or "").replace("_", "").replace("-", "").lower()
                    aliases = {
                        expected,
                        _KIND_TO_PROOF.get(expected, ""),
                        # Procedure category refs (for example
                        # ``failure-stop``) intentionally identify the
                        # qualification role, not a new ontology type.
                        "procedureproof" if expected in _KIND_TO_PROOF else "",
                    }
                    category_ref = expected in _KIND_TO_PROOF
                    if actual not in aliases and not (
                        expected == "evidence" and actual in {"evidenceartifact", "observation"}
                    ) and not category_ref:
                        raise QualificationResolutionError(
                            "qualification reference "
                            f"{ref.ref_id!r} type mismatch: expected {ref.kind!r}, got {actual!r}"
                        )
                cloned = _clone(value)
                # Verification records must remain bound to this invocation's
                # subject and version context when they declare such bounds.
                md = _metadata(cloned)
                targets = md.get("target_refs") or md.get("subject_refs") or getattr(cloned, "target_refs", None) or []
                if isinstance(targets, str):
                    targets = [targets]
                request_targets = {str(request.work_id), str(getattr(request, "run_id", ""))}
                if (
                    targets
                    and getattr(request, "work_id", None)
                    and not set(map(str, targets)).intersection(request_targets)
                ):
                    raise QualificationResolutionError(
                        f"qualification reference {ref.ref_id!r} is bound to a different target"
                    )
                proof_versions = md.get("subject_version_refs") or getattr(cloned, "subject_version_refs", None) or []
                request_versions = getattr(request, "subject_version_refs", None) or []
                if isinstance(proof_versions, str):
                    proof_versions = [proof_versions]
                if proof_versions and (
                    not request_versions
                    or not set(map(str, proof_versions)).intersection(map(str, request_versions))
                ):
                    raise QualificationResolutionError(
                        f"qualification reference {ref.ref_id!r} version binding does not match request"
                    )
                refs.append(ref)
                if bucket == "procedure_proofs":
                    category = _metadata(cloned).get("qualification_kind")
                    target_bucket = (
                        _KIND_TO_PROOF.get(str(category).replace("_", "").replace("-", "").lower())
                        if category
                        else None
                    )
                    if target_bucket:
                        if target_bucket == "verification_results":
                            proofs.setdefault(target_bucket, []).append(_verification_from_record(cloned))
                        elif target_bucket in {"evidence_artifacts", "decisions", "relations", "checkpoints", "grants"}:
                            proofs.setdefault(target_bucket, []).append(cloned)
                        else:
                            payload = _as_procedure_item(cloned, bucket)
                            proofs.setdefault(target_bucket, []).append(payload)
                        continue
                item = _as_procedure_item(cloned, bucket)
                if isinstance(item, dict) and bucket == "procedure_proofs":
                    nested = item.get("qualification_kind")
                    target_bucket = (
                        _KIND_TO_PROOF.get(str(nested).replace("_", "").replace("-", "").lower())
                        if nested
                        else None
                    )
                    if target_bucket:
                        proofs.setdefault(target_bucket, []).append(item)
                    else:
                        proofs[bucket].append(item)
                elif (
                    isinstance(item, dict)
                    and bucket == "procedure_proofs"
                    and any(k in item for k in _KIND_TO_PROOF.values())
                ):
                    proofs[bucket].append(item)
                else:
                    proofs[bucket].append(item)

        payload = {
            "refs": [ref.model_dump(mode="json", by_alias=True) for ref in refs],
            "proofs": {
                key: [_dump(value) for value in values]
                for key, values in sorted(proofs.items())
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        return cls(
            work=_clone(work),
            run=_clone(run),
            proofs={key: list(values) for key, values in proofs.items()},
            refs=tuple(refs),
            digest=digest,
        )

    def refresh_matches(self, store: Any, request: Any) -> bool:
        """Resolve the same refs again and compare the qualification digest."""

        fresh = self.resolve(store, request)
        return fresh.digest == self.digest
