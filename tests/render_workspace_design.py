"""Capture the source widgets with Windows QPA and a private synthetic profile."""
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

from test_workspace_design import WorkspaceDesignTests


def capture(directory):
    # Create the native application before the shared fixture requests offscreen.
    qt = QApplication(['ps2ase-ui-review', '-platform', 'windows'])
    suite = WorkspaceDesignTests
    suite.setUpClass()
    case = suite()
    try:
        case.setUp()
        w = case.w
        app = case.fixture.app
        bridge = case.fixture.fixture.b
        w.current_lang = 'ko'
        w.refresh_ui_language()
        w.resize(440, 730)
        w.show()

        def save(widget, name):
            app.processEvents()
            if not widget.grab().save(str(directory / f'{name}.png')):
                raise RuntimeError(f'Could not capture {name}')

        scale = round(w.devicePixelRatio() * 100)
        if scale == 100:
            save(w, 'workspace-empty')
        img = Image.new('RGBA', (144, 96))
        pixels = ImageDraw.Draw(img)
        pixels.rectangle((16, 53, 127, 74), fill='#425775')
        pixels.rectangle((35, 29, 83, 64), fill='#9bc8ed')
        pixels.rectangle((75, 19, 111, 54), fill='#c5b6ff')
        pixels.rectangle((91, 27, 99, 34), fill='#202432')
        file = BytesIO()
        img.save(file, 'PNG')
        w.last_job_id = 'synthetic-review'
        w.current_job_path = str(case.fixture.fixture.root)
        w.clipboard_source = 'photoshop'
        w.clipboard_count = 3
        w.clipboard_frame_mode = 'normal'
        w.undo_stack.append((False, False, 0))
        w.update_ui_state()
        w.set_preview_image(file.getvalue())
        w.update_clipboard_mode_label()
        w.update_status(w.t['clip_ready'].format(src='PS', dst='Ase', count=3),
                        '#dbeafe', '#8ed4b4')
        if scale == 100:
            save(w, 'workspace-copied')
            w.resize(440, 870)
            w.diagnostics_toggle.setChecked(True)
            save(w, 'workspace-diagnostics')
            w.diagnostics_toggle.setChecked(False)
            options = w.option_help
            for index, name in enumerate(('ground', 'center', 'absolute', 'normal', 'folder', 'layer')):
                options.set_target(options.buttons[index])
                options.timer.stop()
                options.show_help()
                save(options.popup, f'help-{name}')
            options.hide_help()
            guide = bridge.InitialSetupDialog(w.t, w)
            guide.set_step(1)
            guide.resize(500, 510)
            guide.show()
            save(guide, 'workspace-setup')
            guide.deleteLater()
            target = dict(case.fixture.fixture.target, path=r'C:\Example\Adobe\Photoshop.exe')
            values = dict(w.settings, photoshop_exe=target['path'], language='ko')
            with patch.object(bridge, 'installed_photoshops', return_value=[target]), \
                    patch.object(bridge, 'running_photoshops', return_value=[]):
                settings = bridge.SettingsDialog(values, w.t, w)
            settings.show()
            save(settings, 'workspace-settings')
            settings.deleteLater()
        elif scale == 200:
            w.current_lang = 'ja'
            w.refresh_ui_language()
            w.resize(390, 480)
            w.content_scroll.ensureWidgetVisible(w.radio_frame_folder, 0, 8)
            app.processEvents()
            assert not w.content_scroll.horizontalScrollBar().maximum()
            save(w, 'workspace-narrow-200')
    finally:
        case.doCleanups()
        suite.doClassCleanups()
        del qt


if __name__ == '__main__':
    capture(Path(sys.argv[1]))
