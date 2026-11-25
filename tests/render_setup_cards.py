"""Capture guide cards using Windows Qt, without changing host settings."""
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication

from test_initial_setup_guide import InitialSetupGuideTests


def render(directory):
    app = QApplication(["ps2ase-guide-review", "-platform", "windows"])
    fixture = InitialSetupGuideTests
    fixture.setUpClass()
    case = fixture()
    try:
        case.setUp()
        bridge = case.b
        app.setStyle("Fusion")
        bridge.apply_workspace_theme(app)
        path = r"C:\Program Files\Adobe\Adobe Photoshop 2027\Photoshop.exe"
        target = dict(path=path, major=28, version="28.0 (illustrative build)", product="Adobe Photoshop 2027")
        case.window.settings["photoshop_exe"] = path
        case.window.settings["aseprite_exe"] = r"C:\Program Files\Aseprite\aseprite.exe"
        with patch.object(bridge, "photoshop_exe_info", return_value=target), \
                patch.object(bridge, "running_photoshops", return_value=[{"Path": path}]), \
                patch.object(bridge, "photoshop_config_path", return_value=str(case.fixture.root / "PSUserConfig.txt")), \
                patch.object(bridge, "aseprite_installation_status", return_value=(True, True)), \
                patch.object(bridge, "aseprite_runtime", return_value=(True, "guide_ps_running")):
            dialog = case.guide("ko")
        dialog.show()
        scale = round(dialog.devicePixelRatioF() * 100)
        pages = (((0, "connection"), (1, "warning"), (2, "aseprite"), (3, "summary"))
                 if scale == 100 else ((1, "compact-200"),))
        for step, name in pages:
            if scale == 200:
                dialog.resize(330, 420)
            dialog.set_step(step)
            app.processEvents()
            if not dialog.grab().save(str(directory / f"{name}.png")):
                raise RuntimeError(f"Could not capture {name}")
    finally:
        case.doCleanups()
        fixture.doClassCleanups()


def contact_sheet(directory):
    fonts = Path(__file__).resolve().parents[1] / "assets/fonts/PretendardVariable.ttf"
    title = ImageFont.truetype(fonts, 22)
    caption = ImageFont.truetype(fonts, 16)
    pages = (
        (("Connection / 100%", "connection"), ("Warnings / 100%", "warning")),
        (("Aseprite / 100% / installed", "aseprite"), ("Summary / 100%", "summary")),
        (("Warnings / 200% / compact", "compact-200"),),
    )
    for index, entries in enumerate(pages, 1):
        views = [(label, Image.open(directory / f"{file}.png").convert("RGB")) for label, file in entries]
        sheet = Image.new("RGB", (60 + sum(image.width for _, image in views),
                                  110 + max(image.height for _, image in views)), "#151822")
        draw = ImageDraw.Draw(sheet)
        draw.text((20, 12), "Photoshop ↔ Aseprite | 0.3.7 development", font=title, fill="#f5f3ff")
        x = 20
        for label, view in views:
            draw.text((x, 53), label, font=caption, fill="#c5b6ff")
            sheet.paste(view, (x, 82))
            x += view.width + 20
        sheet.save(directory / f"review-{index:02}.png")


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    (contact_sheet if "--contact-sheet" in sys.argv else render)(directory)
