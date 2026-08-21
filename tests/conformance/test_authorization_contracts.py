"""Canonical authorization primitive versus explicit legacy normalization."""

from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    is_authorized_for,
    is_authorized_for_legacy,
)


def _grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        principal_ref="human:owner",
        grantee_ref="agent:strict",
        allowed_capabilities=["code.edit"],
        resource_scope=["repo/app"],
        effect_ceiling="write-local",
        subject_version_refs=["patch:v1"],
    )


def test_canonical_authorization_requires_typed_actor_resource_effect_and_version() -> None:
    grant = _grant()
    request = CanonicalAuthorizationRequest(
        capability="code.edit",
        actor_ref="agent:strict",
        resource_ref="repo/app/src/main.py",
        effect_class="write-local",
        subject_version_refs=["patch:v1"],
    )
    assert is_authorized_for(request, grant)
    assert not is_authorized_for({"capability": "code.edit"}, grant)  # type: ignore[arg-type]


def test_legacy_authorization_is_explicit_normalization_only() -> None:
    grant = _grant()
    action = {
        "capability": "code.edit",
        "actor_ref": "agent:strict",
        "resource": "repo/app/src/main.py",
        "effect_class": "write-local",
        "subject_version_refs": ["patch:v1"],
    }
    assert is_authorized_for_legacy(action, grant)
    assert not is_authorized_for_legacy({"capability": "code.edit"}, grant)
