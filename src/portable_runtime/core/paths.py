"""Unified runtime paths (portable, no hard-coded D:\\)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class RuntimePaths(BaseModel):
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    cache_dir: Path = Field(default_factory=lambda: Path("data/cache"))
    log_dir: Path = Field(default_factory=lambda: Path("data/logs"))
    plugin_dir: Path = Field(default_factory=lambda: Path("data/plugins"))
    artifact_dir: Path = Field(default_factory=lambda: Path("data/artifacts"))

    def ensure(self) -> None:
        for p in [self.data_dir, self.cache_dir, self.log_dir, self.plugin_dir, self.artifact_dir]:
            p.mkdir(parents=True, exist_ok=True)
