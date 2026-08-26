from fastapi.testclient import TestClient

from portable_runtime.core.runtime import Runtime
from portable_runtime.public_contracts.http import create_public_app
from portable_runtime.public_contracts.models import (
    ConfirmedOutcomeView,
    GovernanceUseAdmissionView,
    InvocationDispatchCommittedView,
    InvocationPermitView,
    RecoveryView,
)


def test_contract_catalog_http_has_only_local_contract_identity() -> None:
    runtime = Runtime()
    response = TestClient(create_public_app(runtime)).get("/v1/contracts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "portable-runtime/contracts"
    rendered = str(payload)
    assert "source_commit" not in rendered.lower()
    assert "source_repository" not in rendered.lower()


def test_experience_evaluate_is_read_only() -> None:
    runtime = Runtime()
    client = TestClient(create_public_app(runtime))
    before = runtime.store.export_state()
    response = client.post(
        "/v1/experience/use/evaluate",
        json={
            "schema": "experience-use-requirement-v1",
            "projection_refs": [],
            "use_scope": {},
            "subject_version_refs": [],
            "environment_bindings": {},
            "use_context": {},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not-applicable"
    assert runtime.store.export_state() == before


def test_public_views_are_explicitly_non_authoritative() -> None:
    values = (
        GovernanceUseAdmissionView(status="blocked"),
        InvocationPermitView(permit_digest="0" * 64),
        InvocationDispatchCommittedView(event_id="event-1"),
        ConfirmedOutcomeView(outcome_id="outcome-1"),
        RecoveryView(subject_ref="subject-1"),
    )
    assert all(value.authority_bearing is False for value in values)


def test_public_contract_module_does_not_define_internal_authority_objects() -> None:
    from portable_runtime import public_contracts

    assert not hasattr(public_contracts, "InvocationPermit")
    assert not hasattr(public_contracts, "GovernanceUseRequirement")
