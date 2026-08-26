"""Registry-configured reconciliation repeatability authority.

This module answers one narrow question: whether repeating the reconciliation
query for one exact historical request-id subject is eligible under the exact
configured-provider execution binding and reconciliation protocol contract that
owned the original dispatch.

The objects here do not call providers and do not grant provider.invoke,
provider.reconcile, retry, fresh invocation, or recovery-consumer authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import Event
from portable_runtime.governance.provider_execution_binding import (
    ProviderExecutionBinding,
    provider_execution_binding_from_dispatch,
)

RECONCILIATION_REPEATABILITY_CONTRACT_SCHEMA = "reconciliation-repeatability-contract-v1"
RECONCILIATION_REPEATABILITY_AUTHORITY_SCHEMA = "reconciliation-repeatability-authority-v1"
RECONCILIATION_SUBJECT_MODEL = "request-id"
DISPATCH_COMMIT_EVENT = "InvocationDispatchCommitted"

RepeatabilityMode = Literal["repeat-safe", "non-repeat-safe", "unknown"]


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _sha256(value: object) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode()).hexdigest()


class ReconciliationRepeatabilityConfiguration(BaseModel):
    """Configured reconciliation semantics; not durable authority by itself.

    This is accepted only through ProviderRegistry registration. It deliberately
    has no caller-supplied digest and no subject identity. The registry binds it
    to the exact ProviderExecutionBinding; governed dispatch later binds the
    resulting contract to the exact request-id subject.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_model: Literal["request-id"] = RECONCILIATION_SUBJECT_MODEL
    reconciliation_protocol_identity: str = Field(min_length=1)
    reconciliation_protocol_version: str = Field(min_length=1)
    repeatability_mode: RepeatabilityMode = "repeat-safe"
    contract_version: str = Field(min_length=1)


class ReconciliationRepeatabilityContract(BaseModel):
    """Self-validating configured contract bound to one exact B identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    provider_execution_binding_ref: str = Field(min_length=1)
    subject_model: Literal["request-id"] = RECONCILIATION_SUBJECT_MODEL
    reconciliation_protocol_identity: str = Field(min_length=1)
    reconciliation_protocol_version: str = Field(min_length=1)
    repeatability_mode: RepeatabilityMode
    contract_version: str = Field(min_length=1)
    contract_digest: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_integrity(self) -> ReconciliationRepeatabilityContract:
        expected = _contract_digest(
            provider_execution_binding_ref=self.provider_execution_binding_ref,
            subject_model=self.subject_model,
            reconciliation_protocol_identity=self.reconciliation_protocol_identity,
            reconciliation_protocol_version=self.reconciliation_protocol_version,
            repeatability_mode=self.repeatability_mode,
            contract_version=self.contract_version,
        )
        if self.contract_digest != expected:
            raise ValueError("reconciliation repeatability contract digest mismatch")
        if self.id != f"reconciliation_repeatability_contract_{expected}":
            raise ValueError("reconciliation repeatability contract identity mismatch")
        return self


class ReconciliationRepeatabilityAuthority(BaseModel):
    """Exact historical repeat-safe query authority for one request-id subject.

    This is an eligibility/provenance object only. It owns no execution method
    and cannot itself invoke, reconcile, retry, or materialize a fresh request.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    contract_ref: str = Field(min_length=1)
    provider_execution_binding_ref: str = Field(min_length=1)
    subject_model: Literal["request-id"] = RECONCILIATION_SUBJECT_MODEL
    subject_identity: str = Field(min_length=1)
    reconciliation_protocol_identity: str = Field(min_length=1)
    reconciliation_protocol_version: str = Field(min_length=1)
    repeatability_mode: Literal["repeat-safe"] = "repeat-safe"
    contract_version: str = Field(min_length=1)
    contract_digest: str = Field(min_length=1)
    authority_digest: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_integrity(self) -> ReconciliationRepeatabilityAuthority:
        expected = _authority_digest(
            contract_ref=self.contract_ref,
            provider_execution_binding_ref=self.provider_execution_binding_ref,
            subject_model=self.subject_model,
            subject_identity=self.subject_identity,
            reconciliation_protocol_identity=self.reconciliation_protocol_identity,
            reconciliation_protocol_version=self.reconciliation_protocol_version,
            repeatability_mode=self.repeatability_mode,
            contract_version=self.contract_version,
            contract_digest=self.contract_digest,
        )
        if self.authority_digest != expected:
            raise ValueError("reconciliation repeatability authority digest mismatch")
        if self.id != f"reconciliation_repeatability_authority_{expected}":
            raise ValueError("reconciliation repeatability authority identity mismatch")
        return self


