"""Read-only Experience Use Admission.

EUA-B resolves canonical KnowledgeProjection state from one coherent store
snapshot and answers whether selected experience is usable for one exact
context now. It creates no durable authority and grants no execution
permission.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from portable_runtime.records.knowledge import KnowledgeProjection

ExperienceUseStatus = Literal[
    "not-applicable",
    "allowed",
    "blocked",
    "stale",
    "unavailable",
]

_NOISE_KEYS = frozenset({"created_at", "updated_at"})
_EXPECTED_DIRECT_TYPES: dict[str, set[tuple[str, str | None]]] = {
    "current_assertion_refs": {("record", "Assertion")},
    "evidence_summary_refs": {
        ("record", "EvidenceArtifact"),
        ("record", "Observation"),
        ("evidence", None),
    },
    "epistemic_judgment_refs": {("record", "Assertion")},
    "scope_version_refs": {("record", "Revision"), ("record", "ChangeObject")},
    "authorization_refs": {("authorization", None)},
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _without_noise(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_noise(item)
            for key, item in value.items()
            if str(key) not in _NOISE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_without_noise(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _without_noise(_thaw(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normal_refs(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class ExperienceUseRequirement:
    """Caller boundary for one read-only experience-use decision.

    The caller selects canonical projection refs and supplies only concrete use
    context. Assertion/evidence/judgment/counterexample refs are reconstructed
    from store-owned canonical state.
    """

    projection_refs: tuple[str, ...] = ()
    use_scope: Mapping[str, Any] = field(default_factory=dict)
    subject_version_refs: tuple[str, ...] = ()
    environment_bindings: Mapping[str, str] = field(default_factory=dict)
    use_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_refs", _normal_refs(self.projection_refs))
        object.__setattr__(self, "subject_version_refs", _normal_refs(self.subject_version_refs))
        object.__setattr__(self, "use_scope", _freeze(dict(self.use_scope)))
        object.__setattr__(
            self,
            "environment_bindings",
            _freeze({str(key): str(value) for key, value in self.environment_bindings.items()}),
        )
        object.__setattr__(self, "use_context", _freeze(dict(self.use_context)))

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema": "experience-use-requirement-v1",
            "projection_refs": list(self.projection_refs),
            "use_scope": _thaw(self.use_scope),
            "subject_version_refs": list(self.subject_version_refs),
            "environment_bindings": _thaw(self.environment_bindings),
            "use_context": _thaw(self.use_context),
        }


@dataclass(frozen=True)
class ResolvedExperienceUseSnapshot:
    """Immutable in-memory facts checked by one admission.

    This is not a durable historical use fact. EUA-C decides whether and how
    an allowed snapshot becomes bound to an actual judgment.
    """

    semantic_json: str

    def materialize(self) -> dict[str, Any]:
        value = json.loads(self.semantic_json)
        if not isinstance(value, dict):
            raise ValueError("experience-use snapshot must decode to an object")
        return value


@dataclass(frozen=True)
class ExperienceUseAdmission:
    """Read-only eligibility result; never an authorization to act."""

    status: ExperienceUseStatus
    requirement_digest: str
    snapshot_digest: str
    resolved_snapshot: ResolvedExperienceUseSnapshot
    reasons: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


class ExperienceUseAdmissionEvaluator:
    """Resolve current experience truth from one coherent store snapshot."""

    def __init__(self, store: Any) -> None:
        export = getattr(store, "export_state", None)
        if not callable(export):
            raise TypeError("ExperienceUseAdmission requires a StateStore export_state surface")
        self._store = store

    @staticmethod
    def _bucket(state: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
        values = state.get(kind, [])
        if not isinstance(values, list):
            return []
        return [dict(value) for value in values if isinstance(value, dict)]

    @classmethod
    def _find_exact(
        cls,
        state: Mapping[str, Any],
        ref: str,
        *,
        kinds: tuple[str, ...] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        search_kinds = kinds or tuple(str(kind) for kind in state)
        matches: list[tuple[str, dict[str, Any]]] = []
        for kind in search_kinds:
            for raw in cls._bucket(state, kind):
                if raw.get("id") == ref:
                    matches.append((kind, raw))
        if len(matches) != 1:
            return None
        return matches[0]

    @staticmethod
    def _record_type(raw: Mapping[str, Any]) -> str | None:
        value = raw.get("record_type")
        return str(value) if isinstance(value, str) else None

    @classmethod
    def _direct_graph(
        cls,
        state: Mapping[str, Any],
        projection: KnowledgeProjection,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        resolved: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for field_name, expected in _EXPECTED_DIRECT_TYPES.items():
            refs = tuple(getattr(projection, field_name, ()) or ())
            for ref in refs:
                match = cls._find_exact(state, ref)
                if match is None:
                    errors.append(f"unresolved:{field_name}:{ref}")
                    continue
                kind, raw = match
                shape = (kind, cls._record_type(raw) if kind == "record" else None)
                if shape not in expected:
                    errors.append(f"wrong-type:{field_name}:{ref}")
                    continue
                resolved[ref] = {"kind": kind, "value": raw}
        return resolved, errors

    @classmethod
    def _resolve_optional_local_refs(
        cls,
        state: Mapping[str, Any],
        refs: tuple[str, ...] | list[str],
        *,
        role: str,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        resolved: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for ref in refs:
            match = cls._find_exact(state, str(ref))
            if match is None:
                errors.append(f"unresolved:{role}:{ref}")
                continue
            kind, raw = match
            resolved[str(ref)] = {"kind": kind, "value": raw}
        return resolved, errors

    @classmethod
    def _related_graph(
        cls,
        state: Mapping[str, Any],
        projection: KnowledgeProjection,
        projection_resolved: Mapping[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
        assertions = set(projection.current_assertion_refs)
        judgments = set(projection.epistemic_judgment_refs)
        evidence = set(projection.evidence_summary_refs)
        scopes = set(projection.scope_version_refs)
        derivations: list[dict[str, Any]] = []
        graph_refs = {projection.id, *projection_resolved.keys()}
        for raw in cls._bucket(state, "record"):
            if raw.get("record_type") != "Derivation":
                continue
            premise_refs = {str(value) for value in raw.get("premise_refs", []) if isinstance(value, str)}
            evidence_refs = {str(value) for value in raw.get("evidence_refs", []) if isinstance(value, str)}
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            scope_refs = {
                str(value)
                for value in metadata.get("scope_version_refs", [])
                if isinstance(value, str)
            }
            if (
                raw.get("conclusion_ref") in assertions
                or premise_refs.intersection(judgments)
                or evidence_refs.intersection(evidence)
                or scope_refs.intersection(scopes)
            ):
                derivations.append(raw)
                identifier = raw.get("id")
                if isinstance(identifier, str):
                    graph_refs.add(identifier)

        relations: list[dict[str, Any]] = []
        # Expand one canonical hop. The seed is per-projection so one selected
        # experience cannot pull another selected projection's graph into its
        # eligibility domain.
        for raw in cls._bucket(state, "relation"):
            subject = raw.get("subject_ref")
            obj = raw.get("object_ref")
            if subject in graph_refs or obj in graph_refs:
                relations.append(raw)
                if isinstance(subject, str):
                    graph_refs.add(subject)
                if isinstance(obj, str):
                    graph_refs.add(obj)
        return derivations, relations, graph_refs

    @staticmethod
    def _scope_matches(projection: KnowledgeProjection, requirement: ExperienceUseRequirement) -> bool:
        required = _thaw(projection.validity_scope)
        actual = _thaw(requirement.use_scope)
        return all(key in actual and actual[key] == value for key, value in required.items())

    @staticmethod
    def _environment_matches(projection: KnowledgeProjection, requirement: ExperienceUseRequirement) -> bool:
        actual = _thaw(requirement.environment_bindings)
        return all(actual.get(key) == value for key, value in projection.environment_bindings.items())

    @staticmethod
    def _subject_versions_match(projection: KnowledgeProjection, requirement: ExperienceUseRequirement) -> bool:
        return set(projection.scope_version_refs).issubset(set(requirement.subject_version_refs))

    @staticmethod
    def _classify_direct_records(
        projection: KnowledgeProjection,
        resolved: Mapping[str, dict[str, Any]],
    ) -> tuple[ExperienceUseStatus | None, list[str]]:
        reasons: list[str] = []
        for ref in projection.current_assertion_refs:
            raw = resolved.get(ref, {}).get("value", {})
            lifecycle = str(raw.get("lifecycle_status", ""))
            epistemic = str(raw.get("epistemic_status", ""))
            if lifecycle in {"superseded", "archived"}:
                reasons.append(f"stale-assertion:{ref}")
            if epistemic in {"contested", "refuted"}:
                return "blocked", [*reasons, f"blocked-assertion:{ref}:{epistemic}"]
            if epistemic in {"unknown", "revalidation-required", "unverified"}:
                reasons.append(f"stale-assertion:{ref}:{epistemic}")
        for ref in projection.evidence_summary_refs:
            raw = resolved.get(ref, {}).get("value", {})
            if str(raw.get("lifecycle_status", "")) in {"superseded", "archived"}:
                reasons.append(f"stale-evidence:{ref}")
        for ref in projection.epistemic_judgment_refs:
            raw = resolved.get(ref, {}).get("value", {})
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            role = str(metadata.get("epistemic_role", metadata.get("role", ""))).lower()
            if str(raw.get("epistemic_status", "")) != "supported" or role in {
                "approval",
                "authorization",
                "governance",
                "decision",
            }:
                return "unavailable", [*reasons, f"invalid-epistemic-judgment:{ref}"]
        return ("stale", reasons) if reasons else (None, [])

    @staticmethod
    def _projection_payload(projection: KnowledgeProjection) -> dict[str, Any]:
        return {
            "id": projection.id,
            "lifecycle_status": projection.lifecycle_status,
            "current_assertion_refs": list(projection.current_assertion_refs),
            "evidence_summary_refs": list(projection.evidence_summary_refs),
            "epistemic_judgment_refs": list(projection.epistemic_judgment_refs),
            "authorization_refs": list(projection.authorization_refs),
            "scope_version_refs": list(projection.scope_version_refs),
            "validity_scope": dict(projection.validity_scope),
            "environment_bindings": dict(projection.environment_bindings),
            "counterexample_refs": list(projection.counterexample_refs),
            "negative_knowledge_refs": list(projection.negative_knowledge_refs),
            "reopen_conditions": list(projection.reopen_conditions),
        }

    @classmethod
    def _snapshot_payload(
        cls,
        requirement: ExperienceUseRequirement,
        projections: list[KnowledgeProjection],
        resolved_objects: Mapping[str, dict[str, Any]],
        derivations: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        unresolved: list[str],
    ) -> dict[str, Any]:
        return {
            "schema": "resolved-experience-use-snapshot-v1",
            "requirement": requirement.semantic_payload(),
            "projections": sorted(
                (cls._projection_payload(projection) for projection in projections),
                key=lambda item: str(item["id"]),
            ),
            "resolved_objects": [
                {"ref": ref, **_without_noise(value)}
                for ref, value in sorted(resolved_objects.items())
            ],
            "derivations": sorted(
                (_without_noise(value) for value in derivations),
                key=lambda item: str(item.get("id", "")),
            ),
            "relations": sorted(
                (_without_noise(value) for value in relations),
                key=lambda item: str(item.get("id", "")),
            ),
            "unresolved": sorted(set(unresolved)),
        }

    def evaluate(self, requirement: ExperienceUseRequirement) -> ExperienceUseAdmission:
        requirement_digest = _digest(requirement.semantic_payload())
        state = self._store.export_state()
        if not isinstance(state, dict):
            raise TypeError("StateStore export_state must return a state mapping")

        projections: list[KnowledgeProjection] = []
        resolved_objects: dict[str, dict[str, Any]] = {}
        derivations: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        unresolved: list[str] = []
        reasons: list[str] = []
        statuses: list[ExperienceUseStatus] = []

        if not requirement.projection_refs:
            statuses.append("not-applicable")
            reasons.append("no-projection-selected")

        for projection_ref in requirement.projection_refs:
            match = self._find_exact(state, projection_ref, kinds=("knowledge_projection",))
            if match is None:
                unresolved.append(f"projection:{projection_ref}")
                statuses.append("unavailable")
                reasons.append(f"projection-unavailable:{projection_ref}")
                continue
            _, raw_projection = match
            try:
                projection = KnowledgeProjection.model_validate(raw_projection)
            except ValueError:
                unresolved.append(f"projection:{projection_ref}")
                statuses.append("unavailable")
                reasons.append(f"projection-invalid:{projection_ref}")
                continue
            projections.append(projection)

            if projection.lifecycle_status in {"deprecated", "archived"}:
                statuses.append("stale")
                reasons.append(f"projection-stale:{projection_ref}:{projection.lifecycle_status}")
            elif projection.lifecycle_status != "official":
                statuses.append("unavailable")
                reasons.append(f"projection-not-official:{projection_ref}:{projection.lifecycle_status}")

            direct, direct_errors = self._direct_graph(state, projection)
            counterexamples, counter_errors = self._resolve_optional_local_refs(
                state,
                projection.counterexample_refs,
                role="counterexample",
            )
            negative, negative_errors = self._resolve_optional_local_refs(
                state,
                projection.negative_knowledge_refs,
                role="negative-knowledge",
            )
            projection_resolved = {**direct, **counterexamples, **negative}
            resolved_objects.update(projection_resolved)
            projection_errors = [*direct_errors, *counter_errors, *negative_errors]
            unresolved.extend(projection_errors)
            if projection_errors:
                statuses.append("unavailable")
                reasons.extend(projection_errors)

            related_derivations, related_relations, graph_refs = self._related_graph(
                state,
                projection,
                projection_resolved,
            )
            derivations.extend(related_derivations)
            relations.extend(related_relations)

            if not self._scope_matches(projection, requirement):
                statuses.append("not-applicable")
                reasons.append(f"scope-mismatch:{projection_ref}")
            if not self._environment_matches(projection, requirement):
                statuses.append("stale")
                reasons.append(f"environment-drift:{projection_ref}")
            if not self._subject_versions_match(projection, requirement):
                statuses.append("stale")
                reasons.append(f"subject-version-drift:{projection_ref}")

            direct_status, direct_reasons = self._classify_direct_records(
                projection,
                projection_resolved,
            )
            if direct_status is not None:
                statuses.append(direct_status)
                reasons.extend(direct_reasons)

            if projection.counterexample_refs:
                statuses.append("blocked")
                reasons.append(f"canonical-counterexample:{projection_ref}")
            if projection.negative_knowledge_refs:
                statuses.append("blocked")
                reasons.append(f"canonical-negative-knowledge:{projection_ref}")

            for relation in related_relations:
                relation_type = relation.get("relation_type")
                touches_graph = (
                    relation.get("subject_ref") in graph_refs
                    or relation.get("object_ref") in graph_refs
                )
                if relation_type == "requires-revalidation" and touches_graph:
                    statuses.append("stale")
                    reasons.append(f"requires-revalidation:{relation.get('id', '')}")
                if relation_type == "contradicts" and touches_graph:
                    statuses.append("blocked")
                    reasons.append(f"canonical-contradiction:{relation.get('id', '')}")

        status: ExperienceUseStatus
        if "unavailable" in statuses:
            status = "unavailable"
        elif "stale" in statuses:
            status = "stale"
        elif "blocked" in statuses:
            status = "blocked"
        elif "not-applicable" in statuses:
            status = "not-applicable"
        else:
            status = "allowed"

        payload = self._snapshot_payload(
            requirement,
            projections,
            resolved_objects,
            derivations,
            relations,
            unresolved,
        )
        semantic_json = _canonical_json(payload)
        snapshot = ResolvedExperienceUseSnapshot(semantic_json=semantic_json)
        return ExperienceUseAdmission(
            status=status,
            requirement_digest=requirement_digest,
            snapshot_digest=hashlib.sha256(semantic_json.encode("utf-8")).hexdigest(),
            resolved_snapshot=snapshot,
            reasons=tuple(sorted(set(reasons))),
        )


__all__ = [
    "ExperienceUseAdmission",
    "ExperienceUseAdmissionEvaluator",
    "ExperienceUseRequirement",
    "ExperienceUseStatus",
    "ResolvedExperienceUseSnapshot",
]
