"""Qt synthetic input regressions; these are NOT Windows hardware-mouse tests."""
import json
import sys
import time
import types
import unittest
from unittest.mock import patch

import test_photoshop_job_lifecycle as lifecycle


class StartupInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lifecycle.JobLifecycleTests.setUpClass()
        cls.addClassCleanup(lifecycle.JobLifecycleTests.doClassCleanups)

    def setUp(self):
        self.fixture = lifecycle.JobLifecycleTests("test_success_then_second_copy")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.b = self.fixture.b
        self.window = self.fixture.window

    def test_first_qt_mouse_click_at_each_delay_closes_tutorial(self):
        from PySide6.QtTest import QTest
        for delay in (0, 100, 250, 500, 1000):
            with self.subTest(qt_synthetic_delay_ms=delay):
                begin = len(self.window.diagnostic_records)
                dialog = self.b.TutorialDialog(self.window.t, self.window)
                clicks = []
                dialog.btn_close.clicked.connect(lambda: clicks.append(True))
                self.b.QTimer.singleShot(delay, lambda: QTest.mouseClick(dialog.btn_close, self.b.Qt.LeftButton))
                result = dialog.exec()
                events = [e["details"] for e in list(self.window.diagnostic_records)[begin:]
                          if e["state"] == "STARTUP_DIALOG_INPUT"]
                phases = [e["phase"] for e in events]
                self.assertEqual(result, self.b.QDialog.Accepted)
                self.assertEqual(clicks, [True])
                for phase in ("SHOWN", "PRESS", "RELEASE", "CLICKED", "ACCEPT_BEGIN", "HIDDEN", "FINISHED", "ACCEPT_END"):
                    self.assertEqual(phases.count(phase), 1, (delay, phases))
                self.assertLess(phases.index("CLICKED"), phases.index("ACCEPT_BEGIN"))
                press = next(e for e in events if e["phase"] == "PRESS")
                ended = next(e for e in events if e["phase"] == "ACCEPT_END")
                self.assertTrue(press["active_modal"])
                self.assertTrue(press["enabled"])
                self.assertLess(ended["monotonic_ms"] - press["monotonic_ms"], 200)
                self.fixture.shiboken.delete(dialog)

    def test_modal_dialog_suppresses_both_poll_callbacks(self):
        from PySide6.QtTest import QTest
        dialog = self.b.TutorialDialog(self.window.t, self.window)
        def during_modal():
            self.window.poll_clipboard()
            QTest.mouseClick(dialog.btn_close, self.b.Qt.LeftButton)
        with patch.object(self.window, "check_clipboard") as clipboard, \
                patch.object(self.window, "check_temp_folder") as jobs:
            self.b.QTimer.singleShot(0, during_modal)
            dialog.exec()
            clipboard.assert_not_called()
            jobs.assert_not_called()
            self.window.poll_clipboard()
            clipboard.assert_called_once()
            jobs.assert_called_once()
        self.fixture.shiboken.delete(dialog)

    def test_history_scan_has_no_sleep_and_incomplete_json_retries(self):
        root = self.fixture.root / "history"
        root.mkdir()
        self.window.temp_dir = str(root)
        self.window.processed_jobs.clear()
        for i in range(55):
            self.copy_job(root, str(i))
        partial = root / "partial"
        partial.mkdir()
        (partial / "trigger_copy.json").write_text('{"source_app":')
        writes = []
        with patch.object(self.window, "publish_copy_payload", side_effect=lambda payload: writes.append(payload) is None), \
                patch.object(self.b.time, "sleep") as sleep:
            self.window.check_temp_folder()
            self.assertEqual(len(self.window.processed_jobs), 55)
            self.assertNotIn("partial", self.window.processed_jobs)
            self.copy_job(root, "partial")
            self.window.check_temp_folder()
            self.assertEqual(len(self.window.processed_jobs), 56)
            self.assertEqual(len(writes), 2)
            self.assertTrue(all(p["settings"]["align_mode"] == "ground_line" for p in writes))
            sleep.assert_not_called()

    @staticmethod
    def copy_job(root, job_id):
        job = root / job_id
        job.mkdir(exist_ok=True)
        payload = {"signature": "ase_ps_bridge_payload", "source_app": "aseprite", "job_id": job_id,
                   "job_path": str(job), "summary": {"layer_count": 1}}
        (job / "trigger_copy.json").write_text(json.dumps(payload))
        (job / "metadata.json").write_text("{}")
        (job / "status_done.json").write_text(json.dumps({"job_id": job_id, "status": "done", "layer_count": 1}))
        return payload

    def test_legacy_inbox_does_not_republish_on_restart_but_retains_valid_clipboard(self):
        root = self.fixture.root / "temp"
        root.mkdir()
        payload = self.copy_job(root, "old")
        (root / "pending-before-start").mkdir()
        with patch.object(self.b, "BASE_DIR", str(self.fixture.root)), \
                patch.object(self.b, "get_resource_path", side_effect=lambda path: str(lifecycle.ROOT / path)):
            restarted = self.b.BridgeApp()
        restarted.clip_timer.stop()
        self.addCleanup(lambda: self.fixture.shiboken.delete(restarted))
        self.copy_job(root, "pending-before-start")
        clipboard = types.SimpleNamespace(OpenClipboard=lambda: None, CloseClipboard=lambda: None,
                                          CF_UNICODETEXT=13, IsClipboardFormatAvailable=lambda _: True,
                                          GetClipboardData=lambda _: json.dumps(payload))
        with patch.object(restarted, "publish_copy_payload", return_value=True) as publish, \
                patch.dict(sys.modules, win32clipboard=clipboard), \
                patch.object(restarted, "start_preview_generation") as preview:
            for current_clipboard in ("user text", None):
                clipboard.IsClipboardFormatAvailable = lambda _: current_clipboard is not None
                clipboard.GetClipboardData = lambda _: current_clipboard
                restarted.check_clipboard()
                restarted.check_temp_folder()
            clipboard.IsClipboardFormatAvailable = lambda _: True
            clipboard.GetClipboardData = lambda _: json.dumps(payload)
            restarted.check_clipboard()
            restarted.check_temp_folder()
            publish.assert_not_called()
            preview.assert_called_once_with(payload["job_path"])
            self.assertTrue(restarted.btn_ps_paste.isEnabled())
            self.assertTrue((root / "old/trigger_copy.json").is_file())
            self.copy_job(root, "new")
            restarted.check_temp_folder()
            self.assertEqual(publish.call_args.args[0]["job_id"], "new")

    def test_pending_copy_waits_for_completion_and_newest_ready_wins_after_failed_publish(self):
        root = self.fixture.root / "history"
        root.mkdir()
        self.window.temp_dir = str(root)
        self.window.snapshot_copy_inbox()
        self.copy_job(root, "older")
        self.copy_job(root, "newer")
        done = root / "newer/status_done.json"
        content = done.read_text()
        done.unlink()
        with patch.object(self.window, "clipboard_sequence", return_value=14), \
                patch.object(self.window, "publish_copy_payload", side_effect=[False, True]) as publish:
            self.window.check_temp_folder()
            self.assertEqual(publish.call_args.args[0]["job_id"], "older")
            done.write_text(content)
            self.window.check_temp_folder()
            self.window.check_temp_folder()
            self.assertEqual([c.args[0]["job_id"] for c in publish.call_args_list], ["older", "newer"])

    def test_failed_publish_does_not_retry_over_newer_clipboard_content(self):
        root = self.fixture.root / "history"
        root.mkdir()
        self.window.temp_dir = str(root)
        self.window.snapshot_copy_inbox()
        self.copy_job(root, "new")
        with patch.object(self.window, "clipboard_sequence", side_effect=[4, 5]), \
                patch.object(self.window, "publish_copy_payload", return_value=False) as publish:
            self.window.check_temp_folder()
            self.window.check_temp_folder()
            publish.assert_called_once()
            self.assertIn("new", self.window.processed_jobs)

    def test_managed_startup_defers_poll_timer_until_popups_finish(self):
        window = self.b.BridgeApp(startup_progress=lambda *a: None)
        try:
            self.assertFalse(window.clip_timer.isActive())
            window._startup_ui_ready = True
            window.show_startup_dialogs()
            self.assertTrue(window.clip_timer.isActive())
        finally:
            window.clip_timer.stop()
            window.close()
            self.fixture.shiboken.delete(window)

    def test_heartbeat_records_a_blocked_gui_loop(self):
        from PySide6.QtTest import QTest
        dialog = self.b.TutorialDialog(self.window.t, self.window)
        self.b.QTimer.singleShot(0, lambda: time.sleep(0.2))  # Test-only injected stall.
        self.b.QTimer.singleShot(250, lambda: QTest.mouseClick(dialog.btn_close, self.b.Qt.LeftButton))
        dialog.exec()
        stalls = [e for e in self.window.diagnostic_records if e["state"] == "STARTUP_DIALOG_INPUT"
                  and e["details"]["phase"] == "GUI_STALL"]
        self.assertTrue(stalls)
        self.assertGreater(stalls[-1]["details"]["gap_ms"], 150)
        self.fixture.shiboken.delete(dialog)


if __name__ == "__main__":
    unittest.main()
