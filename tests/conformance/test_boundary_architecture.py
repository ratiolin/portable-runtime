"""Architecture locks for the single provider invocation capability."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "portable_runtime"
BOUNDARY = SRC / "core" / "boundary.py"


class _InvocationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_name: str | None = None
        self.function_name: str | None = None
        self.calls: list[tuple[str | None, str | None, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous = self.class_name
        self.class_name = node.name
        self.generic_visit(node)
        self.class_name = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        previous = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "invoke"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "provider"
        ):
            self.calls.append((self.class_name, self.function_name, node.lineno))
        self.generic_visit(node)


def test_provider_invoke_is_boundary_owned_and_legacy_shim_is_unreachable() -> None:
    calls: list[tuple[Path, str | None, str | None, int]] = []
    for path in SRC.rglob("*.py"):
        visitor = _InvocationVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        calls.extend((path, *call) for call in visitor.calls)

    assert calls, "the runtime must have one explicit provider invocation seam"
    assert {path.relative_to(ROOT) for path, *_rest in calls} == {Path("src/portable_runtime/core/boundary.py")}
    assert all(class_name == "RealityBoundary" for _path, class_name, _function, _line in calls)

    # The private compatibility shim may remain for callers that reached the
    # old helper, but its historical implementation must not be a second live
    # reality exit.  Its provider call is after the unconditional delegation.
    legacy_calls = [line for _path, _class_name, function, line in calls if function == "_execute_legacy"]
    if legacy_calls:
        tree = ast.parse(BOUNDARY.read_text(encoding="utf-8"))
        legacy = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_execute_legacy")
        returns = [node.lineno for node in legacy.body if isinstance(node, ast.Return)]
        assert returns and min(legacy_calls) > min(returns)
