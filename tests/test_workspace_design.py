"""Display-only regression tests. No real clipboard, settings or host apps."""
import unittest
from unittest.mock import patch

import test_preview_layout as preview


class WorkspaceDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        preview.PreviewLayoutTests.setUpClass()
        cls.addClassCleanup(preview.PreviewLayoutTests.doClassCleanups)
        b = preview.lifecycle.JobLifecycleTests.b
        app = preview.lifecycle.JobLifecycleTests.app
        app.setStyle('Fusion')
        b.apply_workspace_theme(app)

    def setUp(self):
        self.fixture = preview.PreviewLayoutTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.w = self.fixture.window
        clipboard = patch.object(self.w, 'update_clipboard_align_mode')
        self.align_updates = clipboard.start()
        self.addCleanup(clipboard.stop)
        self.w.resize(390, 480)
        self.w.show()
        self.fixture.app.processEvents()

    def test_segments_fit_and_stay_exclusive_in_all_languages(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtTest import QTest

        w = self.w
        for language in ('ko', 'en', 'ja'):
            w.current_lang = language
            w.refresh_ui_language()
            self.fixture.app.processEvents()
            for group in (w.option_help.buttons[:3], w.option_help.buttons[3:]):
                with self.subTest(language=language, group=group[0].text()):
                    self.assertLessEqual(max(b.width() for b in group) - min(b.width() for b in group), 1)
                    for button in group:
                        for line in button.display_lines().splitlines():
                            self.assertLessEqual(QFontMetrics(button.font()).horizontalAdvance(line) + 14,
                                                 button.width())
                        self.assertTrue(button.accessibleDescription())
                        self.assertEqual(w.content_scroll.horizontalScrollBar().maximum(), 0)
                        button.click()
                        self.assertEqual([b for b in group if b.isChecked()], [button])
            w.radio_frame_normal.click()
            w.radio_frame_normal.setFocus()
            QTest.keyClick(w.radio_frame_normal, Qt.Key_Right)
            self.assertEqual(w.get_frame_mode(), 'folder_frames')
        self.assertEqual(w.get_align_mode(), 'absolute')
        self.assertEqual(self.align_updates.call_count, 9)

    def test_help_hover_leave_disabled_and_keyboard(self):
        from PySide6.QtCore import QEvent, QPoint, QRect, Qt
        from PySide6.QtGui import QEnterEvent, QMouseEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        w = self.w
        button = w.radio_ground_line
        w.content_scroll.ensureWidgetVisible(button)
        self.fixture.app.processEvents()
        help_ui = w.option_help
        button.setEnabled(False)
        center = button.rect().center()
        parent = button.parentWidget()
        pos = button.mapTo(parent, center)
        global_pos = button.mapToGlobal(center)
        QApplication.sendEvent(parent, QMouseEvent(QEvent.MouseMove, pos, global_pos,
                                                    Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.assertEqual(help_ui.timer.interval(), 500)
        self.assertFalse(help_ui.popup.isVisible())
        QTest.qWait(550)
        self.assertTrue(help_ui.popup.isVisible())
        anchor = QRect(button.mapToGlobal(QPoint()), button.size())
        self.assertTrue(button.screen().availableGeometry().contains(help_ui.popup.geometry()))
        self.assertFalse(help_ui.popup.geometry().intersects(anchor))
        self.assertTrue(help_ui.popup.windowFlags() & Qt.WindowTransparentForInput)
        QApplication.sendEvent(button, QEvent(QEvent.Leave))
        self.assertFalse(help_ui.popup.isVisible())
        button.setEnabled(True)
        button.setFocus()
        QTest.keyClick(button, Qt.Key_F1)
        self.assertTrue(help_ui.popup.isVisible())
        QTest.keyClick(button, Qt.Key_Space)
        self.assertFalse(help_ui.popup.isVisible())
        self.assertEqual(w.get_align_mode(), 'ground_line')
        QApplication.sendEvent(button, QEnterEvent(center, center, button.mapToGlobal(center)))
        self.assertTrue(help_ui.timer.isActive())

    def test_alignment_diagrams_share_one_offset(self):
        from bridge_visuals import alignment_example
        canvas, original = alignment_example(2)
        for index in (0, 1):
            _, art = alignment_example(index)
            self.assertEqual(art[1].topLeft() - art[0].topLeft(),
                             original[1].topLeft() - original[0].topLeft())
            bounds = art[0].united(art[1])
            self.assertEqual(bounds.x(), (canvas.width() - bounds.width()) // 2)
            expected = (canvas.height() // 2 - bounds.height() if index == 0 else
                        (canvas.height() - bounds.height()) // 2)
            self.assertEqual(bounds.top(), expected)

    def test_short_workspace_keeps_both_transfers_visible_without_scrolling(self):
        from PySide6.QtCore import QPoint, QRect
        w = self.w
        viewport = w.content_scroll.viewport()
        for language in ('ko', 'en', 'ja'):
            w.current_lang = language
            w.refresh_ui_language()
            w.resize(390, 380)
            w.content_scroll.verticalScrollBar().setValue(0)
            for copied in (False, True):
                if copied:
                    w.set_preview_image(self.fixture.image(144, 96))
                    status = w.t["clip_ready"].format(src="PS", dst="Ase", count=3)
                else:
                    w.clear_preview()
                    status = w.t["clip_empty"]
                w.update_status(status, "#f3f4f6", "#374151")
                self.fixture.app.processEvents()
                compact = w.preview_label.height()
                for button in (w.btn_ps_copy, w.btn_ase_copy, w.btn_ps_paste, w.btn_ase_paste):
                    self.assertTrue(viewport.rect().contains(QRect(button.mapTo(viewport, QPoint()), button.size())),
                                    (language, button.text(), copied))
            w.resize(460, 620)
            self.fixture.app.processEvents()
            self.assertEqual(w.content_scroll.verticalScrollBar().maximum(), 0, language)
            w.resize(460, 730)
            self.fixture.app.processEvents()
            self.assertGreater(w.preview_label.height(), compact)

    def test_preview_restores_original_raster_and_nearest_neighbor_colors(self):
        from io import BytesIO
        from PIL import Image
        source = Image.new('RGB', (128, 160))
        source.paste('red', (0, 0, 64, 160))
        source.paste('blue', (64, 0, 128, 160))
        encoded = BytesIO()
        source.save(encoded, 'PNG')
        w = self.w
        w.set_preview_image(encoded.getvalue())
        compact = w.preview_label.pixmap().deviceIndependentSize().height()
        w.resize(460, 750)
        self.fixture.app.processEvents()
        large = w.preview_label.pixmap()
        self.assertGreater(large.deviceIndependentSize().height(), compact)
        self.assertGreater(large.deviceIndependentSize().height(), 160)
        self.assertAlmostEqual(large.deviceIndependentSize().height(),
                               w.preview_label.contentsRect().height(), delta=1)
        raster = large.toImage()
        self.assertEqual({raster.pixelColor(x, 20).name() for x in range(raster.width())},
                         {'#ff0000', '#0000ff'})
        w.clear_preview()
        w.resize(390, 380)
        self.fixture.app.processEvents()
        self.assertTrue(w.preview_label.pixmap().isNull())

    def test_font_and_vector_icon_modes(self):
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon, QRawFont
        self.assertIn('Pretendard', QRawFont.fromFont(self.fixture.app.font()).familyName())
        for button, _ in self.w.transform_actions:
            icon = button.icon()
            self.assertEqual(button.iconSize(), QSize(20, 20))
            self.assertNotEqual(icon.pixmap(QSize(20, 20), 2, QIcon.Normal).toImage(),
                                icon.pixmap(QSize(20, 20), 2, QIcon.Disabled).toImage())
