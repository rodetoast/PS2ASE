"""Real Qt thread lifecycle with simulated Photoshop IPC; no user documents/settings."""
import importlib.util
import builtins
import io
import types
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_photoshop_compatibility import ROOT


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt dependencies unavailable")
class JobLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "temp").mkdir(exist_ok=True)
        cls.profile = tempfile.TemporaryDirectory(dir=ROOT / "temp", prefix="job_lifecycle_")
        cls.addClassCleanup(cls.profile.cleanup)
        environment = patch.dict(os.environ, APPDATA=cls.profile.name, QT_QPA_PLATFORM="offscreen")
        environment.start()
        cls.addClassCleanup(environment.stop)
        spec = importlib.util.spec_from_file_location("bridge_lifecycle_tests", ROOT / "bridge_ui.py")
        cls.b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.b)
        import shiboken6
        cls.shiboken = shiboken6
        cls.app = cls.b.QApplication.instance() or cls.b.QApplication([])
        cls.addClassCleanup(lambda: cls.shiboken.delete(cls.app))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "temp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        b = self.b
        settings = {"language": "en", "photoshop_exe": str(self.root / "Photoshop.exe"),
                    "aseprite_exe": "not-used.exe", "aseprite_trust_confirmed": True,
                    "show_tutorial": False, "default_alignment": "ground_line",
                    "ground_line_default_migrated": True}
        Path(settings["photoshop_exe"]).touch()
        settings_file = self.root / "bridge_settings.json"
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
        self.target = {"path": settings["photoshop_exe"], "major": 27, "version": "27.11",
                       "product": "Adobe Photoshop 2026"}
        self.patch(b, "SETTINGS_FILE", str(settings_file))
        self.patch(b, "BRIDGE_DATA_DIR", str(self.root))
        self.patch(b, "setup_aseprite_environment", lambda *args: (True, "ok"))
        self.patch(b, "running_photoshops", lambda: [{"Id": 42, "Path": self.target["path"]}])
        self.patch(b, "photoshop_exe_info", lambda path: self.target)
        self.patch(b.PhotoshopCLIWorker, "RESPONSE_TIMEOUT", 0.08)
        self.patch(b.PhotoshopCLIWorker, "POLL_INTERVAL", 0.005)
        self.window = b.BridgeApp()
        self.window.clip_timer.stop()
        self.window.temp_dir = str(self.root / "jobs")
        Path(self.window.temp_dir).mkdir()
        self.addCleanup(self.dispose_window)
        self.launches = []
        self.mode = "done"
        self.patch(b.subprocess, "Popen", self.launch)

    def patch(self, obj, name, value):
        context = patch.object(obj, name, value)
        context.start()
        self.addCleanup(context.stop)

    def dispose_window(self):
        worker = getattr(self.window, "ps_worker", None)
        if worker and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)
        self.app.processEvents()
        self.window.close()
        self.shiboken.delete(self.window)
        self.app.processEvents()

    def launch(self, args, **kwargs):
        wrapper = Path(args[1])
        token = wrapper.stem[len("run_bridge_"):]
        job = wrapper.parent
        self.launches.append((job, token))
        if self.mode == "launch_error":
            raise OSError("simulated process launch failure")
        if self.mode == "done":
            (job / f"ps_result_{token}.txt").write_text("done", encoding="utf-8")
        elif self.mode == "error":
            (job / f"ps_result_{token}.txt").write_text("error\nPhotoshop duplication error 8007", encoding="utf-8")
        elif self.mode == "delayed_approval":
            def finish():
                (job / f"ps_started_{token}.txt").write_text("27.11", encoding="utf-8")
                (job / f"ps_result_{token}.txt").write_text("done", encoding="utf-8")
            timer = threading.Timer(0.025, finish)
            timer.start()
            self.addCleanup(timer.join)
        return object()

    def spin(self, predicate, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.002)
        self.fail("Qt lifecycle did not reach expected state")

    def run_copy(self, mode):
        self.mode = mode
        self.window.run_ps_copy()
        job_id = self.window._active_ps_job_id
        self.spin(lambda: not hasattr(self.window, "ps_worker"))
        self.assertFalse(self.window.ui_busy_transfer)
        self.assertTrue(self.window.btn_ps_copy.isEnabled())
        self.assertTrue(self.window.btn_clean.isEnabled())
        return job_id

    def assert_retry(self, first_mode):
        first = self.run_copy(first_mode)
        second = self.run_copy("done")
        self.assertNotEqual(first, second)
        ready = [r for r in self.window.diagnostic_records if r["state"] == "READY_FOR_NEXT_JOB"]
        self.assertEqual([r["job_id"] for r in ready], [first, second])

    def test_success_then_second_copy(self):
        self.assert_retry("done")

    def test_jsx_error_then_second_copy(self):
        self.assert_retry("error")
        self.assertTrue(any(r["state"] == "FAILED" for r in self.window.diagnostic_records))

    def test_process_launch_failure_then_retry(self):
        self.assert_retry("launch_error")

    def test_timeout_then_retry_and_late_response_ignored(self):
        first = self.run_copy("timeout")
        job, token = self.launches[0]
        (job / f"ps_result_{token}.txt").write_text("done")
        self.assertEqual((job / "active_ps_attempt.txt").read_text(), "")
        self.assertFalse((job / "ps_copy_accepted.txt").exists())
        second = self.run_copy("done")
        self.assertNotEqual(first, second)
        self.assertTrue(any(r["state"] == "TIMEOUT" for r in self.window.diagnostic_records))

    def test_explicit_interruption_then_retry(self):
        self.mode = "timeout"
        self.window.run_ps_copy()
        self.spin(lambda: bool(self.launches))
        self.window.ps_worker.requestInterruption()
        self.spin(lambda: not hasattr(self.window, "ps_worker"))
        self.assertTrue(any(r["state"] == "CANCELLED" for r in self.window.diagnostic_records))
        self.run_copy("done")

    def test_result_before_native_thread_exit_remains_busy_and_logs_duplicate(self):
        release = threading.Event()
        original = self.b.PhotoshopCLIWorker.trace
        def trace(worker, state, **details):
            original(worker, state, **details)
            if state == "CLEANUP_STARTED":
                release.wait(2)
        self.patch(self.b.PhotoshopCLIWorker, "trace", trace)
        self.addCleanup(release.set)
        self.mode = "done"
        self.window.run_ps_copy()
        self.spin(lambda: getattr(self.window, "ps_worker", None) is not None
                  and self.window.ps_worker.outcome is not None)
        self.assertTrue(self.window.ps_worker.isRunning())
        self.assertTrue(self.window.ui_busy_transfer)
        self.assertFalse(self.window.btn_ps_copy.isEnabled())
        self.assertFalse(self.window.btn_clean.isEnabled())
        count = len(self.launches)
        self.window.run_ps_copy()
        self.assertEqual(len(self.launches), count)
        self.assertTrue(any(r["state"] == "COPY_BLOCKED" for r in self.window.diagnostic_records))
        sentinel = Path(self.window.temp_dir) / "keep.txt"
        sentinel.write_text("active job data")
        self.window.clean_temp_folder()
        self.assertTrue(sentinel.exists())
        release.set()
        self.spin(lambda: not hasattr(self.window, "ps_worker"))
        self.assertTrue(self.window.btn_ps_copy.isEnabled())
        self.run_copy("done")

    def test_diagnostic_write_failure_does_not_block_cleanup(self):
        self.patch(self.window.diagnostic_log, "write", lambda *args: (_ for _ in ()).throw(OSError("disk failed")))
        self.assert_retry("error")

    def test_worker_diagnostics_are_delivered_on_gui_thread(self):
        thread_ids = []
        self.patch(self.window.diagnostic_log, "write", lambda event: thread_ids.append(threading.get_ident()))
        self.run_copy("done")
        self.assertTrue(thread_ids)
        self.assertEqual(set(thread_ids), {threading.get_ident()})

    def test_marker_cleanup_failure_still_releases_worker_and_allows_retry(self):
        original_open = builtins.open
        writes = {}
        def open_file(path, mode="r", *args, **kwargs):
            if str(path).endswith("active_ps_attempt.txt") and mode == "w":
                writes[str(path)] = writes.get(str(path), 0) + 1
                if writes[str(path)] == 2:
                    raise PermissionError("simulated marker cleanup failure")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(builtins, "open", side_effect=open_file):
            self.assert_retry("error")
        self.assertTrue(any(r["state"] == "CLEANUP_WARNING" for r in self.window.diagnostic_records))
        self.assertFalse((self.launches[0][0] / "ps_copy_accepted.txt").exists())

    def test_unexpected_python_error_in_partial_job_then_retry(self):
        original = self.window.ps_copy_jsx
        self.window.ps_copy_jsx = str(self.root / "missing_template.jsx")
        self.run_copy("done")
        self.assertTrue(any(r["state"] == "PYTHON_EXCEPTION" for r in self.window.diagnostic_records))
        self.assertFalse(self.launches)
        self.window.ps_copy_jsx = original
        self.run_copy("done")

    def test_photoshop_exit_response_then_retry(self):
        self.patch(self.b, "running_photoshops",
                   lambda: [] if self.launches else [{"Id": 42, "Path": self.target["path"]}])
        self.run_copy("timeout")
        self.assertIn(self.b.LANG["en"]["ps_timeout_closed"], self.window.log_console.toPlainText())
        self.run_copy("done")

    def test_qthread_start_failure_recovers(self):
        with patch.object(self.b.PhotoshopCLIWorker, "start", side_effect=RuntimeError("cannot start")):
            self.window.run_ps_copy()
        self.assertFalse(self.window.ui_busy_transfer)
        self.assertTrue(self.window.btn_ps_copy.isEnabled())
        self.assertFalse(hasattr(self.window, "ps_worker"))
        self.run_copy("done")

    def test_confirmation_delay_is_not_script_started_until_marker_exists(self):
        self.mode = "delayed_approval"
        self.window.run_ps_copy()
        self.spin(lambda: bool(self.launches))
        self.assertFalse(any(r["state"] == "SCRIPT_STARTED" for r in self.window.diagnostic_records))
        self.spin(lambda: not hasattr(self.window, "ps_worker"))
        self.assertTrue(any(r["state"] == "SCRIPT_STARTED" for r in self.window.diagnostic_records))

    def test_display_clear_does_not_change_active_job_or_markers(self):
        self.mode = "timeout"
        self.window.run_ps_copy()
        self.spin(lambda: bool(self.launches))
        job = self.window._active_ps_job_id
        self.window.clear_diagnostic_display()
        self.assertEqual(self.window._active_ps_job_id, job)
        self.assertTrue(self.window.ui_busy_transfer)
        self.assertTrue((self.launches[0][0] / "active_ps_attempt.txt").read_text())
        self.spin(lambda: not hasattr(self.window, "ps_worker"))

    def test_debug_filter_manual_scroll_and_redaction(self):
        self.window.show()
        self.window.diagnostics_toggle.setChecked(True)
        self.app.processEvents()
        self.window.trace_job("example", "STARTING")
        self.assertNotIn("STARTING", self.window.log_console.toPlainText())
        self.window.debug_checkbox.setChecked(True)
        self.assertIn("STARTING", self.window.log_console.toPlainText())
        for i in range(100):
            self.window.log_message("line " + str(i))
        bar = self.window.log_console.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        self.window.log_message(r"C:\private\secret.psd")
        self.assertEqual(bar.value(), 0)
        self.assertNotIn("secret.psd", self.window.log_console.toPlainText())
        self.assertIn("<local-path>", self.window.log_console.toPlainText())

    def test_file_log_flush_and_rotation(self):
        logger = self.window.diagnostic_log
        logger.handler.maxBytes = 512
        for i in range(60):
            logger.write(self.b.diagnostic_event("test", "Test", "EVENT", line="x" * 100))
        logger.close()
        files = list(Path(logger.directory).glob("bridge.log*"))
        self.assertGreater(len(files), 1)
        self.assertLessEqual(len(files), 4)
        self.assertTrue(any('"job_id": "test"' in p.read_text(encoding="utf-8") for p in files))

    def previous_preview(self):
        from PIL import Image
        old = self.root / "previous_success"
        old.mkdir()
        self.window.last_job_id = "previous_success"
        self.window.current_job_path = str(old)
        self.window.clipboard_source = "photoshop"
        self.window.clipboard_count = 5
        data = io.BytesIO()
        Image.new("RGBA", (16, 8), "red").save(data, format="PNG")
        self.window.set_preview_image(data.getvalue())
        return self.window.preview_label.pixmap().cacheKey()

    def test_failed_copy_retains_previous_clipboard_and_labels_old_preview(self):
        key = self.previous_preview()
        self.mode = "error"
        self.window.run_ps_copy()
        self.assertEqual(self.window.status_label.text(), self.window.t["copy_previous_preview"])
        self.spin(lambda: not hasattr(self.window, "ps_worker"))
        self.assertEqual(self.window.last_job_id, "previous_success")
        self.assertEqual(self.window.preview_label.pixmap().cacheKey(), key)
        self.assertEqual(self.window.status_label.text(), self.window.t["copy_failed_retained"])
        self.run_copy("done")
        self.assertEqual(self.window.status_label.text(), self.window.t["copy_preview_pending"])

    def test_failed_copy_without_clipboard_does_not_claim_new_preview(self):
        self.run_copy("error")
        self.assertIsNone(self.window.last_job_id)
        self.assertEqual(self.window.status_label.text(), self.window.t["copy_failed_empty"])
        self.assertTrue(self.window.preview_label.pixmap().isNull())

    def test_stale_clipboard_clear_never_removes_active_job_files_or_busy_flag(self):
        self.previous_preview()
        self.patch(self.b.PhotoshopCLIWorker, "RESPONSE_TIMEOUT", 1)
        self.mode = "timeout"
        self.window.run_ps_copy()
        active = self.window._active_ps_job_id
        self.spin(lambda: bool(self.launches))
        job = self.launches[0][0]
        (job / "status_done.json").write_text("old sentinel, not accepted")
        before = {p.name: p.read_bytes() for p in job.iterdir() if p.is_file()}
        clipboard = types.SimpleNamespace(OpenClipboard=lambda: None, CloseClipboard=lambda: None,
                                          IsClipboardFormatAvailable=lambda kind: False, CF_UNICODETEXT=13)
        with patch.dict(sys.modules, win32clipboard=clipboard):
            for _ in range(5):
                self.window.check_clipboard()
        after = {p.name: p.read_bytes() for p in job.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.window._active_ps_job_id, active)
        self.assertTrue(self.window.ui_busy_transfer)
        self.assertTrue(self.window.ps_worker.isRunning())
        self.assertIsNone(self.window.last_job_id)
        self.assertTrue(self.window.preview_label.pixmap().isNull())
        self.window.ps_worker.requestInterruption()
        self.spin(lambda: not hasattr(self.window, "ps_worker"))

    def test_exported_png_alpha_bbox_is_measured_not_inferred_from_trim(self):
        from PIL import Image
        original = self.launch
        def launch(args, **kwargs):
            layers = Path(args[1]).parent / "layers"
            layers.mkdir()
            image = Image.new("RGBA", (8, 8))
            image.paste((255, 0, 0, 255), (1, 2, 4, 6))
            image.save(layers / "layer_0.png")
            return original(args, **kwargs)
        self.patch(self.b.subprocess, "Popen", launch)
        self.run_copy("done")
        event = next(e for e in self.window.diagnostic_records if e["state"] == "RENDER_OUTPUT_CHECK")
        self.assertEqual(event["details"]["samples"][0]["alpha_bbox"], [1, 2, 4, 6])


