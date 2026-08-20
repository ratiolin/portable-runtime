from __future__ import annotations

from typing import Protocol


class ArtifactStore(Protocol):
    def put(self, data: bytes, *, media_type: str | None = None) -> str: ...

    def get(self, uri: str) -> bytes: ...
