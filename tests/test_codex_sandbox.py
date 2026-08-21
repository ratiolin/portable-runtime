from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderHealth
from portable_runtime.core.process import ProcessResult, ProcessSpec
from portable_runtime.providers.codex.provider import (
    CODEX_SANDBOX_BY_CAPABILITY,
    CodexProvider,
    sandbox_for_capability,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.specs: list[ProcessSpec] = []

    async def run(self, spec: ProcessSpec) -> ProcessResult:
        self.specs.append(spec)
        return ProcessResult(exit_code=0, stdout="ok", stderr="")


class _PreparedBoundary:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self.env = {"PORTABLE_RUNTIME_BOUNDARY": "1"}
        self.cleaned = False

    def cleanup(self) -> None:
        self.cleaned = True


class _InjectedBoundary:
    def __init__(self, session_dir: Path, cwd: Path) -> None:
        self.session_dir = session_dir
        self.prepared = _PreparedBoundary(cwd)

    def prepare(self, repo: str, sandbox: str) -> _PreparedBoundary:
        assert repo
        assert sandbox in {"read-only", "workspace-write"}
        return self.prepared

    @staticmethod
    def redact_transcript(text: str) -> str:
        return f"redacted:{text}"


@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        ("reason.generate", "read-only"),
        ("code.read", "read-only"),
        ("git.diff", "read-only"),
        ("code.edit", "workspace-write"),
        ("code.test", "workspace-write"),
        ("shell.exec", "workspace-write"),
        ("unknown.capability", "read-only"),
    ],
)
def test_sandbox_for_capability_fails_closed(capability: str, expected: str) -> None:
    assert sandbox_for_capability(capability) == expected


@pytest.mark.parametrize("capability", ["reason.generate", "code.read", "unknown.capability"])
def test_codex_provider_rejects_sandbox_widening(capability: str) -> None:
    with pytest.raises(ValueError, match="would widen"):
        CodexProvider(sandbox_by_capability={capability: "workspace-write"})


def test_codex_provider_allows_only_tightening_write_capabilities() -> None:
    provider = CodexProvider(sandbox_by_capability={"code.test": "read-only"})

    assert provider.descriptor.metadata["sandbox_override"] == "tighten-only"
    assert provider.descriptor.metadata["sandbox_overrides"] == {"code.test": "read-only"}


@pytest.mark.asyncio
async def test_codex_provider_uses_capability_mapping_and_rejects_override(tmp_path: Path) -> None:
    executor = _FakeExecutor()
    provider = CodexProvider(cli="codex", executor=executor, working_directory=tmp_path)

    async def health() -> ProviderHealth:
        return ProviderHealth(provider_id=provider.descriptor.id, available=True)

    provider.health = health  # type: ignore[method-assign]
    for capability, expected in (
        ("reason.generate", "read-only"),
        ("code.read", "read-only"),
        ("git.diff", "read-only"),
        ("code.edit", "workspace-write"),
        ("code.test", "workspace-write"),
        ("shell.exec", "workspace-write"),
        ("unknown.capability", "read-only"),
    ):
        result = await provider.invoke(
            CapabilityRequest(
                id=f"request-{capability}",
                capability=capability,
                instruction="test",
                parameters={"sandbox": "danger-full-access"},
            ),
            InvocationContext(runtime_id="test"),
        )
        assert result.status == "succeeded"
        argv = executor.specs[-1].argv
        assert argv[argv.index("--sandbox") + 1] == expected
        assert "danger-full-access" not in argv


def test_codex_manifest_declares_provider_neutral_sandbox_contract() -> None:
    manifest_path = Path(__file__).parents[1] / "src" / "portable_runtime" / "providers" / "codex" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = manifest["metadata"]
    assert metadata["sandbox_by_capability"] == CODEX_SANDBOX_BY_CAPABILITY
    assert metadata["unknown_capability_sandbox"] == "read-only"
    assert metadata["sandbox_override"] == "tighten-only"


@pytest.mark.asyncio
async def test_codex_provider_accepts_injected_execution_boundary(tmp_path: Path) -> None:
    executor = _FakeExecutor()
    boundary = _InjectedBoundary(tmp_path / "sessions", tmp_path / "isolated")
    provider = CodexProvider(
        cli="codex-not-installed",
        executor=executor,
        working_directory=tmp_path / "repo",
        execution_boundary=boundary,
    )

    result = await provider.invoke(
        CapabilityRequest(id="request-boundary", capability="code.edit", instruction="edit"),
        InvocationContext(runtime_id="test"),
    )

    assert result.status == "succeeded"
    assert executor.specs[-1].cwd == boundary.prepared.cwd
    assert executor.specs[-1].env == boundary.prepared.env
    assert boundary.prepared.cleaned


def test_codex_provider_has_no_control_plane_imports() -> None:
    provider_path = Path(__file__).parents[1] / "src" / "portable_runtime" / "providers" / "codex" / "provider.py"
    tree = ast.parse(provider_path.read_text(encoding="utf-8"), filename=str(provider_path))
    imported_modules = [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    imported_names = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert all(not module.startswith("control_plane") for module in imported_modules)
    assert all(not name.startswith("control_plane") for name in imported_names)
