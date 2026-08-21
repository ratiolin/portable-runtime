"""Codex provider wrapping the existing Codex CLI execution.

Core never imports this module; it is discovered via ProviderRegistry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, Protocol

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.process import PortableSubprocessExecutor, ProcessExecutor, ProcessSpec
from portable_runtime.stores.filesystem import FilesystemArtifactStore

logger = logging.getLogger(__name__)

SandboxProfile = Literal["read-only", "workspace-write"]


class PreparedExecutionBoundary(Protocol):
    """Structural contract for one isolated Codex process invocation."""

    @property
    def cwd(self) -> Path: ...

    @property
    def env(self) -> Mapping[str, str]: ...

    def cleanup(self) -> None: ...


class ExecutionBoundary(Protocol):
    """Injectable deployment boundary; kept provider-neutral by design."""

    session_dir: Path

    def prepare(self, repo: str, sandbox: SandboxProfile) -> PreparedExecutionBoundary: ...

    def redact_transcript(self, text: str) -> str: ...

# The capability is the authority for the Codex process sandbox.  Keep the
# default mapping immutable so callers cannot widen it at runtime; an explicit
# deployment mapping may only tighten a write-capable capability to read-only.
CODEX_SANDBOX_BY_CAPABILITY: Final[Mapping[str, SandboxProfile]] = MappingProxyType(
    {
        "reason.generate": "read-only",
        "code.read": "read-only",
        "git.diff": "read-only",
        "code.edit": "workspace-write",
        "code.test": "workspace-write",
        "shell.exec": "workspace-write",
    }
)
_ALLOWED_CODEX_SANDBOXES = frozenset({"read-only", "workspace-write"})


def sandbox_for_capability(capability: str) -> SandboxProfile:
    """Return the least-privilege Codex sandbox for a capability.

    Unknown capabilities fail closed to ``read-only``.  ``danger-full-access``
    is intentionally not an accepted profile value for the portable provider;
    real remote/deployment effects belong to a separate Provider behind the
    Runtime RealityBoundary.
    """

    return CODEX_SANDBOX_BY_CAPABILITY.get(capability, "read-only")


def _validate_sandbox_overrides(overrides: Mapping[str, str] | None) -> dict[str, SandboxProfile]:
    """Validate deployment overrides without allowing a capability widening.

    The canonical capability mapping is the authority.  Overrides are useful
    for a more constrained deployment (for example, running ``code.test`` in
    a read-only sandbox), but they can never turn a canonical read-only or
    unknown capability into ``workspace-write``.
    """

    validated: dict[str, SandboxProfile] = {}
    for capability, sandbox in (overrides or {}).items():
        if sandbox == "read-only":
            validated[capability] = "read-only"
            continue
        if sandbox == "workspace-write":
            canonical = sandbox_for_capability(capability)
            if canonical != "workspace-write":
                raise ValueError(
                    f"Codex sandbox override for {capability!r} would widen the canonical "
                    f"{canonical!r} sandbox to 'workspace-write'"
                )
            validated[capability] = "workspace-write"
            continue
        raise ValueError(
            f"unsupported Codex sandbox {sandbox!r} for {capability!r}; "
            f"allowed={sorted(_ALLOWED_CODEX_SANDBOXES)}"
        )
    return validated


def _resolve_cli(explicit: str | Path | None) -> Path:
    if explicit:
        return Path(explicit)
    found = shutil.which("codex.cmd") or shutil.which("codex")
    return Path(found) if found else Path("codex")


class CodexProvider:
    """Wraps `codex exec` as a CapabilityProvider.

    Capabilities:
      - reason.generate
      - code.read
      - code.edit
      - code.test
      - shell.exec
      - git.diff
    """

    def __init__(
        self,
        *,
        provider_id: str = "codex-primary",
        model: str = "opencode-go/deepseek-v4-flash",
        cli: str | Path | None = None,
        working_directory: str | Path | None = None,
        timeout_seconds: float | None = None,
        executor: ProcessExecutor | None = None,
        artifact_store: FilesystemArtifactStore | None = None,
        gateway_base_url: str | None = None,
        sandbox_by_capability: Mapping[str, str] | None = None,
        execution_boundary: ExecutionBoundary | None = None,
    ) -> None:
        self._cli = _resolve_cli(cli)
        self._model = model
        self._working_directory = Path(working_directory) if working_directory else None
        self._timeout = timeout_seconds
        self._executor: ProcessExecutor = executor or PortableSubprocessExecutor()
        self._artifact_store = artifact_store
        self._gateway_base_url = gateway_base_url
        # Deployment-specific process isolation is injected by the application;
        # the provider itself remains independent of control-plane modules.
        self._execution_boundary = execution_boundary
        self._sandbox_by_capability: dict[str, SandboxProfile] = dict(CODEX_SANDBOX_BY_CAPABILITY)
        self._sandbox_overrides = _validate_sandbox_overrides(sandbox_by_capability)
        self._sandbox_by_capability.update(self._sandbox_overrides)
        self._descriptor = ProviderDescriptor(
            id=provider_id,
            name="Codex Provider",
            version="1.0.0",
            capabilities=[
                "reason.generate",
                "code.read",
                "code.edit",
                "code.test",
                "shell.exec",
                "git.diff",
            ],
            priority=10,
            tags={"external-tool", "supports-files"},
            constraints={},
            metadata={
                "model": model,
                "cli": str(self._cli),
                "gateway_base_url": gateway_base_url or "",
                "sandbox_by_capability": dict(CODEX_SANDBOX_BY_CAPABILITY),
                "unknown_capability_sandbox": "read-only",
                "sandbox_override": "tighten-only",
                "sandbox_overrides": dict(self._sandbox_overrides),
            },
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        # Probe codex --version; do not fail runtime on missing CLI.
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self._cli),
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            except TimeoutError:
                try:  # noqa: SIM105,S110
                    proc.kill()
                except Exception:  # noqa: S110
                    pass  # noqa: S110
                return ProviderHealth(provider_id=self.descriptor.id, available=False, detail="codex version probe timed out")  # noqa: E501
            out = (stdout or b"").decode("utf-8", errors="replace").strip()
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            if proc.returncode == 0 and out:
                # Optional gateway probe (non-blocking)
                detail = out.splitlines()[0][:200]
                if self._gateway_base_url:
                    detail += f" gateway={self._gateway_base_url}"
                return ProviderHealth(provider_id=self.descriptor.id, available=True, detail=detail)
            return ProviderHealth(
                provider_id=self.descriptor.id,
                available=False,
                detail=f"codex version probe failed exit {proc.returncode}: {(err or out)[:300]}",
            )
        except FileNotFoundError as exc:
            return ProviderHealth(provider_id=self.descriptor.id, available=False, detail=f"codex not found at {self._cli}: {exc}")  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(provider_id=self.descriptor.id, available=False, detail=str(exc)[:500])

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        # Build prompt: prefer instruction, else parameters.prompt
        prompt = request.instruction or str(request.parameters.get("prompt", "") or "")
        if not prompt:
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "invalid_request", "message": "CodexProvider requires instruction or parameters.prompt"},
            )
        repo = str(request.parameters.get("repo", "") or self._working_directory or "")
        # Use provider-level model unless overridden per-request
        model = str(request.parameters.get("model", self._model))
        sandbox = self._sandbox_by_capability.get(request.capability, "read-only")
        cwd = Path(repo) if repo else (self._working_directory or Path.cwd())
        boundary = None
        if self._execution_boundary is not None:
            boundary = self._execution_boundary.prepare(str(cwd), sandbox)
            cwd = boundary.cwd
        # Ensure session dir for transcript.  Keep transcripts outside the
        # ephemeral worktree when a deployment boundary is supplied.
        if self._execution_boundary is not None:
            session_dir = self._execution_boundary.session_dir
        else:
            session_dir = cwd / "data" / "agent-sessions" if cwd else Path("data/agent-sessions")
        # Fallback to portable artifact dir if repo not set
        try:  # noqa: SIM105,S110
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: S110
            pass  # noqa: S110
        argv = [str(self._cli), "exec", "--model", model, "--sandbox", sandbox, "--skip-git-repo-check", "--json", prompt]  # noqa: E501
        # Normalize Windows path for cwd (same as control_plane.codex_runner.repo_path_to_windows)
        import os

        cwd_str = str(cwd)
        if os.name == "nt":
            cwd_str = cwd_str.replace("/", "\\")
        spec = ProcessSpec(
            argv=argv,
            cwd=Path(cwd_str) if cwd_str else None,
            env=dict(boundary.env) if boundary is not None else None,
            timeout_seconds=request.timeout_seconds or self._timeout or 900,
        )
        # Optional preflight
        try:
            health = await self.health()
            if not health.available and (
                "not found" in health.detail.lower() or "probe failed" in health.detail.lower()
            ):  # noqa: SIM102
                pass
            result = await self._executor.run(spec)
        except BaseException:
            if boundary is not None:
                boundary.cleanup()
            raise
        if result.timed_out:
            if boundary is not None:
                boundary.cleanup()
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "timeout", "message": "codex session timed out", "stderr": result.stderr[-2000:]},
                metadata={"duration_ms": result.duration_ms, "sandbox": sandbox, "capability": request.capability},
            )
        # Persist transcript as artifact if available
        artifact_refs: list[str] = []
        if result.stdout and self._artifact_store is not None:
            try:
                uri = self._artifact_store.put(result.stdout.encode("utf-8"), media_type="application/jsonl")
                artifact_refs.append(uri)
            except Exception:
                logger.debug("failed to store codex transcript", exc_info=True)
        # Also write to session dir for legacy parity (best-effort)
        if result.stdout:
            try:
                run_id = request.run_id or context.run_id or "unknown"
                jsonl_path = session_dir / f"{request.id}.jsonl"
                header = json.dumps({"type": "control_plane_meta", "run_id": run_id, "request_id": request.id, "started_at": int(time.time())}, ensure_ascii=False)  # noqa: E501
                # Apply redaction similar to control_plane.audit.redact_text
                try:
                    if self._execution_boundary is not None:
                        stored = self._execution_boundary.redact_transcript(result.stdout)
                    else:
                        stored = result.stdout[:200_000]
                except Exception:
                    stored = result.stdout[:200_000]
                jsonl_path.write_text(header + "\n" + stored, encoding="utf-8")
            except Exception:
                logger.debug("failed to write codex session jsonl", exc_info=True)
        if result.exit_code != 0:
            if boundary is not None:
                boundary.cleanup()
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "codex_exit", "exit_code": result.exit_code, "stderr": result.stderr[-2000:]},
                output_artifact_refs=artifact_refs,
                message=result.stdout[:20000] if result.stdout else result.stderr[:5000],
                metadata={
                    "duration_ms": result.duration_ms,
                    "exit_code": result.exit_code,
                    "sandbox": sandbox,
                    "capability": request.capability,
                },
            )
        if boundary is not None:
            boundary.cleanup()
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            output_artifact_refs=artifact_refs,
            message=result.stdout[:20000],
            metadata={
                "duration_ms": result.duration_ms,
                "model": model,
                "sandbox": sandbox,
                "capability": request.capability,
            },
        )

    async def cancel(self, request_id: str) -> None:
        # Best-effort: Codex exec is not cancellable via explicit API; tree kill handled by executor timeout.
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        """Codex has no remote operation ledger to reconcile."""

        return None

def create_codex_provider_from_toml(path: Path, provider_id: str = "codex-primary") -> CodexProvider:
    """Factory reading [[providers]] with type=codex from a TOML file."""
    import tomllib

    data: dict = {}
    if path.is_file():
        with path.open("rb") as f:
            data = tomllib.load(f)
    providers = [p for p in data.get("providers", []) if isinstance(p, dict) and p.get("id") == provider_id]
    cfg = providers[0].get("config", {}) if providers else {}
    # Fallback to legacy [agent] section
    agent = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
    model = str(cfg.get("model") or agent.get("model") or "opencode-go/deepseek-v4-flash")
    cli = cfg.get("cli") or agent.get("codex_cli") or ""
    gateway = cfg.get("gateway_base_url") or agent.get("gateway_base_url") or ""
    return CodexProvider(provider_id=provider_id, model=model, cli=cli, gateway_base_url=gateway)



