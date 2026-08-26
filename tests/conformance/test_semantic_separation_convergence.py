from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cross_layer_separation_contracts_are_registered() -> None:
    text = (ROOT / "docs" / "responsibility-separation-contracts.md").read_text(
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
        assert contract_id in text

    assert "Framework judgment" in text
    assert "GovernedApplication" in text
    assert "epistemic_status=supported" in text
    assert "PolicyDecision=allow" in text
    assert "existing_assignment_use_allowed" in text
    assert "Governance admissibility validation does not prove external source truth" in text


def test_runtime_docs_declare_ratio_as_canonical_owner() -> None:
    implementation = (
        ROOT / "docs" / "distinction-governance-implementation.md"
    ).read_text(encoding="utf-8")
    contracts = (ROOT / "docs" / "responsibility-separation-contracts.md").read_text(
        encoding="utf-8"
    )

    assert "xiongweilin/ratio/责任拓扑" in implementation
    assert "xiongweilin/ratio/责任拓扑" in contracts
    assert "does not keep local canonical" in implementation
    assert "MUST NOT be recreated as canonical" in contracts
