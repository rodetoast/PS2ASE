"""Opt-in tests with the installed Aseprite engine and a disposable profile."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASEPRITE = os.environ.get("PS2ASE_ASEPRITE_TEST_EXE", "")


@unittest.skipUnless(Path(ASEPRITE).is_file(), "set PS2ASE_ASEPRITE_TEST_EXE to use the installed host")
class AsepritePracticeTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory(prefix="ps2ase-ase-test-") as scratch:
            root = Path(scratch)
            practice = scenario in ("practice", "expired", "other_target", "ended", "wrong_canvas",
                                    "wrong_count", "button", "stale_session", "path_alias", "sidecar_denied")
            exercise = scenario.startswith("copy_frame_")
            if practice:
                target = root / ("ps2ase-paste-" + "1" * 32) / "Paste practice.png"
            elif exercise:
                target = root / ("ps2ase-copy-" + "1" * 32) / "Copy practice.aseprite"
            elif scenario == "ordinary_practice_basename":
                target = root / "Paste practice.png"
            elif scenario == "legacy_paste_tab":
                target = root / "ps2ase-guide-old" / "Aseprite" / ("ps2ase-paste-" + "1" * 32 + ".png")
            else:
                target = root / "ordinary.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            size = (33, 32) if scenario == "wrong_canvas" else (300, 300) if scenario == "wrong_count" else (32, 32)
            image = Image.new("RGBA", size)
            if scenario == "copy":
                image.paste((116, 216, 236, 255), (8, 6, 20, 18))
            if exercise:
                shutil.copyfile(ROOT / "assets/practice/testfile.aseprite", target)
                (target.parent / "practice_copy.json").write_text(json.dumps({
                    "token": "2" * 32 if scenario.endswith("_stale") else "1" * 32,
                    "document": str(target).replace("\\", "/")}), encoding="utf-8")
            else:
                image.save(target)
            job = root / ("guide_" + "a" * 32 if practice else "job")
            (job / "layers").mkdir(parents=True)
            (root / "jobs").mkdir()
            prefs = root / "Ase-PS-Bridge"
            prefs.mkdir()
            (prefs / "logs").mkdir()
            (prefs / "bridge_settings.json").write_text(
                json.dumps({"language": "en", "active_temp_path": str(root / "jobs")}), encoding="utf-8")
            png = job / "layers/layer_0.png"
            if scenario == "corrupt_png":
                png.write_bytes(b"not a PNG")
            elif scenario != "missing_png":
                Image.new("RGBA", (6, 4), (116, 216, 236, 255)).save(png)
            if scenario != "missing_metadata":
                (job / "metadata.json").write_text(
                    json.dumps({"layers": [{"type": "layer", "id": "layer_0", "name": "Practice",
                                            "x": 0, "y": 0, "width": 6, "height": 4, "file": "layers/layer_0.png"}]}))
            normal = {"signature": "ase_ps_bridge_payload", "source_app": "photoshop", "job_path": str(job)}
            if practice and scenario != "ended":
                guide = dict(normal, guide_nonce="a" * 32, guide_target=str(target),
                             guide_expires=int(time.time()) + (-60 if scenario == "expired" else 60),
                             guide_session="2" * 32 if scenario == "stale_session" else "1" * 32,
                             guide_layer_count=4 if scenario == "wrong_count" else 1)
                if scenario == "path_alias":
                    guide["guide_target"] = str(root / "noncanonical" / target.parent.name / target.name)
                elif scenario == "other_target":
                    guide["guide_target"] = str(root / "a-different-document.png")
                Path(str(target) + ".ps2ase.json").write_text(json.dumps(guide), encoding="utf-8")
            if scenario in ("button", "button_wrong_target", "ordinary_expired_button"):
                (prefs / "guide_paste_request.json").write_text(json.dumps({
                    "target": str(target if scenario == "button" else root / "different.png"),
                    "nonce": "a" * 32, "expires": int(time.time()) + (-60 if scenario == "ordinary_expired_button" else 60)}))
            if scenario == "ordinary_during_practice":
                session = root / ("ps2ase-paste-" + "1" * 32)
                session.mkdir()
                example = session / "Paste practice.png"
                image.save(example)
                Path(str(example) + ".ps2ase.json").write_text(json.dumps(dict(
                    normal, guide_target=str(example), guide_expires=int(time.time()) + 60,
                    guide_layer_count=1, guide_nonce="a" * 32, guide_session="1" * 32)))
            clipboard = {"plain": "not JSON", "scalar": "false", "wrong_signature": '{"signature":"other"}'}
            (root / "test_clipboard.txt").write_text(clipboard.get(scenario, json.dumps(normal)))
            cmd = [ASEPRITE, "--batch"]
            for key, value in (("root", root), ("repo", ROOT), ("target", target), ("scenario", scenario)):
                cmd += ["--script-param", f"{key}={value}"]
            cmd += ["--script", str(ROOT / "tests/aseprite_practice_harness.lua")]
            result = subprocess.run(cmd, env={**os.environ, "APPDATA": str(root)}, capture_output=True,
                                    timeout=20, check=False)
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr,
                                                    sorted(str(path.relative_to(root)) for path in root.rglob("*"))))
            self.assertTrue((root / "passed.txt").is_file(), (result.stdout, result.stderr))

    def test_ordinary_and_practice_complete_without_console(self):
        for scenario in ("copy", "ordinary", "practice", "button", "ordinary_expired_button",
                         "ordinary_during_practice", "ordinary_practice_basename"):
            with self.subTest(scenario=scenario):
                self.run_case(scenario)

    def test_invalid_input_leaves_the_document_unchanged(self):
        for scenario in ("plain", "scalar", "wrong_signature", "missing_metadata", "missing_png",
                         "corrupt_png", "expired", "other_target", "ended", "wrong_canvas", "wrong_count",
                         "stale_session", "path_alias", "sidecar_denied", "button_wrong_target", "legacy_paste_tab"):
            with self.subTest(scenario=scenario):
                self.run_case(scenario)

    def test_user_asset_frames_and_isolation(self):
        for number in (1, 2, 3):
            with self.subTest(frame=number):
                self.run_case(f"copy_frame_{number}")

    def test_practice_path_errors_and_native_stat_fallback(self):
        for condition in ("stale", "stat_false", "deleted", "denied", "no_settings"):
            with self.subTest(condition=condition):
                self.run_case("copy_frame_1_" + condition)
