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
    path.write_text(text, encoding="utf-8")
