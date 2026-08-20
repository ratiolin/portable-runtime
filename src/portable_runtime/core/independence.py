from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IndependenceContext(BaseModel):
    """Typed independence requirement - failure domain separation."""

    reference_provider_refs: list[str] = Field(default_factory=list, description="reference provider ids to be independent from")
    independent_on: list[str] = Field(default_factory=list, description="dimensions: provider_family, credential_domain, execution_domain, etc")

    def is_satisfied(self, candidate: Any, references: list[Any]) -> tuple[bool, str]:
        """Check candidate is independent from all references on all required dimensions. Fail-closed if missing."""
        for dim in self.independent_on:
            cand_val = getattr(candidate, dim, None)
            if cand_val is None and isinstance(candidate, dict):
                cand_val = candidate.get(dim)
            if cand_val is None:
                return False, f"candidate missing required domain {dim} -> ineligible (fail-closed)"
            for ref in references:
                ref_val = getattr(ref, dim, None)
                if ref_val is None and isinstance(ref, dict):
                    ref_val = ref.get(dim)
                if ref_val is None:
                    return False, f"reference missing domain {dim} -> ineligible (fail-closed)"
                if cand_val == ref_val:
                    return False, f"candidate {dim}={cand_val!r} equals reference {getattr(ref, 'id', '?')} {dim} -> not independent"
        return True, "independent"

    @classmethod
    def from_request(cls, request: Any) -> "IndependenceContext | None":
        meta = getattr(request, "metadata", {}) if hasattr(request, "metadata") else {}
        constraints = getattr(request, "constraints", {}) if hasattr(request, "constraints") else {}
        if isinstance(meta, dict):
            if "independence_context" in meta and isinstance(meta["independence_context"], dict):
                ic = meta["independence_context"]
                return cls(
                    reference_provider_refs=list(ic.get("reference_provider_refs") or []),
                    independent_on=list(ic.get("independent_on") or []),
                )
            ind = meta.get("independence_constraints") if isinstance(meta.get("independence_constraints"), dict) else None
            if ind:
                return cls(
                    reference_provider_refs=list(ind.get("reference_provider_refs") or ind.get("independent_from_provider_ids") or []),
                    independent_on=list(ind.get("independent_on") or []),
                )
        refs = constraints.get("reference_provider_refs") or constraints.get("independent_from_provider_ids") or []
        dims = constraints.get("independent_on") or constraints.get("required_independence") or []
        if refs or dims:
            if not dims and isinstance(meta, dict):
                ind2 = meta.get("independence_constraints", {}) if isinstance(meta.get("independence_constraints"), dict) else {}
                dims = ind2.get("independent_on") or []
                refs = refs or ind2.get("reference_provider_refs") or ind2.get("independent_from_provider_ids") or refs
            return cls(reference_provider_refs=list(refs), independent_on=list(dims))
        if isinstance(meta, dict):
            refs2 = meta.get("independent_from") or constraints.get("independent_from")
            if refs2:
                dims2 = meta.get("independent_on") or []
                return cls(reference_provider_refs=list(refs2) if isinstance(refs2, list) else [refs2], independent_on=list(dims2))
        return None
