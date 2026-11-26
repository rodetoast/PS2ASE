"""Widget-scale Southpaw launcher graphics and option help (display only)."""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton, QSizePolicy, QStyle,
                               QStyleOptionButton, QStylePainter, QToolTip, QVBoxLayout, QWidget,
                               QDialog, QMainWindow)


class NativeDarkCaption(QObject):
    """Use the same DWM caption attributes as the Southpaw launcher."""

    def __init__(self, app):
        super().__init__(app)
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.set_attribute = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
        self.set_attribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        self.set_attribute.restype = wintypes.LONG
        app.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Show and isinstance(watched, (QDialog, QMainWindow))
                and watched.isWindow() and not watched.windowFlags() & Qt.FramelessWindowHint):
            try:
                hwnd = int(watched.winId())
                apply = self.set_attribute
                c = self.ctypes
                caption = c.c_uint32(0x2B1E1B)
                ink = c.c_uint32(0xFFF3F5)
                if apply(hwnd, 35, c.byref(caption), 4) == 0 and apply(hwnd, 36, c.byref(ink), 4) != 0:
                    default = c.c_uint32(0xFFFFFFFF)
                    apply(hwnd, 35, c.byref(default), 4)
                dark = c.c_int(1)
                apply(hwnd, 20, c.byref(dark), 4)
            except (OSError, RuntimeError):
                pass
        return False


# Original 24-unit line drawings; no external icon dependency.
_PATHS = {
    'btn_flip_h': 'M12 3v18 M9 7H4v10h5 M15 7h5v10h-5',
    'btn_flip_v': 'M3 12h18 M7 9V4h10v5 M7 15v5h10v-5',
    'clipboard': 'M9 5H5v16h14V5h-4 M9 3h6v5H9z M8 12h8m-8 4h8',
    'app_window': 'M3 4h18v16H3z M3 9h18 M6 6.5h.2 M9 6.5h.2',
    'btn_rotate': 'M20 4v6h-6m6 0a8 8 0 1 0 0 5',
    'btn_undo': 'M9 4L3 10l6 6m-6-6h11a6 6 0 0 1 6 6v3',
    'btn_redo': 'M15 4l6 6-6 6m6-6H10a6 6 0 0 0-6 6v3',
    'diag_copy': 'M8 8h12v13H8z M16 5V3H4v14h1',
    'diag_folder': 'M3 19V5h7l3 3h8v11z',
    'diag_clear': 'M5 6h14M9 6V3h6v3m2 0-1 15H8L7 6m3 4v7m4-7v7',
    'check': 'M12 22a10 10 0 1 0 0-20 10 10 0 1 0 0 20 M7.5 12l3 3 6-6',
    'help': 'M12 22a10 10 0 1 0 0-20 10 10 0 1 0 0 20 M9 9a3 3 0 1 1 4 3c-1 .6-1 1-1 2m0 3v.2',
    'settings': 'M9 3h6l1 4 4 1v8l-4 1-1 4H9l-1-4-4-1V8l4-1z M12 15a3 3 0 1 0 0-6 3 3 0 1 0 0 6',
    'diagnostics': 'M8 5l7 7-7 7',
    'diagnostics_open': 'M5 8l7 7 7-7',
}


def tool_icon(name, *, ink="#f5f3ff"):
    icon = QIcon()
    for mode, color in ((QIcon.Normal, ink), (QIcon.Disabled, '#9296ac')):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<path d="{_PATHS[name]}" fill="none" stroke="{color}" stroke-width="1.7" '
               'stroke-linecap="round" stroke-linejoin="round"/></svg>')
        renderer = QSvgRenderer(svg.encode('ascii'))
        for scale in (1, 1.25, 1.5, 2):
            pixmap = QPixmap(round(20 * scale), round(20 * scale))
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            icon.addPixmap(pixmap, mode)
    return icon


