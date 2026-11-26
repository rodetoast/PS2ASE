"""Opt-in tests with the installed Aseprite engine and a disposable profile."""
import json
import os
from pathlib import Path
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
            practice = scenario in ("practice", "expired", "other_target")
            target = root / (f"ps2ase-paste-{'1' * 32}.png" if practice else "ordinary.png")
            image = Image.new("RGBA", (32, 32))
            if scenario == "copy":
                image.paste((116, 216, 236, 255), (8, 6, 20, 18))
            image.save(target)
            job = root / "job"
            (job / "layers").mkdir(parents=True)
            (root / "jobs").mkdir()
            prefs = root / "Ase-PS-Bridge"
            prefs.mkdir()
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
            if practice:
                guide = dict(normal, guide_nonce="a" * 32, guide_target=str(target),
                             guide_expires=int(time.time()) + (-60 if scenario == "expired" else 60))
                if scenario == "other_target":
                    guide["guide_target"] = str(root / "a-different-document.png")
                Path(str(target) + ".ps2ase.json").write_text(json.dumps(guide), encoding="utf-8")
            clipboard = {"plain": "not JSON", "scalar": "false", "wrong_signature": '{"signature":"other"}'}
            (root / "test_clipboard.txt").write_text(clipboard.get(scenario, json.dumps(normal)))
            cmd = [ASEPRITE, "--batch"]
            for key, value in (("root", root), ("repo", ROOT), ("target", target), ("scenario", scenario)):
                cmd += ["--script-param", f"{key}={value}"]
            cmd += ["--script", str(ROOT / "tests/aseprite_practice_harness.lua")]
            result = subprocess.run(cmd, env={**os.environ, "APPDATA": str(root)}, capture_output=True,
                                    timeout=20, check=False)
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
            self.assertTrue((root / "passed.txt").is_file(), (result.stdout, result.stderr))

    def test_ordinary_and_practice_complete_without_console(self):
        for scenario in ("copy", "ordinary", "practice"):
            with self.subTest(scenario=scenario):
                self.run_case(scenario)

    def test_invalid_input_leaves_the_document_unchanged(self):
        for scenario in ("plain", "scalar", "wrong_signature", "missing_metadata", "missing_png",
                         "corrupt_png", "expired", "other_target"):
            with self.subTest(scenario=scenario):
                self.run_case(scenario)
