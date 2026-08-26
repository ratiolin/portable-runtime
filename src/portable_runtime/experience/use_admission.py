"""Read-only Experience Use Admission.

EUA-B resolves canonical ``KnowledgeProjection`` state from one coherent store
snapshot and answers whether one exact, already-selected experience set is
usable for one concrete context now. It creates no durable authority, performs
no retrieval/ranking/fallback, and grants no execution permission.
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
_NegativeApplicability = Literal["current", "outside", "unknown"]

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


def _string_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return _normal_refs([str(item) for item in value if isinstance(item, str)])


def _nonempty_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or not value:
        return None
    return {str(key): item for key, item in value.items()}


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    metadata = value.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


@dataclass(frozen=True)
class ExperienceUseRequirement:
    """Exact intended reliance set for one read-only experience-use decision.

    ``projection_refs`` are not retrieval candidates. Upstream retrieval may
    rank or select experience, but once this boundary is crossed the refs are
    the exact set the pending judgment intends to rely on. The evaluator uses
    AND semantics: every selected projection must be currently admissible.

    The caller supplies only projection refs and concrete use context. It may
    not provide assertion/evidence/judgment/counterexample facts; those are
    reconstructed from one store-owned coherent state snapshot.
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

    Snapshot existence is not positive use authority. Only an
    ``ExperienceUseAdmission`` whose status is ``allowed`` is a positive
    current-use result. This snapshot is not a durable historical use fact.
    """

    semantic_json: str

    def materialize(self) -> dict[str, Any]:
        value = json.loads(self.semantic_json)
        if not isinstance(value, dict):
            raise ValueError("experience-use snapshot must decode to an object")
        return value


@dataclass(frozen=True)
class ExperienceUseAdmission:
    """Read-only current-use eligibility result; never authority to act."""

    status: ExperienceUseStatus
    requirement_digest: str
    snapshot_digest: str
    resolved_snapshot: ResolvedExperienceUseSnapshot
    reasons: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


class ExperienceUseAdmissionEvaluator:
    """Resolve current experience truth from exactly one coherent state export."""

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
            premise_refs = {
                str(value) for value in raw.get("premise_refs", []) if isinstance(value, str)
            }
            evidence_refs = {
                str(value) for value in raw.get("evidence_refs", []) if isinstance(value, str)
            }
            metadata = _metadata(raw)
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

        # Exactly one relation hop from the reconstructed projection graph.
        # The seed is frozen before scanning so iteration order cannot turn
        # this into an accidental transitive traversal.
        relation_seed = set(graph_refs)
        relations: list[dict[str, Any]] = []
        for raw in cls._bucket(state, "relation"):
            subject = raw.get("subject_ref")
            obj = raw.get("object_ref")
            if subject in relation_seed or obj in relation_seed:
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
            metadata = _metadata(raw)
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
    def _unique_mapping_state(
        candidates: list[dict[str, Any]],
        actual: Mapping[str, Any],
    ) -> _NegativeApplicability:
        if not candidates:
            return "unknown"
        normalized = {_canonical_json(candidate) for candidate in candidates}
        if len(normalized) != 1:
            return "unknown"
        expected = candidates[0]
        return (
            "current"
            if all(key in actual and actual[key] == value for key, value in expected.items())
            else "outside"
        )

    @staticmethod
    def _unique_version_state(
        candidates: list[tuple[str, ...]],
        actual: tuple[str, ...],
    ) -> _NegativeApplicability:
        if not candidates:
            return "unknown"
        normalized = {tuple(sorted(candidate)) for candidate in candidates}
        if len(normalized) != 1:
            return "unknown"
        expected = set(candidates[0])
        return "current" if expected.issubset(set(actual)) else "outside"

    @classmethod
    def _negative_applicability(
        cls,
        resolved_value: Mapping[str, Any],
        relation: Mapping[str, Any] | None,
        requirement: ExperienceUseRequirement,
    ) -> _NegativeApplicability:
        """Classify one negative fact without inferring missing applicability.

        A counterexample or negative-knowledge fact is disqualifying only when
        authoritative scope, subject-version, and environment applicability
        can all be established for the current use. A definitive mismatch in
        any one dimension proves the limitation is outside the current use.
        Missing or conflicting applicability stays unknown and therefore fails
        closed rather than being guessed into either blocking or harmlessness.
        """

        fact_metadata = _metadata(resolved_value)
        relation_metadata = _metadata(relation or {})

        scope_candidates: list[dict[str, Any]] = []
        for value in (
            resolved_value.get("scope"),
            fact_metadata.get("use_scope"),
            (relation or {}).get("scope"),
            relation_metadata.get("use_scope"),
        ):
            candidate = _nonempty_mapping(value)
            if candidate is not None:
                scope_candidates.append(candidate)

        version_candidates: list[tuple[str, ...]] = []
        for value in (
            fact_metadata.get("subject_version_refs"),
            fact_metadata.get("scope_version_refs"),
            relation_metadata.get("subject_version_refs"),
            relation_metadata.get("scope_version_refs"),
        ):
            refs = _string_refs(value)
            if refs:
                version_candidates.append(refs)

        environment_candidates: list[dict[str, Any]] = []
        for value in (
            resolved_value.get("environment_versions"),
            fact_metadata.get("environment_bindings"),
            relation_metadata.get("environment_bindings"),
            relation_metadata.get("environment_versions"),
        ):
            candidate = _nonempty_mapping(value)
            if candidate is not None:
                environment_candidates.append(candidate)

        scope_state = cls._unique_mapping_state(
            scope_candidates,
            _thaw(requirement.use_scope),
        )
        version_state = cls._unique_version_state(
            version_candidates,
            requirement.subject_version_refs,
        )
        environment_state = cls._unique_mapping_state(
            environment_candidates,
            _thaw(requirement.environment_bindings),
        )
        states = (scope_state, version_state, environment_state)
        if "outside" in states:
            return "outside"
        if states == ("current", "current", "current"):
            return "current"
        return "unknown"

    @classmethod
    def _classify_negative_knowledge(
        cls,
        projection: KnowledgeProjection,
        requirement: ExperienceUseRequirement,
        projection_resolved: Mapping[str, dict[str, Any]],
        related_relations: list[dict[str, Any]],
    ) -> tuple[ExperienceUseStatus | None, list[str]]:
        """Keep negative knowledge visible without equating presence with block."""

        negative_refs = sorted(
            set(projection.counterexample_refs).union(projection.negative_knowledge_refs)
        )
        if not negative_refs:
            return None, []

        current_assertions = set(projection.current_assertion_refs)
        reasons: list[str] = []
        saw_unknown = False

        for ref in negative_refs:
            entry = projection_resolved.get(ref)
            raw = entry.get("value") if isinstance(entry, Mapping) else None
            if not isinstance(raw, Mapping):
                saw_unknown = True
                reasons.append(f"negative-fact-unavailable:{ref}")
                continue

            bound_relations = [
                relation
                for relation in related_relations
                if relation.get("relation_type") == "contradicts"
                and (
                    (
                        relation.get("subject_ref") == ref
                        and relation.get("object_ref") in current_assertions
                    )
                    or (
                        relation.get("object_ref") == ref
                        and relation.get("subject_ref") in current_assertions
                    )
                )
            ]

            if not bound_relations:
                applicability = cls._negative_applicability(raw, None, requirement)
                if applicability == "outside":
                    reasons.append(f"negative-fact-outside-use:{ref}")
                    continue
                saw_unknown = True
                reasons.append(
                    f"negative-fact-unbound:{ref}"
                    if applicability == "current"
                    else f"negative-applicability-unknown:{ref}"
                )
                continue

            relation_states = [
                (
                    relation,
                    cls._negative_applicability(raw, relation, requirement),
                )
                for relation in bound_relations
            ]
            current = [relation for relation, state in relation_states if state == "current"]
            if current:
                reasons.extend(
                    f"applicable-contradiction:{relation.get('id', '')}:{ref}"
                    for relation in current
                )
                return "blocked", reasons
            if any(state == "unknown" for _, state in relation_states):
                saw_unknown = True
                reasons.append(f"negative-applicability-unknown:{ref}")
            else:
                reasons.append(f"negative-fact-outside-use:{ref}")

        return ("unavailable", reasons) if saw_unknown else (None, reasons)

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
        # One call is necessary but not sufficient: EUA-B relies on each store
        # backend making export_state itself a coherent point-in-time read.
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
            reasons.append("no-experience-reliance-declared")

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

            # Lifecycle is a resolved usability fact. A present but non-usable
            # projection is blocked, not unavailable and not merely stale.
            if projection.lifecycle_status != "official":
                statuses.append("blocked")
                reasons.append(
                    f"projection-non-usable-lifecycle:{projection_ref}:{projection.lifecycle_status}"
                )

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

            related_derivations, related_relations, _graph_refs = self._related_graph(
                state,
                projection,
                projection_resolved,
            )
            derivations.extend(related_derivations)
            relations.extend(related_relations)

            if not self._scope_matches(projection, requirement):
                statuses.append("blocked")
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

            negative_status, negative_reasons = self._classify_negative_knowledge(
                projection,
                requirement,
                projection_resolved,
                related_relations,
            )
            if negative_status is not None:
                statuses.append(negative_status)
            reasons.extend(negative_reasons)

            freshness_refs = {
                projection.id,
                *projection.current_assertion_refs,
                *projection.evidence_summary_refs,
                *projection.epistemic_judgment_refs,
                *projection.scope_version_refs,
                *(
                    str(item.get("id"))
                    for item in related_derivations
                    if isinstance(item.get("id"), str)
                ),
            }
            for relation in related_relations:
                if relation.get("relation_type") != "requires-revalidation":
                    continue
                if (
                    relation.get("subject_ref") in freshness_refs
                    or relation.get("object_ref") in freshness_refs
                ):
                    statuses.append("stale")
                    reasons.append(f"requires-revalidation:{relation.get('id', '')}")

        # Exact-set AND semantics. A resolved blocker is decisive even if a
        # different required projection is unavailable; the exact set is
        # already proven unusable. Staleness is likewise a decisive current
        # freshness failure. Missing facts alone remain unavailable.
        status: ExperienceUseStatus
        if "blocked" in statuses:
            status = "blocked"
        elif "stale" in statuses:
            status = "stale"
        elif "unavailable" in statuses:
            status = "unavailable"
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
