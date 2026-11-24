"""Layout tests use Qt scaling, never change Windows display settings."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_photoshop_job_lifecycle as lifecycle

REAL_POPEN = subprocess.Popen


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt dependencies unavailable")
class PreviewLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lifecycle.JobLifecycleTests.setUpClass()
        cls.addClassCleanup(lifecycle.JobLifecycleTests.doClassCleanups)

    def setUp(self):
        self.fixture = lifecycle.JobLifecycleTests("test_success_then_second_copy")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.window = self.fixture.window
        self.app = self.fixture.app

    def image(self, width, height):
        from PIL import Image
        data = io.BytesIO()
        Image.new("RGBA", (width, height), (255, 0, 0, 255)).save(data, format="PNG")
        return data.getvalue()

    def rect(self, widget):
        from PySide6.QtCore import QPoint, QRect
        return QRect(widget.mapTo(self.window.content_scroll.widget(), QPoint(0, 0)), widget.size())

    def assert_independent_rows(self):
        w = self.window
        self.app.processEvents()
        preview = self.rect(w.preview_label)
        row = self.rect(w.transform_bar)
        panel = self.rect(w.preview_panel)
        for part in (self.rect(w.status_label), preview, row):
            self.assertTrue(panel.contains(part))
        self.assertLess(self.rect(w.status_label).bottom(), preview.top())
        self.assertGreater(row.top(), preview.bottom())
        for button in (w.btn_undo, w.btn_flip_h, w.btn_flip_v, w.btn_rotate, w.btn_redo):
            self.assertFalse(preview.intersects(self.rect(button)))
            self.assertTrue(row.contains(self.rect(button)))
        content = w.content_scroll.widget()
        self.assertGreaterEqual(content.height(), content.minimumHeight())
        self.assertGreaterEqual(content.width(), content.minimumWidth())

    def test_layout_matrix(self):
        w = self.window
        for size in ((460, 680), (700, 900)):
            w.showNormal()
            w.resize(*size)
            for debug in (False, True):
                w.diagnostics_toggle.setChecked(debug)
                w.debug_checkbox.setChecked(debug)
                for has_image in (False, True):
                    with self.subTest(size=size, debug=debug, image=has_image):
                        if has_image:
                            w.set_preview_image(self.image(320, 80))
                        else:
                            w.clear_preview()
                        self.assert_independent_rows()
        w.showMaximized()
        self.assert_independent_rows()
        w.showNormal()
        w.resize(460, 680)
        w.diagnostics_toggle.setChecked(True)
        self.app.processEvents()
        self.assertGreater(w.content_scroll.verticalScrollBar().maximum(), 0)

    def test_diagnostics_toggle_does_not_reset_debug(self):
        w = self.window
        self.assertTrue(w.diagnostics_panel.isHidden())
        w.diagnostics_toggle.click()
        self.assertFalse(w.diagnostics_panel.isHidden())
        w.debug_checkbox.setChecked(True)
        w.diagnostics_toggle.click()
        self.assertTrue(w.diagnostics_panel.isHidden())
        self.assertTrue(w.debug_checkbox.isChecked())

    def test_image_ratio_and_no_preview_have_stable_geometry(self):
        w = self.window
        w.show()
        self.app.processEvents()
        empty_geometry = self.rect(w.preview_label)
        row_geometry = self.rect(w.transform_bar)
        for size in ((2048, 1024), (32, 64), (400, 10)):
            w.set_preview_image(self.image(*size))
            self.app.processEvents()
            pixmap = w.preview_label.pixmap()
            self.assertLessEqual(pixmap.width(), w.preview_label.contentsRect().width())
            self.assertLessEqual(pixmap.height(), w.preview_label.contentsRect().height())
            factor = min(1, w.preview_label.contentsRect().width() / size[0],
                         w.preview_label.contentsRect().height() / size[1])
            self.assertAlmostEqual(pixmap.width(), size[0] * factor, delta=1)
            self.assertAlmostEqual(pixmap.height(), size[1] * factor, delta=1)
            self.assertEqual(self.rect(w.preview_label), empty_geometry)
            self.assertEqual(self.rect(w.transform_bar), row_geometry)
        w.clear_preview()
        self.assertEqual(self.rect(w.preview_label), empty_geometry)

    def test_qt_scaling_100_125_150_percent_in_isolated_processes(self):
        code = (
            "import sys,unittest;sys.path.insert(0," + repr(str(Path(__file__).parent)) + ");"
            "from test_preview_layout import PreviewLayoutTests;"
            "result=unittest.TextTestRunner().run(unittest.TestSuite([PreviewLayoutTests('test_layout_matrix')]));"
            "sys.exit(not result.wasSuccessful())"
        )
        for scale in ("1", "1.25", "1.5"):
            with self.subTest(scale=scale):
                env = dict(os.environ, QT_SCALE_FACTOR=scale, QT_QPA_PLATFORM="offscreen")
                with patch.object(subprocess, "Popen", REAL_POPEN):
                    result = subprocess.run([sys.executable, "-c", code], env=env, text=True,
                                            encoding="utf-8", capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
