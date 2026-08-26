from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cross_layer_separation_contracts_are_canonically_registered() -> None:
    canonical = (
        ROOT / "contracts" / "semantics" / "core" / "responsibility-separation-v1.md"
    ).read_text(encoding="utf-8")
    readable = (ROOT / "docs" / "responsibility-separation-contracts.md").read_text(
        encoding="utf-8"
    )
    for contract_id in (
        "RSC-007",
        "RSC-008",
        "RSC-009",
        "RSC-010",
        "RSC-011",
        "RSC-012",
    ):
        assert contract_id in canonical
        assert contract_id in readable

    assert "GovernanceDecision" in canonical
    assert "GovernedApplication" in canonical
    assert "epistemic_status=supported" in canonical
    assert "PolicyDecision=allow" in canonical
    assert "existing_assignment_use_allowed" in canonical
    assert "Governance admissibility validation does not prove external source truth" in canonical


def test_runtime_docs_declare_local_contracts_as_canonical_owner() -> None:
    implementation = (
        ROOT / "docs" / "distinction-governance-implementation.md"
    ).read_text(encoding="utf-8")
    readable = (ROOT / "docs" / "responsibility-separation-contracts.md").read_text(
        encoding="utf-8"
    )

    assert "portable-runtime/contracts" in implementation
    assert "contracts/semantics/governance/distinction-governance-v1.md" in implementation
    assert "contracts/semantics/core/responsibility-separation-v1.md" in readable
    assert "If it conflicts with `contracts/`, `contracts/` wins" in readable
