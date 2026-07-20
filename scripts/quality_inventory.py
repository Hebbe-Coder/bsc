"""Report encoding-risk and trivially unreachable-statement inventory."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}
SKIP_PARTS = {".git", ".venv", "node_modules", "dist", "__pycache__", "lib"}
MOJIBAKE_MARKERS = (
    "\u93e1",
    "\u6fc2",
    "\u95f2",
    "\u7f01",
    "\u95b9",
    "\u9502",
    "\u95b3",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    files = [path for path in root.rglob("*") if _is_source(path, root)]
    report = {
        "encoding_risk": _encoding_risk(files, root),
        "python_unreachable": _python_unreachable(files, root),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _is_source(path: Path, root: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in SOURCE_SUFFIXES
        and not any(part in SKIP_PARTS for part in path.relative_to(root).parts)
    )


def _encoding_risk(files: list[Path], root: Path) -> list[dict[str, object]]:
    findings = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"file": str(path.relative_to(root)), "reason": "not_utf8"})
            continue
        lines = [
            number
            for number, line in enumerate(text.splitlines(), 1)
            if any(marker in line for marker in MOJIBAKE_MARKERS)
        ]
        if lines:
            findings.append({"file": str(path.relative_to(root)), "lines": lines})
    return findings


def _python_unreachable(files: list[Path], root: Path) -> list[dict[str, object]]:
    findings = []
    for path in files:
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        visitor = _UnreachableVisitor()
        visitor.visit(tree)
        for line in visitor.lines:
            findings.append({"file": str(path.relative_to(root)), "line": line})
    return findings


class _UnreachableVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.lines: list[int] = []

    def visit_body(self, body: list[ast.stmt]) -> None:
        terminal = False
        for statement in body:
            if terminal:
                self.lines.append(statement.lineno)
            self.visit(statement)
            if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                terminal = True

    def visit_Module(self, node: ast.Module) -> None:
        self.visit_body(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_body(node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node: ast.If) -> None:
        self.visit_body(node.body)
        self.visit_body(node.orelse)

    def visit_For(self, node: ast.For) -> None:
        self.visit_body(node.body)
        self.visit_body(node.orelse)

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While) -> None:
        self.visit_body(node.body)
        self.visit_body(node.orelse)

    def visit_Try(self, node: ast.Try) -> None:
        self.visit_body(node.body)
        self.visit_body(node.orelse)
        self.visit_body(node.finalbody)
        for handler in node.handlers:
            self.visit_body(handler.body)


if __name__ == "__main__":
    main()
