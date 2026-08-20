# Portable Runtime config ( §25 )

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    id: str = "personal-runtime"
    data_dir: Path = Path("./data")


class StoreConfig(BaseModel):
    state: str = "sqlite"
    events: str = "sqlite"
    artifacts: str = "filesystem"


class ProviderConfig(BaseModel):
    id: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class PortableConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)
    providers: list[ProviderConfig] = Field(default_factory=list)
    plugins: list[dict[str, Any]] = Field(default_factory=list)
    routing: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PortableConfig:
        if not path.is_file():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        # Normalize [[providers]] and [[plugins]]
        providers = []
        for p in data.get("providers", []):
            if isinstance(p, dict) and "id" in p:
                providers.append(ProviderConfig.model_validate(p))
        runtime = RuntimeConfig.model_validate(data.get("runtime", {}))
        store = StoreConfig.model_validate(data.get("store", {}))
        plugins = data.get("plugins", [])
        if isinstance(plugins, dict):
            plugins = [plugins]
        return cls(runtime=runtime, store=store, providers=providers, plugins=plugins, routing=data.get("routing", {}))
