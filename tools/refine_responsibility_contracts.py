from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if content.count(old) != 1:
        raise RuntimeError(f"{path}: replacement target count={content.count(old)}")
    write(path, content.replace(old, new, 1))


# Tighten qualification transitions: the transition is an epistemic-status
# change, not a loophole for bundling unrelated semantic mutations.
transition_path = "src/portable_runtime/records/qualification_transition.py"
replace_once(
    transition_path,
    '''    if before.statement != after.statement:
        raise ValueError("qualification transition cannot change the asserted proposition")
    if before.lifecycle_status != after.lifecycle_status:
        raise ValueError("qualification transition cannot bundle a lifecycle transition")
''',
    '''    before_payload = before.model_dump(mode="json")
    after_payload = after.model_dump(mode="json")
    before_metadata = before_payload.pop("metadata", {})
    after_metadata = after_payload.pop("metadata", {})
    for payload in (before_payload, after_payload):
        payload.pop("created_at", None)
        payload.pop("epistemic_status", None)
        payload.pop("version", None)
    if before_payload != after_payload:
        raise ValueError("qualification transition cannot bundle other semantic changes")
    before_metadata = before_metadata if isinstance(before_metadata, dict) else {}
    after_metadata = after_metadata if isinstance(after_metadata, dict) else {}
    changed_metadata = {
        key
        for key in set(before_metadata) | set(after_metadata)
        if before_metadata.get(key) != after_metadata.get(key)
    }
    if not changed_metadata.issubset({"authorization_use_ref", "revision_ref"}):
        raise ValueError("qualification transition may only change authority metadata")
    if before.lifecycle_status != after.lifecycle_status:
        raise ValueError("qualification transition cannot bundle a lifecycle transition")
''',
)

validation_path = "src/portable_runtime/protocol/validation.py"
replace_once(
    validation_path,
    '''    if record.epistemic_status == existing.epistemic_status:
        return
    if record.version != existing.version + 1:
        raise ValueError(
            f"qualification transition for {record.id!r} must advance version by exactly one"
        )
    expected_before = _qualification_transition_snapshot(existing)
''',
    '''    if record.epistemic_status == existing.epistemic_status:
        return
    if record.version != existing.version + 1:
        raise ValueError(
            f"qualification transition for {record.id!r} must advance version by exactly one"
        )
    old_payload = existing.model_dump(mode="json")
    new_payload = record.model_dump(mode="json")
    old_metadata = old_payload.pop("metadata", {})
    new_metadata = new_payload.pop("metadata", {})
    for payload in (old_payload, new_payload):
        payload.pop("created_at", None)
        payload.pop("epistemic_status", None)
        payload.pop("version", None)
    if old_payload != new_payload:
        raise ValueError(
            f"qualification transition for {record.id!r} cannot bundle other semantic changes"
        )
    old_metadata = old_metadata if isinstance(old_metadata, dict) else {}
    new_metadata = new_metadata if isinstance(new_metadata, dict) else {}
    changed_metadata = {
        key
        for key in set(old_metadata) | set(new_metadata)
        if old_metadata.get(key) != new_metadata.get(key)
    }
    if not changed_metadata.issubset({"authorization_use_ref", "revision_ref"}):
        raise ValueError(
            f"qualification transition for {record.id!r} may only change authority metadata"
        )
    expected_before = _qualification_transition_snapshot(existing)
''',
)

qualification_test = "tests/conformance/test_qualification_transition.py"
with (ROOT / qualification_test).open("a", encoding="utf-8") as handle:
    handle.write(
        '''\n\ndef test_qualification_transition_cannot_bundle_other_semantic_changes() -> None:\n'''
        '''    store = InMemoryStateStore()\n'''
        '''    before = Assertion(\n'''
        '''        id="assert_narrow_transition",\n'''
        '''        statement="same proposition",\n'''
        '''        lifecycle_status="current",\n'''
        '''        epistemic_status="supported",\n'''
        '''        version=1,\n'''
        '''    )\n'''
        '''    store.save_record(before)\n'''
        '''    after = _authorized_after(store, before, "contested").model_copy(\n'''
        '''        update={"assumptions": ["silently changed"]}\n'''
        '''    )\n'''
        '''    with pytest.raises(ValueError, match="cannot bundle other semantic changes"):\n'''
        '''        commit_qualification_transition(\n'''
        '''            store,\n'''
        '''            after,\n'''
        '''            expected_version=1,\n'''
        '''            reason_refs=["observation:new"],\n'''
        '''            event_id="event_narrow_transition",\n'''
        '''        )\n'''
        '''    assert store.get_event("event_narrow_transition") is None\n'''
        '''    assert store.get_record(before.id).assumptions == []\n'''
    )


