from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request

from portable_runtime.api.http import create_app
from portable_runtime.core.runtime import Runtime
from portable_runtime.public_contracts.catalog import contract_catalog
from portable_runtime.public_contracts.experience import (
    commit_historical_experience_use_contract,
    evaluate_experience_use_contract,
    get_historical_experience_use_contract,
)
from portable_runtime.public_contracts.models import (
    ApiProblemV1,
    ExperienceUseAdmissionV1,
    ExperienceUseRequirementV1,
    HistoricalExperienceUseCommitV1,
    HistoricalExperienceUseV1,
)


def _problem(code: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ApiProblemV1(code=code, message=message, details=details or {}).model_dump(mode="json")


def _require_local_mutation(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else None
    if host not in {None, "127.0.0.1", "::1", "localhost", "testclient", "testserver"}:
        raise HTTPException(status_code=403, detail=_problem("LocalControlRequired", "mutating contract API is local-only"))


def contract_router(runtime: Runtime) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/contracts")
    def get_contracts() -> dict[str, Any]:
        return contract_catalog()

    @router.post("/v1/experience/use/evaluate", response_model=ExperienceUseAdmissionV1)
    def evaluate_experience(value: ExperienceUseRequirementV1) -> ExperienceUseAdmissionV1:
        try:
            return evaluate_experience_use_contract(runtime, value)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=_problem("InvalidContractInput", str(exc)),
            ) from exc

    @router.post("/v1/experience/historical-use/commit", response_model=HistoricalExperienceUseV1)
    def commit_historical_experience(
        value: HistoricalExperienceUseCommitV1,
        request: Request,
    ) -> HistoricalExperienceUseV1:
        _require_local_mutation(request)
        try:
            return commit_historical_experience_use_contract(runtime, value)
        except ValueError as exc:
            message = str(exc)
            code = "HistoricalUseCommitRejected"
            if "rebound" in message:
                code = "HistoricalUseIdentityRebound"
            elif "backfill" in message or "qualifies selected experience" in message:
                code = "HistoricalUseSelfQualificationForbidden"
            elif "changed" in message or "digest" in message:
                code = "HistoricalUseDigestMismatch"
            raise HTTPException(status_code=409, detail=_problem(code, message)) from exc

    @router.get("/v1/experience/historical-use/{judgment_id}", response_model=HistoricalExperienceUseV1)
    def historical_experience(judgment_id: str) -> HistoricalExperienceUseV1:
        value = get_historical_experience_use_contract(runtime, judgment_id)
        if value is None:
            raise HTTPException(
                status_code=404,
                detail=_problem("HistoricalUseNotFound", "historical experience use not found"),
            )
        return value

    return router


def create_public_app(runtime: Runtime | None = None) -> FastAPI:
    """Return the existing control-plane app with canonical contract routes attached."""

    runtime = runtime or Runtime()
    app = create_app(runtime)
    app.include_router(contract_router(runtime))
    return app
