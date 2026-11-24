"""Setup UI and consent regressions; all files live in a private test APPDATA."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_photoshop_job_lifecycle as lifecycle


class InitialSetupGuideTests(unittest.TestCase):
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
        self.window = self.fixture.window

    def guide(self, language="en"):
        dialog = self.b.InitialSetupDialog(self.b.LANG[language], self.window)
        self.addCleanup(lambda: self.fixture.shiboken.delete(dialog))
        return dialog

    def test_legacy_completed_users_skip_guide_without_claiming_it_was_seen(self):
        settings = dict(self.window.settings)
        settings.pop("show_initial_setup")
        settings["photoshop_warning_choice"] = {"exe": "saved-path", "disabled": True}
        with patch.object(self.b, "load_settings", return_value=settings):
            window = self.b.BridgeApp()
        try:
            self.assertFalse(window.settings["show_initial_setup"])
            self.assertNotIn("initial_setup_seen", window.settings)
            self.assertTrue(window.settings["aseprite_trust_confirmed"])
            self.assertEqual(window.settings["photoshop_warning_choice"], settings["photoshop_warning_choice"])
        finally:
            window.clip_timer.stop()
            window.close()
            self.fixture.shiboken.delete(window)

    def test_new_user_order_is_language_then_guide_without_automatic_tutorial(self):
        from PySide6.QtWidgets import QInputDialog
        settings = {"photoshop_exe": self.window.settings["photoshop_exe"], "aseprite_exe": "unused.exe"}
        order = []
        with patch.object(self.b, "SETTINGS_FILE", str(self.fixture.root / "missing.json")), \
                patch.object(self.b, "load_settings", return_value=settings), \
                patch.object(QInputDialog, "getItem", side_effect=lambda *a: (order.append("language") or ("English", True))), \
                patch.object(self.b.BridgeApp, "show_initial_setup", lambda w: order.append("guide")), \
                patch.object(self.b.BridgeApp, "show_tutorial") as tutorial:
            window = self.b.BridgeApp(startup_progress=lambda *a: None)
            try:
                self.assertFalse(window.clip_timer.isActive())
                window._startup_ui_ready = True
                window.show_startup_dialogs()
                self.assertEqual(order, ["language", "guide"])
                tutorial.assert_not_called()
                self.assertTrue(window._startup_interaction_ready)
                self.assertTrue(window.clip_timer.isActive())
            finally:
                window.clip_timer.stop()
                window.close()
                self.fixture.shiboken.delete(window)

    def test_later_and_finish_never_grant_trust_and_opt_out_persists(self):
        self.window.settings["aseprite_trust_confirmed"] = False
        self.window.settings["show_initial_setup"] = True
        dialog = self.guide()
        dialog.cb_dont_show.setChecked(True)
        dialog.reject()
        saved = json.loads(Path(self.b.SETTINGS_FILE).read_text(encoding="utf-8"))
        self.assertTrue(saved["initial_setup_seen"])
        self.assertFalse(saved["show_initial_setup"])
        self.assertFalse(saved["aseprite_trust_confirmed"])
        self.assertFalse(saved["aseprite_hotkeys_confirmed"])
        dialog.accept()
        self.assertFalse(self.window.settings["aseprite_trust_confirmed"])
        reopened = self.guide()
        self.assertTrue(reopened.cb_dont_show.isChecked())
        reopened.cb_dont_show.setChecked(False)
        reopened.reject()
        self.assertTrue(self.window.settings["show_initial_setup"])

    def test_settings_save_preserves_setup_flags_migrations_and_unknown_keys(self):
        expected = dict(self.window.settings, initial_setup_seen=True, show_initial_setup=False,
                        aseprite_hotkeys_confirmed=True, future_setting={"value": 7})
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]):
            dialog = self.b.SettingsDialog(expected, self.window.t, self.window)
        try:
            actual = dialog.get_settings()
            for key in ("initial_setup_seen", "show_initial_setup", "aseprite_hotkeys_confirmed",
                        "ground_line_default_migrated", "future_setting", "aseprite_trust_confirmed"):
                self.assertEqual(actual[key], expected[key])
            self.assertEqual(dialog.btn_setup_guide.text(), self.window.t["guide_reopen"])
        finally:
            self.fixture.shiboken.delete(dialog)

    def test_photoshop_only_settings_preserves_other_fields_and_exact_path(self):
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]):
            dialog = self.b.SettingsDialog(self.window.settings, self.window.t, self.window, photoshop_only=True)
        try:
            self.assertEqual(dialog.windowTitle(), self.window.t["guide_steps"][0])
            self.assertNotIn(self.window.t["ps_warning"],
                             [b.text() for b in dialog.findChildren(self.b.QPushButton)])
            self.assertEqual(dialog.ps_versions.currentData(), self.fixture.target["path"])
            dialog.ps_path_input.setText("missing/Photoshop.exe")
            self.assertEqual(dialog.ps_versions.currentIndex(), 0)
            actual = dialog.get_settings()
            self.assertEqual(actual["photoshop_exe"], "missing/Photoshop.exe")
            self.assertEqual(actual["aseprite_trust_confirmed"], self.window.settings["aseprite_trust_confirmed"])
            self.assertEqual(actual["default_alignment"], "ground_line")
        finally:
            self.fixture.shiboken.delete(dialog)

    def test_connection_and_warning_have_distinct_actions(self):
        for language in ("ko", "en", "ja"):
            with self.subTest(language=language):
                dialog = self.guide(language)
                dialog.show()
                self.assertIn(dialog.lang["guide_ps_running"], dialog.ps_status.text())
                self.assertEqual(dialog.btn_next.text(), dialog.lang["guide_ps_continue"])
                with patch.object(self.b, "SettingsDialog") as settings, \
                        patch.object(self.b, "configure_photoshop_warning") as warning:
                    settings.return_value.exec.return_value = False
                    dialog.ps_edit.click()
                    settings.assert_called_once_with(self.window.settings, dialog.lang, dialog, photoshop_only=True)
                    warning.assert_not_called()
                    dialog.btn_next.click()
                    self.assertEqual(dialog.pages.currentIndex(), 1)
                    self.assertEqual(dialog.btn_next.text(), dialog.lang["guide_warning_continue"])
                    self.app.processEvents()
                    self.assertLessEqual(dialog.btn_next.geometry().right(), dialog.rect().right())
                    dialog.warning_edit.click()
                    self.assertEqual(warning.call_args.args[-1](), self.fixture.target["path"])
                    settings.assert_called_once()
                    dialog.btn_next.click()
                    self.assertEqual(dialog.pages.currentIndex(), 2)

    def test_reopening_guide_preserves_pending_path_edit_unless_guide_changes_target(self):
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]):
            dialog = self.b.SettingsDialog(self.window.settings, self.window.t, self.window)
        try:
            dialog.ps_path_input.setText("pending/Photoshop.exe")
            with patch.object(self.b, "InitialSetupDialog") as factory:
                factory.return_value.open_tutorial_requested = False
                dialog.show_initial_setup()
                self.assertEqual(dialog.ps_path_input.text(), "pending/Photoshop.exe")
                factory.return_value.exec.side_effect = lambda: self.window.settings.update(photoshop_exe="chosen/Photoshop.exe")
                dialog.show_initial_setup()
                self.assertEqual(dialog.ps_path_input.text(), "chosen/Photoshop.exe")
        finally:
            self.fixture.shiboken.delete(dialog)

    def test_real_file_and_key_status_is_separate_from_user_confirmation(self):
        self.real_setup(self.window.ase_paste_lua_orig, self.window.ase_copy_lua_orig)
        self.window.settings["aseprite_trust_confirmed"] = False
        dialog = self.guide()
        self.assertIn(dialog.lang["guide_files_ok"], dialog.ase_status.text())
        self.assertIn(dialog.lang["guide_keys_ok"], dialog.ase_status.text())
        self.assertIn(dialog.lang["guide_trust_no"], dialog.summary.text())
        self.assertIn(dialog.lang["guide_keys_untested"], dialog.summary.text())
        dialog.hotkeys_confirmed.setChecked(True)
        self.assertIn(dialog.lang["guide_keys_tested"], dialog.summary.text())
        self.assertFalse(self.window.settings["aseprite_trust_confirmed"])

    def test_first_synthetic_click_advances_and_does_not_query_dom_or_files(self):
        from PySide6.QtTest import QTest
        dialog = self.guide()
        states = []
        def click():
            states.append((self.app.activeModalWidget() is dialog, dialog.parentWidget() is self.window))
            with patch.object(self.b, "photoshop_exe_info", side_effect=AssertionError("query during navigation")), \
                    patch.object(self.window, "check_clipboard") as clipboard, \
                    patch.object(self.window, "check_temp_folder") as jobs:
                self.window.poll_clipboard()
                QTest.mouseClick(dialog.btn_next, self.b.Qt.LeftButton)
                self.assertEqual(dialog.pages.currentIndex(), 1)
                clipboard.assert_not_called()
                jobs.assert_not_called()
                QTest.mouseClick(dialog.btn_later, self.b.Qt.LeftButton)
        self.b.QTimer.singleShot(0, click)
        self.assertEqual(dialog.exec(), self.b.QDialog.Rejected)
        self.assertEqual(states, [(True, True)])

    def test_tutorial_is_requested_only_after_setup_dialog_is_hidden(self):
        dialog = self.guide()
        dialog.set_step(3)
        original = dialog.exec
        def run():
            self.b.QTimer.singleShot(0, dialog.btn_tutorial.click)
            return original()
        seen = []
        with patch.object(self.b, "InitialSetupDialog", return_value=dialog), \
                patch.object(dialog, "exec", side_effect=run), \
                patch.object(self.window, "show_tutorial", side_effect=lambda: seen.append(dialog.isVisible())):
            self.window.show_initial_setup()
        self.assertEqual(seen, [False])

    def test_three_languages_cover_all_guide_keys_and_usage_only(self):
        keys = {k for k in self.b.LANG["en"] if k.startswith("guide_")}
        for language in ("ko", "en", "ja"):
            labels = self.b.LANG[language]
            self.assertEqual(keys, {k for k in labels if k.startswith("guide_")})
            self.assertTrue(all(labels[k] for k in keys))
            self.assertEqual(len(labels["guide_steps"]), 4)
            text = labels["tut_content"]
            for mode in ("Normal", "Folder → Frames", "Layer → Frames", "Ground Line", "Center", "Absolute"):
                self.assertIn(mode, text)
            self.assertNotIn("Give full trust", text)
            self.assertNotIn("WarnRunningScripts", text)
            dialog = self.guide(language)
            for step in range(4):
                dialog.set_step(step)
                self.assertEqual(dialog.step_title.text(), labels["guide_steps"][step])

    def test_warning_defaults_to_no_then_explicit_consent_preserves_and_backs_up(self):
        path = self.fixture.root / "PSUserConfig.txt"
        before = b"OtherOption 1\r\nWarnRunningScripts 1\r\n"
        path.write_bytes(before)
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]), \
                patch.object(self.b, "photoshop_config_path", return_value=str(path)), \
                patch.object(self.b, "running_photoshops", return_value=[]), \
                patch.object(self.b.QMessageBox, "information"), \
                patch.object(self.b.QMessageBox, "question", return_value=self.b.QMessageBox.No) as question:
            dialog = self.b.SettingsDialog(self.window.settings, self.window.t, self.window, photoshop_only=True)
            try:
                dialog.configure_photoshop_warning()
                self.assertEqual(question.call_args.args[-1], self.b.QMessageBox.No)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list(self.fixture.root.glob("PSUserConfig.txt.*.bak")), [])
                self.assertNotIn("photoshop_warning_choice", self.window.settings)
                question.return_value = self.b.QMessageBox.Yes
                dialog.configure_photoshop_warning()
                self.assertEqual(path.read_bytes(), before.replace(b"Scripts 1", b"Scripts 0"))
                backups = list(self.fixture.root.glob("PSUserConfig.txt.*.bak"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), before)
                self.assertEqual(self.window.settings["photoshop_warning_choice"]["exe"], self.fixture.target["path"])
                dialog.configure_photoshop_warning()
                self.assertEqual(len(list(self.fixture.root.glob("PSUserConfig.txt.*.bak"))), 1)
            finally:
                self.fixture.shiboken.delete(dialog)

    def test_2024_through_2027_warning_paths_are_read_only_and_version_scoped(self):
        paths = []
        for year in (2024, 2025, 2026, 2027):
            name = "Adobe Photoshop " + str(year)
            folder = Path(os.environ["APPDATA"]) / "Adobe" / name / (name + " Settings")
            folder.mkdir(parents=True, exist_ok=True)
            paths.append(folder / "PSUserConfig.txt")
        for major, path in zip((25, 26, 27, 28), paths):
            target = dict(self.fixture.target, major=major, product=f"Adobe Photoshop {major + 1999}")
            self.assertEqual(Path(self.b.photoshop_config_path(target)), path)
        self.assertTrue(all(not p.exists() for p in paths))
        dialog = self.guide()
        self.assertIn(dialog.lang["guide_warning_keep"], dialog.warning_status.text())
        self.assertTrue(all(not p.exists() for p in paths))


if __name__ == "__main__":
    unittest.main()
