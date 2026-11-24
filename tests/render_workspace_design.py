"""Capture the source widgets with Windows QPA and a private synthetic profile."""
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, QRect
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
        w.resize(460, 620)
        w.show()
        app.processEvents()

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
            w.resize(460, 760)
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
            w.resize(390, 380)
            w.content_scroll.verticalScrollBar().setValue(0)
            app.processEvents()
            app.processEvents()
            assert not w.content_scroll.horizontalScrollBar().maximum()
            viewport = w.content_scroll.viewport()
            for button in (w.btn_ps_copy, w.btn_ase_paste, w.btn_ase_copy, w.btn_ps_paste):
                bounds = QRect(button.mapTo(viewport, QPoint()), button.size())
                assert viewport.rect().contains(bounds), (bounds, w.preview_label.height())
            save(w, 'workspace-narrow-200')
    finally:
        case.doCleanups()
        suite.doClassCleanups()
        del qt


def contact_sheet(directory):
    fonts = Path(__file__).resolve().parents[1] / 'assets/fonts/PretendardVariable.ttf'
    title_font = ImageFont.truetype(fonts, 25)
    label_font = ImageFont.truetype(fonts, 17)
    pages = (
        ('01-workspace', 2, (('Workspace / 100% / copied', 'workspace-copied'),
                             ('Compact / Japanese / 200%', 'workspace-narrow-200'))),
        ('02-settings', 2, (('Settings / 100%', 'workspace-settings'),
                            ('Setup guide / 100% / warning step', 'workspace-setup'))),
        ('03-help', 3, (('Ground Line', 'help-ground'), ('Center', 'help-center'),
                        ('Absolute', 'help-absolute'), ('Normal', 'help-normal'),
                        ('Folder to Frames', 'help-folder'), ('Layer to Frames', 'help-layer'))),
    )
    for name, columns, entries in pages:
        images = [(label, Image.open(directory / f'{file}.png').convert('RGB')) for label, file in entries]
        widths = [max(img.width for _, img in images[col::columns]) + 20 for col in range(columns)]
        rows = [images[i:i + columns] for i in range(0, len(images), columns)]
        heights = [max(img.height for _, img in row) + 46 for row in rows]
        page = Image.new('RGB', (sum(widths) + 20, 64 + sum(heights)), '#151822')
        painter = ImageDraw.Draw(page)
        painter.text((20, 16), 'Photoshop ↔ Aseprite | 0.3.7 development', font=title_font, fill='#f5f3ff')
        y = 64
        for row, height in zip(rows, heights):
            x = 20
            for (title, img), width in zip(row, widths):
                painter.text((x, y), title, font=label_font, fill='#c5b6ff')
                page.paste(img, (x, y + 26))
                x += width
            y += height
        page.save(directory / f'review-{name}.png')


if __name__ == '__main__':
    directory = Path(sys.argv[1])
    if '--contact-sheet' in sys.argv:
        contact_sheet(directory)
    else:
        capture(directory)
