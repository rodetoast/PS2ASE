"""Launch source/EXE with a persistent, private profile for real mouse testing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from startup_exe_probe import visible_windows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--existing", action="store_true")
    parser.add_argument("--tutorial-only", action="store_true")
    parser.add_argument("--exit-after-dialog", action="store_true")
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        raise ValueError("Invalid private profile name")
    base = Path("C:/Dev/aseps-startup-validation")
    profile = base / "manual-profiles" / args.name
    settings_dir = profile / "Ase-PS-Bridge"
    settings_dir.mkdir(parents=True, exist_ok=True)
    if args.existing or args.tutorial_only:
        settings = {"language": "en", "photoshop_exe": "not-launched.exe", "aseprite_exe": "not-launched.exe",
                    "aseprite_trust_confirmed": True, "show_tutorial": False,
                    "ground_line_default_migrated": True, "default_alignment": "ground_line"}
        if args.tutorial_only:
            settings.update(language="ko", show_tutorial=True)
        (settings_dir / "bridge_settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if args.exe:
        executable = args.exe.resolve()
        if not executable.is_relative_to(base):
            raise ValueError("Private validation EXE only")
        command = [str(executable)]
    else:
        executable = base / "venv/Scripts/python.exe"
        command = [str(executable), str(Path(__file__).resolve().parents[1] / "bridge_ui.py")]
    env = dict(os.environ, APPDATA=str(profile))
    for key in ("PYTHONPATH", "QT_QPA_PLATFORM", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(key, None)
    observed_executable = executable
    if not args.exe:
        observed_executable = Path(subprocess.check_output(
            [str(executable), "-c", "import sys; print(sys._base_executable)"],
            env=env, text=True, encoding="utf-8").strip())
    started = time.time()
    process = subprocess.Popen(command, env=env)
    print(json.dumps({"profile": str(profile), "pid": process.pid, "started": started}), flush=True)
    previous = None
    with (profile / "window-events.jsonl").open("w", encoding="utf-8") as log:
        while process.poll() is None:
            windows = visible_windows(observed_executable)
            if windows != previous:
                log.write(json.dumps({"elapsed": time.time() - started, "windows": windows}) + "\n")
                log.flush()
                previous = windows
            if args.exit_after_dialog:
                diagnostic = settings_dir / "logs/bridge.log"
                if diagnostic.exists() and '"state": "STARTUP_INTERACTIVE"' in diagnostic.read_text(encoding="utf-8"):
                    # Stop only the private test processes after all input records were written.
                    for pid in {w["pid"] for w in windows} - {process.pid}:
                        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=10)
                    break
            time.sleep(0.02)
    print("Validation process exit:", process.returncode, flush=True)
