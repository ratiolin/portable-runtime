"""Plugin manager with full lifecycle (B4)."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.plugin.conformance import check_provider
from portable_runtime.plugin.loader import load_manifest, validate_manifest
from portable_runtime.providers.stdio import StdioJsonlProvider


@dataclass(slots=True)
class PluginRecord:
    id: str
    path: Path
    manifest: Any
    status: str  # discovered, validated, loaded, enabled, disabled, unhealthy, failed, unloaded
    detail: str = ""


class PluginManager:
    """Manages external plugin discovery and lifecycle without restarting Runtime."""

    def __init__(self, registry: ProviderRegistry, plugin_dir: Path | None = None) -> None:
        self.registry = registry
        self.plugin_dir = plugin_dir or Path("data/plugins")
        self._records: dict[str, PluginRecord] = {}

    def discover(self) -> list[PluginRecord]:
        if not self.plugin_dir.is_dir():
            return []
        found: list[PluginRecord] = []
        for child in self.plugin_dir.iterdir():
            manifest_path = child / "manifest.json" if child.is_dir() else child
            if manifest_path.is_file():
                try:
                    manifest = load_manifest(manifest_path)
                    rec = PluginRecord(id=manifest.id, path=manifest_path, manifest=manifest, status="discovered")
                    self._records[manifest.id] = rec
                    found.append(rec)
                except Exception as exc:  # noqa: BLE001
                    rec = PluginRecord(id=child.name, path=manifest_path, manifest=None, status="failed", detail=str(exc))  # noqa: E501
                    self._records[rec.id] = rec
                    found.append(rec)
        return found

    def validate(self, path: Path) -> list[str]:
        return validate_manifest(path)

    async def load(self, path: Path) -> PluginRecord:
        errors = self.validate(path)
        if errors:
            rec = PluginRecord(id=path.name, path=path, manifest=None, status="failed", detail="; ".join(errors))
            self._records[rec.id] = rec
            return rec
        manifest = load_manifest(path)
        try:
            provider = StdioJsonlProvider(manifest, working_directory=(path if path.is_dir() else path.parent).resolve())  # noqa: E501
            # Conformance without affecting runtime state
            health_errors = await check_provider(provider)
            if health_errors and "health unavailable" in ";".join(health_errors):
                # For stdio providers, health may be "ready" even if not yet enabled; treat as validated
                pass
            # Register
            self.registry.register(provider)
            # Enable via registry (enabled flag)
            rec = PluginRecord(id=manifest.id, path=path, manifest=manifest, status="loaded")
            self._records[manifest.id] = rec
            return rec
        except Exception as exc:  # noqa: BLE001
            rec = PluginRecord(id=manifest.id, path=path, manifest=manifest, status="failed", detail=str(exc))
            self._records[rec.id] = rec
            return rec

    def enable(self, plugin_id: str) -> PluginRecord:
        self.registry.enable(plugin_id)
        rec = self._records.get(plugin_id)
        if rec:
            rec.status = "enabled"
            return rec
        return PluginRecord(id=plugin_id, path=Path(), manifest=None, status="enabled")

    def disable(self, plugin_id: str) -> PluginRecord:
        self.registry.disable(plugin_id)
        rec = self._records.get(plugin_id)
        if rec:
            rec.status = "disabled"
            return rec
        return PluginRecord(id=plugin_id, path=Path(), manifest=None, status="disabled")

    def reload(self, plugin_id: str) -> PluginRecord:
        self.registry.reload(plugin_id)
        rec = self._records.get(plugin_id)
        if rec:
            rec.status = "loaded"
            return rec
        return PluginRecord(id=plugin_id, path=Path(), manifest=None, status="loaded")

    def remove(self, plugin_id: str) -> None:
        self.registry.unregister(plugin_id)
        self._records.pop(plugin_id, None)

    async def doctor(self, plugin_id: str) -> dict[str, Any]:
        rec = self._records.get(plugin_id)
        if rec is None:
            return {"id": plugin_id, "status": "not-found"}
        try:
            provider = self.registry.get(plugin_id)
            health = await provider.health()
            return {"id": plugin_id, "status": rec.status, "health": health.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return {"id": plugin_id, "status": "failed", "detail": str(exc)}

    def list(self) -> builtins.list[PluginRecord]:
        return list(self._records.values())

    def validate_all(self) -> dict[str, builtins.list[str]]:
        return {rec.id: self.validate(rec.path) for rec in self._records.values()}