@dataclass(frozen=True)
class ReconciliationRepeatabilityEligibility:
    status: Literal["eligible", "ineligible"]
    eligible: bool
    reason: str = ""


def _contract_digest(
    *,
    provider_execution_binding_ref: str,
    subject_model: str,
    reconciliation_protocol_identity: str,
    reconciliation_protocol_version: str,
    repeatability_mode: str,
    contract_version: str,
) -> str:
    return _sha256(
        {
            "schema": RECONCILIATION_REPEATABILITY_CONTRACT_SCHEMA,
            "provider_execution_binding_ref": provider_execution_binding_ref,
            "subject_model": subject_model,
            "reconciliation_protocol_identity": reconciliation_protocol_identity,
            "reconciliation_protocol_version": reconciliation_protocol_version,
            "repeatability_mode": repeatability_mode,
            "contract_version": contract_version,
        }
    )


def _authority_digest(
    *,
    contract_ref: str,
    provider_execution_binding_ref: str,
    subject_model: str,
    subject_identity: str,
    reconciliation_protocol_identity: str,
    reconciliation_protocol_version: str,
    repeatability_mode: str,
    contract_version: str,
    contract_digest: str,
) -> str:
    return _sha256(
        {
            "schema": RECONCILIATION_REPEATABILITY_AUTHORITY_SCHEMA,
            "contract_ref": contract_ref,
            "provider_execution_binding_ref": provider_execution_binding_ref,
            "subject_model": subject_model,
            "subject_identity": subject_identity,
            "reconciliation_protocol_identity": reconciliation_protocol_identity,
            "reconciliation_protocol_version": reconciliation_protocol_version,
            "repeatability_mode": repeatability_mode,
            "contract_version": contract_version,
            "contract_digest": contract_digest,
        }
    )


def build_reconciliation_repeatability_contract(
    binding: ProviderExecutionBinding,
    configuration: ReconciliationRepeatabilityConfiguration,
) -> ReconciliationRepeatabilityContract:
    """Bind configured reconciliation semantics to one exact B identity."""

    digest = _contract_digest(
        provider_execution_binding_ref=binding.id,
        subject_model=configuration.subject_model,
        reconciliation_protocol_identity=configuration.reconciliation_protocol_identity,
        reconciliation_protocol_version=configuration.reconciliation_protocol_version,
        repeatability_mode=configuration.repeatability_mode,
        contract_version=configuration.contract_version,
    )
    return ReconciliationRepeatabilityContract(
        id=f"reconciliation_repeatability_contract_{digest}",
        provider_execution_binding_ref=binding.id,
        subject_model=configuration.subject_model,
        reconciliation_protocol_identity=configuration.reconciliation_protocol_identity,
        reconciliation_protocol_version=configuration.reconciliation_protocol_version,
        repeatability_mode=configuration.repeatability_mode,
        contract_version=configuration.contract_version,
        contract_digest=digest,
    )


def build_reconciliation_repeatability_authority(
    contract: ReconciliationRepeatabilityContract,
    *,
    subject_identity: str,
) -> ReconciliationRepeatabilityAuthority:
    """Instantiate a positive exact-subject authority from a configured contract."""

    subject = subject_identity.strip()
    if not subject:
        raise ValueError("reconciliation repeatability authority requires exact subject identity")
    if contract.subject_model != RECONCILIATION_SUBJECT_MODEL:
        raise ValueError("unsupported reconciliation repeatability subject model")
    if contract.repeatability_mode != "repeat-safe":
        raise ValueError("only an explicit repeat-safe contract can establish positive authority")
    digest = _authority_digest(
        contract_ref=contract.id,
        provider_execution_binding_ref=contract.provider_execution_binding_ref,
        subject_model=contract.subject_model,
        subject_identity=subject,
        reconciliation_protocol_identity=contract.reconciliation_protocol_identity,
        reconciliation_protocol_version=contract.reconciliation_protocol_version,
        repeatability_mode="repeat-safe",
        contract_version=contract.contract_version,
        contract_digest=contract.contract_digest,
    )
    return ReconciliationRepeatabilityAuthority(
        id=f"reconciliation_repeatability_authority_{digest}",
        contract_ref=contract.id,
        provider_execution_binding_ref=contract.provider_execution_binding_ref,
        subject_model=contract.subject_model,
        subject_identity=subject,
        reconciliation_protocol_identity=contract.reconciliation_protocol_identity,
        reconciliation_protocol_version=contract.reconciliation_protocol_version,
        repeatability_mode="repeat-safe",
        contract_version=contract.contract_version,
        contract_digest=contract.contract_digest,
        authority_digest=digest,
    )


