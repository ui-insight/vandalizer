#!/usr/bin/env python3
"""Check all backend bodies, with type-only annotations for the frozen rubric.

The published legacy runner is a hash-bound artifact. Even annotation edits
would invalidate existing enrollments. Mypy's shadow-file facility lets it check
those same bodies with missing contracts supplied in a disposable copy. No file
is excluded, no diagnostic is ignored, and the runtime artifact stays untouched.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
LEGACY = Path('app/services/certification_versions/rubrics/legacy_20261002.py')
LEGACY_SHA256 = '068c24fee471c6f5ebca16c52581d249c129381d7e89301670dc3b35f5efe113'
TYPE_IMPORTS = (
    'from collections.abc import Iterable\n'
    'from typing import cast\n'
    'from app.config import Settings\n'
    'from app.models.user import User\n'
)


class ExecutableBody(ast.NodeTransformer):
    """Erase only annotations and our JSON-boundary casts for equivalence QA."""

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.annotation = None
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        node.returns = None
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        node.returns = None
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == 'cast'
                and len(node.args) == 2 and not node.keywords):
            return node.args[1]
        return node


def annotated_legacy(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != LEGACY_SHA256:
        raise ValueError('The frozen rubric changed; review its archive and typing contracts')
    replacements = {
        'async def get_progress(user_id: str):':
            'async def get_progress(user_id: str) -> CertificationProgress:',
        'async def provision_module_documents(user, module_id: str, settings) -> dict:':
            'async def provision_module_documents(user: User, module_id: str, settings: Settings) -> dict:',
        '    def _add(values) -> None:':
            '    def _add(values: Iterable[object]) -> None:',
        # These two pinned assets are JSON objects; the general package reader
        # also serves arrays, so its dynamic JSON result needs this boundary.
        "return pinned_package().json('exercises.json')":
            "return cast(dict, pinned_package().json('exercises.json'))",
        "return pinned_package().json('lessons.json')":
            "return cast(dict, pinned_package().json('lessons.json'))",
    }
    shadow = source
    for original, replacement in replacements.items():
        if shadow.count(original) != 1:
            raise ValueError(f'The frozen typing boundary is ambiguous: {original}')
        shadow = shadow.replace(original, replacement)
    # Compare before adding type-only imports. All expressions, control flow,
    # defaults, decorators and data must remain exactly the archived program.
    original_ast = ExecutableBody().visit(ast.parse(source))
    shadow_ast = ExecutableBody().visit(ast.parse(shadow))
    if ast.dump(original_ast) != ast.dump(shadow_ast):
        raise ValueError('The typing overlay changed executable legacy behavior')
    return TYPE_IMPORTS + shadow


def main() -> int:
    source = (BACKEND / LEGACY).read_text()
    shadow = annotated_legacy(source)
    with tempfile.TemporaryDirectory(prefix='vandalizer-legacy-types-') as temporary:
        path = Path(temporary) / 'legacy_20261002.py'
        path.write_text(shadow)
        return subprocess.call([
            sys.executable, '-m', 'mypy', '--shadow-file', str(LEGACY), str(path), 'app',
        ], cwd=BACKEND)


if __name__ == '__main__':
    raise SystemExit(main())
