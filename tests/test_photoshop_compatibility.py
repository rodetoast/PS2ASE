"""Stdlib-only compatibility tests; no Photoshop or user settings are changed."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import datetime
import traceback
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class Signal:
    def __init__(self, *args):
        self.events = []

    def emit(self, *args):
        self.events.append(args)


class Thread:
    def __init__(self):
        pass


def helpers():
    # Load only the isolated helpers/worker, so tests also run without Qt/pywin32.
    import re
    import shutil
    import uuid
    import winreg
    tree = ast.parse((ROOT / "bridge_ui.py").read_text(encoding="utf-8"))
    names = {"_photoshop_query", "photoshop_exe_info", "running_photoshops",
             "installed_photoshops", "resolve_photoshop_target", "photoshop_config_path",
             "photoshop_warning_config", "disable_photoshop_warning",
             "make_photoshop_wrapper", "PhotoshopCLIWorker", "diagnostic_event"}
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    bridge = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "BridgeApp")
    nodes.append(next(node for node in bridge.body if isinstance(node, ast.FunctionDef)
                      and node.name == "check_temp_folder"))
    messages = {key: key for key in ("ps_script_error", "ps_timeout_pending", "ps_timeout_running",
                                     "ps_timeout_closed", "ps_timeout_unknown")}
    ns = dict(os=os, json=json, re=re, shutil=shutil, uuid=uuid, winreg=winreg,
              subprocess=subprocess, time=time, datetime=datetime, traceback=traceback, QThread=Thread, Signal=Signal,
              LANG={"ko": messages})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "bridge_ui.py", "exec"), ns)
    return ns


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.ns = helpers()
        (ROOT / "temp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "temp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = {"path": str(self.root / "Photoshop.exe"), "major": 27,
                       "version": "27.11", "product": "Adobe Photoshop"}

    def test_settings_paths_2024_2025_2026(self):
        for major, year in ((25, 2024), (26, 2025), (27, 2026)):
            folder = self.root / "Adobe" / f"Adobe Photoshop {year}" / f"Adobe Photoshop {year} Settings"
            folder.mkdir(parents=True)
            info = dict(self.target, major=major)
            self.assertEqual(self.ns["photoshop_config_path"](info, str(self.root)),
                             str(folder / "PSUserConfig.txt"))
        with self.assertRaises(ValueError):
            self.ns["photoshop_config_path"](dict(self.target, major=99), str(self.root))
        with self.assertRaises(ValueError):
            self.ns["photoshop_config_path"](dict(self.target, product="Photoshop Beta"), str(self.root))

    def test_missing_settings_is_not_created_or_guessed(self):
        with self.assertRaises(ValueError):
            self.ns["photoshop_config_path"](self.target, str(self.root))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_new_product_year_uses_verified_product_not_install_folder(self):
        for major, year in ((28, 2027), (29, 2028)):
            folder = self.root / "Adobe" / f"Adobe Photoshop {year}" / f"Adobe Photoshop {year} Settings"
            folder.mkdir(parents=True)
            info = dict(self.target, major=major, product=f"Adobe Photoshop {year}",
                        path=str(self.root / "Adobe Photoshop 2025" / "Photoshop.exe"))
            self.assertEqual(self.ns["photoshop_config_path"](info, str(self.root)),
                             str(folder / "PSUserConfig.txt"))

    def test_unidentified_future_product_and_version_disagreement_fail_closed(self):
        for info in (dict(self.target, major=28),
                     dict(self.target, major=27, product="Adobe Photoshop 2027"),
                     dict(self.target, major=28, product="Adobe Photoshop 2027 Beta")):
            with self.assertRaises(ValueError):
                self.ns["photoshop_config_path"](info, str(self.root))

    def test_no_arbitrary_version_fallback(self):
        other = dict(self.target, path=str(self.root / "other" / "Photoshop.exe"))
        with patch.dict(self.ns, photoshop_exe_info=lambda path: self.target):
            resolve = self.ns["resolve_photoshop_target"]
            self.assertEqual(resolve(self.target["path"], [{"Path": self.target["path"]}], []), self.target)
            with self.assertRaises(ValueError):
                resolve(self.target["path"], [{"Path": other["path"]}], [])
            with self.assertRaises(ValueError):
                resolve("", [], [self.target, other])
            self.assertEqual(resolve("", [], [self.target]), self.target)
        with patch.dict(self.ns, photoshop_exe_info=lambda path: (_ for _ in ()).throw(ValueError("invalid"))):
            with self.assertRaises(ValueError):
                self.ns["resolve_photoshop_target"]("missing.exe", [], [self.target])

    def test_version_is_read_from_executable_not_folder_name(self):
        Path(self.target["path"]).touch()
        response = {"ProductName": "Adobe Photoshop", "FileVersion": "27.11", "FileMajorPart": 27}
        with patch.dict(self.ns, _photoshop_query=lambda cmd: response):
            self.assertEqual(self.ns["photoshop_exe_info"](self.target["path"])["major"], 27)
        with patch.dict(self.ns, _photoshop_query=lambda cmd: {}):
            with self.assertRaises(ValueError):
                self.ns["photoshop_exe_info"](self.target["path"])

    def test_unreadable_running_path_is_not_ignored(self):
        with patch.dict(self.ns, _photoshop_query=lambda cmd: [{"Id": 123, "Path": None}]):
            with self.assertRaises(RuntimeError):
                self.ns["running_photoshops"]()

    def test_config_backup_preserve_and_idempotence(self):
        config = self.root / "PSUserConfig.txt"
        original = b"# keep\r\nOtherOption 1\r\nWarnRunningScripts 1 # note\r\n"
        config.write_bytes(original)
        backup = self.ns["disable_photoshop_warning"](str(config))
        self.assertEqual(Path(backup).read_bytes(), original)
        self.assertEqual(config.read_bytes(), original.replace(b"Scripts 1", b"Scripts 0"))
        before = config.stat().st_mtime_ns
        self.assertIsNone(self.ns["disable_photoshop_warning"](str(config)))
        self.assertEqual(config.stat().st_mtime_ns, before)
        self.assertEqual(len(list(self.root.glob("*.bak"))), 1)

    def test_config_append_and_utf16_endianness(self):
        for encoding, bom in (("utf-8", b""), ("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")):
            config = self.root / (encoding + ".txt")
            original = bom + "# keep\r\nOtherOption 1".encode(encoding)
            config.write_bytes(original)
            self.ns["disable_photoshop_warning"](str(config))
            self.assertEqual(config.read_bytes(), original + "\r\nWarnRunningScripts 0\r\n".encode(encoding))
            config.write_bytes(bom + "WarnRunningScripts 1\r\n# keep".encode(encoding))
            self.ns["disable_photoshop_warning"](str(config))
            self.assertEqual(config.read_bytes(), bom + "WarnRunningScripts 0\r\n# keep".encode(encoding))

    def test_duplicate_or_unknown_option_fails_without_writing(self):
        for text in ("WarnRunningScripts 1\nWarnRunningScripts 0\n", "WarnRunningScripts yes\n",
                     "WarnRunningScripts 0\nWarnRunningScripts yes\n"):
            config = self.root / "PSUserConfig.txt"
            config.write_text(text, encoding="utf-8")
            original = config.read_bytes()
            with self.assertRaises(ValueError):
                self.ns["disable_photoshop_warning"](str(config))
            self.assertEqual(config.read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.bak")), [])

    def worker(self, template="photoshop_copy.jsx"):
        worker = self.ns["PhotoshopCLIWorker"](str(ROOT / "scripts" / template),
                                               self.target["path"], "test_job", str(self.root), "ground_line")
        worker.result_ready.events.clear()
        worker.log.events.clear()
        return worker

    def run_worker(self, response=None, started=False, running=True, mode="normal", align="ground_line",
                   template="photoshop_copy.jsx", debug=False):
        worker = self.worker(template)
        worker.debug = debug
        worker.frame_mode = mode
        worker.align_mode = align
        def launch(*args, **kwargs):
            job = Path(worker.job_path)
            token = (job / "active_ps_attempt.txt").read_text()
            if started:
                (job / f"ps_started_{token}.txt").write_text("27.11")
            if response is not None:
                (job / f"ps_result_{token}.txt").write_text(response)
            return object()
        ticks = iter((0, 0, 31))
        processes = [{"Id": 123, "Path": self.target["path"]}] if running else []
        with patch.dict(self.ns, running_photoshops=lambda: processes,
                        resolve_photoshop_target=lambda *args: self.target), \
                patch.object(subprocess, "Popen", side_effect=launch), \
                patch.object(time, "time", side_effect=lambda: next(ticks)), \
                patch.object(time, "sleep"):
            worker.run()
        self.assertEqual((Path(worker.job_path) / "active_ps_attempt.txt").read_text(), "")
        return worker

    def test_attempt_success_and_internal_error(self):
        worker = self.run_worker("done")
        self.assertEqual(worker.result_ready.events[-1], (True, "Success"))
        self.assertTrue((Path(worker.job_path) / "ps_copy_accepted.txt").exists())
        worker = self.run_worker("error\nscript failed")
        self.assertEqual(worker.result_ready.events[-1], (False, "ps_script_errorscript failed"))

    def test_copy_modes_and_paste_alignment_body_injection_unchanged(self):
        for template in ("photoshop_copy.jsx", "photoshop_paste.jsx"):
            for mode in ("normal", "folder_frames", "layer_frames"):
                for align in ("center", "absolute", "ground_line"):
                    with self.subTest(template=template, mode=mode, align=align):
                        worker = self.run_worker("done", mode=mode, align=align, template=template)
                        job = Path(worker.job_path)
                        generated = max(job.glob("ps_body_*.jsx"), key=lambda p: p.stat().st_mtime_ns)
                        expected = Path(worker.jsx_template_path).read_text(encoding="utf-8")
                        expected = expected.replace('"REPLACE_ME_JOB_PATH"',
                                                    json.dumps(worker.job_path, ensure_ascii=False))
                        expected = expected.replace('"REPLACE_ME_ALIGN_MODE"', json.dumps(align))
                        expected = expected.replace('"REPLACE_ME_FRAME_MODE"', json.dumps(mode))
                        expected = expected.replace('"REPLACE_ME_DEBUG_ENABLED"', "false")
                        token = generated.stem[len("ps_body_"):]
                        expected = expected.replace('"REPLACE_ME_DIAGNOSTICS_PATH"', json.dumps(str(job / ("ps_events_" + token + ".jsonl"))))
                        expected = expected.replace('"REPLACE_ME_ATTEMPT_TOKEN"', json.dumps(token))
                        expected = self.ns["re"].sub(r"(?m)^\s*#target[^\r\n]*", "", expected)
                        self.assertEqual(generated.read_text(encoding="utf-8"), expected)

    def test_debug_snapshot_is_injected_as_boolean_for_each_job(self):
        for enabled in (True, False):
            with self.subTest(debug=enabled):
                worker = self.run_worker("done", debug=enabled)
                generated = Path(worker.job_path) / ("ps_body_" + worker.attempt_token + ".jsx")
                source = generated.read_text(encoding="utf-8")
                self.assertIn("var DEBUG_ENABLED = " + str(enabled).lower() + " === true;", source)
                self.assertNotIn('"REPLACE_ME_DEBUG_ENABLED"', source)

    def test_timeout_diagnostics_and_stale_done_not_accepted(self):
        for started, running, reason in ((False, True, "ps_timeout_pending"),
                                         (True, True, "ps_timeout_running"),
                                         (False, False, "ps_timeout_closed")):
            worker = self.worker()
            job = Path(worker.job_path)
            job.mkdir(exist_ok=True)
            (job / "status_done.json").write_text('{"status":"done"}')
            worker = self.run_worker(started=started, running=running)
            self.assertEqual(worker.result_ready.events[-1], (False, reason))
            self.assertFalse((job / "ps_copy_accepted.txt").exists())

    def test_wrapper_preserves_mode_body_and_checks_host_before_eval(self):
        wrapper = self.ns["make_photoshop_wrapper"](self.target, "body.jsx", "attempt.txt", "unique-token",
                                                   "started.txt", "result.txt", "job")
        self.assertLess(wrapper.index("app.path.fsName"), wrapper.index("$.evalFile"))
        self.assertIn('if (read(attempt) !== token) return', wrapper)
        self.assertIn('app.version.split(".")[0]', wrapper)

    def test_late_copy_trigger_requires_this_attempt_acceptance(self):
        import types
        import sys
        job = self.root / "job"
        job.mkdir()
        payload = {"source_app": "photoshop", "settings": {}}
        (job / "trigger_copy.json").write_text(json.dumps(payload))
        (job / "active_ps_attempt.txt").write_text("")
        updates = []
        fake_clipboard = types.SimpleNamespace(
            OpenClipboard=lambda: None, EmptyClipboard=lambda: None,
            SetClipboardText=lambda text, kind: updates.append(json.loads(text)),
            CloseClipboard=lambda: None, CF_UNICODETEXT=13)
        app = types.SimpleNamespace(temp_dir=str(self.root), processed_jobs=set(),
                                    get_align_mode=lambda: "ground_line",
                                    read_job_frame_mode=lambda path: "folder_frames",
                                    update_clipboard_mode_label=lambda: None)
        with patch.dict(sys.modules, win32clipboard=fake_clipboard), patch.object(time, "sleep"):
            self.ns["check_temp_folder"](app)
            self.assertEqual(updates, [])
            (job / "ps_copy_accepted.txt").write_text("accepted-token")
            self.ns["check_temp_folder"](app)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["settings"]["align_mode"], "ground_line")

    def test_generated_wrapper_with_mock_photoshop_runtime(self):
        node = Path(os.environ.get("NODE_BINARY", str(Path(sys.executable).parent.parent / "node" / "bin" / "node.exe")))
        if not node.is_file():
            self.skipTest("Bundled Node unavailable; JSX runtime mock not run")
        wrapper = self.ns["make_photoshop_wrapper"](self.target, "body.jsx", "attempt.txt", "token",
                                                   "started.txt", "result.txt", "job")
        prelude = r'''
var files = {"attempt.txt": "token", "job/status_done.json": "STALE"};
var calls = 0;
function File(path) { this.fsName = path; }
Object.defineProperty(File.prototype, "exists", {get: function() {return this.fsName in files;}});
File.prototype.open = function(mode) {if (mode === "w") files[this.fsName] = ""; return true;};
File.prototype.read = function() {return files[this.fsName];};
File.prototype.write = function(text) {files[this.fsName] = text;};
File.prototype.close = function() {};
File.prototype.remove = function() {delete files[this.fsName];};
'''
        for scenario in ("done", "wrong_host", "expired", "error", "missing", "late"):
            with self.subTest(scenario=scenario):
                app = {"version": "26.0" if scenario == "wrong_host" else "27.11",
                       "path": {"fsName": str(Path(self.target["path"]).parent)}}
                body = "calls++; if (files['job/status_done.json']) throw Error('stale status survived');"
                if scenario == "done":
                    body += "files['job/status_done.json'] = '{}';"
                elif scenario == "error":
                    body += "throw Error('body error');"
                elif scenario == "late":
                    body += "files['attempt.txt'] = ''; files['job/status_done.json'] = '{}';"
                setup = prelude + "var app = " + json.dumps(app) + ";\n"
                setup += "var $ = {evalFile: function(file) {" + body + "}};\n"
                if scenario == "expired":
                    setup += "files['attempt.txt'] = '';\n"
                script = setup + wrapper.replace("#target photoshop", "")
                script += "\nconsole.log(JSON.stringify({files: files, calls: calls}));"
                result = subprocess.run([str(node), "-e", script], capture_output=True, text=True, check=True)
                output = json.loads(result.stdout)
                files = output["files"]
                if scenario == "done":
                    self.assertEqual(files["result.txt"], "done")
                elif scenario in ("expired", "late"):
                    self.assertNotIn("result.txt", files)
                else:
                    self.assertTrue(files["result.txt"].startswith("error\n"))
                self.assertEqual(output["calls"], 0 if scenario in ("wrong_host", "expired") else 1)


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt dependencies unavailable")
class PhotoshopSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "temp").mkdir(exist_ok=True)
        cls.profile = tempfile.TemporaryDirectory(dir=ROOT / "temp", prefix="ps_selection_")
        cls.addClassCleanup(cls.profile.cleanup)
        env = patch.dict(os.environ, APPDATA=cls.profile.name, QT_QPA_PLATFORM="offscreen")
        env.start()
        cls.addClassCleanup(env.stop)
        spec = importlib.util.spec_from_file_location("bridge_selection_tests", ROOT / "bridge_ui.py")
        cls.bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bridge)
        existing = cls.bridge.QApplication.instance()
        cls.app = existing or cls.bridge.QApplication([])
        if existing is None:
            import shiboken6
            cls.addClassCleanup(lambda: shiboken6.delete(cls.app))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "temp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = self.root / "Photoshop 2026" / "Photoshop.exe"
        self.exe.parent.mkdir()
        self.exe.touch()
        self.info = {"path": str(self.exe), "product": "Adobe Photoshop 2026",
                     "version": "27.11", "major": 27}

    def dialog(self, settings, detected=None):
        b = self.bridge
        with patch.object(b, "running_photoshops", return_value=[]), \
                patch.object(b, "installed_photoshops", return_value=[self.info] if detected is None else detected):
            dlg = b.SettingsDialog(settings, b.LANG["en"])
        import shiboken6
        def dispose():
            dlg.close()
            shiboken6.delete(dlg)
        self.addCleanup(dispose)
        return dlg

    def test_selected_2026_is_restored_when_settings_reopens(self):
        first = self.dialog({})
        first.select_photoshop_version(1)
        saved = first.get_settings()
        reopened = self.dialog(saved)
        self.assertEqual(reopened.ps_versions.currentIndex(), 1)
        self.assertEqual(reopened.ps_versions.currentData(), saved["photoshop_exe"])
        self.assertEqual(reopened.ps_path_input.text(), str(self.exe))

    def test_selection_restores_from_saved_settings_after_restart(self):
        first = self.dialog({})
        first.select_photoshop_version(1)
        settings_file = str(self.root / "bridge_settings.json")
        with patch.object(self.bridge, "SETTINGS_FILE", settings_file):
            self.bridge.save_settings(first.get_settings())
            restarted = self.dialog(self.bridge.load_settings())
        self.assertEqual(restarted.ps_versions.currentData(), str(self.exe))
        self.assertEqual(restarted.ps_path_input.text(), str(self.exe))

    def test_nonexistent_saved_exe_is_not_selected(self):
        missing = str(self.root / "missing" / "Photoshop.exe")
        dlg = self.dialog({"photoshop_exe": missing})
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)
        self.assertEqual(dlg.get_settings()["photoshop_exe"], missing)

    def test_same_version_different_paths_match_only_saved_path(self):
        other = self.root / "other 2026" / "Photoshop.exe"
        other.parent.mkdir()
        other.touch()
        detected = [self.info, dict(self.info, path=str(other))]
        dlg = self.dialog({"photoshop_exe": str(other)}, detected)
        self.assertEqual(dlg.ps_versions.currentIndex(), 2)
        self.assertEqual(dlg.ps_versions.currentData(), str(other))
        unknown = str(self.root / "third 2026" / "Photoshop.exe")
        Path(unknown).parent.mkdir()
        Path(unknown).touch()
        dlg.ps_path_input.setText(unknown)
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)
        self.assertEqual(dlg.get_settings()["photoshop_exe"], unknown)

    def test_deleted_2025_does_not_switch_to_detected_2026(self):
        old = str(self.root / "Photoshop 2025" / "Photoshop.exe")
        dlg = self.dialog({"photoshop_exe": old})
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)
        self.assertEqual(dlg.ps_path_input.text(), old)

    def test_no_detected_photoshop_keeps_placeholder_and_saved_path(self):
        dlg = self.dialog({"photoshop_exe": str(self.exe)}, [])
        self.assertEqual(dlg.ps_versions.count(), 1)
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)
        self.assertEqual(dlg.get_settings()["photoshop_exe"], str(self.exe))

    def test_path_edits_and_browse_updates_keep_selection_consistent(self):
        dlg = self.dialog({"photoshop_exe": str(self.exe)})
        dlg.ps_versions.setCurrentIndex(0)
        dlg.select_photoshop_version(0)
        self.assertEqual(dlg.ps_versions.currentData(), str(self.exe))
        dlg.ps_path_input.setText("")
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)
        dlg.ps_path_input.setText(str(self.exe))
        self.assertEqual(dlg.ps_versions.currentData(), str(self.exe))
        self.exe.unlink()
        dlg.sync_photoshop_version_selection()
        self.assertEqual(dlg.ps_versions.currentIndex(), 0)

    def test_windows_case_and_separator_normalization(self):
        path = str(self.exe).upper().replace("\\", "/")
        dlg = self.dialog({"photoshop_exe": path})
        self.assertEqual(dlg.ps_versions.currentIndex(), 1)
        self.assertEqual(dlg.get_settings()["photoshop_exe"], path)


if __name__ == "__main__":
    unittest.main()