# Revalidation proof-class requirements are driven by the declaration field,
# not by an obligation naming convention.
completion_path = "src/portable_runtime/workflows/completion.py"
replace_once(
    completion_path,
    '''        # Preserve declaration order while eliminating duplicate obligations.
        return list(dict.fromkeys(values))

    @staticmethod
    def _proof_metadata(record: object) -> dict[str, Any] | None:
''',
    '''        # Preserve declaration order while eliminating duplicate obligations.
        return list(dict.fromkeys(values))

    @staticmethod
    def revalidation_obligation_refs(work: Work) -> list[str]:
        values: list[str] = []

        def add(raw: object) -> None:
            if isinstance(raw, str) and raw.strip():
                values.append(raw.strip())
                return
            if not isinstance(raw, list):
                return
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    for key in ("id", "ref", "key", "name", "description"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            values.append(candidate.strip())
                            break

        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        constraints = work.constraints if isinstance(work.constraints, dict) else {}
        for source in (metadata, constraints):
            add(source.get("revalidation_obligations"))
            add(source.get("required_revalidation_obligations"))
            policy = source.get("verification_policy")
            if isinstance(policy, dict):
                add(policy.get("revalidation_obligations"))
                add(policy.get("required_revalidation_obligations"))
        return list(dict.fromkeys(values))

    @staticmethod
    def _proof_metadata(record: object) -> dict[str, Any] | None:
''',
)
replace_once(
    completion_path,
    '''        required_obligations = set(CompletionAuthority.required_obligation_refs(work))
        covered_obligations: set[str] = set()
''',
    '''        required_obligations = set(CompletionAuthority.required_obligation_refs(work))
        revalidation_obligations = set(CompletionAuthority.revalidation_obligation_refs(work))
        covered_obligations: set[str] = set()
''',
)
replace_once(
    completion_path,
    '''            covered_obligations.update(
                obligation
                for obligation in candidates
                if CompletionAuthority._proof_can_cover(proof_class, obligation)
            )
''',
    '''            covered_obligations.update(
                obligation
                for obligation in candidates
                if (obligation not in revalidation_obligations or proof_class == "revalidation")
                and CompletionAuthority._proof_can_cover(proof_class, obligation)
            )
''',
)

terminal_test = "tests/conformance/test_terminal_authority.py"
replace_once(
    terminal_test,
    '"revalidation_obligations": ["revalidate.subject-v2"],',
    '"revalidation_obligations": ["revalidation-review"],',
)
replace_once(
    terminal_test,
    '        "revalidate.subject-v2",\n',
    '        "revalidation-review",\n',
)
replace_once(
    terminal_test,
    'metadata={"revalidation_obligations": ["revalidate.subject-v2"]},',
    'metadata={"revalidation_obligations": ["fresh-source-check"]},',
)
replace_once(
    terminal_test,
    '"obligation_refs": ["revalidate.subject-v2"],',
    '"obligation_refs": ["fresh-source-check"],',
)
replace_once(
    terminal_test,
    'assert result.metadata["completion_required_obligations"] == ["revalidate.subject-v2"]',
    'assert result.metadata["completion_required_obligations"] == ["fresh-source-check"]',
)
replace_once(
    terminal_test,
    'assert result.metadata["completion_covered_obligations"] == ["revalidate.subject-v2"]',
    'assert result.metadata["completion_covered_obligations"] == ["fresh-source-check"]',
)

print("responsibility contract refinements applied")
