from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


def _catalog_path() -> Path:
    """Resolve the canonical catalog in a source checkout or installed wheel.

    `contracts/` remains the only semantic owner.  Wheel builds package an
    immutable distribution copy under ``portable_runtime/_contracts`` so the
    public API does not depend on a source-repository checkout at runtime.
    """

    package_root = Path(__file__).resolve().parents[1]
    packaged = package_root / "_contracts" / "catalog.toml"
    if packaged.is_file():
        return packaged

    source_root = Path(__file__).resolve().parents[3]
    source_catalog = source_root / "contracts" / "catalog.toml"
    if source_catalog.is_file():
        return source_catalog
    raise FileNotFoundError("portable-runtime canonical contract catalog is unavailable")


@lru_cache(maxsize=1)
def contract_catalog() -> dict[str, Any]:
    """Return the repository-owned canonical public-contract catalog."""

    with _catalog_path().open("rb") as handle:
        value = tomllib.load(handle)
    if value.get("owner") != "portable-runtime/contracts":
        raise ValueError("public contract catalog owner mismatch")
    return value