class JSXDiagnosticTests(unittest.TestCase):
    def test_folder_tree_cache_preserves_groups_and_reduces_dom_reads(self):
        node = Path(os.environ.get("NODE_BINARY", str(Path(sys.executable).parent.parent / "node" / "bin" / "node.exe")))
        if not node.is_file():
            self.skipTest("Bundled Node not available")
        source = (ROOT / "scripts" / "photoshop_copy.jsx").read_text(encoding="utf-8")
        source = source.replace("#target photoshop", "").split("// 스크립트 실행 시작", 1)[0]
        script = r'''
var Units={PIXELS:1}, app={preferences:{}}, reads=0;
'''+ source + r'''
function item(id, children){var o={};
    Object.defineProperty(o,"id",{get:function(){reads++;return id;}});
    Object.defineProperty(o,"typename",{get:function(){reads++;return children?"LayerSet":"ArtLayer";}});
    Object.defineProperty(o,"layers",{get:function(){reads++;return children;}});return o;}
function collect(tree, ids){var map={}, groups=[];
    for(var i=0;i<ids.length;i++)map[ids[i]]=true;
    collectDirectSelectedFolders(tree,map,groups);
    if(!groups.length)for(var t=0;t<tree.length;t++){
        var top=tree[t];if(top.typename!=="LayerSet")continue;
        var selected=[];collectSelectedIdsInFolder(top.layers,map,selected);
        if(selected.length)groups.push({folder:top.source||top,ids:selected});}
    return {groups:groups.map(function(g){return {id:g.folder.id,ids:g.ids};}),remaining:Object.keys(map)};}
var results=[];
for(var s=0;s<3;s++){
    var ids=[[11,1,2,12,3],[1,2,3],[11,1,2]][s];
    var tree=[item(10,[item(11,[item(1),item(2)]),item(12,[item(3)])])];
    reads=0;var original=collect(tree,ids);var rawReads=reads;
    reads=0;var cached=collect(captureSelectionTree(tree),ids);var cachedReads=reads;
    results.push({original:original,cached:cached,raw:rawReads,cost:cachedReads});
}
var touched=false;
var doc={};Object.defineProperty(doc,"layers",{get:function(){touched=true;throw Error("expensive");}});
DEBUG_ENABLED=false;var details=diagnosticLayers(doc);
console.log(JSON.stringify({results:results,touched:touched,details:details}));
'''
        result = subprocess.run([str(node)], input=script, text=True, encoding="utf-8", capture_output=True, check=True)
        data = json.loads(result.stdout)
        for result in data["results"]:
            self.assertEqual(result["original"], result["cached"])
            self.assertLess(result["cost"], result["raw"])
        self.assertFalse(data["touched"])
        self.assertEqual(data["details"], [])

    def normal_scenario(self, scenario, active_id=None, unavailable_context=False, debug=True, mode="normal", retry=False, baseline=False):
        node = Path(os.environ.get("NODE_BINARY", str(Path(sys.executable).parent.parent / "node" / "bin" / "node.exe")))
        if not node.is_file():
            self.skipTest("Bundled Node not available")
        source = (ROOT / "scripts" / "photoshop_copy.jsx").read_text(encoding="utf-8")
        if baseline:
            git_env = {k: v for k, v in os.environ.items()
                       if k != "GIT_CONFIG_COUNT" and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
            comparison = subprocess.run(["git", "show", "v0.3.6:scripts/photoshop_copy.jsx"], cwd=ROOT,
                                        capture_output=True, text=True, encoding="utf-8", env=git_env)
            if comparison.returncode:
                raise RuntimeError("Cannot read v0.3.6 baseline: " + comparison.stderr)
            source = comparison.stdout
        source = source.replace("#target photoshop", "").split("// 스크립트 실행 시작", 1)[0]
        prelude = r'''
var files={}, closed=[], trimmed=[], commands=[], saved=[], closeAttempts=[], Units={PIXELS:1}, scenario=SCENARIO;
var saveCount=0, duplicateCount=0, nextDocumentCreated=false;
function unit(n){return {as:function(){return n;}};}
function layer(id){return {id:id, name:"Layer"+id, typename:"ArtLayer", kind:"NORMAL", visible:true,
    opacity:100, bounds:[unit(0),unit(0),unit(32),unit(16)],
    duplicate:function(dest){duplicateCount++;if(scenario==="layer_duplicate_failed")throw Error("layer duplicate failed");dest.layers.push(layer(id+1));}};}
function document(id){return {id:id,name:"PRIVATE.psd",width:unit(128),height:unit(64),resolution:72,
    mode:"RGB",bitsPerChannel:8,layers:[layer(id+1)],
    trim:function(){trimmed.push(this.id);if(scenario==="trim_failed" || scenario==="close_failed"){
        var e=new Error("unsupported trim operation");e.number=12345;e.line=81;throw e;}},
    close:function(){closeAttempts.push(this.id);if((scenario==="close_failed" || scenario==="cleanup_failed_primary" || scenario==="cleanup_failed_success") && this.id===268)throw Error("frame close failed");
        if((scenario==="export_close_failed" || scenario==="export_and_close_failed") && this.id===300)throw Error("export close failed");
        closed.push(this.id);var i=documents.indexOf(this);if(i>=0)documents.splice(i,1);},
    saveAs:function(file){saved.push(this.id);saveCount++;
        if(scenario==="export_failed" || scenario==="cleanup_failed_primary" || scenario==="export_and_close_failed" || (scenario==="export_failed_late" && saveCount===2)){
            var e=new Error("PNG export failed");e.number=2468;e.line=91;e.fileName="C:/private/export.jsx";throw e;}
        files[file.fsName]="PNG";}};}
var original=document(60), temporary=document(268), other=document(90);
var documents=[original,other], active=original;
var app={version:"27.11",preferences:{},documents:documents};
Object.defineProperty(app,"activeDocument",{get:function(){return active;},set:function(doc){
    if(scenario==="restore_failed" && nextDocumentCreated && doc===original)throw Error("source activation failed");active=doc;}});
documents.add=function(w,h,res,name){
    if(scenario==="export_create_failed")throw Error("export document creation failed");
    if(scenario==="export_existing")return other;
    if(scenario==="export_original")return original;
    if(scenario==="export_source")return app.activeDocument;
    var doc=document(300);doc.name=name;documents.push(doc);app.activeDocument=doc;
    if(scenario==="export_create_failed_after_create")throw Error("export document creation failed");
    return doc;};
function File(path){this.fsName=path;this.name=path.split(/[\\/]/).pop();}
Object.defineProperty(File.prototype,"exists",{get:function(){return this.fsName in files;}});
Object.defineProperty(File.prototype,"length",{get:function(){return (files[this.fsName]||"").length;}});
File.prototype.open=function(mode){if(mode==="w" || !files[this.fsName])files[this.fsName]="";return true;};
File.prototype.write=function(s){files[this.fsName]+=s;};
File.prototype.writeln=function(s){files[this.fsName]+=s+"\n";};File.prototype.close=function(){};
function ActionDescriptor(){this.items={};}
ActionDescriptor.prototype.putReference=function(k,v){this.items[k]=v.items;};
ActionDescriptor.prototype.putString=function(k,v){this.items[k]=v;};
function ActionReference(){this.items=[];}
ActionReference.prototype.putClass=function(v){this.items.push({type:"class",value:v});};
ActionReference.prototype.putEnumerated=function(c,t,v){this.items.push({type:"enumerated",class:c,enum_type:t,value:v});};
function charIDToTypeID(s){return s;}
var DialogModes={NO:0},TrimType={TRANSPARENT:0},SaveOptions={DONOTSAVECHANGES:0},
    NewDocumentMode={RGB:0},DocumentFill={TRANSPARENT:0},ElementPlacement={PLACEATBEGINNING:0},Extension={LOWERCASE:0};
function PNGSaveOptions(){};
function executeAction(event,descriptor,dialogs){commands.push({event:event,descriptor:descriptor.items,dialogs:dialogs});
    if(scenario==="duplicate_failed"){var e=new Error("host cancelled operation");e.number=8007;throw e;}
    if(scenario==="switch_existing" || scenario==="existing_named_temp"){
        if(scenario==="existing_named_temp")other.name=descriptor.items["Nm  "];
        app.activeDocument=other;return;}
    if(scenario!=="no_temporary_document"){
        temporary=document(268);temporary.name=descriptor.items["Nm  "];documents.push(temporary);app.activeDocument=temporary;nextDocumentCreated=true;
        if(scenario==="wrong_name")temporary.name="Unrelated new document";
        if(scenario==="multiple_new")documents.push(document(777));
        if(scenario==="unknown_id")Object.defineProperty(temporary,"id",{get:function(){throw Error("id unavailable");}});
        if(scenario==="missing_pixel")temporary.layers=[];
        if(scenario==="unexpected")Object.defineProperty(temporary,"width",{get:function(){throw Error("width unavailable");}});
        if(scenario==="duplicate_failed_after_create"){var e=new Error("host cancelled operation");e.number=8007;e.line=321;e.fileName="C:/private/copy.jsx";throw e;}
    }}
'''.replace("SCENARIO", json.dumps(scenario))
        context = ""
        if active_id is not None:
            context += "original.layers.push(layer(62)); original.activeLayer = {id:" + str(active_id) + ',typename:"ArtLayer"};\n'
        if unavailable_context:
            context += ('Object.defineProperty(original,"activeLayer",{get:function(){throw Error("unavailable");}});'
                        'Object.defineProperty(original,"activeChannels",{get:function(){throw Error("unavailable");}});\n')
        if mode != "normal":
            context += r'''
function group(id, children){return {id:id,name:"Group"+id,typename:"LayerSet",layers:children};}
original.layers=[group(70,[group(71,[layer(61),layer(62)]),group(72,[layer(63)])])];
var selectedForFrame=[];
selectLayerIds=function(ids){selectedForFrame=ids.slice();};
selectLayerById=function(id){selectedForFrame=[id];};
'''
        selected_ids = [61, 62] if active_id is not None else [61]
        if mode == "folder_frames":
            selected_ids = [71, 61, 62, 72, 63]
        elif mode == "layer_frames":
            selected_ids = [63, 61, 62]
        suffix = context + r'''
JOB_PATH="job";DIAGNOSTICS_PATH="events";ATTEMPT_TOKEN="token";FRAME_MODE=MODE_VALUE;DEBUG_ENABLED=DEBUG_VALUE;
var LayerKind={NORMAL:"NORMAL"};
function testDocumentId(doc){try{return doc.id;}catch(e){return null;}}
if(scenario==="source_unknown")Object.defineProperty(original,"id",{get:function(){throw Error("source id unavailable");}});
var sourceIds=SOURCE_IDS;
getSelectedLayerIds=function(info){if(info)info.method="targetLayersIDs";return app.activeDocument===original?sourceIds:[app.activeDocument.id+1];};
try{COPY_FUNCTION(original,{name:"job",fsName:"job",toString:function(){return "job";}},"job/layers");}
catch(e){writeStatusError(e.toString(),e);}
var firstFiles=JSON.parse(JSON.stringify(files)),retrySource=null;
if(RETRY){scenario="success";var retryDoc=app.activeDocument;retrySource=testDocumentId(retryDoc);
    try{COPY_FUNCTION(retryDoc,{name:"retry",fsName:"retry",toString:function(){return "retry";}},"retry/layers");}
    catch(e){writeStatusError(e.toString(),e);}}
console.log(JSON.stringify({files:files,first_files:firstFiles,closed:closed,close_attempts:closeAttempts,
    trimmed:trimmed,saved:saved,active:testDocumentId(app.activeDocument),retry_source:retrySource,commands:commands}));
'''.replace("SOURCE_IDS", json.dumps(selected_ids)).replace("DEBUG_VALUE", json.dumps(debug)).replace(
            "MODE_VALUE", json.dumps(mode)).replace("RETRY", json.dumps(retry)).replace("COPY_FUNCTION", {
                "normal": "runNormalCopy", "folder_frames": "runFolderFramesCopy", "layer_frames": "runLayerFramesCopy"}[mode])
        result = subprocess.run([str(node)], input=prelude + source + suffix, text=True,
                                encoding="utf-8", capture_output=True, check=True)
        data = json.loads(result.stdout)
        data["events"] = [json.loads(line) for line in data["files"].get("events", "").splitlines()]
        return data

    def test_normal_debug_modes_preserve_outputs_and_duplication(self):
        detailed = self.normal_scenario("success", debug=True)
        basic = self.normal_scenario("success", debug=False)
        for path in ("job/metadata.json", "job/trigger_copy.json", "job/status_done.json"):
            left, right = (json.loads(data["files"][path]) for data in (detailed, basic))
            left.pop("timestamp", None)
            right.pop("timestamp", None)
            self.assertEqual(left, right)
        self.assertEqual(detailed["commands"], basic["commands"])
        self.assertEqual(detailed["closed"], basic["closed"])
        self.assertTrue(any(e["state"] == "COPY_STAGE_TIMING" for e in basic["events"]))
        selected = next(e for e in basic["events"] if e["state"] == "NORMAL_SELECTION_CAPTURED")
        self.assertEqual(selected["details"]["selection"]["ids"], [61])
        self.assertEqual(selected["details"]["layers"], [])

    def test_normal_8007_keeps_failure_context_without_debug(self):
        data = self.normal_scenario("duplicate_failed", debug=False)
        failed = next(e for e in data["events"] if e["state"] == "NORMAL_DUPLICATION_FAILED")
        self.assertEqual(failed["details"]["error"]["number"], 8007)
        self.assertEqual(failed["details"]["command_context"]["selection"]["ids"], [61])
        self.assertEqual(len(data["commands"]), 1)

    def test_frame_modes_debug_on_off_preserve_metadata_and_selected_order(self):
        for mode in ("folder_frames", "layer_frames"):
            with self.subTest(mode=mode):
                detailed = self.normal_scenario("success", debug=True, mode=mode)
                basic = self.normal_scenario("success", debug=False, mode=mode)
                for path in ("job/metadata.json", "job/trigger_copy.json", "job/status_done.json"):
                    left, right = (json.loads(data["files"][path]) for data in (detailed, basic))
                    left.pop("timestamp", None)
                    right.pop("timestamp", None)
                    self.assertEqual(left, right)
                metadata = json.loads(basic["files"]["job/metadata.json"])
                self.assertEqual(metadata["frame_mode"], mode)
                self.assertEqual([e["frame_index"] for e in metadata["elements"]],
                                 [0, 1] if mode == "folder_frames" else [0, 1, 2])
                if mode == "folder_frames":
                    frames = [e["details"]["selected_ids"] for e in basic["events"]
                              if e["state"] == "FRAME_CONTAINER_COLLECTED"]
                    self.assertEqual(frames, [[71], [72]])
                else:
                    self.assertEqual([e["name"] for e in metadata["elements"]], ["Layer61", "Layer62", "Layer63"])
                self.assertEqual(detailed["commands"], basic["commands"])

    def test_normal_context_separates_active_layer_from_same_selected_id_set(self):
        first = self.normal_scenario("duplicate_failed", active_id=61)
        second = self.normal_scenario("duplicate_failed", active_id=62)
        contexts = [next(e["details"] for e in data["events"] if e["state"] == "NORMAL_MAKE_CONTEXT")
                    for data in (first, second)]
        self.assertEqual(contexts[0]["selection"], contexts[1]["selection"])
        self.assertEqual([context["active_layer_id"] for context in contexts], [61, 62])
        self.assertEqual(first["commands"], second["commands"])
        self.assertEqual(len(first["commands"]), 1)
        self.assertEqual(first["commands"][0], {
            "event": "Mk  ", "dialogs": 0, "descriptor": {
                "null": [{"type": "class", "value": "Dcmn"}], "Nm  ": "TempBridgeDoc",
                "Usng": [{"type": "enumerated", "class": "Lyr ", "enum_type": "Ordn", "value": "Trgt"}]}})

    def test_normal_context_query_failures_do_not_change_copy_or_retry_command(self):
        data = self.normal_scenario("success", unavailable_context=True)
        context = next(e["details"] for e in data["events"] if e["state"] == "NORMAL_MAKE_CONTEXT")
        self.assertTrue(context["active_layer_unavailable"])
        self.assertTrue(context["active_channels_unavailable"])
        self.assertEqual(len(data["commands"]), 1)
        self.assertIn("job/status_done.json", data["files"])
        self.assertEqual(data["active"], 60)

    def test_normal_trim_failure_retains_original_error_and_restores_source(self):
        data = self.normal_scenario("trim_failed")
        failed = next(e for e in data["events"] if e["state"] == "NORMAL_TRIM_FAILED")
        self.assertEqual(failed["details"]["error"]["number"], 12345)
        self.assertEqual(failed["details"]["temporary_document"]["id"], 268)
        self.assertEqual(failed["details"]["alpha_measurement"], "unverified_trim_exception")
        self.assertEqual(data["closed"], [268])
        self.assertEqual(data["active"], 60)
        self.assertNotIn("job/status_done.json", data["files"])
        self.assertIn("unsupported trim operation", data["files"]["job/status_error.txt"])
        self.assertNotIn("PRIVATE", data["files"]["events"])

    def test_normal_duplicate_failure_is_not_claimed_to_be_no_selection(self):
        data = self.normal_scenario("duplicate_failed")
        selected = next(e for e in data["events"] if e["state"] == "NORMAL_SELECTION_CAPTURED")
        self.assertEqual(selected["details"]["selection"]["ids"], [61])
        failed = next(e for e in data["events"] if e["state"] == "NORMAL_DUPLICATION_FAILED")
        self.assertEqual(failed["details"]["error"]["number"], 8007)
        self.assertEqual(data["active"], 60)
        self.assertEqual(data["closed"], [])
        self.assertNotIn("job/status_done.json", data["files"])

    def test_normal_export_failure_closes_owned_export_and_normal_temp_documents(self):
        data = self.normal_scenario("export_failed")
        self.assertEqual(data["closed"], [300, 268])
        self.assertEqual(data["active"], 60)
        self.assertTrue(any(e["state"] == "PNG_EXPORT_FAILED" for e in data["events"]))
        self.assertNotIn("job/status_done.json", data["files"])

    def test_normal_success_keeps_metadata_and_source_order(self):
        data = self.normal_scenario("success")
        metadata = json.loads(data["files"]["job/metadata.json"])
        self.assertEqual(metadata["layer_count"], 1)
        self.assertEqual(metadata["elements"][0]["name"], "Layer269")
        self.assertEqual(data["closed"], [300, 268])
        self.assertEqual(data["active"], 60)
        self.assertIn("job/status_done.json", data["files"])

    def test_normal_no_new_document_never_trims_or_closes_original(self):
        data = self.normal_scenario("no_temporary_document")
        self.assertEqual(data["closed"], [])
        self.assertEqual(data["trimmed"], [])
        self.assertEqual(data["active"], 60)
        self.assertNotIn("job/status_done.json", data["files"])

    def test_normal_close_failure_does_not_hide_trim_error_or_block_source_restore(self):
        data = self.normal_scenario("close_failed")
        self.assertEqual(data["active"], 60)
        self.assertTrue(any(e["state"] == "NORMAL_TEMP_CLOSE_FAILED" for e in data["events"]))
        self.assertTrue(any(e["state"] == "NORMAL_SOURCE_RESTORED" for e in data["events"]))
        self.assertIn("unsupported trim operation", data["files"]["job/status_error.txt"])

    def assert_failed_without_user_document_operations(self, data, restored=True):
        for calls in ("trimmed", "close_attempts", "saved"):
            self.assertNotIn(60, data[calls], calls)
            self.assertNotIn(90, data[calls], calls)
        if restored:
            self.assertEqual(data["active"], 60)
        for output in ("job/metadata.json", "job/trigger_copy.json", "job/status_done.json"):
            self.assertNotIn(output, data["files"])
        self.assertIn("job/status_error.txt", data["files"])

    def test_audit_six_failure_cases_protect_original_and_cleanup(self):
        for scenario in ("no_temporary_document", "export_failed"):
            for mode in ("normal", "folder_frames", "layer_frames"):
                with self.subTest(scenario=scenario, mode=mode):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    self.assertEqual(data["closed"], [] if scenario == "no_temporary_document" else [300, 268])

    def test_frame_modes_refuse_preexisting_ambiguous_or_unverifiable_documents(self):
        for mode in ("normal", "folder_frames", "layer_frames"):
            for scenario in ("switch_existing", "existing_named_temp", "unknown_id", "wrong_name", "multiple_new"):
                for debug in (False, True):
                    with self.subTest(mode=mode, scenario=scenario, debug=debug):
                        data = self.normal_scenario(scenario, debug=debug, mode=mode)
                        self.assert_failed_without_user_document_operations(data)
                        self.assertEqual(data["trimmed"], [])
                        self.assertEqual(data["saved"], [])
                        self.assertEqual(data["close_attempts"], [])

    def test_export_document_must_also_be_new_and_owned(self):
        for mode in ("normal", "folder_frames", "layer_frames"):
            for scenario in ("export_existing", "export_original", "export_source"):
                with self.subTest(mode=mode, scenario=scenario):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    self.assertEqual(data["closed"], [268])
                    self.assertEqual(data["saved"], [])

    def test_frame_8007_after_document_creation_is_not_retried_and_is_preserved(self):
        for mode, prefix in (("folder_frames", "FOLDER"), ("layer_frames", "LAYER")):
            for debug in (False, True):
                with self.subTest(mode=mode, debug=debug):
                    data = self.normal_scenario("duplicate_failed_after_create", debug=debug, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    self.assertEqual(data["closed"], [268])
                    self.assertEqual(len(data["commands"]), 1)
                    event = next(e for e in data["events"] if e["state"] == prefix + "_DUPLICATION_FAILED")
                    error = event["details"]["error"]
                    self.assertEqual((error["number"], error["line"], error["file"]), (8007, 321, "copy.jsx"))
                    self.assertEqual(error["message"], "host cancelled operation")

    def test_frame_trim_failure_preserves_error_and_restores_original(self):
        for mode in ("folder_frames", "layer_frames"):
            with self.subTest(mode=mode):
                data = self.normal_scenario("trim_failed", debug=False, mode=mode)
                self.assert_failed_without_user_document_operations(data)
                self.assertEqual(data["closed"], [268])
                self.assertIn("unsupported trim operation", data["files"]["job/status_error.txt"])
                failed = next(e for e in data["events"] if e["state"] == "FAILED")
                self.assertEqual(failed["details"]["error"]["number"], 12345)

    def test_frame_pixel_duplication_and_export_document_creation_failures_cleanup(self):
        for mode in ("folder_frames", "layer_frames"):
            for scenario, closed in (("layer_duplicate_failed", [300, 268]),
                                     ("export_create_failed", [268]),
                                     ("export_create_failed_after_create", [300, 268])):
                with self.subTest(mode=mode, scenario=scenario):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    self.assertEqual(data["closed"], closed)

    def test_frame_cleanup_failure_keeps_primary_export_error_and_separate_diagnostic(self):
        for mode, prefix in (("folder_frames", "FOLDER_FRAME"), ("layer_frames", "LAYER_FRAME")):
            for scenario in ("cleanup_failed_primary", "export_and_close_failed"):
                with self.subTest(mode=mode, scenario=scenario):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    message = data["files"]["job/status_error.txt"]
                    self.assertIn("PNG export failed", message)
                    self.assertNotIn("close failed", message)
                    failed = next(e for e in data["events"] if e["state"] == "PNG_EXPORT_FAILED")
                    error = failed["details"]["error"]
                    self.assertEqual((error["number"], error["line"], error["file"]), (2468, 91, "export.jsx"))
                    cleanup_state = (prefix if scenario == "cleanup_failed_primary" else "PNG") + "_TEMP_CLOSE_FAILED"
                    self.assertTrue(any(e["state"] == cleanup_state for e in data["events"]))

    def test_frame_cleanup_failure_after_success_cannot_generate_done_marker(self):
        for mode in ("folder_frames", "layer_frames"):
            for scenario in ("cleanup_failed_success", "export_close_failed"):
                with self.subTest(mode=mode, scenario=scenario):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data)
                    self.assertIn("cleanup failed", data["files"]["job/status_error.txt"])

    def test_original_activation_failure_is_diagnosed_without_closing_other_documents(self):
        for mode, prefix in (("folder_frames", "FOLDER_FRAME"), ("layer_frames", "LAYER_FRAME")):
            with self.subTest(mode=mode):
                data = self.normal_scenario("restore_failed", debug=False, mode=mode)
                self.assert_failed_without_user_document_operations(data, restored=False)
                self.assertTrue(any(e["state"] == prefix + "_SOURCE_RESTORE_FAILED" for e in data["events"]))

    def test_partial_export_failure_and_next_copy_use_original_not_old_temp(self):
        for mode in ("folder_frames", "layer_frames"):
            with self.subTest(mode=mode):
                data = self.normal_scenario("export_failed_late", debug=False, mode=mode, retry=True)
                first = data["first_files"]
                self.assertEqual(first["job/layers/layer_0.png"], "PNG")
                for output in ("job/metadata.json", "job/trigger_copy.json", "job/status_done.json"):
                    self.assertNotIn(output, first)
                self.assertEqual(data["retry_source"], 60)
                self.assertIn("retry/status_done.json", data["files"])
                self.assertNotIn(60, data["close_attempts"])
                self.assertNotIn(90, data["close_attempts"])

    def test_frame_unexpected_error_missing_pixels_and_unverified_source_are_safe(self):
        for mode in ("normal", "folder_frames", "layer_frames"):
            for scenario in ("unexpected", "source_unknown"):
                with self.subTest(mode=mode, scenario=scenario):
                    data = self.normal_scenario(scenario, debug=False, mode=mode)
                    self.assert_failed_without_user_document_operations(data, restored=scenario != "source_unknown")
                    if scenario == "source_unknown":
                        self.assertEqual(data["commands"], [])
                        self.assertEqual(data["close_attempts"], [])
                    else:
                        self.assertEqual(data["closed"], [268])
        data = self.normal_scenario("missing_pixel", debug=False, mode="layer_frames")
        self.assert_failed_without_user_document_operations(data)
        self.assertEqual(data["closed"], [268])

    def test_frame_success_keeps_metadata_order_and_only_closes_created_documents(self):
        for mode, frame_count in (("folder_frames", 2), ("layer_frames", 3)):
            for debug in (False, True):
                with self.subTest(mode=mode, debug=debug):
                    data = self.normal_scenario("success", debug=debug, mode=mode)
                    metadata = json.loads(data["files"]["job/metadata.json"])
                    self.assertEqual(metadata["version"], "1.1")
                    self.assertEqual(metadata["source_app"], "photoshop")
                    self.assertEqual(metadata["frame_mode"], mode)
                    self.assertEqual(metadata["layer_count"], frame_count)
                    self.assertEqual([e["frame_index"] for e in metadata["elements"]], list(range(frame_count)))
                    self.assertEqual([e["name"] for e in metadata["elements"]],
                                     ["Layer269"] * 2 if mode == "folder_frames" else ["Layer61", "Layer62", "Layer63"])
                    self.assertEqual(data["closed"], [300, 268] * frame_count)
                    self.assertEqual(data["close_attempts"], data["closed"])
                    self.assertEqual(data["saved"], [300] * frame_count)
                    self.assertEqual(data["active"], 60)
                    self.assertIn("job/status_done.json", data["files"])
        for mode in ("normal", "folder_frames", "layer_frames"):
            baseline = self.normal_scenario("success", debug=False, mode=mode, baseline=True)
            current = self.normal_scenario("success", debug=False, mode=mode)
            for path in ("job/metadata.json", "job/trigger_copy.json", "job/status_done.json"):
                before, after = (json.loads(data["files"][path]) for data in (baseline, current))
                before.pop("timestamp", None)
                after.pop("timestamp", None)
                self.assertEqual(before, after, (mode, path))
            self.assertEqual(baseline["commands"], current["commands"])
            self.assertEqual(baseline["saved"], current["saved"])
            self.assertEqual({k: v for k, v in baseline["files"].items() if k.endswith(".png")},
                             {k: v for k, v in current["files"].items() if k.endswith(".png")})

    def test_folder_duplication_failure_reports_number_line_and_document_without_names(self):
        node = Path(os.environ.get("NODE_BINARY", str(Path(sys.executable).parent.parent / "node" / "bin" / "node.exe")))
        if not node.is_file():
            self.skipTest("Bundled Node not available")
        source = (ROOT / "scripts" / "photoshop_copy.jsx").read_text(encoding="utf-8")
        source = source.replace("#target photoshop", "").split("// 스크립트 실행 시작", 1)[0]
        prelude = r'''
var files = {}, Units = {PIXELS: 1};
var doc = {id: 1, name: "PRIVATE.psd", layers: []};
var folder = {id: 11, name: "PRIVATE FOLDER", typename: "LayerSet", layers: [], parent: doc};
doc.layers = [folder];
var app = {version: "27.11", preferences: {}, activeDocument: doc, documents: [doc]};
function File(path) {this.fsName=path; this.name=path.split(/[\\/]/).pop();}
Object.defineProperty(File.prototype, "exists", {get:function(){return this.fsName in files;}});
Object.defineProperty(File.prototype, "length", {get:function(){return (files[this.fsName] || "").length;}});
File.prototype.open=function(mode){if(mode==="w" || !files[this.fsName]) files[this.fsName]=""; return true;};
File.prototype.write=function(text){files[this.fsName]+=text;};
File.prototype.writeln=function(text){files[this.fsName]+=text+"\n";};
File.prototype.close=function(){};
function ActionDescriptor(){};
ActionDescriptor.prototype.putReference=ActionDescriptor.prototype.putString=function(){};
function ActionReference(){};
ActionReference.prototype.putClass=ActionReference.prototype.putEnumerated=function(){};
function charIDToTypeID(s){return s;}
var DialogModes={NO:0};
function executeAction(){var e=new Error("host cancelled operation");e.number=8007;e.line=321;e.fileName="C:/private/ps_body.jsx";throw e;}
'''
        suffix = r'''
JOB_PATH="job"; DIAGNOSTICS_PATH="diagnostic.jsonl"; ATTEMPT_TOKEN="token"; FRAME_MODE="folder_frames";
getSelectedLayerIds=function(){return [11];}; selectLayerIds=function(){};
runFolderFramesCopy(doc, {name:"job"}, "layers");
console.log(JSON.stringify({files:files, active:app.activeDocument.id}));
'''
        result = subprocess.run([str(node)], input=prelude + source + suffix, text=True,
                                encoding="utf-8", capture_output=True, check=True)
        data = json.loads(result.stdout)
        events = [json.loads(line) for line in data["files"]["diagnostic.jsonl"].splitlines()]
        failed = next(event for event in events if event["state"] == "FOLDER_DUPLICATION_FAILED")
        self.assertEqual(failed["details"]["error"]["number"], 8007)
        self.assertEqual(failed["details"]["error"]["line"], 321)
        self.assertEqual(failed["details"]["error"]["file"], "ps_body.jsx")
        self.assertEqual(failed["details"]["active_document"]["id"], 1)
        self.assertEqual(data["active"], 1)
        self.assertNotIn("PRIVATE", data["files"]["diagnostic.jsonl"])
        self.assertFalse(any(event["state"] == "CANCELLED" for event in events))
        self.assertIn("job/status_error.txt", data["files"])


if __name__ == "__main__":
    unittest.main()
