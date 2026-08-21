from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tarfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

from portable_runtime.core.models import utcnow


def _safe_output_path(p: Path) -> Path:
    if not str(p).strip():
        raise ValueError("output path must not be empty")
    if ".." in p.parts:
        cwd = Path.cwd().resolve()
        resolved = p.resolve()
        if not (resolved.is_relative_to(cwd) or resolved.is_relative_to(cwd.parent)):
            raise ValueError(f"output path escapes allowed base: {p}")
    return p


BUNDLE_SCHEMA_VERSION = "1"
BUNDLE_FORMAT = "portable-runtime-bundle-v1"

_KIND_TO_FILENAME: dict[str, str] = {
    "work": "works.jsonl",
    "run": "runs.jsonl",
    "artifact": "artifacts.jsonl",
    "evidence": "evidence.jsonl",
    "decision": "decisions.jsonl",
    "action": "actions.jsonl",
    "outcome": "outcomes.jsonl",
    "knowledge": "knowledge.jsonl",
    "knowledge_projection": "knowledge_projections.jsonl",
    "event": "events.jsonl",
    "step": "steps.jsonl",
    "attempt": "attempts.jsonl",
    "checkpoint": "checkpoints.jsonl",
    "compensation": "compensations.jsonl",
    "record": "records.jsonl",
    "relation": "relations.jsonl",
    "authorization": "authorizations.jsonl",
}

_FILENAME_TO_KIND: dict[str, str] = {v: k for k, v in _KIND_TO_FILENAME.items()}

ARTIFACT_DIR = "artifacts"


def _is_safe_member_name(name: str) -> bool:
    """Return True if tar member name is safe (relative, no traversal, no absolute)."""
    if not name or name in (".", "./"):
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if len(name) >= 2 and name[1] == ":":
        return False
    posix = PurePosixPath(name)
    if posix.is_absolute():
        return False
    for part in posix.parts:
        if part == "..":
            return False
    return not ("\\" in name and ":" in name)


def _manifest(counts: dict[str, int], artifact_files: list[str], runtime_id: str, checksums: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "runtime_id": runtime_id,
        "exported_at": utcnow().isoformat(),
        "counts": counts,
        "artifact_files": sorted(artifact_files),
        "checksums": checksums or {},
    }


def _jsonl_bytes(records: list[dict[str, object]]) -> bytes:
    if not records:
        return b""
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _parse_jsonl(data: bytes) -> list[dict[str, object]]:
    if not data.strip():
        return []
    result: list[dict[str, object]] = []
    for line in data.decode("utf-8").splitlines():
        if line.strip():
            result.append(json.loads(line))
    return result


def _try_import_zstd():
    try:
        import zstandard as zstd  # type: ignore[import-not-found]
        return zstd
    except ImportError:
        return None


def _compress_if_needed(data: bytes, want_zst: bool) -> bytes:
    if not want_zst:
        return data
    zstd = _try_import_zstd()
    if zstd is not None:
        cctx = zstd.ZstdCompressor(level=3)
        return cctx.compress(data)
    return gzip.compress(data)


def _decompress_if_needed(data: bytes) -> bytes:
    if data[:4] == b"\x28\xb5\x2f\xfd":
        zstd = _try_import_zstd()
        if zstd is not None:
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(data, max_output_size=1024 * 1024 * 1024)
        raise ValueError("zstd compressed bundle requires 'zstandard' package (not installed)")
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


