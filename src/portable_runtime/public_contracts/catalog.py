from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def contract_catalog() -> dict[str, Any]:
    """Return the repository-owned canonical public-contract catalog."""

    root = Path(__file__).resolve().parents[3]
    with (root / "contracts" / "catalog.toml").open("rb") as handle:
        value = tomllib.load(handle)
    if value.get("owner") != "portable-runtime/contracts":
        raise ValueError("public contract catalog owner mismatch")
    return value
