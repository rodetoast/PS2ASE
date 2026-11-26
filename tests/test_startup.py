"""Startup UI tests never touch the real profile, scripts or clipboard."""
import importlib.util
import builtins
import json
import os
import subprocess
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import test_photoshop_job_lifecycle as lifecycle

REAL_POPEN = subprocess.Popen


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt unavailable")
class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lifecycle.JobLifecycleTests.setUpClass()
        cls.real_setup = staticmethod(lifecycle.JobLifecycleTests.b.setup_aseprite_environment)
        cls.addClassCleanup(lifecycle.JobLifecycleTests.doClassCleanups)

    def setUp(self):
        self.fixture = lifecycle.JobLifecycleTests("test_success_then_second_copy")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.b = self.fixture.b
        self.app = self.fixture.app

    def boot(self, alive):
        closed = []
        module = types.SimpleNamespace(is_alive=lambda: alive, close=lambda: closed.append(True))
        return module, closed

    def test_source_fallback_shows_and_closes_idempotently(self):
        module, _ = self.boot(False)
        with patch.dict(sys.modules, pyi_splash=module):
            splash = self.b.StartupSplash(self.app)
        self.assertTrue(splash.widget.isVisible())
        for language in ("ko", "en", "ja"):
            splash.update("startup_settings", language)
            self.assertEqual(splash.widget.message(), self.b.LANG[language]["startup_settings"])
        splash.close()
        self.assertFalse(splash.widget.isVisible())
        splash.close()
        splash.update("startup_ui")
        self.assertFalse(splash.widget.isVisible())

    def test_bootloader_uses_no_second_qt_splash(self):
        module, closed = self.boot(True)
        with patch.dict(sys.modules, pyi_splash=module):
            splash = self.b.StartupSplash(self.app)
        self.assertIsNone(splash.widget)
        splash.update("startup_ui", "ja")
        splash.close()
        splash.close()
        self.assertEqual(closed, [True])

    def test_bootloader_api_failure_falls_back_to_qt(self):
        module = types.SimpleNamespace(is_alive=lambda: (_ for _ in ()).throw(OSError("not connected")))
        with patch.dict(sys.modules, pyi_splash=module):
            splash = self.b.StartupSplash(self.app)
        self.assertTrue(splash.widget.isVisible())
        splash.close()

    def test_constructor_failure_closes_bootloader_and_propagates_error(self):
        module, closed = self.boot(True)
        with patch.dict(sys.modules, pyi_splash=module), patch.object(self.b, "BridgeApp", side_effect=RuntimeError("init failed")):
            with self.assertRaisesRegex(RuntimeError, "init failed"):
                self.b.create_main_window(self.app)
        self.assertEqual(closed, [True])

    def test_ready_window_is_shown_before_splash_closes(self):
        window = self.fixture.window
        closed_while_visible = []
        module = types.SimpleNamespace(is_alive=lambda: True,
                                       close=lambda: closed_while_visible.append(window.isVisible()))
        with patch.dict(sys.modules, pyi_splash=module), patch.object(self.b, "BridgeApp", return_value=window):
            actual = self.b.create_main_window(self.app)
        self.assertIs(actual, window)
        self.assertEqual(closed_while_visible, [True])
        self.assertTrue(any(e["state"] == "STARTUP_READY" for e in window.diagnostic_records))

    def test_language_picker_hides_splash_before_modal(self):
        module, closed = self.boot(True)
        with patch.dict(sys.modules, pyi_splash=module):
            splash = self.b.StartupSplash(self.app)
        splash.update(None)
        self.assertEqual(closed, [True])
        splash.update("startup_ui", "ko")
        self.assertTrue(splash.closed)

    def test_splash_geometry_and_scaling_policy(self):
        module, _ = self.boot(False)
        with patch.dict(sys.modules, pyi_splash=module):
            splash = self.b.StartupSplash(self.app)
        self.assertEqual((splash.widget.width(), splash.widget.height()), (460, 200))
        available = splash.widget.screen().availableGeometry()
        self.assertLessEqual(abs(splash.widget.geometry().center().x() - available.center().x()), 2)
        self.assertLessEqual(abs(splash.widget.geometry().center().y() - available.center().y()), 2)
        splash.close()

    def test_bootloader_spec_includes_existing_resources_and_splash(self):
        root = Path(self.b.__file__).parent
        text = (root / "bridge_ui.spec").read_text(encoding="utf-8")
        for part in ("('scripts', 'scripts')", "('bridge_icon.ico', '.')", "('bridge_splash.png', '.')", "splash.binaries"):
            self.assertIn(part, text)
        self.assertTrue((root / "bridge_splash.png").is_file())

    def test_initialization_phases_follow_actual_work(self):
        phases = []
        window = self.b.BridgeApp(startup_progress=lambda stage, language=None: phases.append(stage))
        try:
            self.assertEqual(phases, ["startup_settings", "startup_environment", "startup_ui"])
        finally:
            window.clip_timer.stop()
            window.close()
            self.fixture.shiboken.delete(window)

    def test_first_run_closes_splash_before_language_selection(self):
        from PySide6.QtWidgets import QInputDialog
        phases = []
        def picker(*args):
            self.assertIs(args[0], window)
            self.assertTrue(window._startup_ui_ready)
            return "English", True
        with patch.object(self.b, "SETTINGS_FILE", str(self.fixture.root / "first-run.json")), \
                patch.object(self.b, "load_settings", return_value={k: v for k, v in self.fixture.window.settings.items()
                                                                    if k != "show_initial_setup"}), \
                patch.object(QInputDialog, "getItem", side_effect=picker), \
                patch.object(self.b.BridgeApp, "show_first_run_introduction") as guide:
            window = self.b.BridgeApp(startup_progress=lambda stage, language=None: phases.append(stage))
            self.assertTrue(window._needs_language_selection)
            window._startup_ui_ready = True
            window.show_startup_dialogs()
            guide.assert_called_once()
        try:
            self.assertEqual(phases, ["startup_settings", "startup_environment", "startup_ui"])
            self.assertEqual(window.settings["language"], "en")
        finally:
            window.clip_timer.stop()
            window.close()
            self.fixture.shiboken.delete(window)

    def test_current_scripts_and_keys_are_not_rewritten(self):
        w = self.fixture.window
        self.assertTrue(self.real_setup(w.ase_paste_lua_orig, w.ase_copy_lua_orig)[0])
        folder = Path(os.environ["APPDATA"]) / "Aseprite"
        files = [folder / "scripts" / "aseprite_paste.lua", folder / "scripts" / "aseprite_copy.lua",
                 folder / "user.aseprite-keys"]
        before = [(p.stat().st_mtime_ns, p.read_bytes()) for p in files]
        self.assertTrue(self.real_setup(w.ase_paste_lua_orig, w.ase_copy_lua_orig)[0])
        self.assertEqual(before, [(p.stat().st_mtime_ns, p.read_bytes()) for p in files])

    def test_qt_scale_factors_in_isolated_processes(self):
        for scale in ("1", "1.25", "1.5"):
            with self.subTest(scale=scale), patch.object(subprocess, "Popen", REAL_POPEN):
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "test_startup.StartupTests.test_splash_geometry_and_scaling_policy"],
                    cwd=Path(__file__).parent,
                    env=dict(os.environ, QT_SCALE_FACTOR=scale), capture_output=True, text=True,
                    encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_heavy_import_failure_closes_bootloader_before_reraising(self):
        source = Path(self.b.__file__).read_text(encoding="utf-8").split("# ==========================================", 1)[0]
        original_import = builtins.__import__
        for failing in ("PIL", "PySide6.QtWidgets"):
            module, closed = self.boot(True)
            def importing(name, *args, **kwargs):
                if name == failing:
                    raise ImportError("simulated dependency failure")
                return original_import(name, *args, **kwargs)
            with patch.dict(sys.modules, pyi_splash=module), patch.object(builtins, "__import__", importing):
                with self.assertRaisesRegex(ImportError, "simulated dependency failure"):
                    exec(compile(source, "startup-import-test", "exec"), {})
            self.assertEqual(closed, [True])

    def test_existing_clipboard_is_restored_after_ready_without_rewriting(self):
        w = self.fixture.window
        job = self.fixture.root / "existing_job"
        job.mkdir()
        (job / "metadata.json").write_text('{"frame_mode":"layer_frames"}', encoding="utf-8")
        payload = json.dumps({"signature": "ase_ps_bridge_payload", "job_id": "existing_job",
                              "source_app": "photoshop", "job_path": str(job),
                              "summary": {"layer_count": 1}})
        clipboard = types.SimpleNamespace(OpenClipboard=lambda: None, CloseClipboard=lambda: None,
                                          CF_UNICODETEXT=13, IsClipboardFormatAvailable=lambda _: True,
                                          GetClipboardData=lambda _: payload)
        module, closed = self.boot(True)
        with patch.dict(sys.modules, pyi_splash=module, win32clipboard=clipboard), \
                patch.object(self.b, "BridgeApp", return_value=w), \
                patch.object(w, "start_preview_generation") as preview:
            self.b.create_main_window(self.app)
            w.check_clipboard()
        self.assertEqual(closed, [True])
        self.assertEqual(w.last_job_id, "existing_job")
        self.assertEqual(w.clipboard_frame_mode, "layer_frames")
        preview.assert_called_once_with(str(job))

    def test_saved_executable_does_not_trigger_photoshop_scan_on_startup(self):
        with patch.object(self.b, "find_photoshop_exe", side_effect=AssertionError("unexpected scan")):
            window = self.b.BridgeApp()
        try:
            self.assertEqual(window.settings["photoshop_exe"], str(self.fixture.root / "Photoshop.exe"))
        finally:
            window.clip_timer.stop()
            window.close()
            self.fixture.shiboken.delete(window)

    def test_expired_popup_callback_cannot_run_before_splash_handoff(self):
        closed = []
        popup_states = []
        module = types.SimpleNamespace(is_alive=lambda: True, close=lambda: closed.append(True))
        original = self.b.BridgeApp.show_startup_dialogs
        def show(window):
            popup_states.append((bool(closed), window._startup_ui_ready))
            return original(window)
        with patch.dict(sys.modules, pyi_splash=module), patch.object(self.b.BridgeApp, "show_startup_dialogs", show):
            w = self.b.create_main_window(self.app)
            try:
                self.assertEqual(popup_states, [])
                self.assertFalse(w.btn_settings.isEnabled())
                for _ in range(4):
                    self.app.processEvents()
                self.assertEqual(popup_states, [(True, True)])
                self.assertTrue(w._startup_interaction_ready)
                self.assertTrue(w.btn_settings.isEnabled())
            finally:
                w.clip_timer.stop()
                w.close()
                self.fixture.shiboken.delete(w)

    def test_handoff_waits_for_actual_bootloader_window_disappearance(self):
        module, closed = self.boot(True)
        w = self.fixture.window
        w._startup_ui_ready = False
        with patch.dict(sys.modules, pyi_splash=module), \
                patch.object(self.b, "bootloader_splash_visible", side_effect=[True, False]):
            splash = self.b.StartupSplash(self.app)
            splash.finish(w)
            self.app.processEvents()
            self.assertFalse(w._startup_ui_ready)
            self.app.processEvents()
            self.assertTrue(w._startup_ui_ready)
            self.assertEqual(closed, [True])
        w._startup_handoff_timer.stop()

    def test_setup_modal_is_owned_enabled_and_mouse_clickable_in_qt(self):
        from PySide6.QtTest import QTest
        w = self.fixture.window
        dialog = self.b.AsepriteSetupDialog(w.t, w)
        seen = []
        def click_later():
            seen.append((self.app.activeModalWidget() is dialog, dialog.isEnabled(), dialog.parentWidget() is w))
            QTest.mouseClick(dialog.btn_later, self.b.Qt.LeftButton)
        self.b.QTimer.singleShot(0, click_later)
        result = dialog.exec()
        self.assertEqual(result, self.b.QDialog.Rejected)
        self.assertEqual(seen, [(True, True, True)])
        self.fixture.shiboken.delete(dialog)

    def test_language_cancel_keeps_english_and_does_not_confirm_trust(self):
        from PySide6.QtWidgets import QInputDialog
        w = self.fixture.window
        w._needs_language_selection = True
        w._startup_ui_ready = True
        w.settings["aseprite_trust_confirmed"] = False
        w.settings["show_initial_setup"] = True
        with patch.object(QInputDialog, "getItem", return_value=("日本語", False)), \
                patch.object(w, "show_first_run_introduction") as setup, \
                patch.object(w, "show_tutorial") as tutorial:
            w.show_startup_dialogs()
            w.show_startup_dialogs()
        setup.assert_called_once()
        tutorial.assert_not_called()
        self.assertEqual(w.settings["language"], "en")
        self.assertFalse(w.settings["language_selection_pending"])
        self.assertFalse(w.settings["aseprite_trust_confirmed"])
        self.assertTrue(w._startup_interaction_ready)

    def test_closing_before_handoff_cancels_owned_startup_callbacks(self):
        module, _ = self.boot(True)
        w = self.fixture.window
        with patch.dict(sys.modules, pyi_splash=module), patch.object(w, "show_startup_dialogs") as dialogs:
            splash = self.b.StartupSplash(self.app)
            splash.finish(w)
            w.close()
            for _ in range(3):
                self.app.processEvents()
            dialogs.assert_not_called()

    def test_profile_directory_failure_closes_bootloader(self):
        blocked = self.fixture.root / "blocked-profile"
        blocked.write_text("not a directory", encoding="utf-8")
        module, closed = self.boot(True)
        spec = importlib.util.spec_from_file_location("startup_bad_profile", self.b.__file__)
        candidate = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, pyi_splash=module), patch.dict(os.environ, APPDATA=str(blocked)):
            with self.assertRaises(OSError):
                spec.loader.exec_module(candidate)
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
