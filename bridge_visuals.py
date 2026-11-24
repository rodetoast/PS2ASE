"""Widget-scale Southpaw launcher graphics and option help (display only)."""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton, QSizePolicy, QStyle,
                               QStyleOptionButton, QStylePainter, QToolTip, QVBoxLayout, QWidget)


# Original 24-unit line drawings; no external icon dependency.
_PATHS = {
    'btn_flip_h': 'M12 2v3m0 3v3m0 3v3m0 3v2 M9 6l-6 12h6z M15 6l6 12h-6z',
    'btn_flip_v': 'M2 12h3m3 0h3m3 0h3m3 0h2 M6 9l12-6v6z M6 15l12 6v-6z',
    'btn_rotate': 'M20 4v6h-6m6 0a8 8 0 1 0 0 5',
    'btn_undo': 'M9 4L3 10l6 6m-6-6h11a6 6 0 0 1 6 6v3',
    'btn_redo': 'M15 4l6 6-6 6m6-6H10a6 6 0 0 0-6 6v3',
    'diag_copy': 'M8 8h12v13H8z M16 5V3H4v14h1',
    'diag_folder': 'M3 19V5h7l3 3h8v11z',
    'diag_clear': 'M5 6h14M9 6V3h6v3m2 0-1 15H8L7 6m3 4v7m4-7v7',
    'help': 'M12 22a10 10 0 1 0 0-20 10 10 0 1 0 0 20 M9 9a3 3 0 1 1 4 3c-1 .6-1 1-1 2m0 3v.2',
    'settings': 'M9 3h6l1 4 4 1v8l-4 1-1 4H9l-1-4-4-1V8l4-1z M12 15a3 3 0 1 0 0-6 3 3 0 1 0 0 6',
    'diagnostics': 'M8 5l7 7-7 7',
    'diagnostics_open': 'M5 8l7 7 7-7',
}


def tool_icon(name):
    icon = QIcon()
    for mode, color in ((QIcon.Normal, '#f5f3ff'), (QIcon.Disabled, '#9296ac')):
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
            p.translate(-60, -36)
            canvas, art = alignment_example(self.index)
            p.setPen(QColor('#393e51'))
            p.drawRect(QRect(QPoint(), canvas))
            p.setPen(QPen(QColor('#c5b6ff'), 1, Qt.DashLine))
            if self.index == 2:
                p.drawLine(0, 0, 98, 0)
                p.drawLine(0, 0, 0, 62)
            else:
                p.drawLine(0, 36, 120, 36)
                p.drawLine(60, 0, 60, 72)
            for rect, color in zip(art, colors):
                p.fillRect(rect, color)
            p.setPen(QPen(QColor('#f5f3ff'), 1, Qt.DotLine))
            bounds = art[0].united(art[1])
            p.drawRect(bounds.adjusted(0, 0, 1, 1))
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
        p.end()


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
