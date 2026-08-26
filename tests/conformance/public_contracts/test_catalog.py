import json
from pathlib import Path
import tomllib

from portable_runtime.governance.distinction import (
    DISTINCTION_GOVERNANCE_CONTRACT_ID,
    DISTINCTION_GOVERNANCE_CONTRACT_VERSION,
)


ROOT = Path(__file__).resolve().parents[3]


def _catalog() -> dict[str, object]:
    with (ROOT / "contracts" / "catalog.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_catalog_owns_all_registered_contract_paths() -> None:
    catalog = _catalog()
    assert catalog["owner"] == "portable-runtime/contracts"
    assert catalog["catalog_version"] == "portable-runtime-contracts-v1"
    contracts = catalog["contracts"]
    assert isinstance(contracts, dict)
    for name, raw in contracts.items():
        assert isinstance(raw, dict), name
        for key in ("semantic_path", "schema_path"):
            relative = raw.get(key)
            if relative is not None:
                assert isinstance(relative, str), (name, key)
                assert (ROOT / relative).exists(), relative


def test_public_schemas_are_valid_local_json_schema_documents() -> None:
    contracts = _catalog()["contracts"]
    assert isinstance(contracts, dict)
    for name, raw in contracts.items():
        assert isinstance(raw, dict)
        relative = raw.get("schema_path")
        if relative is None:
            continue
        schema = json.loads((ROOT / str(relative)).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", name
        assert str(schema["$id"]).startswith("portable-runtime://contracts/"), name
        assert schema["type"] == "object", name


def test_every_public_view_is_non_authoritative() -> None:
    views = _catalog()["views"]
    assert isinstance(views, dict)
    assert views
    for name, raw in views.items():
        assert isinstance(raw, dict), name
        assert raw.get("authority_bearing") is False, name


def test_compiled_distinction_identity_matches_local_catalog() -> None:
    distinction = _catalog()["contracts"]["distinction_governance"]
    assert isinstance(distinction, dict)
    assert DISTINCTION_GOVERNANCE_CONTRACT_ID == "distinction-governance"
    assert distinction["current"] == DISTINCTION_GOVERNANCE_CONTRACT_VERSION
