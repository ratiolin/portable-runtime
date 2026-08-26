from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from portable_runtime.experience.use_admission import (
    ExperienceUseRequirement,
    experience_use_requirement_digest,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_vectors(path: Path | None = None) -> dict[str, Any]:
    target = path or (_root() / "contracts" / "vectors" / "experience" / "v1.json")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "portable-runtime-conformance-vectors-v1":
        raise ValueError("unsupported conformance vector file")
    return value


def verify_experience_vectors(path: Path | None = None) -> list[str]:
    document = load_vectors(path)
    verified: list[str] = []
    for vector in document.get("vectors", []):
        if not isinstance(vector, dict):
            continue
        identifier = str(vector.get("id", ""))
        if identifier == "EU-001":
            given = vector["given"]
            requirement = ExperienceUseRequirement(projection_refs=tuple(given["projection_refs"]))
            if list(requirement.projection_refs) != vector["expect"]["projection_refs"]:
                raise ValueError("EU-001 projection ordering mismatch")
            verified.append(identifier)
        elif identifier == "EU-002":
            given = vector["given"]
            requirement = ExperienceUseRequirement(
                projection_refs=tuple(given["projection_refs"]),
                use_scope=given["use_scope"],
                subject_version_refs=tuple(given["subject_version_refs"]),
                environment_bindings=given["environment_bindings"],
                use_context=given["use_context"],
            )
            digest = experience_use_requirement_digest(requirement)
            if digest != vector["expect"]["sha256"]:
                raise ValueError("EU-002 canonical digest mismatch")
            verified.append(identifier)
    required = {"EU-001", "EU-002"}
    if set(verified) != required:
        raise ValueError("required executable canonicalization vectors are missing")
    return verified


def main() -> int:
    verified = verify_experience_vectors()
    print(json.dumps({"verified": verified}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
