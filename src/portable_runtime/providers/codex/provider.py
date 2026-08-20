"""Codex provider wrapping the existing Codex CLI execution.

Core never imports this module; it is discovered via ProviderRegistry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

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


def _resolve_cli(explicit: str | Path | None) -> Path:
    if explicit:
        return Path(explicit)
    # Reuse control_plane logic if available, else fallback to which
    try:
        from control_plane.config import resolve_codex_cli

        return resolve_codex_cli(str(explicit or ""))
    except Exception:
        import shutil

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
    ) -> None:
        self._cli = _resolve_cli(cli)
        self._model = model
        self._working_directory = Path(working_directory) if working_directory else None
        self._timeout = timeout_seconds
        self._executor: ProcessExecutor = executor or PortableSubprocessExecutor()
        self._artifact_store = artifact_store
        self._gateway_base_url = gateway_base_url
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
            metadata={"model": model, "cli": str(self._cli), "gateway_base_url": gateway_base_url or ""},
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
        cwd = Path(repo) if repo else (self._working_directory or Path.cwd())
        # Ensure session dir for transcript
        session_dir = cwd / "data" / "agent-sessions" if cwd else Path("data/agent-sessions")
        # Fallback to portable artifact dir if repo not set
        try:  # noqa: SIM105,S110
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: S110
            pass  # noqa: S110
        argv = [str(self._cli), "exec", "--model", model, "--sandbox", "danger-full-access", "--skip-git-repo-check", "--json", prompt]  # noqa: E501
        # Normalize Windows path for cwd (same as control_plane.codex_runner.repo_path_to_windows)
        import os

        cwd_str = str(cwd)
        if os.name == "nt":
            cwd_str = cwd_str.replace("/", "\\")
        spec = ProcessSpec(argv=argv, cwd=Path(cwd_str) if cwd_str else None, timeout_seconds=request.timeout_seconds or self._timeout or 900)  # noqa: E501
        # Optional preflight
        health = await self.health()
        if not health.available and ("not found" in health.detail.lower() or "probe failed" in health.detail.lower()):  # noqa: SIM102
            pass
        result = await self._executor.run(spec)
        if result.timed_out:
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "timeout", "message": "codex session timed out", "stderr": result.stderr[-2000:]},
                metadata={"duration_ms": result.duration_ms},
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
                    from control_plane.audit import redact_text, truncate_bytes

                    stored, _ = truncate_bytes(redact_text(result.stdout), 200_000)
                except Exception:
                    stored = result.stdout[:200_000]
                jsonl_path.write_text(header + "\n" + stored, encoding="utf-8")
            except Exception:
                logger.debug("failed to write codex session jsonl", exc_info=True)
        if result.exit_code != 0:
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "codex_exit", "exit_code": result.exit_code, "stderr": result.stderr[-2000:]},
                output_artifact_refs=artifact_refs,
                message=result.stdout[:20000] if result.stdout else result.stderr[:5000],
                metadata={"duration_ms": result.duration_ms, "exit_code": result.exit_code},
            )
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            output_artifact_refs=artifact_refs,
            message=result.stdout[:20000],
            metadata={"duration_ms": result.duration_ms, "model": model},
        )

    async def cancel(self, request_id: str) -> None:
        # Best-effort: Codex exec is not cancellable via explicit API; tree kill handled by executor timeout.
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