def export_bundle(
    state_store: Any,
    artifact_store: Any | None,
    output_path: Path,
    runtime_id: str = "runtime",
) -> Path:
    _safe_output_path(output_path).parent.mkdir(parents=True, exist_ok=True)
    state = state_store.export_state()
    counts: dict[str, int] = {k: len(v) for k, v in state.items()}
    artifact_files: list[str] = []
    artifact_blobs: dict[str, bytes] = {}
    if artifact_store is not None:
        for rec in state.get("artifact", []):
            uri = rec.get("uri")
            if not isinstance(uri, str) or not uri:
                continue
            if not uri.startswith("file:"):
                continue
            try:
                data = artifact_store.get(uri)
            except Exception:  # noqa: S112
                # Fallback for minimal FileStore on Windows: try direct file read from URI
                try:
                    from urllib.parse import unquote, urlparse
                    import os
                    parsed2 = urlparse(uri)
                    raw2 = unquote(parsed2.path)
                    if os.name == "nt" and len(raw2) >= 3 and raw2[0] == "/" and raw2[2] == ":":
                        raw2 = raw2[1:]
                    data = Path(raw2).read_bytes()
                except Exception:  # noqa: S112
                    continue
            try:
                from urllib.parse import unquote, urlparse

                parsed = urlparse(uri)
                raw = unquote(parsed.path)
                basename = Path(raw).name
                if not basename or basename in (".", ".."):
                    continue
                if not _is_safe_member_name(basename):
                    continue
                if basename not in artifact_blobs:
                    artifact_blobs[basename] = data
                    artifact_files.append(basename)
            except Exception:  # noqa: S112
                continue
    # Pre-compute jsonl bytes and checksums for manifest
    jsonl_blobs: dict[str, bytes] = {}
    checksums: dict[str, str] = {}
    for kind, filename in _KIND_TO_FILENAME.items():
        records = state.get(kind, [])
        data = _jsonl_bytes(records)
        jsonl_blobs[filename] = data
        checksums[filename] = hashlib.sha256(data).hexdigest()
    artifact_checksums: dict[str, str] = {}
    for basename, blob in sorted(artifact_blobs.items()):
        artifact_checksums[f"{ARTIFACT_DIR}/{basename}"] = hashlib.sha256(blob).hexdigest()
    all_checksums = {**checksums, **artifact_checksums}
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        manifest = _manifest(counts, artifact_files, runtime_id, checksums=all_checksums)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        info.mtime = int(time.time())
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for kind, filename in _KIND_TO_FILENAME.items():
            data = jsonl_blobs[filename]
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
        for basename, blob in sorted(artifact_blobs.items()):
            name = f"{ARTIFACT_DIR}/{basename}"
            if not _is_safe_member_name(name):
                raise ValueError(f"unsafe member {name!r}")
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(blob))
    tar_bytes = tar_buffer.getvalue()
    suffixes = "".join(output_path.suffixes).lower()
    if suffixes.endswith(".zst") or suffixes.endswith(".zstd"):
        tar_bytes = _compress_if_needed(tar_bytes, want_zst=True)
        output_path.write_bytes(tar_bytes)  # NOSONAR
    elif suffixes.endswith(".gz") or suffixes.endswith(".tgz"):
        output_path.write_bytes(gzip.compress(tar_bytes))  # NOSONAR
    else:
        if str(output_path).endswith(".tar"):
            output_path.write_bytes(tar_bytes)  # NOSONAR
        else:
            if "zst" in suffixes:
                tar_bytes = _compress_if_needed(tar_bytes, want_zst=True)
            output_path.write_bytes(tar_bytes)  # NOSONAR
    return output_path


def _validate_state_invariants(state: dict[str, list[dict[str, object]]]) -> None:
    """Validate lifecycle/relation invariants and refs before import. Raises ValueError on failure."""
    from portable_runtime.records.models import BaseRecord
    from portable_runtime.records.relations import RecordRelation, validate_relation
    from portable_runtime.records.validation import validate_record
    for raw in state.get("record", []):
        try:
            br = BaseRecord.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"record invariant violation: {exc}") from exc
        errs = validate_record(br)
        if errs:
            raise ValueError(f"record lifecycle invariant failed for {br.id}: {"; ".join(errs)}")
    for raw in state.get("relation", []):
        try:
            rr = RecordRelation.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"relation invariant violation: {exc}") from exc
        errs = validate_relation(rr)
        if errs:
            raise ValueError(f"relation invariant failed for {rr.id}: {"; ".join(errs)}")
        if not rr.subject_ref or not rr.object_ref:
            raise ValueError(f"relation {rr.id} missing subject_ref/object_ref")
    for raw in state.get("authorization", []):
        try:
            from portable_runtime.records.authorization import AuthorizationGrant
            ag = AuthorizationGrant.model_validate(raw)
            if not ag.principal_ref or not ag.grantee_ref:
                raise ValueError(f"authorization {ag.id} missing principal/grantee")
            if not ag.allowed_capabilities:
                raise ValueError(f"authorization {ag.id} allowed_capabilities must not be empty")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"authorization invariant violation: {exc}") from exc
    # P2-2: object-level validation is not enough for a portable snapshot.
    # Resolve the complete graph before touching the destination store so a
    # malformed import cannot leave a partially imported state behind.
    from portable_runtime.protocol.validation import assert_valid_state_graph

    assert_valid_state_graph(state)


