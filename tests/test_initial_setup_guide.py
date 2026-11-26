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
                patch.object(self.b, "load_settings", return_value=settings):
            window = self.b.BridgeApp(startup_progress=lambda *a: None)
            try:
                self.assertFalse(window.clip_timer.isActive())
                window._startup_ui_ready = True
                # Construction connects bound Qt signals. Install spies afterward
                # so the test exercises startup without changing those bindings.
                with patch.object(QInputDialog, "getItem", side_effect=lambda *a: (order.append("language") or ("English", True))), \
                        patch.object(window, "show_initial_setup", side_effect=lambda: order.append("guide")), \
                        patch.object(window, "show_tutorial") as tutorial:
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
        self.assertFalse(saved.get("aseprite_hotkeys_confirmed", False))
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
            self.assertEqual(dialog.windowTitle(), self.window.t["guide_steps"][0].removeprefix("1. "))
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
                dialog.set_step(dialog.CONNECTION)
                dialog.show()
                self.assertEqual(dialog.lang["guide_ps_running"], dialog.ps_status.runtime.text())
                self.assertEqual(dialog.btn_next.text(), dialog.lang["guide_next"])
                with patch.object(self.b, "SettingsDialog") as settings, \
                        patch.object(self.b, "configure_photoshop_warning") as warning, \
                        patch.object(self.b, "photoshop_config_path", return_value=str(self.fixture.root / "PSUserConfig.txt")):
                    settings.return_value.exec.return_value = False
                    dialog.ps_edit.click()
                    settings.assert_called_once_with(self.window.settings, dialog.lang, dialog, photoshop_only=True)
                    warning.assert_not_called()
                    dialog.btn_next.click()
                    self.assertEqual(dialog.pages.currentIndex(), dialog.WARNING)
                    self.assertEqual(dialog.btn_next.text(), dialog.lang["guide_next"])
                    self.app.processEvents()
                    self.assertLessEqual(dialog.btn_next.geometry().right(), dialog.rect().right())
                    dialog.warning_buttons[1].click()
                    warning.assert_called_once()
                    self.assertEqual(dialog.warning_hint.text(), dialog.flow("stop"))
                    with patch.object(self.b, "running_photoshops", return_value=[]):
                        dialog.refresh_status()
                        self.assertTrue(dialog.can_change_warning)
                    self.assertEqual(warning.call_args.args[-1](), self.fixture.target["path"])
                    settings.assert_called_once()
                    dialog.btn_next.click()
                    self.assertEqual(dialog.pages.currentIndex(), dialog.ASEPRITE)

    def test_display_name_preserves_settings_identity(self):
        name = "Photoshop \u2194 Aseprite"
        original_path = self.b.SETTINGS_FILE
        original_data_dir = self.b.BRIDGE_DATA_DIR
        for language in ("ko", "en", "ja"):
            self.window.current_lang = language
            self.window.refresh_ui_language()
            self.assertEqual(self.window.windowTitle(), name)
            guide = self.guide(language)
            self.assertEqual(guide.windowTitle(), guide.flow("name"))
            self.assertEqual(self.b.SETTINGS_FILE, original_path)
        self.assertEqual(self.b.BRIDGE_DATA_DIR, original_data_dir)

    def test_reopening_guide_preserves_pending_path_edit_unless_guide_changes_target(self):
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]):
            dialog = self.b.SettingsDialog(self.window.settings, self.window.t, self.window)
        try:
            dialog.ps_path_input.setText("pending/Photoshop.exe")
            opener = self.window.open_settings
            with patch.object(dialog, "exec", side_effect=dialog.show_initial_setup), \
                    patch.object(self.window, "open_settings") as reopen, \
                    patch.object(self.window, "show_initial_setup") as guide:
                opener(dialog)
                guide.call_args.args[0]()
                self.assertEqual(dialog.ps_path_input.text(), "pending/Photoshop.exe")
                reopen.assert_called_once_with(dialog)
                opener(dialog)
                self.window.settings.update(photoshop_exe="chosen/Photoshop.exe")
                guide.call_args.args[0]()
                self.assertEqual(dialog.ps_path_input.text(), "chosen/Photoshop.exe")
        finally:
            self.fixture.shiboken.delete(dialog)

    def test_real_file_and_key_status_is_separate_from_user_confirmation(self):
        self.real_setup(self.window.ase_paste_lua_orig, self.window.ase_copy_lua_orig)
        self.window.settings["aseprite_trust_confirmed"] = False
        dialog = self.guide()
        self.assertEqual(dialog.ase_status[0].text(), dialog.flow("verified"))
        self.assertEqual(dialog.ase_status[1].text(), dialog.flow("verified"))
        for index in (5, 6, 7):
            self.assertEqual(dialog.review_lines[index].text(), dialog.flow("review_states")[4])
        self.assertFalse(self.window.settings["aseprite_trust_confirmed"])

    def test_settings_separate_installation_trust_and_runtime_without_overwriting_settings(self):
        b = self.b
        values = dict(self.window.settings, hotkey_status="legacy", aseprite_trust_confirmed=False,
                      aseprite_hotkeys_confirmed=True)
        with patch.object(b, "aseprite_installation_status", return_value=(False, True)):
            dialog = b.SettingsDialog(values, b.LANG["ko"], self.window)
        self.addCleanup(lambda: self.fixture.shiboken.delete(dialog))
        lang = b.LANG["ko"]
        self.assertEqual(dialog.hotkey_status.text().splitlines()[-4:],
                         [lang["ase_files_old"], lang["guide_keys_ok"],
                          lang["guide_trust_no"], lang["guide_keys_untested"]])
        self.assertEqual(dialog.button_box.button(b.QDialogButtonBox.Ok).text(), lang["guide_close"])
        self.assertEqual(dialog.button_box.button(b.QDialogButtonBox.Cancel).text(), "취소")
        self.assertEqual(dialog.get_settings()["hotkey_status"], "legacy")
        self.assertFalse(dialog.get_settings()["aseprite_trust_confirmed"])
        self.assertTrue(dialog.get_settings()["aseprite_hotkeys_confirmed"])

    def test_settings_keep_footer_visible_at_compact_size(self):
        from PySide6.QtCore import QPoint, QRect
        b = self.b
        self.app.setStyle("Fusion")
        b.apply_workspace_theme(self.app)
        for language in ("ko", "en", "ja"):
            with self.subTest(language=language):
                dialog = b.SettingsDialog(self.window.settings, b.LANG[language], self.window)
                try:
                    dialog.resize(390, 380)
                    dialog.show()
                    self.app.processEvents()
                    scroll = dialog.findChild(b.QScrollArea)
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                    self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
                    footer = dialog.button_box
                    self.assertTrue(dialog.rect().contains(QRect(footer.mapTo(dialog, QPoint()), footer.size())))
                finally:
                    self.fixture.shiboken.delete(dialog)

    def test_first_synthetic_click_advances_and_does_not_query_dom_or_files(self):
        from PySide6.QtTest import QTest
        dialog = self.guide()
        states = []
        with patch.object(self.b, "InitialSetupDialog", return_value=dialog), \
                patch.object(dialog, "deleteLater"):
            self.window.show_initial_setup()
            states.append((self.app.activeModalWidget() is dialog, dialog.parentWidget() is self.window))
            with patch.object(self.b, "photoshop_exe_info", side_effect=AssertionError("query during navigation")), \
                    patch.object(self.window, "check_clipboard") as clipboard, \
                    patch.object(self.window, "check_temp_folder") as jobs:
                self.window.poll_clipboard()
                QTest.mouseClick(dialog.btn_next, self.b.Qt.LeftButton)
                self.assertEqual(dialog.pages.currentIndex(), 1)
                clipboard.assert_called_once()
                jobs.assert_called_once()
                QTest.mouseClick(dialog.btn_later, self.b.Qt.LeftButton)
        self.assertIsNone(self.window.setup_guide)
        self.assertEqual(states, [(False, True)])

    def test_tutorial_is_requested_only_after_setup_dialog_is_hidden(self):
        dialog = self.guide()
        dialog.set_step(dialog.REVIEW)
        seen = []
        with patch.object(self.b, "InitialSetupDialog", return_value=dialog), \
                patch.object(dialog, "deleteLater"), \
                patch.object(self.window, "show_tutorial", side_effect=lambda: seen.append(dialog.isVisible())):
            self.window.show_initial_setup()
            dialog.btn_tutorial.click()
            self.app.processEvents()
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
            for step in range(5):
                dialog.set_step(step)
                self.assertTrue(dialog.step_title.text().endswith(f"{step + 1}/5"))
                self.assertEqual(dialog.btn_back.isEnabled(), step > 0)

    def test_warning_defaults_to_no_then_explicit_consent_preserves_and_backs_up(self):
        from PySide6.QtWidgets import QInputDialog

        path = self.fixture.root / "PSUserConfig.txt"
        before = b"OtherOption 1\r\nWarnRunningScripts 1\r\n"
        path.write_bytes(before)
        with patch.object(self.b, "installed_photoshops", return_value=[self.fixture.target]), \
                patch.object(self.b, "photoshop_config_path", return_value=str(path)), \
                patch.object(self.b, "running_photoshops", return_value=[]), \
                patch.object(QInputDialog, "getItem", return_value=(self.window.t["guide_warning_off_title"], True)) as choice, \
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
                self.assertEqual(choice.call_args.args[4], 1)
                choice.return_value = self.window.t["guide_warning_keep_title"], True
                dialog.configure_photoshop_warning()
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse(self.window.settings["photoshop_warning_choice"]["disabled"])
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
        self.assertEqual(dialog.warning_status.warning.text(), dialog.lang["guide_warning_keep"])
        self.assertTrue(all(not p.exists() for p in paths))

    def test_photoshop_card_keeps_identity_build_path_and_runtime_separate(self):
        b = self.b
        full = "28.0 (20261027.r.20 3951c45)"
        target = dict(self.fixture.target, product="Adobe Photoshop 2027", version=full)
        another = {"Id": 43, "Path": r"C:\Example\Other\Photoshop.exe"}
        with patch.object(b, "photoshop_exe_info", return_value=target):
            dialog = self.guide("ko")
            card = dialog.ps_status
            self.assertEqual(card.product.text(), "Adobe Photoshop 2027")
            self.assertEqual(card.version.text(), "버전 28.0")
            self.assertIn(full, card.version.toolTip())
            self.assertEqual(card.path.text(), target["path"])
            self.assertFalse(card.icon.pixmap().isNull())
            for paths, key, other in (([], "guide_ps_closed", False),
                                      ([another], "guide_ps_closed", True),
                                      ([another, {"Id": 42, "Path": target["path"]}], "guide_ps_running", True)):
                with patch.object(b, "running_photoshops", return_value=paths):
                    dialog.refresh_status()
                self.assertEqual(card.runtime.text(), dialog.lang[key])
                self.assertEqual(not card.other.isHidden(), other)
            with patch.object(b, "running_photoshops", side_effect=RuntimeError):
                dialog.refresh_status()
            self.assertEqual(card.runtime.text(), dialog.lang["guide_ps_runtime_unknown"])
        with patch.object(b, "photoshop_exe_info", side_effect=ValueError), \
                patch.object(b, "QFileIconProvider") as provider:
            dialog.refresh_status()
            provider.assert_not_called()
        self.assertEqual(card.product.text(), dialog.lang["guide_ps_missing"])
        self.assertTrue(card.version.isHidden())
        self.assertFalse(card.icon.pixmap().isNull())
        self.assertFalse(dialog.can_change_warning)
        self.assertTrue(all(not button.isEnabled() for button in dialog.warning_buttons))

    def test_guide_cards_fit_compact_layout_in_all_languages(self):
        b = self.b
        self.app.setStyle("Fusion")
        b.apply_workspace_theme(self.app)
        for language in ("ko", "en", "ja"):
            dialog = self.guide(language)
            dialog.resize(330, 330)
            dialog.show()
            for step in range(5):
                with self.subTest(language=language, step=step):
                    dialog.set_step(step)
                    self.app.processEvents()
                    self.assertEqual(dialog.pages.currentWidget().horizontalScrollBar().maximum(), 0)
                    self.assertTrue(dialog.btn_next.isVisible())
                    self.assertLess(dialog.btn_next.geometry().bottom(), dialog.height())
                    action = (dialog.step_title, dialog.ps_edit, dialog.warning_buttons[1], dialog.ase_edit, dialog.btn_tutorial)[step]
                    self.assertTrue(dialog.isAncestorOf(action))
                    if step != dialog.WELCOME:
                        self.assertTrue(dialog.pages.isAncestorOf(action))
                    self.assertTrue(action.isVisible())
                    if step == dialog.REVIEW:
                        grid = dialog.review_lines[0].parentWidget().layout().itemAt(0).layout()
                        for row, label in enumerate(dialog.review_lines):
                            name = grid.itemAtPosition(row, 0).layout()
                            self.assertGreaterEqual(label.x(), name.geometry().right() + 1)
                    card = {dialog.CONNECTION: dialog.ps_status, dialog.WARNING: dialog.warning_status}.get(step)
                    if card:
                        for label in (card.product, card.path):
                            if label.isVisible():
                                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
            dialog.resize(580, 685)
            for step in (dialog.WARNING, dialog.REVIEW):
                dialog.set_step(step)
                self.app.processEvents()
                self.assertEqual(dialog.pages.currentWidget().verticalScrollBar().maximum(), 0, (language, step))
            dialog.hide()

    def test_fresh_probe_is_observed_without_clipboard_write(self):
        import sys
        from unittest.mock import Mock
        dialog = self.guide()
        self.window.setup_guide = dialog
        self.addCleanup(setattr, self.window, "setup_guide", None)
        dialog.set_step(dialog.ASEPRITE)
        dialog.ase_test.setEnabled(True)
        dialog.start_probe()
        self.addCleanup(dialog._probe_dir.cleanup)
        self.assertEqual(dialog.key_status[0].text(), dialog.flow("waiting"))
        practice = Path(dialog._probe_path)
        token = practice.parent.name.removeprefix("ps2ase-copy-")
        self.assertEqual(practice.read_bytes(), (lifecycle.ROOT / "assets/practice/testfile.aseprite").read_bytes())
        clipboard = Mock()
        with patch.dict(sys.modules, win32clipboard=clipboard):
            for name, path, frame, session, status, expected in (
                ("other", practice.with_name("Other.aseprite"), 1, token, True, False),
                ("empty", practice, 2, token, True, False),
                ("stale", practice, 1, "f" * 32, True, False),
                ("partial", practice, 3, token, False, False),
                ("first", practice, 3, token, True, True),
            ):
                job = practice.parent / "copies" / name
                (job / "layers").mkdir(parents=True)
                (job / "layers/pixel.png").touch()
                (job / "trigger_copy.json").write_text(json.dumps({
                    "job_id": name, "signature": "ase_ps_bridge_payload", "source_app": "aseprite"}))
                (job / "metadata.json").write_text(json.dumps({"job_id": name, "document_name": practice.name}))
                if status:
                    (job / "status_done.json").write_text(json.dumps({
                        "job_id": name, "status": "done", "layer_count": 1, "practice_frame": frame,
                        "practice_token": session, "practice_path": str(path)}))
                dialog.poll_practice()
                self.assertEqual(dialog.f5_seen, expected)
        clipboard.OpenClipboard.assert_not_called()
        self.assertFalse(dialog.f4_seen)

    def test_transient_clipboard_does_not_clear_practice_edit_history(self):
        import sys
        from unittest.mock import Mock
        guide = self.guide()
        guide.set_step(guide.ASEPRITE)
        guide.ase_test.setEnabled(True)
        guide.start_probe()
        self.addCleanup(guide._probe_dir.cleanup)
        self.window.setup_guide = guide
        self.addCleanup(setattr, self.window, "setup_guide", None)
        self.window.last_job_id = "previous"
        self.window.current_job_path = str(self.fixture.root)
        self.window.undo_stack = [(False, False, 0)]
        self.window.redo_stack = [(True, False, 90)]
        clipboard = Mock()
        clipboard.GetClipboardData.side_effect = OSError("Clipboard temporarily busy")
        with patch.dict(sys.modules, win32clipboard=clipboard):
            self.window.check_clipboard()
            clipboard.CloseClipboard.assert_called_once()
            clipboard.GetClipboardData.side_effect = None
            clipboard.GetClipboardData.return_value = "Copy practice.aseprite"
            for _ in range(6):
                self.window.check_clipboard()
        self.assertEqual(self.window.last_job_id, "previous")
        self.assertEqual(self.window.undo_stack, [(False, False, 0)])
        self.assertEqual(self.window.redo_stack, [(True, False, 90)])

    def test_existing_warning_value_is_not_reported_as_session_change(self):
        cfg = self.fixture.root / "PSUserConfig.txt"
        cfg.write_text("WarnRunningScripts 0\n")
        with patch.object(self.b, "photoshop_config_path", return_value=str(cfg)), \
                patch.object(self.b, "running_photoshops", return_value=[]):
            dialog = self.guide()
            self.assertEqual(dialog.warning_status.warning.text(), dialog.flow("disabled"))
            self.assertEqual(dialog.warning_live.text(), dialog.lang["warning_observe"])
            self.assertNotIn(dialog.flow("restart"), dialog.warning_hint.text())
            self.window.guide_warning_changes.add(str(cfg))
            dialog.refresh_status()
            self.assertEqual(dialog.warning_hint.text(), dialog.flow("restart"))

    def test_f4_isolated_lesson_only_after_f5_and_rejects_stale_result(self):
        dialog = self.guide()
        dialog.set_step(dialog.ASEPRITE)
        self.window.undo_stack = [(False, False, 0)]
        self.window.redo_stack = [(True, False, 90)]
        dialog.ase_test.setEnabled(True)
        dialog.start_probe()
        self.addCleanup(dialog._probe_dir.cleanup)
        self.assertTrue(dialog.f4_record.isHidden())
        dialog.start_paste_practice()
        self.assertIsNone(dialog._practice_source)
        dialog.f5_seen = True
        dialog.update_summary()
        dialog.start_paste_practice()
        self.assertNotEqual(dialog._practice_source, dialog._practice_target)
        with self.b.Image.open(dialog._practice_target) as sprite:
            self.assertIsNone(sprite.getbbox())
        self.assertTrue(dialog.f4_record.isHidden())
        dialog.copy_practice()
        self.fixture.spin(lambda: not hasattr(self.window, "ps_worker"))
        path, token, ready = dialog._practice_job
        self.assertTrue(ready)
        self.assertFalse(Path(path).is_relative_to(self.window.temp_dir))
        marker = Path(dialog._practice_target + ".ps2ase.json")
        payload = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(payload["guide_target"], dialog._practice_target)
        self.assertEqual(payload["guide_nonce"], token)
        response = Path(path) / "aseprite_paste_done.txt"
        response.write_text("stale")
        dialog.check_practice_paste()
        self.assertFalse(dialog.f4_seen)
        response.write_text(token)
        dialog.check_practice_paste()
        self.assertTrue(dialog.f4_received)
        self.assertTrue(dialog.f4_seen and dialog.f5_seen)
        self.assertEqual(dialog.review_lines[6].text(), dialog.lang["f4_observed"])
        self.assertEqual(dialog.probe_intro.text(), dialog.flow("test_close_note"))
        self.assertEqual(self.window.undo_stack, [(False, False, 0)])
        self.assertEqual(self.window.redo_stack, [(True, False, 90)])
        self.window.cur_h, self.window.cur_v, self.window.cur_angle = True, False, 0
        self.window.handle_undo()
        self.assertEqual((self.window.cur_h, self.window.cur_v, self.window.cur_angle), (False, False, 0))
        self.window.handle_redo()
        self.assertEqual((self.window.cur_h, self.window.cur_v, self.window.cur_angle), (True, False, 0))
        dialog.finish_probe()
        self.assertFalse(marker.exists())
        self.assertTrue(dialog.f4_seen and dialog.f5_seen)

    def test_startup_never_installs_and_conflicting_keys_need_explicit_consent(self):
        b = self.b
        ase = self.fixture.root / "Aseprite"
        ase.mkdir()
        keys = ase / "user.aseprite-keys"
        old = b'<keyboard version="1"><commands><key command="Other" shortcut="F4"/></commands></keyboard>'
        keys.write_bytes(old)
        paste = self.fixture.root / "paste.lua"
        copy = self.fixture.root / "copy.lua"
        paste.touch()
        copy.touch()
        with patch.object(b, "setup_aseprite_environment") as install:
            self.window.init_environment()
            install.assert_not_called()
        with patch.dict(self.b.os.environ, APPDATA=str(self.fixture.root)):
            ok, message = self.real_setup(str(paste), str(copy))
            self.assertFalse(ok)
            self.assertIn("F4", message)
            self.assertEqual(keys.read_bytes(), old)
            self.assertFalse((ase / "scripts").exists())
            ok, _ = self.real_setup(str(paste), str(copy), replace_conflicts=True)
            self.assertTrue(ok)
            self.assertEqual(next(ase.glob("user.aseprite-keys.*.bak")).read_bytes(), old)
            self.assertEqual(b.aseprite_installation_status(str(paste), str(copy)), (True, True))
            contents = keys.read_bytes()
            self.assertTrue(self.real_setup(str(paste), str(copy))[0])
            self.assertEqual(keys.read_bytes(), contents)
            self.assertEqual(len(list(ase.glob("user.aseprite-keys.*.bak"))), 1)

    def test_unremembered_alignment_is_not_reset_when_settings_close(self):
        b = self.b
        self.window.settings["default_alignment"] = "ground_line"
        self.window.remember_alignment.setChecked(False)
        self.window.radio_center.click()
        dialog = b.SettingsDialog(self.window.settings, self.window.t, self.window)
        with patch.object(dialog, "exec", return_value=True):
            self.window.open_settings(dialog)
        self.assertEqual(self.window.get_align_mode(), "center")
        self.assertEqual(b.load_settings()["default_alignment"], "ground_line")
        self.window.remember_alignment.setChecked(True)
        self.assertEqual(b.load_settings()["default_alignment"], "center")


    def test_direct_open_uses_only_the_generated_file_and_never_relaunches_existing_host(self):
        exe = r"C:\Example\Aseprite\aseprite.exe"
        self.window.settings["aseprite_exe"] = exe
        dialog = self.guide()
        dialog.set_step(dialog.ASEPRITE)
        dialog.ase_test.setEnabled(True)
        dialog.start_probe()
        self.addCleanup(dialog._probe_dir.cleanup)
        path = dialog._probe_path
        with patch.object(self.b.QProcess, "startDetached", return_value=(False, 0)) as launch, \
                patch.object(dialog, "open_probe_folder") as show_folder:
            for state in ("guide_ps_running", "guide_ps_runtime_unknown"):
                with patch.object(self.b, "aseprite_runtime", return_value=(True, state)):
                    dialog.open_probe_document()
                    self.assertEqual(dialog.probe_open_note.text(), dialog.flow("use_running"))
                    self.assertTrue(dialog.probe_open.isHidden())
                    self.assertFalse(dialog.probe_folder.isHidden())
            launch.assert_not_called()
            with patch.object(self.b, "aseprite_runtime", return_value=(True, "guide_ps_closed")):
                dialog.open_probe_document()
                launch.assert_called_once_with(exe, [path], os.path.dirname(exe))
                self.assertEqual(dialog.probe_open_note.text(), dialog.flow("open_failed"))
                self.assertFalse(dialog.probe_folder.isHidden())
                self.assertTrue(dialog.probe_open.isHidden())
                show_folder.assert_called_once()
                dialog.finish_probe()
                dialog.ase_test.setEnabled(True)
                dialog.start_probe()
                launch.return_value = (True, 1)
                dialog.open_probe_document()
                self.assertEqual(dialog.probe_open_note.text(), dialog.flow("open_requested"))
                dialog.open_probe_document()
                self.assertEqual(launch.call_count, 2)
        self.assertFalse(dialog.f5_seen)

    def test_probe_runtime_refresh_only_updates_current_test(self):
        exe = r"C:\Example\Aseprite\aseprite.exe"
        self.window.settings["aseprite_exe"] = exe
        dialog = self.guide()
        dialog.set_step(dialog.ASEPRITE)
        dialog.ase_test.setEnabled(True)
        with patch.object(dialog, "request_probe_runtime"):
            dialog.start_probe()
        self.addCleanup(dialog._probe_dir.cleanup)
        request = (dialog._probe_path, exe)
        dialog._probe_runtime_request = request
        dialog.apply_probe_runtime(("stale", exe), (True, "guide_ps_closed"))
        self.assertTrue(dialog.probe_open.isHidden())
        dialog.apply_probe_runtime(request, (True, "guide_ps_closed"))
        self.assertFalse(dialog.probe_open.isHidden())
        self.assertTrue(dialog.probe_folder.isHidden())
        dialog._probe_runtime_request = request
        dialog.apply_probe_runtime(request, (True, "guide_ps_running"))
        self.assertTrue(dialog.probe_open.isHidden())
        self.assertFalse(dialog.probe_folder.isHidden())

    def test_probe_navigation_cleans_only_probe_and_preserves_session_results(self):
        dialog = self.guide()
        dialog.set_step(dialog.ASEPRITE)
        dialog.ase_test.setEnabled(True)
        dialog.start_probe()
        work = Path(dialog._probe_dir.name)
        jpeg = work / "unrelated.txt"
        jpeg.touch()
        generated = Path(dialog._probe_path)
        self.assertEqual(dialog.btn_next.text(), dialog.flow("skip_test_next"))
        dialog.f5_seen = True
        dialog.update_summary()
        dialog.next_step()
        self.assertEqual(dialog.pages.currentIndex(), dialog.REVIEW)
        self.assertFalse(generated.exists())
        self.assertTrue(jpeg.exists())
        self.assertTrue(dialog.f5_seen)
        dialog.reject()
        self.assertTrue(self.guide().f5_seen)
        self.window.settings["aseprite_exe"] = r"C:\Other\aseprite.exe"
        self.assertFalse(self.guide().f5_seen)

    def test_ready_aseprite_does_not_reinstall_and_unknown_running_state_biases_to_read_only(self):
        b = self.b
        self.window.settings["aseprite_exe"] = r"C:\Example\aseprite.exe"
        with patch.object(b, "aseprite_runtime", return_value=(True, "guide_ps_runtime_unknown")), \
                patch.object(b, "aseprite_installation_status", return_value=(False, False)) as inspect, \
                patch.object(b, "setup_aseprite_environment") as install:
            dialog = self.guide()
            dialog.set_step(dialog.ASEPRITE)
            self.assertFalse(dialog.ase_test.isEnabled())
            self.assertFalse(dialog.ase_install.isEnabled())
            self.assertFalse(dialog.ase_edit.isEnabled())
            inspect.return_value = (True, True)
            dialog.refresh_status()
            self.assertTrue(dialog.ase_test.isEnabled())
            self.assertTrue(dialog.ase_install.isHidden())
            self.assertEqual(dialog.ase_edit.text(), dialog.lang["ase_trust_action"])
            dialog.ase_edit.click()
            self.assertIsNotNone(dialog._trust_dialog)
            self.assertIsNone(dialog._probe_dir)
            self.assertIsNone(dialog._probe_name)
            self.assertFalse(dialog.f5_seen)
            dialog._trust_dialog.reject()
            dialog.ase_test.click()
            self.assertTrue(Path(dialog._probe_path).is_file())
            self.addCleanup(dialog._probe_dir.cleanup)
            install.assert_not_called()


    def test_summary_actions_reopen_the_relevant_step_and_keep_warning_optional(self):
        cfg = self.fixture.root / "PSUserConfig.txt"
        with patch.object(self.b, "photoshop_config_path", return_value=str(cfg)):
            dialog = self.guide()
        dialog.show()
        self.assertFalse(dialog.cb_dont_show.isVisible())
        dialog.set_step(dialog.REVIEW)
        self.assertTrue(dialog.cb_dont_show.isVisible())
        self.assertIn(dialog.flow("optional"), dialog.review_lines[2].text())
        self.assertIn(dialog.lang["guide_warning_keep"], dialog.review_lines[2].text())
        self.assertTrue(dialog.review_actions[2].isHidden())
        dialog.review_actions[7].click()
        self.assertEqual(dialog.pages.currentIndex(), dialog.ASEPRITE)
        self.assertFalse(dialog.cb_dont_show.isVisible())


if __name__ == "__main__":
    unittest.main()
