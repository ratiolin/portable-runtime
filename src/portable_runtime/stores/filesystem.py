from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import unquote, urlparse


class FilesystemArtifactStore:
    """Content-addressed artifact bytes; metadata remains in the state store."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, *, media_type: str | None = None) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / digest
        if not path.exists():
            path.write_bytes(data)
        return path.as_uri()

    def get(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError("artifact URI must use the file scheme")
        raw_path = unquote(parsed.path)
        if os.name == "nt" and len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
        candidate = Path(raw_path).resolve()
        root = self.root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            # Fallback: try basename lookup for migrated bundles (old absolute URI)
            basename = Path(raw_path).name
            if basename and basename not in (".", ".."):
                fallback = (root / basename).resolve()
                try:
                    fallback.relative_to(root)
                except ValueError as exc:
                    raise ValueError("invalid artifact URI") from exc
                if fallback.is_file():
                    return fallback.read_bytes()
            raise ValueError("invalid artifact URI") from None
        if candidate == root:
            raise ValueError("invalid artifact URI")
        return candidate.read_bytes()

    # ---- bundle helpers ----

    def export_artifacts(self) -> list[str]:
        """List artifact digests present in this store (for bundle manifest)."""
        return [p.name for p in self.root.iterdir() if p.is_file()]

    def import_artifact_bytes(self, digest: str, data: bytes) -> Path:
        """Import raw bytes under a given digest (used by bundle import)."""
        if not digest or "/" in digest or "\\" in digest or ".." in digest:
            raise ValueError(f"invalid digest: {digest!r}")
        target = self.root / digest
        # Safety: ensure inside root
        try:
            target.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"artifact digest escapes root: {digest!r}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return target

    def list_artifact_uris(self) -> list[str]:
        return [(self.root / name).as_uri() for name in self.export_artifacts()]

FileSystemArtifactStore = FilesystemArtifactStore