def import_bundle(
    state_store: Any,
    artifact_store: Any | None,
    input_path: Path,
) -> dict[str, Any]:
    raw = input_path.read_bytes()  # NOSONAR
    try:
        tar_bytes = _decompress_if_needed(raw)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"failed to decompress bundle: {exc}") from exc
    state: dict[str, list[dict[str, object]]] = {}
    raw_blobs: dict[str, bytes] = {}
    artifact_blobs: dict[str, bytes] = {}
    manifest: dict[str, Any] | None = None
    tar_buffer = io.BytesIO(tar_bytes)
    try:
        with tarfile.open(fileobj=tar_buffer, mode="r", format=tarfile.PAX_FORMAT) as tar:
            for member in tar.getmembers():
                name = member.name
                if name.startswith("./"):
                    name = name[2:]
                if not name or name == ".":
                    continue
                if not _is_safe_member_name(name):
                    raise ValueError(f"unsafe bundle member path: {name!r} (absolute or traversal not allowed)")
                if member.isdir():
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                data = f.read()
                if name == "manifest.json":
                    manifest = json.loads(data.decode("utf-8"))
                    raw_blobs[name] = data
                elif name in _FILENAME_TO_KIND:
                    kind = _FILENAME_TO_KIND[name]
                    raw_blobs[name] = data
                    state[kind] = _parse_jsonl(data)
                elif name.startswith(f"{ARTIFACT_DIR}/"):
                    basename = name[len(ARTIFACT_DIR) + 1 :]
                    if not basename or "/" in basename or "\\" in basename:
                        raise ValueError(f"invalid artifact member: {name!r}")
                    if not _is_safe_member_name(basename):
                        raise ValueError(f"unsafe artifact name: {basename!r}")
                    raw_blobs[name] = data
                    artifact_blobs[basename] = data
                else:
                    raise ValueError(f"unexpected bundle member: {name!r} (not in allowed manifest)")
    except tarfile.TarError as exc:
        raise ValueError(f"invalid tar bundle: {exc}") from exc
    if manifest is None:
        raise ValueError("bundle missing manifest.json")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError(f"unsupported bundle schema_version: {manifest.get('schema_version')}")
    checksums = manifest.get("checksums") or {}
    if isinstance(checksums, dict) and checksums:
        for fname, expected in checksums.items():
            if not isinstance(expected, str):
                continue
            actual_data = raw_blobs.get(fname)
            if actual_data is None:
                raise ValueError(f"checksum entry {fname!r} missing from bundle")
            actual = hashlib.sha256(actual_data).hexdigest()
            if actual != expected:
                raise ValueError(f"checksum mismatch for {fname!r}: expected {expected}, got {actual}")
    counts = manifest.get("counts") or {}
    if isinstance(counts, dict):
        for kind, expected_count in counts.items():
            if kind in _KIND_TO_FILENAME:
                actual_count = len(state.get(kind, []))
                if actual_count != expected_count:
                    raise ValueError(f"count mismatch for {kind!r}: manifest {expected_count} vs actual {actual_count}")
    for kind in _KIND_TO_FILENAME:
        state.setdefault(kind, [])
    _validate_state_invariants(state)
    state_store.import_state(state)
    if artifact_store is not None and artifact_blobs:
        root = getattr(artifact_store, "root", None)
        if isinstance(root, Path):
            for basename, blob in artifact_blobs.items():
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", basename):
                    raise ValueError(f"invalid artifact basename: {basename!r}")
                if "/" in basename or "\\" in basename or ".." in basename:
                    raise ValueError(f"unsafe artifact basename: {basename!r}")
                sanitized = basename
                target = (Path(root) / sanitized).resolve()
                try:
                    target.relative_to(Path(root).resolve())
                except ValueError as exc:
                    raise ValueError(f"artifact target escapes root: {basename!r}") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != blob:
                    target.write_bytes(blob)
            try:
                for rec in state.get("artifact", []):
                    old_uri = rec.get("uri")
                    if not isinstance(old_uri, str) or not old_uri.startswith("file:"):
                        continue
                    from urllib.parse import unquote, urlparse
                    parsed = urlparse(old_uri)
                    basename = Path(unquote(parsed.path)).name
                    if basename not in artifact_blobs:
                        continue
                    new_path = Path(root) / basename
                    new_uri = new_path.as_uri()
                    if old_uri != new_uri:
                        art_id = rec.get("id")
                        if isinstance(art_id, str) and hasattr(state_store, "get_artifact"):
                            existing = state_store.get_artifact(art_id)
                            if existing is not None and getattr(existing, "uri", None) != new_uri:
                                try:
                                    updated = existing.model_copy(update={"uri": new_uri})
                                except Exception:
                                    continue
                                state_store.save_artifact(updated)
            except Exception:
                pass
        else:
            for _basename, blob in artifact_blobs.items():
                try:
                    artifact_store.put(blob)
                except Exception:
                    try:
                        artifact_store.put(blob, media_type="application/octet-stream")
                    except Exception:
                        continue
    return manifest


def bundle_contains_absolute_paths(bundle_path: Path) -> bool:
    raw = bundle_path.read_bytes()
    try:
        tar_bytes = _decompress_if_needed(raw)
    except Exception:
        tar_bytes = raw
    buf = io.BytesIO(tar_bytes)
    try:
        with tarfile.open(fileobj=buf, mode="r") as tar:
            for m in tar.getmembers():
                if m.name.startswith("/") or ":\\" in m.name or m.name.startswith("\\"):
                    return True
                if ".." in PurePosixPath(m.name).parts:
                    return True
    except Exception:
        return False
    return False














