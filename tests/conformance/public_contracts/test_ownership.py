from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ts", ".tsx", ".mjs"}


def _tracked_text() -> str:
    chunks: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in {".git", ".venv", "node_modules", "dist"} for part in path.parts):
            continue
        if path == Path(__file__):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_local_contract_root_is_present_and_legacy_sources_are_absent() -> None:
    assert (ROOT / "contracts" / "catalog.toml").exists()
    assert (ROOT / "contracts" / "semantics" / "core" / "ownership-v1.md").exists()
    assert (ROOT / "contracts" / "semantics" / "core" / "responsibility-separation-v1.md").exists()

    for relative in (
        "semantic-" + "sources.toml",
        "src/portable_runtime/governance/semantic_" + "sources.py",
        "docs/responsibility-record-plane.md",
        "docs/action-responsibility-practice.md",
    ):
        assert not (ROOT / relative).exists(), relative


def test_external_source_pin_model_cannot_reenter_active_tree() -> None:
    text = _tracked_text()
    banned = (
        "semantic-" + "sources.toml",
        "portable_runtime.governance.semantic_" + "sources",
        "DISTINCTION_GOVERNANCE_" + "SOURCE_COMMIT",
        "ef9e" + "490987ed47ebef3ac455851109304f24a97c",
        "10b6" + "f8d4de6f4e4a247a30ebd915136532cfd4f6",
        "canonical Framework semantics are " + "owned by",
        "canonical definitions live only " + "in ratio",
        "upstream framework " + "owns",
    )
    for token in banned:
        assert token not in text, token


def test_formal_relationship_is_explicitly_non_normative() -> None:
    text = (ROOT / "docs" / "formal-kernel-relationship.md").read_text(encoding="utf-8")
    assert "non-normative" in text.lower()
    assert "No external repository is a normative dependency" in text
    assert "portable-runtime/contracts/" in text
