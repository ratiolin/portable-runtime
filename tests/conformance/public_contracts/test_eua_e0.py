from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_eua_e0_remains_closed_after_public_contract_extraction() -> None:
    text = (ROOT / "docs" / "eua-e0-reassessment-after-public-contracts.md").read_text(
        encoding="utf-8"
    )
    assert "CLOSED / NOT OPENED" in text
    assert "ExperienceUseAdmission" in text
    assert "HistoricalExperienceUse" in text
    assert "implicit Decision" in text
    assert "implicit Authorization" in text
    assert "implicit InvocationPermit" in text
    assert "Do not implement EUA-E0 speculatively" in text