class PixelPreview(QLabel):
    """Keep the original raster so enlarging the viewport restores lost detail."""

    MIN_HEIGHT = 48

    def __init__(self, text):
        super().__init__(text)
        self.source = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(340, self.MIN_HEIGHT)

    def minimumSizeHint(self):
        return QSize(0, self.MIN_HEIGHT)

    def set_image(self, data):
        self.source.loadFromData(data, 'PNG')
        self.render_image()

    def setText(self, text):
        self.source = QPixmap()
        super().setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.source.isNull():
            self.render_image()

    def event(self, event):
        if event.type() == QEvent.DevicePixelRatioChange and not self.source.isNull():
            self.render_image()
        return super().event(event)

    def render_image(self):
        if self.source.isNull():
            self.setPixmap(QPixmap())
            return
        area = self.contentsRect()
        dpr = self.devicePixelRatioF()
        target = QSize(int(area.width() * dpr), int(area.height() * dpr))
        if target.isEmpty():
            return
        ratio = min(target.width() / self.source.width(), target.height() / self.source.height())
        fitted = QSize(max(1, round(self.source.width() * ratio)), max(1, round(self.source.height() * ratio)))
        pixmap = self.source.scaled(fitted, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        pixmap.setDevicePixelRatio(dpr)
        self.setPixmap(pixmap)


class SegmentButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setProperty('uiSegment', True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(90, max(34, self.fontMetrics().lineSpacing() * 2 + 7))

    minimumSizeHint = sizeHint

    def display_lines(self):
        text = self.text()
        if self.fontMetrics().horizontalAdvance(text) > self.width() - 14 and ' → ' in text:
            before, after = text.split(' → ', 1)
            return f'{before} →\n{after}'
        return text

    def paintEvent(self, _):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, option)
        painter.setPen(QColor('#f5f3ff' if self.isEnabled() else '#9296ac'))
        painter.drawText(self.rect().adjusted(7, 2, -7, -2), Qt.AlignCenter, self.display_lines())
        painter.end()


ALIGN_KEYS = ('align_ground_line', 'align_center', 'align_abs')
FRAME_KEYS = ('frame_mode_normal', 'frame_mode_folder_frames', 'frame_mode_layer_frames')
_HELP_TEXT = {
    'en': (
        'Centers the copied bounds horizontally and puts their bottom on the Aseprite canvas midline.',
        'Centers the copied bounds on the Aseprite canvas, keeping layer offsets relative to each other.',
        'Uses the copied coordinates as-is, without centering on the Aseprite canvas.',
        'Pastes the copied selection into the current Aseprite frame, without splitting it into frames.',
        'One frame per folder in Photoshop panel order, starting at the current frame. Layer rows are reused from the active row down.',
        'One frame per selected pixel layer in Photoshop panel order. All cels go on the active Aseprite layer.',
    ),
    'ko': (
        '복사 영역을 좌우 가운데에 두고, 영역의 하단을 Aseprite 캔버스의 가로 중앙선에 맞춥니다.',
        '레이어 간 위치 관계를 유지한 채 복사 영역 전체를 Aseprite 캔버스 중앙에 배치합니다.',
        'Aseprite 캔버스 중앙에 다시 맞추지 않고 복사 데이터의 좌표를 그대로 사용합니다.',
        '복사한 선택을 프레임으로 나누지 않고 현재 Aseprite 프레임에 붙여넣습니다.',
        'Photoshop 패널 순서대로 폴더마다 한 프레임을 만듭니다. 현재 프레임에서 시작하며, 선택한 레이어부터 아래로 행을 재사용합니다.',
        'Photoshop 패널 순서대로 선택한 픽셀 레이어마다 한 프레임을 만듭니다. 현재 Aseprite 레이어 한 줄에만 붙여넣습니다.',
    ),
    'ja': (
        'コピー範囲を左右中央に置き、下端を Aseprite キャンバスの水平中央線に合わせます。',
        '各レイヤーの相対位置を保ったまま、コピー範囲を Aseprite キャンバスの中央に配置します。',
        '中央に移動せず、コピーされた座標をそのまま使用します。',
        'コピーした選択範囲を分割せず、Aseprite の現在のフレームに貼り付けます。',
        'Photoshop のパネル順にフォルダーをフレームへ分けます。現在のフレームから、選択行以下のレイヤーを再利用します。',
        'Photoshop のパネル順に選択ピクセルレイヤーをフレームへ分け、Aseprite の現在のレイヤーに貼り付けます。',
    ),
}


def alignment_example(index):
    # The two rectangles share one exported bounding box and one offset.
    art = (QRect(12, 13, 17, 24), QRect(34, 29, 25, 17))
    bounds = art[0].united(art[1])
    canvas = QSize(120, 72)
    x = (canvas.width() - bounds.width()) // 2 - bounds.x()
    y = ((canvas.height() - bounds.height()) // 2 if index == 1 else
         canvas.height() // 2 - bounds.height()) - bounds.y()
    offset = QPoint(0, 0) if index == 2 else QPoint(x, y)
    return canvas, tuple(rect.translated(offset) for rect in art)


class OptionDiagram(QWidget):
    def __init__(self):
        super().__init__()
        self.index = 0
        self.lang = 'en'
        self.setFixedHeight(98)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#151822'))
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        scale = min(1, self.width() / 218)
        p.scale(scale, scale)
        colors = tuple(map(QColor, ('#9bc8ed', '#c5b6ff', '#8ed4b4')))
        if self.index < 3:
            p.translate(-73, -35)
            canvas, art = alignment_example(self.index)
            p.setPen(QColor('#393e51'))
            p.drawRect(QRect(QPoint(), canvas))
            for rect, color in zip(art, colors):
                p.fillRect(rect, color)
            p.setPen(QPen(QColor('#f5f3ff'), 1, Qt.DotLine))
            bounds = art[0].united(art[1])
            p.drawRect(bounds)
            accent = QColor('#c5b6ff')
            p.setPen(QPen(accent, 1, Qt.DashLine))
            if self.index == 0:
                p.drawLine(-6, 36, 126, 36)
                p.setPen(QPen(accent, 2))
                p.drawLine(bounds.x(), 36, bounds.x() + bounds.width(), 36)
                p.drawLine(bounds.x(), 32, bounds.x(), 39)
                p.drawLine(bounds.x() + bounds.width(), 32, bounds.x() + bounds.width(), 39)
            elif self.index == 1:
                p.drawLine(0, 36, 120, 36)
                p.drawLine(60, 0, 60, 72)
                p.setPen(QPen(accent, 1))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPoint(60, 36), 5, 5)
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawEllipse(QPoint(bounds.x() + bounds.width() // 2,
                                     bounds.y() + bounds.height() // 2), 2, 2)
            else:
                x, y = bounds.x(), bounds.y()
                p.drawLine(x, 0, x, y)
                p.drawLine(0, y, x, y)
                p.setPen(QPen(accent, 1))
                p.drawLine(0, 0, 0, 60)
                p.drawLine(0, 0, 108, 0)
                p.setBrush(accent)
                p.drawEllipse(QPoint(0, 0), 2, 2)
                p.drawEllipse(QPoint(x, y), 2, 2)
                p.drawText(6, -3, '(0, 0)')
                p.drawText(44, 15, f'({x}, {y})')
        else:
            p.translate(-100, -33)
            p.setPen(QColor('#b7b9cb'))
            p.drawText(4, 12, 'Photoshop')
            p.drawText(113, 12, 'Aseprite')
            p.drawLine(77, 42, 102, 42)
            p.drawLine(102, 42, 96, 37)
            p.drawLine(102, 42, 96, 47)
            sources, frames = {
                3: (((0, 1, 2),), ((0, 1, 2),)),
                4: (((0, 1), (2,)), ((0, 1), (2, None))),
                5: (((0, 1, 2),), ((0,), (1,), (2,))),
            }[self.index]
            for column, stack in enumerate(sources):
                x = 4 + column * 35
                if self.index == 4:
                    p.setPen(QColor('#9296ac'))
                    p.drawRect(x, 20, 28, 13 * len(stack) + 7)
                    p.drawLine(x + 2, 18, x + 12, 18)
                for row, item in enumerate(stack):
                    p.fillRect(x + 5, 24 + row * 13, 18, 9, colors[item])
            for column, frame in enumerate(frames):
                for row, item in enumerate(frame):
                    cell = QRect(113 + column * 28, 21 + row * 14, 25, 12)
                    p.setPen(QColor('#9296ac' if column == 0 else '#545a74'))
                    p.drawRect(cell)
                    if item is not None:
                        p.fillRect(cell.adjusted(3, 3, -2, -2), colors[item])
            p.setPen(QColor('#b7b9cb'))
            p.drawText(QRect(0, 65, 205, 17), Qt.AlignCenter,
                       {'ko': '열: 프레임 · 행: 레이어',
                        'en': 'Cols: Frames / Rows: Layers',
                        'ja': '列: フレーム / 行: レイヤー'}[self.lang])
        p.end()


class PracticeDiagram(QWidget):
    """A DPI-aware diagram of the supplied sprite and its real frame structure."""

    def __init__(self, mode, character, names=(), parent=None):
        super().__init__(parent)
        self.mode, self.character, self.names = mode, character, names
        self.setMinimumHeight(155 if mode == "timeline" else 111)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#151822"))
        scale = min(self.width() / 280, self.height() / 150) if self.mode == "timeline" else min(self.width() / 280, self.height() / 106)
        p.translate((self.width() - 280 * scale) / 2, (self.height() - (150 if self.mode == "timeline" else 106) * scale) / 2)
        p.scale(scale, scale)
        border, panel = QColor("#454b60"), QColor("#242938")
        ink, muted, accent = QColor("#f5f3ff"), QColor("#b7b9cb"), QColor("#c5b6ff")

        def box(x, y, w, h, color, stroke=border):
            p.setPen(stroke)
            p.setBrush(color)
            p.drawRoundedRect(QRect(x, y, w, h), 4, 4)

        def label(x, y, w, h, text, color=ink):
            p.setPen(color)
            p.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

        def canvas(x, y, side, sprite=None):
            for row in range(6):
                for col in range(6):
                    p.fillRect(QRect(x + col * (side // 6), y + row * (side // 6), side // 6, side // 6),
                               QColor("#323745" if (row + col) % 2 else "#474c5b"))
            if sprite is not None and not sprite.isNull():
                sprite = sprite.scaled(side - 10, side - 10, Qt.KeepAspectRatio, Qt.FastTransformation)
                p.drawPixmap(x + (side - sprite.width()) // 2, y + (side - sprite.height()) // 2, sprite)

        if self.mode == "timeline":
            canvas(108, 7, 54, self.character)
            box(20, 69, 240, 75, panel)
            for col in range(3):
                label(124 + col * 30, 68, 26, 15, str(col + 1), muted)
            for row in range(4):
                y = 84 + row * 14
                label(28, y, 78, 14, f"Layer {4 - row}", accent if row == 3 else ink)
                for col in range(3):
                    x = 124 + col * 30
                    active = row == 3 and col == 0
                    box(x, y, 26, 12, QColor("#7146bd") if active else QColor("#303647"), accent if active else border)
                    if col != 1:
                        p.setPen(Qt.NoPen)
                        p.setBrush(accent if active else muted)
                        p.drawEllipse(QPoint(x + 13, y + 6), 2, 2)
        elif self.mode == "layers":
            canvas(20, 18, 66, self.character)
            box(108, 11, 152, 86, panel)
            label(120, 12, 128, 22, self.names[0])
            for row, name in enumerate(self.names[1:]):
                y = 34 + row * 24
                box(117, y, 133, 20, QColor("#382d57") if row == 0 else panel, accent if row == 0 else border)
                p.fillRect(123, y + 5, 11, 10, accent if row == 0 else muted)
                label(139, y, 107, 20, name)
        elif self.mode == "edit":
            versions = (self.character, self.character.transformed(QTransform().scale(-1, 1)),
                        self.character.transformed(QTransform().rotate(90)))
            for i, version in enumerate(versions):
                x = 15 + i * 92
                canvas(x + 7, 10, 54, version)
                label(x - 4, 69, 76, 22, self.names[i], muted)
        elif self.mode in ("bridge_forward", "bridge_reverse"):
            box(26, 5, 228, 95, panel)
            for row, caption in enumerate(("Photoshop → Aseprite", "Aseprite → Photoshop")):
                y = 8 + row * 44
                label(34, y, 212, 16, caption)
                for col in range(2):
                    x = 34 + col * 108
                    highlight = self.mode == ("bridge_forward" if row == 0 else "bridge_reverse")
                    box(x, y + 18, 104, 22, QColor("#7146bd") if highlight else QColor("#303647"))
                    label(x + 1, y + 18, 102, 22, self.names[row * 2 + col])
        else:
            for x, name, show in ((22, self.names[0], self.mode == "welcome"),
                                  (186, self.names[1], True)):
                box(x - 10, 8, 86, 90, panel)
                canvas(x + 6, 17, 54, self.character if show else None)
                label(x - 9, 74, 84, 19, name)
            label(107, 19, 66, 61, "↔" if self.mode == "welcome" else "→", accent)


class OptionHelp(QObject):
    """One non-interactive tooltip for both option groups."""

    def __init__(self, window, buttons):
        super().__init__(window)
        self.window = window
        self.buttons = buttons
        self.target = None
        self.popup = QWidget(window, Qt.ToolTip | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.popup.setAttribute(Qt.WA_ShowWithoutActivating)
        self.popup.setObjectName('optionHelp')
        self.popup.setAttribute(Qt.WA_StyledBackground)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(6)
        self.title, self.description = QLabel(), QLabel()
        self.title.setProperty('uiHeading', True)
        self.description.setProperty('uiMuted', True)
        self.description.setWordWrap(True)
        self.diagram = OptionDiagram()
        for widget in (self.title, self.diagram, self.description):
            layout.addWidget(widget)
        self.timer = QTimer(self, singleShot=True, interval=500)
        self.timer.timeout.connect(self.show_help)
        for button in buttons:
            button.setMouseTracking(True)
            button.parentWidget().setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        self.refresh()

    def refresh(self):
        self.hide_help()
        descriptions = _HELP_TEXT[self.window.current_lang]
        for button, description in zip(self.buttons, descriptions):
            button.setAccessibleDescription(description)

    def set_target(self, button):
        if self.target != button:
            self.hide_help()
            self.target = button
            if button:
                self.timer.start()

    def hide_help(self):
        self.timer.stop()
        self.popup.hide()
        self.target = None

    def show_help(self):
        button = self.target
        if not button or button.visibleRegion().isEmpty():
            return
        origin = button.mapToGlobal(QPoint())
        anchor = QRect(origin, button.size())
        screen = QApplication.screenAt(anchor.center()) or self.window.screen()
        area = screen.availableGeometry()
        self.popup.setFixedWidth(min(305, area.width() - 12))
        self.title.setText(button.text())
        self.description.setText(button.accessibleDescription())
        self.diagram.index = self.buttons.index(button)
        self.diagram.lang = self.window.current_lang
        self.diagram.update()
        self.popup.adjustSize()
        height = self.popup.height()
        x = max(area.left(), min(anchor.left(), area.right() - self.popup.width() + 1))
        below, above = anchor.bottom() + 6, anchor.top() - height - 5
        if below + height - 1 <= area.bottom():
            y = below
        elif above >= area.top():
            y = above
        else:
            return
        QToolTip.hideText()
        self.popup.move(x, y)
        self.popup.show()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Enter, QEvent.MouseMove, QEvent.ToolTip) and isinstance(watched, QWidget):
            if watched.window() is self.window:
                button = watched if watched in self.buttons else None
                if button is None and kind in (QEvent.MouseMove, QEvent.ToolTip):
                    cursor = event.globalPosition().toPoint() if kind == QEvent.MouseMove else event.globalPos()
                    button = next((b for b in self.buttons if watched.isAncestorOf(b)
                                   and b.visibleRegion().contains(b.mapFromGlobal(cursor))), None)
                self.set_target(button)
                if kind == QEvent.ToolTip and button:
                    return True
        elif kind == QEvent.KeyPress and watched in self.buttons and event.key() == Qt.Key_F1:
            self.set_target(watched)
            self.timer.stop()
            self.show_help()
            return True
        elif ((watched is self.target and kind in (QEvent.Leave, QEvent.Hide, QEvent.FocusOut)) or
              (watched is self.window and kind in (QEvent.WindowDeactivate, QEvent.Hide, QEvent.Move,
                                                  QEvent.Resize, QEvent.Leave)) or
              (self.target and kind in (QEvent.MouseButtonPress, QEvent.Wheel, QEvent.KeyPress))):
            self.hide_help()
        return False
