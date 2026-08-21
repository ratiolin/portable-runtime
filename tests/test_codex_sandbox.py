from __future__ import annotations

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
    assert metadata["sandbox_override"] == "forbidden"
