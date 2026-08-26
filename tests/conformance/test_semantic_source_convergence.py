from pathlib import Path
import tomllib

from portable_runtime.governance.assignment import (
    existing_assignment_use_allowed,
    resolve_allowed,
)
from portable_runtime.governance.distinction import (
    DISTINCTION_GOVERNANCE_CONTRACT_VERSION as runtime_contract,
    DISTINCTION_GOVERNANCE_SOURCE_COMMIT as runtime_executable_baseline,
)
from portable_runtime.governance.semantic_sources import (
    ADOPTED_SEMANTIC_REVISION,
    DISTINCTION_GOVERNANCE_CONTRACT_VERSION,
    DISTINCTION_GOVERNANCE_EXECUTABLE_BASELINE_COMMIT,
    FRAMEWORK_SOURCE_REPOSITORY,
    FRAMEWORK_VERSION,
)


ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> dict[str, object]:
    with (ROOT / "semantic-sources.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_manifest_matches_runtime_and_semantic_source_pins() -> None:
    manifest = _manifest()
    framework = manifest["framework"]
    distinction = manifest["distinction_governance"]

    assert isinstance(framework, dict)
    assert isinstance(distinction, dict)
    assert framework["repository"] == FRAMEWORK_SOURCE_REPOSITORY
    assert framework["version"] == FRAMEWORK_VERSION
    assert framework["adopted_semantic_revision"] == ADOPTED_SEMANTIC_REVISION
    assert distinction["contract"] == DISTINCTION_GOVERNANCE_CONTRACT_VERSION
    assert distinction["contract"] == runtime_contract
    assert (
        distinction["executable_baseline_commit"]
        == DISTINCTION_GOVERNANCE_EXECUTABLE_BASELINE_COMMIT
        == runtime_executable_baseline
    )
    assert distinction["adopted_semantic_revision"] == ADOPTED_SEMANTIC_REVISION


def test_duplicate_canonical_framework_documents_are_absent() -> None:
    assert not (ROOT / "docs" / "responsibility-record-plane.md").exists()
    assert not (ROOT / "docs" / "action-responsibility-practice.md").exists()


def test_existing_assignment_api_is_exact_compatibility_alias() -> None:
    assert existing_assignment_use_allowed is resolve_allowed
