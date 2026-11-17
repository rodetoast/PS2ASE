"""Minimal Qt loader probe for private validation builds, not a release entrypoint."""
import ctypes
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    report = {"python": sys.version, "executable": sys.executable, "steps": [],
              "environment": {k: os.environ.get(k) for k in
                              ("PATH", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")}}
    try:
        import PySide6
        report["pyside_version"] = PySide6.__version__
        report["pyside_path"] = PySide6.__file__
        from PySide6 import QtCore
        report["steps"].append("QtCore")
        from PySide6 import QtGui
        report["steps"].append("QtGui")
        from PySide6 import QtWidgets
        report["steps"].append("QtWidgets")
        app = QtWidgets.QApplication([])
        button = QtWidgets.QPushButton("Qt loader validation - Close")
        button.clicked.connect(app.quit)
        button.show()
        app.processEvents()
        report["steps"].append("QApplication/window")
        print(json.dumps(report), flush=True)
        if os.environ.get("ASEPS_QT_AUTO_EXIT"):
            QtCore.QTimer.singleShot(0, app.quit)
        return app.exec()
    except Exception as error:
        report["error"] = repr(error)
        report["winerror"] = getattr(error, "winerror", None)
        report["traceback"] = traceback.format_exc()
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent / "Lib/site-packages")) / "PySide6"
        report["dll_checks"] = []
        for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"):
            try:
                ctypes.WinDLL(str(base / name))
                report["dll_checks"].append({"dll": name, "loaded": True})
            except OSError as dll_error:
                report["dll_checks"].append({"dll": name, "winerror": dll_error.winerror,
                                             "error": str(dll_error)})
        print(json.dumps(report), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
