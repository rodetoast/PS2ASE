"""Render disposable setup and tutorial states without local host data."""
import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from test_initial_setup_guide import InitialSetupGuideTests


def render(output):
    app = QApplication([])
    fixture = InitialSetupGuideTests
    fixture.setUpClass()
    case = fixture()
    output.mkdir(parents=True, exist_ok=True)
    try:
        case.setUp()
        b = case.b
        b.apply_workspace_theme(app)
        photoshop = r"C:\Program Files\Adobe\Adobe Photoshop 2027\Photoshop.exe"
        case.window.settings.update(photoshop_exe=photoshop, aseprite_exe=r"C:\Program Files\Aseprite\Aseprite.exe")
        target = dict(path=photoshop, major=28, version="28.0.0", product="Adobe Photoshop 2027")
        with patch.object(b, "photoshop_exe_info", return_value=target), \
                patch.object(b, "running_photoshops", return_value=[{"Path": photoshop}]), \
                patch.object(b, "photoshop_config_path", return_value=str(case.fixture.root / "PSUserConfig.txt")), \
                patch.object(b, "aseprite_installation_status", return_value=(True, True)), \
                patch.object(b, "aseprite_runtime", return_value=(True, "guide_ps_running")):
            guide = case.guide("ko")
            guide.resize(380, 520)
            guide.show()
            for step, name in ((guide.WELCOME, "welcome"), (guide.WARNING, "warning")):
                guide.set_step(step)
                app.processEvents()
                assert guide.grab().save(str(output / f"{name}.png"))
            guide.set_step(guide.ASEPRITE)
            guide.start_probe()
            app.processEvents()
            assert guide._probe_name
            assert guide.grab().save(str(output / "f5-practice.png"))
            guide.f5_seen = True
            guide.update_summary()
            guide.start_paste_practice()
            app.processEvents()
            assert guide._practice_source
            assert guide.grab().save(str(output / "f4-practice.png"))
            guide.reject()
            tutorial = b.TutorialDialog(b.LANG["ko"])
            tutorial.resize(380, 520)
            tutorial.show()
            for topic, name in ((0, "tutorial-transfer"), (2, "tutorial-frame-modes"), (4, "tutorial-edit")):
                tutorial.topics.setCurrentIndex(topic)
                app.processEvents()
                assert tutorial.grab().save(str(output / f"{name}.png"))
            tutorial.close()
            case.fixture.shiboken.delete(tutorial)
    finally:
        case.doCleanups()
        fixture.doClassCleanups()


if __name__ == "__main__":
    render(Path(sys.argv[1]))
