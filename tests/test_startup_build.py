"""Build preflight tests need no PyInstaller installation or real DLL changes."""
import ast
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class StartupBuildTests(unittest.TestCase):
    def test_icu_guard_rejects_wrong_exports_and_accepts_compatible_icu(self):
        tree = ast.parse((ROOT / "bridge_ui.spec").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_qt_icu")
        ns = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "spec-guard", "exec"), ns)
        exported = [b"ucnv_open_78"]
        def pe(path):
            return types.SimpleNamespace(
                DIRECTORY_ENTRY_IMPORT=[types.SimpleNamespace(dll=b"icuuc.dll", imports=[types.SimpleNamespace(name=b"ucnv_open")])],
                DIRECTORY_ENTRY_EXPORT=types.SimpleNamespace(symbols=[types.SimpleNamespace(name=x) for x in exported]),
                close=lambda: None)
        binaries = [("PySide6/Qt6Core.dll", "core", "BINARY"), ("icuuc.dll", "wrong-icu", "BINARY")]
        with patch.dict(sys.modules, pefile=types.SimpleNamespace(PE=pe)):
            with self.assertRaisesRegex(SystemExit, "Incompatible ICU"):
                ns["validate_qt_icu"](binaries)
            exported[:] = [b"ucnv_open"]
            ns["validate_qt_icu"](binaries)
            ns["validate_qt_icu"](binaries[:1])

    def test_validation_build_sanitizes_only_child_environment(self):
        spec = importlib.util.spec_from_file_location("private_builder", ROOT / "tests/build_startup_validation.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, PATH="unrelated/poppler", PYTHONPATH="unrelated", QT_PLUGIN_PATH="wrong"):
            original = dict(os.environ)
            env = module.clean_build_environment(Path("C:/Dev/test/Scripts/python.exe"))
            self.assertEqual(dict(os.environ), original)
            self.assertNotIn("poppler", env["PATH"])
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("QT_PLUGIN_PATH", env)
