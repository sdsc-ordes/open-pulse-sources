"""Verify every `src.*` import in this repo resolves to a module in this repo.

Static AST check — no third-party deps needed. Used after copying code from
the git-metadata-extractor monolith (see MIGRATION.md) to prove the tree is
self-contained. Exits non-zero listing any import of a `src.*` module that
has no corresponding file here.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def module_exists(dotted: str) -> bool:
    rel = Path(*dotted.split("."))
    return (
        (ROOT / rel).is_dir()
        or (ROOT / rel.with_suffix(".py")).is_file()
    )


def src_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("open_pulse_sources."):
                    yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module and node.module.startswith("open_pulse_sources."):
                yield node.lineno, node.module


def main() -> int:
    failures = []
    py_files = [p for d in ("open_pulse_sources", "tests") for p in (ROOT / d).rglob("*.py")]
    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(ROOT)}: SYNTAX ERROR: {exc}")
            continue
        for lineno, mod in src_imports(tree):
            if not module_exists(mod):
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: unresolved {mod}")
    print(f"checked {len(py_files)} files")
    if failures:
        print(f"{len(failures)} unresolved src.* imports:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("all src.* imports resolve inside this repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
