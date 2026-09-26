"""Run offline unittest classes, excluding legacy live-provider probe scripts.

Usage from the repository root: .venvapp/bin/python backend/run_tests.py
"""
import ast
from pathlib import Path
import unittest


def main():
    from app.config import settings

    # Prevent tests from spending real provider credits through an unmocked path.
    for field in type(settings).model_fields:
        if field.endswith(('_API_KEY', '_API_TOKEN', '_TOKEN', '_PASSWORD', '_LOGIN')):
            setattr(settings, field, '')
    modules = []
    for path in sorted(Path(__file__).parent.glob('test_*.py')):
        tree = ast.parse(path.read_text())
        if any(isinstance(node, ast.ClassDef) and any('TestCase' in ast.unparse(base) for base in node.bases)
               for node in tree.body):
            modules.append(path.stem)
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
