"""Build only private startup verification artifacts, with an unpolluted PATH."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def clean_build_environment(python):
    system = Path(os.environ["SystemRoot"])
    env = dict(os.environ)
    # Do not let Poppler/other apps supply same-named DLLs to Qt dependency analysis.
    env["PATH"] = os.pathsep.join((str(python.parent), str(Path(sys.base_prefix)),
                                  str(system / "System32"), str(system)))
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(key, None)
    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("python", type=Path)
    parser.add_argument("--spec", type=Path, default=Path(__file__).resolve().parents[1] / "bridge_ui.spec")
    parser.add_argument("--variant", default="bridge-clean")
    args = parser.parse_args()
    if not args.variant.replace("-", "").isalnum():
        raise ValueError("Invalid validation variant")
    private = Path("C:/Dev/aseps-startup-validation") / args.variant
    subprocess.run([str(args.python), "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(private / "dist"), "--workpath", str(private / "work"), str(args.spec)],
                   cwd=Path(__file__).resolve().parents[1], env=clean_build_environment(args.python), check=True)
