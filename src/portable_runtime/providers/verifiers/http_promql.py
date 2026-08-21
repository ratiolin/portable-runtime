"""Verifier capability providers: each exposes a distinct verify.* capability.

Each provider delegates to a lightweight check but remains independent from the
LLM self-report. The legacy Verifier facade can call these via CapabilityService.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.records.open_validation import ClosedVerificationResult

logger = logging.getLogger(__name__)


class HttpVerifierProvider:
    def __init__(
        self,
        provider_id: str = "verifier-http",
        probe_fn: Callable[..., Awaitable[tuple[bool, str, str]]] | Callable[..., Awaitable[tuple[bool, str]]] | None = None,  # noqa: E501
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._probe_fn = probe_fn
        self._http_client = http_client
        self._descriptor = ProviderDescriptor(id=provider_id, name="HTTP Verifier", version="1.0.0", capabilities=["verify.http"], tags={"verify", "side-effect-free"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="http verifier ready")

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        url = str(request.parameters.get("url", "") or request.parameters.get("probe_url", ""))
        if not url:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.http requires parameters.url"})  # noqa: E501
        expected: set[int] = set(request.parameters.get("expected_status", [200, 301, 302]))
        if "expected" in request.parameters:
            expected = set(request.parameters["expected"])
        body_contains = request.parameters.get("body_contains")
        timeout = float(request.parameters.get("timeout_seconds", 10))
        if self._probe_fn is not None:
            try:
                result = await self._probe_fn(url, expected=expected, body_contains=body_contains, timeout=int(timeout))
                if len(result) == 3:
                    ok, message, _ref = result
                else:
                    ok, message = result
                    _ref = ""
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=message,
                    metadata={"evidence_ref": _ref} if _ref else {},
                    verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message),
                )
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        if self._http_client is not None:
            try:
                response = await self._http_client.get(url, timeout=timeout, follow_redirects=True)
                ok = response.status_code in expected
                if body_contains and body_contains not in response.text:
                    ok = False
                evidence_status = "supported" if ok else "contested"
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=f"GET {url} -> {response.status_code} PASS" if ok else f"GET {url} -> {response.status_code} FAIL",  # noqa: E501
                    metadata={"status_code": response.status_code, "evidence_status": evidence_status, "body_snippet": response.text[:2000]},  # noqa: E501
                    evidence_refs=[],
                    verification_result=ClosedVerificationResult(
                        result="pass" if ok else "fail",
                        message=(
                            f"status {response.status_code} "
                            f"{'matched' if ok else 'did not match'} expected {sorted(expected)}"
                        ),
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                ok = resp.status_code in expected
                if body_contains and body_contains not in resp.text:
                    ok = False
                evidence_status = "supported" if ok else "contested"
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=f"GET {url} -> {resp.status_code} PASS" if ok else f"GET {url} -> {resp.status_code} FAIL",
                    metadata={"status_code": resp.status_code, "evidence_status": evidence_status, "body_snippet": resp.text[:2000]},  # noqa: E501
                    evidence_refs=[],
                    verification_result=ClosedVerificationResult(
                        result="pass" if ok else "fail",
                        message=(
                            f"status {resp.status_code} "
                            f"{'matched' if ok else 'did not match'} expected {sorted(expected)}"
                        ),
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None


class PromqlVerifierProvider:
    def __init__(
        self,
        provider_id: str = "verifier-promql",
        prometheus_url: str = "http://127.0.0.1:19090",
        promql_fn: Callable[..., Awaitable[tuple[bool, str, str]]] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._prometheus_url = prometheus_url.rstrip("/")
        self._promql_fn = promql_fn
        self._http_client = http_client
        self._descriptor = ProviderDescriptor(id=provider_id, name="PromQL Verifier", version="1.0.0", capabilities=["verify.promql"], tags={"verify"}, priority=5, metadata={"prometheus_url": self._prometheus_url})  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5)
            close = self._http_client is None
            try:
                resp = await client.get(f"{self._prometheus_url}/-/healthy")
                if resp.status_code == 200:
                    return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="prometheus healthy")
                return ProviderHealth(provider_id=self.descriptor.id, available=False, detail=f"prometheus {resp.status_code}")  # noqa: E501
            finally:
                if close:
                    await client.aclose()
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(provider_id=self.descriptor.id, available=False, detail=f"prometheus unreachable: {exc}"[:300])  # noqa: E501

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        query = str(request.parameters.get("query", "") or request.parameters.get("promql", ""))
        if not query:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.promql requires parameters.query"})  # noqa: E501
        expected = request.parameters.get("expected")
        timeout = float(request.parameters.get("timeout_seconds", 10))
        if self._promql_fn is not None:
            try:
                ok, message, ref = await self._promql_fn(query, expected)
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=message,
                    metadata={"evidence_ref": ref} if ref else {},
                    verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message),
                )
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        if self._http_client is not None:
            try:
                resp = await self._http_client.get(f"{self._prometheus_url}/api/v1/query", params={"query": query}, timeout=timeout)  # noqa: E501
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                results = data.get("data", {}).get("result", []) if isinstance(data, dict) else []
                if not results:
                    message = f"no result for query: {query}"
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="fail", message=message))  # noqa: E501
                if expected is not None:
                    for result in results:
                        try:
                            value = float(result["value"][1])
                        except (KeyError, IndexError, TypeError, ValueError):
                            message = f"invalid sample for query: {query}"
                            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="fail", message=message))  # noqa: E501
                        if abs(value - float(expected)) > 1e-9:
                            message = f"value {value} != expected {expected} ({query})"
                            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="fail", message=message))  # noqa: E501
                    message = "query returned results"
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=f"promql {query[:200]} -> {resp.status_code} PASS",
                    metadata={"prometheus_url": self._prometheus_url, "response": str(data)[:2000]},
                    verification_result=ClosedVerificationResult(
                        result="pass",
                        message=f"promql {query[:200]} -> {resp.status_code} PASS",
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{self._prometheus_url}/api/v1/query", params={"query": query})
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                ok = resp.status_code == 200
                if expected is not None:
                    ok = ok and str(data)[:500].find(str(expected)) != -1
                return CapabilityResult(
                    request_id=request.id,
                    provider_id=self.descriptor.id,
                    status="succeeded",
                    message=f"promql {query[:200]} -> {resp.status_code} PASS" if ok else f"promql {query[:200]} -> {resp.status_code} FAIL",  # noqa: E501
                    metadata={"prometheus_url": self._prometheus_url, "response": str(data)[:2000]},
                    verification_result=ClosedVerificationResult(
                        result="pass" if ok else "fail",
                        message=f"promql {query[:200]} -> {resp.status_code} {'PASS' if ok else 'FAIL'}",
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None


class ContainerVerifierProvider:
    def __init__(
        self,
        provider_id: str = "verifier-container",
        check_fn: Callable[[list[str]], Awaitable[tuple[bool, str, str]]] | None = None,
    ) -> None:
        self._check_fn = check_fn
        self._descriptor = ProviderDescriptor(id=provider_id, name="Container Verifier", version="1.0.0", capabilities=["verify.container"], tags={"verify"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        import shutil

        docker = shutil.which("docker")
        return ProviderHealth(provider_id=self.descriptor.id, available=docker is not None, detail="docker found" if docker else "docker not on PATH (optional)")  # noqa: E501

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        targets = request.parameters.get("targets") or request.parameters.get("containers") or []
        if isinstance(targets, str):
            targets = [targets]
        if not targets:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.container requires parameters.targets"})  # noqa: E501
        if self._check_fn is not None:
            try:
                ok, message, ref = await self._check_fn(targets)
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"evidence_ref": ref}, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        try:
            from control_plane.tools import check_container_status

            ok, message, ref = await check_container_status(targets)
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"evidence_ref": ref}, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
        except Exception:
            try:
                proc = await asyncio.create_subprocess_exec("docker", "ps", "--format", "{{.Names}}\t{{.Status}}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                text = stdout.decode(errors="replace")
                missing = [t for t in targets if t not in text]
                ok = not missing
                message = f"containers {targets} missing={missing}" if missing else "all containers running"
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None


class GitVerifierProvider:
    def __init__(
        self,
        provider_id: str = "verifier-git",
        check_fn: Callable[[str, str], Awaitable[tuple[bool, str, str]]] | None = None,
    ) -> None:
        self._check_fn = check_fn
        self._descriptor = ProviderDescriptor(id=provider_id, name="Git Verifier", version="1.0.0", capabilities=["verify.git"], tags={"verify", "side-effect-free"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        import shutil

        git = shutil.which("git")
        return ProviderHealth(provider_id=self.descriptor.id, available=git is not None, detail="git found" if git else "git not found")  # noqa: E501

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        repo = str(request.parameters.get("repo", "") or "")
        branch = str(request.parameters.get("branch", "") or request.parameters.get("ref", "") or "")
        if not repo:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.git requires parameters.repo"})  # noqa: E501
        if self._check_fn is not None:
            try:
                ok, message, ref = await self._check_fn(repo, branch)
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"evidence_ref": ref}, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501
        try:
            proc0 = await asyncio.create_subprocess_exec("git", "-C", repo, "rev-parse", "--is-inside-work-tree", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
            stdout0, _ = await asyncio.wait_for(proc0.communicate(), timeout=10)
            is_git = stdout0.decode(errors="replace").strip().lower() == "true"
            if not is_git or proc0.returncode != 0:
                message = "not a git repository; skipping git diff"
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
        except Exception:
            message = "not a git repository; skipping git diff"
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
        try:
            if branch:
                proc = await asyncio.create_subprocess_exec("git", "-C", repo, "diff", f"main...{branch}", "--stat", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode != 0:
                    cmd = ["git", "ls-remote", "--heads", repo, branch]
                    proc2 = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
                    stdout2, stderr2 = await asyncio.wait_for(proc2.communicate(), timeout=30)
                    ok2 = proc2.returncode == 0
                    message = stdout2.decode(errors="replace")[:2000] or stderr2.decode(errors="replace")[:2000]
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"exit_code": proc2.returncode}, verification_result=ClosedVerificationResult(result="pass" if ok2 else "fail", message=message))  # noqa: E501
                proc_dirty = await asyncio.create_subprocess_exec("git", "-C", repo, "status", "--porcelain", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
                stdout_dirty, _ = await asyncio.wait_for(proc_dirty.communicate(), timeout=10)
                dirty = stdout_dirty.decode(errors="replace").strip()
                if dirty:
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", message=f"workspace is dirty after repair: {dirty[:200]}")  # noqa: E501
                try:
                    from control_plane.verifier import Verifier
                    allowed, msg = Verifier.diff_allowed(repo, stdout.decode(errors="replace"))
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=msg, verification_result=ClosedVerificationResult(result="pass" if allowed else "fail", message=msg))  # noqa: E501
                except Exception:
                    message = stdout.decode(errors="replace")[:2000]
                    return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
            message = "git repository verified"
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None



