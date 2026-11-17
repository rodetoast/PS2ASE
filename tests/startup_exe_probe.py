"""Read-only window/process telemetry for a private onefile validation build.

Never pass a user's working executable: each launch uses an isolated APPDATA,
and the child processes of the supplied private executable are terminated.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def visible_windows(executable):
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    user.IsWindowEnabled.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetForegroundWindow.restype = wintypes.HWND
    results = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return True
            if os.path.normcase(path.value) != os.path.normcase(str(executable)):
                return True
            title = ctypes.create_unicode_buffer(512)
            cls = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(hwnd, title, len(title))
            user.GetClassNameW(hwnd, cls, len(cls))
            results.append({"pid": pid.value, "title": title.value, "class": cls.value,
                            "enabled": bool(user.IsWindowEnabled(hwnd)),
                            "foreground": user.GetForegroundWindow() == hwnd,
                            "minimized": bool(user.IsIconic(hwnd)),
                            "owner": user.GetWindow(hwnd, 4)})
        finally:
            kernel.CloseHandle(handle)
        return True

    callback = callback_type(visit)
    user.EnumWindows(callback, 0)
    return results


def run(executable, repeats):
    # This explicit boundary prevents accidentally targeting the release EXE.
    if not executable.is_relative_to(Path("C:/Dev/aseps-startup-validation")):
        raise ValueError("Only the private C:/Dev/aseps-startup-validation build is allowed")
    for attempt in range(repeats):
        if visible_windows(executable):
            raise RuntimeError("Close other private validation instances before measuring")
        with tempfile.TemporaryDirectory(dir=executable.parent, prefix="profile_") as folder:
            profile = Path(folder)
            settings_dir = profile / "Ase-PS-Bridge"
            settings_dir.mkdir()
            settings = {"language": "en", "photoshop_exe": "not-launched.exe",
                        "aseprite_exe": "not-launched.exe", "aseprite_trust_confirmed": True,
                        "show_tutorial": False, "ground_line_default_migrated": True,
                        "default_alignment": "ground_line"}
            (settings_dir / "bridge_settings.json").write_text(json.dumps(settings), encoding="utf-8")
            runtime = profile / "runtime.jsonl"
            env = dict(os.environ, APPDATA=str(profile), ASEPS_STARTUP_PROBE=str(runtime))
            env.pop("QT_QPA_PLATFORM", None)
            started_wall = time.time()
            started = time.perf_counter()
            process = subprocess.Popen([str(executable)], env=env)
            observed = set()
            first_splash = first_main = splash_gone = None
            ready = None
            interactive = None
            error_window = None
            splash_at_error = None
            try:
                while time.perf_counter() - started < 30:
                    now = time.perf_counter() - started
                    windows = visible_windows(executable)
                    observed.update(w["pid"] for w in windows)
                    error_window = next((w["title"] for w in windows if "Unhandled exception" in w["title"]), None)
                    if error_window:
                        splash_at_error = any(w["class"].startswith("Tk") for w in windows)
                        break
                    splash = any(w["class"].startswith("Tk") for w in windows)
                    main = any(w["class"].startswith("Qt") for w in windows)
                    if splash and first_splash is None:
                        first_splash = now
                    if main and first_main is None:
                        first_main = now
                    log = settings_dir / "logs" / "bridge.log"
                    if log.exists():
                        for line in log.read_text(encoding="utf-8").splitlines():
                            try:
                                event = json.loads(line)
                                if event["state"] == "STARTUP_READY":
                                    ready = event
                                if event["state"] == "STARTUP_INTERACTIVE":
                                    interactive = event
                            except (ValueError, KeyError):
                                pass
                    if first_main is not None and not splash:
                        if splash_gone is None:
                            splash_gone = now
                        if ready and interactive:
                            break
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)  # External sampling only, not an application delay.
                report = {"run": attempt + 1, "splash_s": first_splash, "main_s": first_main,
                          "splash_gone_s": splash_gone, "ready": ready, "interactive": interactive,
                          "runtime": runtime.read_text() if runtime.exists() else None,
                          "started_wall": started_wall, "exit": process.poll(), "error_window": error_window,
                          "splash_visible_at_error": splash_at_error}
                print(json.dumps(report), flush=True)
            finally:
                # Only this isolated executable is allowed above, never Photoshop/Aseprite.
                for pid in observed - {process.pid}:
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run(args.executable.resolve(), args.repeats)
