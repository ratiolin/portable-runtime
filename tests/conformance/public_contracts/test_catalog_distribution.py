from __future__ import annotations

from pathlib import Path

from portable_runtime.public_contracts.catalog import _catalog_path, contract_catalog


def test_contract_catalog_resolves_and_keeps_canonical_owner() -> None:
    catalog_path = _catalog_path()
    assert catalog_path.name == "catalog.toml"
    assert catalog_path.is_file()
    catalog = contract_catalog()
    assert catalog["catalog_version"] == "portable-runtime-contracts-v1"
    assert catalog["owner"] == "portable-runtime/contracts"


def test_wheel_build_declares_canonical_contract_distribution_copy() -> None:
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert '[tool.hatch.build.targets.wheel.force-include]' in text
    assert '"contracts" = "portable_runtime/_contracts"' in text
