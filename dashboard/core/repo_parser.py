from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, py_file: Path, root_path: Path):
        self.py_file = py_file
        self.root_path = root_path
        self.symbols: List[Dict[str, any]] = []
        self.class_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbols.append(
            {
                "kind": "class",
                "name": node.name,
                "file": str(self.py_file.relative_to(self.root_path)),
                "line": node.lineno,
            }
        )
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self.class_stack else "function"
        self.symbols.append(
            {
                "kind": kind,
                "name": node.name,
                "file": str(self.py_file.relative_to(self.root_path)),
                "line": node.lineno,
                "args": [a.arg for a in node.args.args],
                "class": self.class_stack[-1] if self.class_stack else None,
            }
        )
        self.generic_visit(node)


class RepoParser:
    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)

    def _is_skipped(self, path: Path) -> bool:
        parts = set(path.parts)
        return (
            "venv" in parts
            or "__pycache__" in parts
            or ".venv" in parts
            or "node_modules" in parts
        )

    def generate_symbols(self) -> List[Dict[str, any]]:
        symbols: List[Dict[str, any]] = []
        for py_file in self.root_path.rglob("*.py"):
            if self._is_skipped(py_file):
                continue
            try:
                tree = ast.parse(
                    py_file.read_text(encoding="utf-8"), filename=str(py_file)
                )
            except SyntaxError:
                continue
            visitor = _SymbolVisitor(py_file, self.root_path)
            visitor.visit(tree)
            symbols.extend(visitor.symbols)
        return symbols

    def get_structure(self) -> Dict[str, any]:
        files = []
        for py_file in self.root_path.rglob("*.py"):
            if self._is_skipped(py_file):
                continue
            files.append(str(py_file.relative_to(self.root_path)))
        return {
            "root": str(self.root_path),
            "files": files,
            "symbols": self.generate_symbols(),
        }
