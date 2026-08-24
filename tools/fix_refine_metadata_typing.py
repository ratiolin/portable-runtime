from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in (
    "src/portable_runtime/records/qualification_transition.py",
    "src/portable_runtime/protocol/validation.py",
):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    text = text.replace("before_metadata: dict[str, Any] = (", "before_metadata = (")
    text = text.replace("after_metadata: dict[str, Any] = (", "after_metadata = (")
    text = text.replace("old_metadata: dict[str, Any] = (", "old_metadata = (")
    text = text.replace("new_metadata: dict[str, Any] = (", "new_metadata = (")
    if rel.endswith("protocol/validation.py"):
        text = text.replace(
            "for payload in (old_payload, new_payload):\n        payload.pop(\"created_at\", None)\n        payload.pop(\"epistemic_status\", None)\n        payload.pop(\"version\", None)",
            "for snapshot_payload in (old_payload, new_payload):\n        snapshot_payload.pop(\"created_at\", None)\n        snapshot_payload.pop(\"epistemic_status\", None)\n        snapshot_payload.pop(\"version\", None)",
        )
    path.write_text(text, encoding="utf-8")