def reconciliation_repeatability_authority_from_dispatch(
    event: Event,
) -> ReconciliationRepeatabilityAuthority:
    """Decode only an exact B-bound, request-bound historical C authority."""

    if event.type != DISPATCH_COMMIT_EVENT:
        raise ValueError("reconciliation repeatability authority requires InvocationDispatchCommitted")
    payload = event.payload if isinstance(event.payload, dict) else {}
    raw = payload.get("reconciliation_repeatability_authority")
    authority_ref = payload.get("reconciliation_repeatability_authority_ref")
    if not isinstance(raw, dict) or not isinstance(authority_ref, str) or not authority_ref:
        raise ValueError(
            "historical dispatch has no original reconciliation repeatability authority; backfill unsupported"
        )
    authority = ReconciliationRepeatabilityAuthority.model_validate(raw)
    if authority.id != authority_ref:
        raise ValueError("dispatch reconciliation repeatability authority ref mismatch")
    binding = provider_execution_binding_from_dispatch(event)
    if authority.provider_execution_binding_ref != binding.id:
        raise ValueError("reconciliation repeatability authority does not match historical execution binding")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("dispatch reconciliation repeatability subject is unavailable")
    if authority.subject_model != RECONCILIATION_SUBJECT_MODEL:
        raise ValueError("unsupported reconciliation repeatability subject model")
    if authority.subject_identity != request_id or event.subject_ref != request_id:
        raise ValueError("reconciliation repeatability authority subject mismatch")
    return authority


def evaluate_reconciliation_repeatability(
    historical_authority: ReconciliationRepeatabilityAuthority | None,
    *,
    historical_binding: ProviderExecutionBinding | None,
    current_contract: ReconciliationRepeatabilityContract | None,
    required_subject_identity: str,
) -> ReconciliationRepeatabilityEligibility:
    """Evaluate exact C eligibility without performing any reality operation."""

    if historical_authority is None:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "historical repeatability authority is absent",
        )
    if historical_binding is None:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "historical configured-provider execution binding is absent",
        )
    if historical_authority.provider_execution_binding_ref != historical_binding.id:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "repeatability authority does not bind the exact historical provider execution identity",
        )
    if historical_authority.subject_model != RECONCILIATION_SUBJECT_MODEL:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "unsupported reconciliation subject model",
        )
    if historical_authority.subject_identity != required_subject_identity:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "repeatability authority does not bind the exact reconciliation subject",
        )
    if current_contract is None:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "current configured repeatability contract is absent or not repeat-safe",
        )
    if current_contract.provider_execution_binding_ref != historical_binding.id:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "current repeatability contract targets a different provider execution binding",
        )
    if current_contract.repeatability_mode != "repeat-safe":
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "current configured reconciliation semantics are not repeat-safe",
        )
    try:
        current_authority = build_reconciliation_repeatability_authority(
            current_contract,
            subject_identity=required_subject_identity,
        )
    except ValueError as exc:
        return ReconciliationRepeatabilityEligibility("ineligible", False, str(exc))
    if current_authority != historical_authority:
        return ReconciliationRepeatabilityEligibility(
            "ineligible",
            False,
            "reconciliation protocol or repeatability contract drifted from historical authority",
        )
    return ReconciliationRepeatabilityEligibility(
        "eligible",
        True,
        "exact historical repeat-safe reconciliation query authority matches current configured contract",
    )
