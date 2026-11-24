import sys
import os
import json
import subprocess
import time
_STARTUP_ENTERED = time.perf_counter()
import shutil
import re
import uuid
import datetime
import traceback
import logging
import logging.handlers
import queue
import threading
from collections import deque
import winreg
import xml.etree.ElementTree as ET
import io


def close_bootloader_on_import_error():
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass


try:
    from PIL import Image
    from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout,
                                   QWidget, QTextEdit, QLabel, QRadioButton, QButtonGroup,
                                   QHBoxLayout, QMessageBox, QFileDialog, QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QComboBox, QStyle, QScrollArea, QSizePolicy, QLayout, QStackedWidget, QProgressBar)
    from PySide6.QtCore import QTimer, QThread, Signal, Slot, Qt, QUrl, QEventLoop, QLocale, QObject, QEvent
    from PySide6.QtGui import QFont, QColor, QPixmap, QDesktopServices
    import win32com.client
    import pythoncom
except Exception:
    close_bootloader_on_import_error()
    raise

# ==========================================
# Job Transform Worker (비파괴 변환: Flip/Rotate 비동기 처리)
# ==========================================
class JobTransformWorker(QThread):
    transform_done = Signal()
    error = Signal(str)
    log = Signal(str)

    def __init__(self, job_path, flip_h, flip_v, angle):
        super().__init__()
        self.job_path = job_path
        self.flip_h = flip_h
        self.flip_v = flip_v
        self.angle = angle # 0, 90, 180, 270 (Clockwise)

    def run(self):
        try:
            self.log.emit(f"Applying transformation (Angle:{self.angle}, H:{self.flip_h}, V:{self.flip_v})...")
            backup_path = os.path.join(self.job_path, "_backup")
            meta_path = os.path.join(self.job_path, "metadata.json")
            layers_path = os.path.join(self.job_path, "layers")
            
            backup_meta = os.path.join(backup_path, "metadata.json")
            backup_layers = os.path.join(backup_path, "layers")

            # 1. 최초 1회 원본 백업 생성 (비파괴 유지)
            if not os.path.exists(backup_path):
                os.makedirs(backup_path)
                if os.path.exists(meta_path):
                    shutil.copy2(meta_path, backup_meta)
                if os.path.exists(layers_path):
                    shutil.copytree(layers_path, backup_layers)
                self.log.emit("✅ 원본 데이터를 안전하게 백업했습니다.")

            # 2. 항상 원본(Backup)에서 시작 (누적 오차 방지)
            if os.path.exists(backup_meta):
                shutil.copy2(backup_meta, meta_path)
            if os.path.exists(backup_layers):
                if os.path.exists(layers_path):
                    shutil.rmtree(layers_path)
                shutil.copytree(backup_layers, layers_path)

            if not self.flip_h and not self.flip_v and self.angle == 0:
                self.transform_done.emit()
                return

            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            elements = metadata.get("elements") or metadata.get("layers", [])
            pixel_layers = [el for el in elements if el.get("type", "layer") == "layer"]
            
            if not pixel_layers:
                self.transform_done.emit()
                return

            # 원본 기준 바운딩 박스 계산
            min_x = min((l.get("x", 0) for l in pixel_layers))
            min_y = min((l.get("y", 0) for l in pixel_layers))
            max_x = max((l.get("x", 0) + l.get("width", 0) for l in pixel_layers))
            max_y = max((l.get("y", 0) + l.get("height", 0) for l in pixel_layers))
            bbox_w, bbox_h = max_x - min_x, max_y - min_y

            # 회전 후 가상의 바운딩 박스 크기
            new_bbox_w = bbox_h if self.angle in [90, 270] else bbox_w
            new_bbox_h = bbox_w if self.angle in [90, 270] else bbox_h

            from PIL import Image

            # 3. 레이어별 좌표 및 이미지 변환
            for el in elements:
                if el.get("type", "layer") == "layer":
                    orig_x, orig_y = el.get("x", 0), el.get("y", 0)
                    orig_w, orig_h = el.get("width", 0), el.get("height", 0)

                    # [3-1] 좌표 회전 (90도 단위 시계방향)
                    if self.angle == 90:
                        el["x"] = min_x + (bbox_h - (orig_y - min_y + orig_h))
                        el["y"] = min_y + (orig_x - min_x)
                        el["width"], el["height"] = orig_h, orig_w
                    elif self.angle == 180:
                        el["x"] = min_x + (bbox_w - (orig_x - min_x + orig_w))
                        el["y"] = min_y + (bbox_h - (orig_y - min_y + orig_h))
                    elif self.angle == 270:
                        el["x"] = min_x + (orig_y - min_y)
                        el["y"] = min_y + (bbox_w - (orig_x - min_x + orig_w))
                        el["width"], el["height"] = orig_h, orig_w

                    # [3-2] 좌표 반전 (회전된 좌표 기준)
                    if self.flip_h:
                        el["x"] = min_x + (new_bbox_w - (el["x"] - min_x + el["width"]))
                    if self.flip_v:
                        el["y"] = min_y + (new_bbox_h - (el["y"] - min_y + el["height"]))

                    # [3-3] 실제 이미지 변환
                    png_path = os.path.join(self.job_path, el.get("file", ""))
                    if os.path.exists(png_path):
                        with Image.open(png_path) as img:
                            # 회전
                            if self.angle == 90: img = img.transpose(Image.ROTATE_270)
                            elif self.angle == 180: img = img.transpose(Image.ROTATE_180)
                            elif self.angle == 270: img = img.transpose(Image.ROTATE_90)
                            # 반전
                            if self.flip_h: img = img.transpose(Image.FLIP_LEFT_RIGHT)
                            if self.flip_v: img = img.transpose(Image.FLIP_TOP_BOTTOM)
                            img.save(png_path)

            # 4. 수정된 메타데이터 저장
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)

            self.transform_done.emit()
        except Exception as e:
            self.error.emit(f"Transform error: {str(e)}")

# ==========================================
# Preview Generator Worker (UI 멈춤 방지용 비동기 합성기)
# ==========================================
class PreviewGeneratorWorker(QThread):
    preview_ready = Signal(bytes, str) # Added job_id for validation
    preview_failed = Signal(str)

    def __init__(self, job_path, job_id):
        super().__init__()
        self.job_path = job_path
        self.job_id = job_id

    def run(self):
        try:
            # 1. 안전 장치: 작업이 완전히 끝났는지(status_done) 다시 한번 확인
            # 클립보드 감지는 빠르지만 파일 시스템 동기화 지연(Race condition) 방지
            done_file = os.path.join(self.job_path, "status_done.json")
            retry_count = 0
            while not os.path.exists(done_file) and retry_count < 10:
                time.sleep(0.1)
                retry_count += 1
                
            if not os.path.exists(done_file):
                self.preview_failed.emit("작업 완료(status_done) 파일을 찾을 수 없습니다.")
                return

            meta_path = os.path.join(self.job_path, "metadata.json")
            if not os.path.exists(meta_path):
                self.preview_failed.emit("metadata.json not found")
                return

            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            elements = metadata.get("elements") or metadata.get("layers", [])
            if metadata.get("frame_mode") in ("folder_frames", "layer_frames"):
                elements = [el for el in elements if int(el.get("frame_index", 0) or 0) == 0]
            if not elements:
                self.preview_failed.emit("표시할 레이어가 없습니다.")
                return

            # 2. 계층 구조 평탄화 (Tree Flattening) 및 렌더 순서(Z-order) 결정
            # 단순히 index만 보면 다른 부모를 가진 형제들끼리 순서가 꼬임.
            # 트리 순회를 통해 Bottom -> Top 렌더링 리스트를 추출해야 함.
            tree_map = {}
            for el in elements:
                p_id = el.get("parent_id") or "root"
                if p_id not in tree_map:
                    tree_map[p_id] = []
                tree_map[p_id].append(el)

            # 형제들끼리 index 오름차순(Bottom->Top) 정렬
            for p_id in tree_map:
                tree_map[p_id].sort(key=lambda x: x.get("index", 0))

            render_list = []
            
            # 깊이 우선 탐색(DFS) 방식으로 Bottom 요소부터 차례대로 평탄화 배열에 담음
            def flatten_tree(parent_id):
                children = tree_map.get(parent_id, [])
                for child in children:
                    if child.get("type") == "group":
                        flatten_tree(child.get("id")) # 폴더면 파고들어 자식들 먼저 수집
                    elif child.get("type", "layer") == "layer" and child.get("visible", True) is not False:
                        render_list.append(child) # 일반 픽셀 레이어면 렌더링 목록에 추가
                        
            flatten_tree("root")

            if not render_list:
                self.preview_failed.emit("표시할 픽셀(visible) 레이어가 없습니다.")
                return

            # 3. 전체 덩어리(Bounding Box) 계산
            min_x = min(l.get("x", 0) for l in render_list)
            min_y = min(l.get("y", 0) for l in render_list)
            max_x = max(l.get("x", 0) + l.get("width", 0) for l in render_list)
            max_y = max(l.get("y", 0) + l.get("height", 0) for l in render_list)

            canvas_w = max_x - min_x
            canvas_h = max_y - min_y

            if canvas_w <= 0 or canvas_h <= 0:
                self.preview_failed.emit("유효하지 않은 캔버스 크기입니다.")
                return

            # 4. 투명 캔버스 생성
            base_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

            # 5. 각 레이어를 캔버스에 얹기 (Alpha Composite)
            for l in render_list:
                png_path = os.path.join(self.job_path, l.get("file", ""))
                if not os.path.exists(png_path):
                    continue

                try:
                    with Image.open(png_path) as layer_img:
                        layer_img = layer_img.convert("RGBA")
                        
                        opacity_pct = l.get("opacity", 100)
                        if opacity_pct < 100:
                            alpha = layer_img.split()[3]
                            alpha = alpha.point(lambda p: int(p * (opacity_pct / 100.0)))
                            layer_img.putalpha(alpha)
                        
                        target_x = l.get("x", 0) - min_x
                        target_y = l.get("y", 0) - min_y
                        
                        base_canvas.alpha_composite(layer_img, dest=(target_x, target_y))
                except Exception:
                    pass

            # 6. 썸네일 축소 (픽셀아트 특성 고려)
            # 원본 이미지가 160x160 보다 작으면 픽셀이 뭉개지지 않도록 NEAREST(Nearest Neighbor)를 사용하여 그대로 키움.
            # 원본이 너무 크면 LANCZOS로 부드럽게 축소.
            target_size = (160, 160)
            if canvas_w < 160 and canvas_h < 160:
                # 작은 도트 이미지는 선명하게 확대 (Aspect Ratio 유지)
                ratio = min(160 / canvas_w, 160 / canvas_h)
                new_w, new_h = int(canvas_w * ratio), int(canvas_h * ratio)
                base_canvas = base_canvas.resize((new_w, new_h), Image.Resampling.NEAREST)
            else:
                # 큰 이미지는 부드럽게 축소
                base_canvas.thumbnail(target_size, Image.Resampling.LANCZOS)

            # 7. 메모리 바이너리로 변환하여 Signal 쏘기
            buf = io.BytesIO()
            base_canvas.save(buf, format="PNG")
            
            self.preview_ready.emit(buf.getvalue(), self.job_id)
            
        except Exception as e:
            self.preview_failed.emit(f"합성 에러: {str(e)}")

# ==========================================
# 실행 환경에 따른 동적 경로 설정 (빌드 배포용)
# ==========================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(bundled_path):
            return bundled_path
    return os.path.join(BASE_DIR, relative_path)

APPDATA_DIR = os.environ.get('APPDATA', '')
BRIDGE_DATA_DIR = os.path.join(APPDATA_DIR, "Ase-PS-Bridge")
if not os.path.exists(BRIDGE_DATA_DIR):
    try:
        os.makedirs(BRIDGE_DATA_DIR)
    except Exception:
        close_bootloader_on_import_error()
        raise
    
SETTINGS_FILE = os.path.join(BRIDGE_DATA_DIR, "bridge_settings.json")
PRODUCT_NAME = "Photoshop ↔ Aseprite"

WORKSPACE_STYLE = """
QWidget#bridgeWorkspace, QDialog, QScrollArea, QWidget#guidePage {
    background: #181b20; color: #edf0f3;
}
QWidget[uiSurface="true"] { background: #22262d; border: 1px solid #383e48; border-radius: 8px; }
QLabel, QCheckBox, QRadioButton { color: #edf0f3; }
QLabel[uiHeading="true"] { font-weight: 700; }
QLabel[uiMuted="true"] { color: #b9c2cd; }
QLabel#guideStatus { background: #272e37; border: 1px solid #414d5a; border-radius: 6px; padding: 8px; }
QWidget#warningNote { background: #2e2920; border: 1px solid #66543a; border-radius: 6px; }
QLabel#warningHeading { color: #f0cb8b; font-weight: 700; }
QPushButton { color: #eef1f4; background: #2c323b; border: 1px solid #454e5a;
              border-radius: 6px; padding: 4px 8px; }
QPushButton[uiRole="quiet"] { background: transparent; color: #c5ced9; border-color: transparent; }
QPushButton[uiRole="copy"] { background: #333e48; font-weight: 600; }
QPushButton[uiRole="primary"] { background: #176b62; border-color: #248577; font-weight: 700; }
QPushButton:hover:enabled { border-color: #7b8c9e; }
QPushButton:pressed:enabled, QPushButton:checked:enabled { background: #3b4653; }
QPushButton:disabled, QPushButton[uiRole="primary"]:disabled, QPushButton[uiRole="copy"]:disabled {
    background: #262a31; color: #8e9aa8; border-color: #373d46;
}
QPushButton:focus:enabled, QRadioButton[uiSegment="true"]:focus, QLineEdit:focus, QComboBox:focus {
    border-color: #9ac8ef;
}
QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled { color: #8e9aa8; }
QRadioButton[uiSegment="true"] {
    background: #272c33; border: 1px solid #454e5a; border-radius: 6px; padding: 5px 4px;
}
QRadioButton[uiSegment="true"]::indicator { width: 0; height: 0; border: none; background: transparent; }
QRadioButton[uiSegment="true"]:checked { background: #203e49; border-color: #6897ad; color: #e0f5ff; }
QRadioButton[uiSegment="true"]:hover { border-color: #9ac8ef; }
QLineEdit, QComboBox, QComboBox QAbstractItemView {
    background: #22262d; color: #edf0f3; border: 1px solid #454e5a; border-radius: 5px; padding: 4px;
    selection-background-color: #345a70;
}
QTextEdit#diagnosticConsole { background: #1a1e24; color: #ccd6e0; border: 1px solid #383e48;
                             border-radius: 6px; padding: 6px; }
QProgressBar { background: #343a44; border: none; border-radius: 2px; }
QProgressBar::chunk { background: #65ab9e; border-radius: 2px; }
QScrollBar:vertical { background: #1c2026; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #515c68; min-height: 24px; border: 2px solid #1c2026; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #728090; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def workspace_section(parent_layout):
    panel = QWidget()
    panel.setProperty("uiSurface", True)
    panel.setAttribute(Qt.WA_StyledBackground)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(5)
    parent_layout.addWidget(panel)
    return layout

# ==========================================
# 다국어 지원 (Localization)
# ==========================================
LANG = {
    "ko": {
        "title": PRODUCT_NAME,
        "workspace_heading": "작업 공간",
        "clip_empty": "📋 클립보드: 비어있음",
        "clip_ready": "📋 {src} -> {dst} ({count}개 레이어)",
        "align_label": "정렬 기준:",
        "align_center": "Center",
        "align_abs": "Absolute",
        "align_ground_line": "Ground Line",
        "frame_mode_label": "PS→Ase 프레임 모드:",
        "frame_mode_normal": "Normal",
        "frame_mode_folder_frames": "Folder → Frames",
        "frame_mode_layer_frames": "Layer → Frames",
        "frame_mode_hint": "다음 복사부터 적용",
        "clipboard_mode_none": "클립보드: 없음",
        "clipboard_mode_unknown": "클립보드: 알 수 없음",
        "clipboard_mode_current": "클립보드: {mode}",
        "clipboard_mode_mismatch": "클립보드: {clip_mode} · 붙여넣기는 클립보드 모드",
        "btn_ps_copy": "복사",
        "btn_ase_paste": "붙여넣기 · F4",
        "btn_ase_copy": "복사 · F5",
        "btn_ps_paste": "붙여넣기",
        "btn_settings": "⚙️ 설정",
        "btn_clean": "🗑️ 임시파일 정리",
        "msg_started": "양방향 UI 시작됨.",
        "msg_detecting": "경로 자동 탐지 중...",
        "msg_detect_fail": "❌ 필수 실행 파일 경로를 찾지 못했습니다.",
        "msg_detect_success": "✅ 프로그램 설치 경로 자동 탐지 완료!",
        "msg_ase_setup_success": "✅ Aseprite 스크립트/단축키(F4/F5) 맵핑 완료! (단축키를 쓰기 전에 메뉴에서 수동 실행하여 Trust 승인 필요)",
        "msg_ase_setup_fail": "⚠️ Aseprite 단축키 맵핑 실패 (수동 설정 필요).",
        "msg_settings_saved": "✅ 설정이 저장되었습니다.",
        "msg_clean_success": "✅ 임시 폴더(Temp)가 깨끗하게 정리되었습니다! 확보된 용량: {size}MB",
        "msg_clean_fail": "❌ 임시 폴더 정리 실패: {error}",
        "msg_ps_copying": "PS: 레이어 추출 중...",
        "msg_ps_pasting": "PS: 레이어 조립 중...",
        "msg_ase_copying": "Aseprite: 레이어 추출 중...",
        "msg_ase_pasting": "Aseprite: 붙여넣기 중...",
        "msg_ps_success": "✅ 포토샵 작업이 성공적으로 완료되었습니다!",
        "msg_clip_update": "클립보드 갱신: {count}개 레이어 준비 완료.",
        "msg_transforming": "변환 적용 중...",
        "msg_transform_success": "✅ 변환 완료 (H:{h}, V:{v}, 각도:{a})",
        "msg_transform_fail": "❌ 변환 실패: {error}",
        "msg_transform_failed": "변환 실패",
        "msg_generating_preview": "미리보기 생성 중...",
        "msg_preview_failed": "미리보기 생성 실패",
        "err_no_ase_clip": "❌ [Error] 클립보드에 Aseprite 데이터가 없습니다.",
        "msg_ase_trust_err": "💡 힌트: 단축키가 작동하지 않거나 엉뚱한 창이 뜬다면, Aseprite 상단 메뉴 [File] ➔ [Scripts] 에서 직접 스크립트를 한 번씩 클릭하여 'Trust' 권한을 승인해 주세요.",
        "set_title": "⚙️ 브릿지 설정",
        "set_ps_path": "Photoshop 경로:",
        "set_ase_path": "Aseprite 경로:",
        "set_find": "찾기",
        "set_align": "기본 정렬 모드:",
        "set_lang": "언어 (Language):",
        "set_hotkey": "Aseprite 단축키 상태:",
        "set_force_reinstall": "Aseprite 스크립트/단축키 강제 재설치",
        "set_show_ase_setup": "Aseprite 초기 설정 다시 보기",
        "ase_setup_title": "Aseprite 초기 설정",
        "ase_setup_content": "<b>[Aseprite 스크립트 Trust 설정]</b><br><br>"
                             "1. Aseprite를 완전히 종료하세요.<br>"
                             "2. 아래 버튼을 눌러 스크립트/단축키를 설치하세요.<br>"
                             "3. Aseprite를 다시 실행하세요.<br>"
                             "4. 상단 메뉴 <b>File &gt; Scripts &gt; aseprite_paste</b>를 실행하고 Trust를 승인하세요.<br>"
                             "5. <b>File &gt; Scripts &gt; aseprite_copy</b>를 실행하고 Trust를 승인하세요.<br>"
                             "6. 완료했다면 아래 체크박스를 체크하세요.<br><br>"
                             "Trust는 Aseprite 보안 단계이므로 앱이 자동 승인할 수 없습니다.",
        "ase_setup_install": "스크립트/단축키 설치",
        "ase_setup_done": "Aseprite에서 두 스크립트를 실행하고 Trust 승인을 완료했습니다.",
        "ase_setup_complete": "완료",
        "ase_setup_later": "나중에",
        "ase_setup_need_check": "완료 체크박스를 먼저 체크해 주세요.",
        "ase_setup_saved": "Aseprite 초기 설정 완료 상태가 저장되었습니다.",
        "btn_tutorial": "❓ 튜토리얼",
        "tut_title": "📖 프로그램 사용 방법",
        "tut_content": "<b>[ 💡 Photoshop ↔ Aseprite 사용 가이드 ]</b><br><br>"
                       "<b>1. 정방향 (Photoshop ➔ Aseprite)</b><br>"
                       "① Photoshop에서 옮길 레이어(또는 폴더)들을 다중 선택합니다.<br>"
                       "② 앱에서 <b>[복사]</b> 버튼을 누릅니다.<br>"
                       "③ Aseprite 캔버스로 넘어간 뒤, 앱의 <b>[붙여넣기 · F4]</b> 버튼을 누르거나 키보드 <b>F4</b>를 누르면 완벽하게 붙여넣어집니다.<br><br>"
                       "<b>2. 역방향 (Aseprite ➔ Photoshop)</b><br>"
                       "① Aseprite에서 레이어를 선택한 뒤, 앱의 <b>[복사 · F5]</b> 버튼을 누르거나 키보드 <b>F5</b>를 누릅니다.<br>"
                       "② Photoshop 문서로 넘어가서, 앱의 <b>[붙여넣기]</b> 버튼을 누릅니다.<br><br>"
                       "<b>⭐ 정렬 모드 설명 (Alignment)</b><br>"
                       "• <b>Center (중앙 정렬)</b>: 캔버스 크기가 달라도 캐릭터 덩어리를 화면 정중앙에 맞춰서 붙여넣습니다. (기본/권장)<br>"
                       "• <b>Absolute (절대 좌표)</b>: 중앙 보정 없이 원래 있던 좌표 그대로 꽂아넣습니다. (양쪽 캔버스 사이즈가 똑같을 때만 쓰세요)<br><br>"
                       "<b>⚠️ Warnings</b><br>"
                       "• <b>[필수] 최초 1회 스크립트 권한 승인</b><br>"
                       "  Aseprite의 보안 정책상, 단축키(F4/F5)를 누르기 전에 <b>반드시 상단 메뉴 [File] ➔ [Scripts]</b>에서 <b>aseprite_copy</b>와 <b>aseprite_paste</b>를 각각 수동으로 한 번씩 클릭해야 합니다.<br>"
                       "  경고창이 뜨면 <b>'Give full trust to this script(이 스크립트를 전적으로 신뢰함)'</b>에 체크하고 OK를 누르세요. 이후부터는 단축키가 정상 작동합니다.<br><br>"
                       "• <b>Aseprite의 '최근 파일(Recent Files)' 목록이 지저분해질 수 있습니다</b><br>"
                       "Photoshop ↔ Aseprite는 픽셀 정확성과 레이어 보존을 위해 임시 이미지를 생성하여 Aseprite에 불러옵니다.<br>"
                       "이 과정에서 Aseprite의 '최근 파일(Recent Files)' 목록에 임시 파일들이 추가될 수 있습니다. 이는 정상적인 동작이며, 원본 데이터에는 전혀 영향을 주지 않습니다.<br><br>"
                       "<b>✔ 추천 작업 방식</b><br>"
                       "1. 자주 사용하는 작업 파일을 <b>'즐겨찾기(Favorites)'</b>에 추가하세요.<br>"
                       "2. Recent 목록 대신 Favorites를 기준으로 작업하세요.<br>"
                       "3. 필요 시 Recent 목록은 주기적으로 정리해 주세요.<br>"
                       "👉 이 방법을 사용하면 Recent 목록 문제 없이 쾌적하게 작업할 수 있습니다.",
        "tut_dont_show": "다음 실행부터 이 창을 띄우지 않음",
        "btn_flip_h": "↔ 좌우 반전",
        "btn_flip_v": "↕ 상하 반전",
        "btn_rotate": "↻ 90° 회전",
        "btn_undo": "↩ Undo",
        "btn_redo": "↪ Redo"
    },
    "en": {
        "title": PRODUCT_NAME,
        "workspace_heading": "Workspace",
        "clip_empty": "📋 Clipboard: Empty",
        "clip_ready": "📋 {src} -> {dst} ({count} Layers)",
        "align_label": "Alignment:",
        "align_center": "Center",
        "align_abs": "Absolute",
        "align_ground_line": "Ground Line",
        "frame_mode_label": "PS→Ase Frame Mode:",
        "frame_mode_normal": "Normal",
        "frame_mode_folder_frames": "Folder → Frames",
        "frame_mode_layer_frames": "Layer → Frames",
        "frame_mode_hint": "Applies on next copy",
        "clipboard_mode_none": "Clipboard: None",
        "clipboard_mode_unknown": "Clipboard: Unknown",
        "clipboard_mode_current": "Clipboard: {mode}",
        "clipboard_mode_mismatch": "Clipboard: {clip_mode} · Paste uses clipboard mode",
        "btn_ps_copy": "Copy",
        "btn_ase_paste": "Paste · F4",
        "btn_ase_copy": "Copy · F5",
        "btn_ps_paste": "Paste",
        "btn_settings": "⚙️ Settings",
        "btn_clean": "🗑️ Clean Temp",
        "btn_flip_h": "↔ Flip Horizontal",
        "btn_flip_v": "↕ Flip Vertical",
        "btn_rotate": "↻ Rotate 90°",
        "btn_undo": "↩ Undo",
        "btn_redo": "↪ Redo",
        "btn_tutorial": "❓ Tutorial",
        "msg_started": "Bi-directional UI Started.",
        "msg_detecting": "Auto-detecting paths...",
        "msg_detect_fail": "❌ Failed to detect essential executable paths.",
        "msg_detect_success": "✅ Auto-detection of program paths completed!",
        "msg_ase_setup_success": "✅ Aseprite scripts & hotkeys (F4/F5) mapped successfully! (You must run them manually from the menu once to grant Trust permissions)",
        "msg_ase_setup_fail": "⚠️ Failed to map Aseprite hotkeys (Manual setup required).",
        "msg_settings_saved": "✅ Settings saved successfully.",
        "msg_clean_success": "✅ Temp folder cleaned successfully! Freed space: {size}MB",
        "msg_clean_fail": "❌ Failed to clean temp folder: {error}",
        "msg_ps_copying": "PS: Extracting layers...",
        "msg_ps_pasting": "PS: Assembling layers...",
        "msg_ase_copying": "Aseprite: Extracting layers...",
        "msg_ase_pasting": "Aseprite: Pasting layers...",
        "msg_ps_success": "✅ Photoshop task completed successfully!",
        "msg_clip_update": "Clipboard updated: {count} layers ready.",
        "msg_transforming": "Applying transformation...",
        "msg_transform_success": "✅ Transform applied (H:{h}, V:{v}, Angle:{a})",
        "msg_transform_fail": "❌ Transform failed: {error}",
        "msg_transform_failed": "Transform Failed",
        "msg_generating_preview": "Generating Preview...",
        "msg_preview_failed": "Preview Generation Failed",
        "err_no_ase_clip": "❌ [Error] No Aseprite data in clipboard.",
        "msg_ase_trust_err": "💡 Hint: If hotkeys (F4/F5) don't work or open wrong windows, go to Aseprite menu [File] ➔ [Scripts] and click the scripts manually once to grant 'Trust' permissions.",
        "set_title": "⚙️ Bridge Settings",
        "set_ps_path": "Photoshop Path:",
        "set_ase_path": "Aseprite Path:",
        "set_find": "Browse",
        "set_align": "Default Alignment:",
        "set_lang": "Language (언어):",
        "set_hotkey": "Aseprite Hotkey Status:",
        "set_force_reinstall": "Force Reinstall Aseprite Scripts/Hotkeys",
        "set_show_ase_setup": "Show Aseprite First Setup Again",
        "ase_setup_title": "Aseprite First Setup",
        "ase_setup_content": "<b>[Aseprite Script Trust Setup]</b><br><br>"
                             "1. Close Aseprite completely.<br>"
                             "2. Click the button below to install scripts/hotkeys.<br>"
                             "3. Start Aseprite again.<br>"
                             "4. Run <b>File &gt; Scripts &gt; aseprite_paste</b> and approve Trust.<br>"
                             "5. Run <b>File &gt; Scripts &gt; aseprite_copy</b> and approve Trust.<br>"
                             "6. Check the box below when finished.<br><br>"
                             "Trust is an Aseprite security step, so this app cannot approve it automatically.",
        "ase_setup_install": "Install Scripts/Hotkeys",
        "ase_setup_done": "I ran both scripts in Aseprite and approved Trust.",
        "ase_setup_complete": "Complete",
        "ase_setup_later": "Later",
        "ase_setup_need_check": "Please check the completion box first.",
        "ase_setup_saved": "Aseprite first setup completion was saved.",
        "tut_title": "📖 How to use",
        "tut_content": "<b>[ 💡 Photoshop ↔ Aseprite Guide ]</b><br><br>"
                       "<b>1. PS ➔ Aseprite</b><br>"
                       "① Select layers/folders in Photoshop.<br>"
                       "② Click <b>[Copy]</b>.<br>"
                       "③ Go to Aseprite, click <b>[Paste · F4]</b> or press <b>F4</b>.<br><br>"
                       "<b>2. Aseprite ➔ PS</b><br>"
                       "① Select layers in Aseprite, click <b>[Copy · F5]</b> or press <b>F5</b>.<br>"
                       "② Go to Photoshop, click <b>[Paste]</b>.<br><br>"
                       "<b>⭐ Alignment Mode</b><br>"
                       "• <b>Center</b>: Auto-centers the bounding box of copied layers to the target canvas. (Recommended)<br>"
                       "• <b>Absolute</b>: Keeps the exact original X/Y coordinates. (Use only when canvas sizes are identical)<br><br>"
                       "<b>⚠️ Warnings</b><br>"
                       "• <b>[REQUIRED] First-time Script Trust Approval</b><br>"
                       "  Due to Aseprite's security policy, before using hotkeys (F4/F5), you <b>MUST manually click</b> <b>aseprite_copy</b> and <b>aseprite_paste</b> from the top menu: <b>[File] ➔ [Scripts]</b> once.<br>"
                       "  When the warning popup appears, check <b>'Give full trust to this script'</b> and click OK. Hotkeys will work normally afterwards.<br><br>"
                       "• <b>Aseprite 'Recent files' list may get messy</b><br>"
                       "  To ensure perfect pixel transfer, this tool repeatedly opens and closes temporary PNG files in the background, which will leave traces in Aseprite's recent files list.<br><br>"
                       "<b>✔ Recommended workflow</b><br>"
                       "1. Add your working files to <b>'Favorites'</b> in Aseprite.<br>"
                       "2. Always work from the Favorites list instead of Recent files.<br>"
                       "3. Occasionally clean up the Recent files list if needed.<br>"
                       "👉 This workflow avoids the Recent files issue and keeps your workspace stable.",
        "tut_dont_show": "Do not show this window on startup"
    },
    "ja": {
        "title": PRODUCT_NAME,
        "workspace_heading": "ワークスペース",
        "clip_empty": "📋 クリップボード：空",
        "clip_ready": "📋 {src} -> {dst} ({count}個のレイヤー)",
        "align_label": "配置の基準:",
        "align_center": "Center",
        "align_abs": "Absolute",
        "align_ground_line": "Ground Line",
        "frame_mode_label": "PS→Aseフレームモード:",
        "frame_mode_normal": "Normal",
        "frame_mode_folder_frames": "Folder → Frames",
        "frame_mode_layer_frames": "Layer → Frames",
        "frame_mode_hint": "次回コピーから適用",
        "clipboard_mode_none": "クリップボード: なし",
        "clipboard_mode_unknown": "クリップボード: 不明",
        "clipboard_mode_current": "クリップボード: {mode}",
        "clipboard_mode_mismatch": "クリップボード: {clip_mode} · 貼り付けはクリップボードモード",
        "btn_ps_copy": "コピー",
        "btn_ase_paste": "貼り付け · F4",
        "btn_ase_copy": "コピー · F5",
        "btn_ps_paste": "貼り付け",
        "btn_settings": "⚙️ 設定",
        "btn_clean": "🗑️ 一時ファイル整理",
        "msg_started": "双方向UIが起動しました。",
        "msg_detecting": "パスの自動検出中...",
        "msg_detect_fail": "❌ 必須の実行ファイルパスが見つかりませんでした。",
        "msg_detect_success": "✅ プログラムのインストールパス自動検出完了！",
        "msg_ase_setup_success": "✅ Asepriteスクリプト/ショートカット(F4/F5)のマッピング完了！ (ショートカットを使う前に、メニューから1回手動で実行してTrust権限を承認してください)",
        "msg_ase_setup_fail": "⚠️ Asepriteショートカットのマッピング失敗 (手動設定が必要)。",
        "msg_settings_saved": "✅ 設定が保存されました。",
        "msg_clean_success": "✅ 一時フォルダ(Temp)が整理されました！確保された容量: {size}MB",
        "msg_clean_fail": "❌ 一時フォルダの整理失敗: {error}",
        "msg_ps_copying": "PS: レイヤーを抽出中...",
        "msg_ps_pasting": "PS: レイヤーを組み立て中...",
        "msg_ase_copying": "Aseprite: レイヤーを抽出中...",
        "msg_ase_pasting": "Aseprite: ペースト中...",
        "msg_ps_success": "✅ Photoshopの作業が正常に完了しました！",
        "msg_clip_update": "クリップボード更新: {count}個のレイヤーが準備完了。",
        "err_no_ase_clip": "❌ [Error] クリップボードにAsepriteのデータがありません。",
        "msg_ase_trust_err": "💡 ヒント: ショートカットが効かない、または別の機能が開く場合は、Asepriteの上部メニュー [File] ➔ [Scripts] から手動でスクリプトを1回ずつクリックし、「Trust(信頼)」権限を承認してください。",
        "set_title": "⚙️ ブリッジ設定",
        "set_ps_path": "Photoshopのパス:",
        "set_ase_path": "Asepriteのパス:",
        "set_find": "参照",
        "set_align": "デフォルトの配置モード:",
        "set_lang": "言語 (Language):",
        "set_hotkey": "Asepriteのショートカット状態:",
        "set_force_reinstall": "Asepriteスクリプト/ショートカットの強制再インストール",
        "set_show_ase_setup": "Aseprite初期設定をもう一度表示",
        "ase_setup_title": "Aseprite初期設定",
        "ase_setup_content": "<b>[AsepriteスクリプトTrust設定]</b><br><br>"
                             "1. Asepriteを完全に終了してください。<br>"
                             "2. 下のボタンでスクリプト/ショートカットをインストールしてください。<br>"
                             "3. Asepriteを再起動してください。<br>"
                             "4. 上部メニュー <b>File &gt; Scripts &gt; aseprite_paste</b> を実行し、Trustを承認してください。<br>"
                             "5. <b>File &gt; Scripts &gt; aseprite_copy</b> を実行し、Trustを承認してください。<br>"
                             "6. 完了したら下のチェックボックスをオンにしてください。<br><br>"
                             "TrustはAsepriteのセキュリティ手順のため、このアプリでは自動承認できません。",
        "ase_setup_install": "スクリプト/ショートカットをインストール",
        "ase_setup_done": "Asepriteで両方のスクリプトを実行し、Trust承認を完了しました。",
        "ase_setup_complete": "完了",
        "ase_setup_later": "後で",
        "ase_setup_need_check": "先に完了チェックボックスをオンにしてください。",
        "ase_setup_saved": "Aseprite初期設定の完了状態を保存しました。",
        "btn_tutorial": "❓ チュートリアル",
        "tut_title": "📖 プログラムの使い方",
        "tut_content": "<b>[ 💡 Photoshop ↔ Aseprite ガイド ]</b><br><br>"
                       "<b>1. 順方向 (Photoshop ➔ Aseprite)</b><br>"
                       "① Photoshopで転送するレイヤー(またはフォルダ)を複数選択します。<br>"
                       "② アプリの <b>[コピー]</b> ボタンを押します。<br>"
                       "③ Asepriteのキャンバスに移動し、アプリの <b>[貼り付け · F4]</b> ボタンを押すか、キーボードの <b>F4</b> を押すと完璧にペーストされます。<br><br>"
                       "<b>2. 逆方向 (Aseprite ➔ Photoshop)</b><br>"
                       "① Asepriteでレイヤーを選択した後、アプリの <b>[コピー · F5]</b> ボタンを押すか、キーボードの <b>F5</b> を押します。<br>"
                       "② Photoshopのドキュメントに移動し、アプリの <b>[貼り付け]</b> ボタンを押します。<br><br>"
                       "<b>⭐ 配置モードの説明 (Alignment)</b><br>"
                       "• <b>Center (中央揃え)</b>: キャンバスのサイズが異なっても、キャラクター全体を画面の中央に合わせてペーストします。(推奨)<br>"
                       "• <b>Absolute (絶対座標)</b>: 中央補正を行わず、元の座標のままペーストします。(両方のキャンバスサイズが完全に同じ時だけ使用してください)<br><br>"
                       "<b>⚠️ Warnings (注意事項)</b><br>"
                       "• <b>[必須] 初回実行時のスクリプト権限承認</b><br>"
                       "  Asepriteのセキュリティポリシーにより、ショートカット(F4/F5)を使用する前に、<b>必ず上部メニュー [File] ➔ [Scripts]</b> から <b>aseprite_copy</b> と <b>aseprite_paste</b> を手動で1回ずつクリックしてください。<br>"
                       "  警告窓が表示されたら、<b>'Give full trust to this script(このスクリプトを完全に信頼する)'</b> にチェックを入れてOKを押します。以降はショートカットが正常に動作します。<br><br>"
                       "• <b>Asepriteの「最近開いたファイル(Recent files)」リストが汚れる可能性があります</b><br>"
                       "完璧なピクセル転送のため、バックグラウンドで一時的なPNGファイルを開閉します。そのため、Asepriteの「最近開いたファイル(Recent files)」リストに一時ファイルが残る場合があります。これは正常な動作であり、データに影響はありません。<br><br>"
                       "<b>✔ お勧めの作業方法</b><br>"
                       "1. よく使う作業ファイルは<b>「お気に入り(Favorites)」</b>に追加してください。<br>"
                       "2. Recentリストの代わりにお気に入りを基準に作業してください。<br>"
                       "3. 必要に応じてRecentリストを定期的に整理してください。",
        "tut_dont_show": "次回からこのウィンドウを表示しない",
        "btn_flip_h": "↔ 左右反転",
        "btn_flip_v": "↕ 上下反転",
        "btn_rotate": "↻ 90° 回転",
        "btn_undo": "↩ 元に戻す",
        "btn_redo": "↪ やり直し",
        "msg_transforming": "変形を適用中...",
        "msg_transform_success": "✅ 変形完了 (H:{h}, V:{v}, 角度:{a})",
        "msg_transform_fail": "❌ 変形失敗: {error}",
        "msg_transform_failed": "変形失敗",
        "msg_generating_preview": "プレビュー生成中...",
        "msg_preview_failed": "プレビュー生成失敗"
    }
}

# ==========================================
# 설정 관리 (Settings Management)
# ==========================================
LANG["ko"].update({
    "ps_versions": "Photoshop 버전 선택", "ps_warning": "스크립트 경고 설정…",
    "ps_warning_title": "Photoshop 실행 경고",
    "ps_warning_info": "대상: {version}\n{exe}\n\n설정 파일: {config}\nWarnRunningScripts: {state}\n\n외부 JSX 실행 시 확인창이 작업을 대기시킬 수 있습니다. 수동으로 실행을 허용하거나, 이 버전의 경고만 비활성화할 수 있습니다. 경고 비활성화는 신뢰할 수 없는 스크립트에도 영향을 줍니다. 기존 파일은 백업하며 다른 설정은 보존합니다. Photoshop을 종료한 뒤 적용하고 다시 시작하세요.\n\n이 버전의 경고를 비활성화할까요?",
    "ps_warning_done": "설정 적용 완료. Photoshop을 다시 시작하세요.\n백업: {backup}",
    "ps_close_first": "설정 변경 전에 모든 Photoshop 프로세스를 종료하세요.",
    "ps_default_warning": "미설정 (Photoshop 기본값)", "ps_no_backup": "변경 없음 또는 새 파일",
    "ps_script_error": "Photoshop 스크립트 오류: ",
    "ps_timeout_pending": "Photoshop 실행 시작 응답이 없습니다. 스크립트 실행 확인창·다른 모달 창과 선택한 버전을 확인하세요. 경고창 존재는 확인되지 않았습니다. 열린 확인창을 취소/닫은 뒤 재시도하세요.",
    "ps_timeout_running": "Photoshop 스크립트 시작은 확인됐으나 완료 응답이 없습니다. 처리 중이거나 내부 대기/오류 상태일 수 있습니다. 작업이 끝나기 전에 재시도하지 마세요.",
    "ps_timeout_closed": "선택한 Photoshop 프로세스가 실행 중이 아닙니다. 실행 실패 또는 종료 여부를 확인하세요.",
    "ps_timeout_unknown": "Photoshop 응답이 없고 프로세스 상태도 확인할 수 없습니다. 실행 확인창과 프로세스 권한을 확인하세요.",
})
LANG["en"].update({
    "ps_versions": "Photoshop version", "ps_warning": "Script warning settings…",
    "ps_warning_title": "Photoshop script warning",
    "ps_warning_info": "Target: {version}\n{exe}\n\nConfig: {config}\nWarnRunningScripts: {state}\n\nAn external JSX confirmation can block the job. Allow it manually, or disable warnings for this version only. Disabling also affects untrusted scripts. Existing files are backed up; other settings are preserved. Close Photoshop before applying, then restart it.\n\nDisable warnings for this version?",
    "ps_warning_done": "Setting applied. Restart Photoshop.\nBackup: {backup}",
    "ps_close_first": "Close all Photoshop processes before changing this setting.",
    "ps_default_warning": "Not set (Photoshop default)", "ps_no_backup": "Unchanged or new file",
    "ps_script_error": "Photoshop script error: ",
    "ps_timeout_pending": "No Photoshop script-start response. Check script confirmations, other modal dialogs and the selected version. A warning dialog has not been verified. Cancel/close pending confirmations before retrying.",
    "ps_timeout_running": "Script start confirmed, but no completion response. Photoshop may still be processing or blocked internally. Do not retry until the operation ends.",
    "ps_timeout_closed": "The selected Photoshop process is not running. Check launch failure or application exit.",
    "ps_timeout_unknown": "No Photoshop response; process status could not be verified. Check confirmation dialogs and process permissions.",
})
LANG["ja"].update({
    "ps_versions": "Photoshop バージョン", "ps_warning": "スクリプト警告設定…",
    "ps_warning_title": "Photoshop 実行警告",
    "ps_warning_info": "対象: {version}\n{exe}\n\n設定: {config}\nWarnRunningScripts: {state}\n\n外部 JSX の確認画面で処理が待機することがあります。手動で許可するか、このバージョンのみ警告を無効化できます。信頼できないスクリプトにも影響します。既存ファイルはバックアップし、他の設定は保持します。適用前に Photoshop を終了し、適用後に再起動してください。\n\nこのバージョンの警告を無効化しますか？",
    "ps_warning_done": "設定を適用しました。Photoshop を再起動してください。\nバックアップ: {backup}",
    "ps_close_first": "設定変更前にすべての Photoshop プロセスを終了してください。",
    "ps_default_warning": "未設定 (Photoshop の既定値)", "ps_no_backup": "変更なし、または新規ファイル",
    "ps_script_error": "Photoshop スクリプトエラー: ",
    "ps_timeout_pending": "スクリプト開始応答がありません。実行確認画面、他のダイアログ、対象バージョンを確認してください。警告画面の存在は未確認です。再試行前に保留中の確認をキャンセルしてください。",
    "ps_timeout_running": "開始は確認できましたが完了応答がありません。処理中または内部待機の可能性があります。終了前に再試行しないでください。",
    "ps_timeout_closed": "対象の Photoshop プロセスがありません。起動失敗または終了を確認してください。",
    "ps_timeout_unknown": "応答がなくプロセス状態も確認できません。実行確認画面と権限を確認してください。",
})

for _language, _labels in {
    "ko": ("DEBUG", "로그 복사", "로그 폴더 열기", "화면 로그만 지우기", "작업 진행 중: {reason}", "작업이 정리 중입니다. 잠시 후 다시 시도하세요."),
    "en": ("DEBUG", "Copy logs", "Open log folder", "Clear displayed logs only", "Job blocked: {reason}", "A job is still being cleaned up. Retry shortly."),
    "ja": ("DEBUG", "ログをコピー", "ログフォルダー", "表示ログのみ消去", "処理中: {reason}", "処理の終了待ちです。少し待って再試行してください。"),
}.items():
    LANG[_language].update(zip(("diag_debug", "diag_copy", "diag_folder", "diag_clear", "diag_blocked", "diag_wait"), _labels))

LANG["ko"]["diag_cancelled"] = "Bridge 작업을 취소했습니다. Photoshop 프로세스는 종료하지 않았습니다."
LANG["en"]["diag_cancelled"] = "Bridge operation cancelled; Photoshop was not terminated."
LANG["ja"]["diag_cancelled"] = "Bridge の処理を中止しました。Photoshop は終了していません。"

for _language, _labels in {
    "ko": ("시작 중...", "설정 불러오는 중...", "환경 확인 중...", "프로그램 준비 중...", "프로그램 초기화에 실패했습니다."),
    "en": ("Starting...", "Loading settings...", "Checking environment...", "Preparing application...", "Application initialization failed."),
    "ja": ("起動中...", "設定を読み込み中...", "環境を確認中...", "アプリを準備中...", "アプリの初期化に失敗しました。"),
}.items():
    LANG[_language].update(zip(("startup_starting", "startup_settings", "startup_environment", "startup_ui", "startup_failed"), _labels))

for _language, _messages in {
    "ko": ("새 복사 진행 중 · 이전 클립보드 미리보기", "Photoshop 복사 진행 중", "새 복사 실패 · 이전 클립보드 유지", "복사 실패 · 새 미리보기 없음", "복사 완료 · 새 클립보드/미리보기 대기"),
    "en": ("Copying · preview of previous clipboard", "Photoshop copy in progress", "Copy failed · previous clipboard retained", "Copy failed · no new preview", "Copy complete · awaiting new clipboard/preview"),
    "ja": ("コピー中 · 前のクリップボードを表示", "Photoshop コピー中", "コピー失敗 · 前のデータを保持", "コピー失敗 · 新しいプレビューなし", "コピー完了 · 新しいデータの反映待ち"),
}.items():
    LANG[_language].update(zip(("copy_previous_preview", "copy_pending", "copy_failed_retained", "copy_failed_empty", "copy_preview_pending"), _messages))


for _language, _guide in {
    "ko": {
        "guide_title": "초기 설정 가이드", "guide_reopen": "초기 설정 가이드 다시 보기",
        "guide_steps": ("1. Photoshop 연결", "2. Photoshop 실행 경고", "3. Aseprite 권한", "4. 확인 및 마침"),
        "guide_ps_intro": "사용할 Photoshop 버전과 실행 파일 경로가 맞으면 ‘이 버전으로 계속’을 누르세요. 확인만 할 때는 종료하지 않아도 됩니다. 다른 버전으로 전환하기 전에는 Photoshop을 종료하는 편이 안전합니다.",
        "guide_ps_edit": "버전 선택 / 경로 변경…",
        "guide_ps_valid": "선택한 Photoshop: {product} ({version})",
        "guide_ps_missing": "Photoshop 연결 미확인: EXE 경로와 버전을 연결 설정에서 확인하세요.",
        "guide_warning_intro": "반복 복사·붙여넣기 중 매번 JSX 실행을 승인하지 않아도 됩니다. 원할 때만 선택한 Photoshop 버전의 실행 경고를 끌 수 있습니다.",
        "guide_warning_caution": "변경 전 확인",
        "guide_warning_optional": "이 설정은 선택한 버전의 모든 외부 JSX에 적용됩니다. 경고 유지를 권장하며, 앱은 실제 승인 여부를 확인할 수 없습니다. 변경하려면 Photoshop을 모두 종료하고 대상 확인 후 동의하세요. 기존 파일은 백업되며, 적용 후 Photoshop을 다시 시작해야 합니다.",
        "guide_warning_edit": "실행 경고 변경 검토…",
        "guide_warning_keep": "경고 설정: 기본값 또는 경고 유지 · 실제 승인 여부 미확인",
        "guide_warning_disabled": "경고 설정: WarnRunningScripts 0 확인 · 적용 후 재시작 필요 · 실제 승인 여부 미확인",
        "guide_warning_unknown": "경고 설정 미확인: 선택 버전의 사용자 설정 폴더를 확인하세요.",
        "guide_ase_intro": "1. Aseprite를 종료하고 스크립트와 단축키를 설치한 뒤 다시 여세요.\n2. File > Scripts에서 aseprite_paste와 aseprite_copy를 각각 실행해 Trust를 직접 승인하세요.\n3. 테스트 문서에서 F5로 복사하고 유효한 Photoshop 복사 데이터로 F4 붙여넣기를 확인하세요. 파일 설치만으로 권한이나 키 동작이 확인되지는 않습니다.",
        "guide_ase_open": "Aseprite 설치 / Trust 안내…", "guide_hotkeys_check": "F4 / F5 동작을 직접 확인했습니다.",
        "guide_files_ok": "Aseprite 스크립트: 설치본이 bundled 파일과 일치",
        "guide_files_pending": "Aseprite 스크립트: 설치 또는 갱신 확인 필요",
        "guide_keys_ok": "단축키 설정 파일: F4 Paste / F5 Copy 등록 확인",
        "guide_keys_pending": "단축키 설정 파일: 미확인 또는 재설치 필요",
        "guide_trust_yes": "Trust: 기존 사용자 완료 확인 기록 있음 (앱에서 직접 검증하지 않음)",
        "guide_trust_no": "Trust: 사용자 완료 확인 없음 · Aseprite에서 직접 승인 필요",
        "guide_keys_tested": "단축키 실제 동작: 사용자 확인 기록 있음",
        "guide_keys_untested": "단축키 실제 동작: 미확인",
        "guide_summary_intro": "아래 상태를 확인하세요. 가이드를 닫는 것은 외부 프로그램의 권한 승인이나 연결 테스트 완료를 의미하지 않습니다. 미확인 항목은 나중에 설정에서 다시 확인할 수 있습니다.",
        "guide_dont_show": "다음 실행 시 초기 설정 가이드를 자동으로 표시하지 않음",
        "guide_back": "이전", "guide_next": "다음", "guide_finish": "가이드 닫기", "guide_later": "나중에 설정",
        "guide_tutorial": "프로그램 사용 방법 열기", "guide_close": "확인",
        "guide_ps_continue": "이 버전으로 계속",
        "guide_ps_running": "선택한 버전 실행 중",
        "guide_ps_closed": "선택한 버전 종료됨",
        "guide_ps_other": "다른 Photoshop이 실행 중입니다. 작업 전에 다른 버전을 종료하세요.",
        "guide_ps_runtime_unknown": "실행 상태 미확인",
        "guide_warning_continue": "경고 설정을 바꾸지 않고 계속",
        "diag_toggle": "진단",
        "preview_empty": "복사된 레이어 없음",
        "tut_content": "<b>Photoshop → Aseprite</b><br>프레임 모드와 Photoshop 레이어/폴더를 선택한 뒤 이 방향의 복사를 누릅니다. Aseprite 대상 문서에서 붙여넣기 · F4를 실행합니다.<br><br>"
                       "<b>Aseprite → Photoshop</b><br>Aseprite에서 레이어를 선택하고 이 방향의 복사 · F5를 실행한 뒤, Photoshop 대상 문서에서 붙여넣기를 누릅니다.<br><br>"
                       "<b>Copy Mode (다음 Photoshop 복사부터 적용)</b><br>Normal: 기존 레이어/폴더 구조로 붙여넣기.<br>Folder → Frames: 선택 폴더별로 연속 프레임에 배치합니다. 선택한 하위 폴더도 개별 프레임이 됩니다. 같은 순번의 레이어는 선택 Aseprite 레이어 포함 아래쪽의 같은 row를 재사용합니다.<br>Layer → Frames: 선택한 픽셀 레이어 하나당 한 프레임, 선택 Aseprite 레이어 한 row에 순차 배치합니다. 폴더 선택은 지원하지 않습니다.<br>프레임 순서는 Photoshop 패널 위→아래이며 Aseprite 현재 프레임부터 시작합니다. 현재 클립보드 모드 표시는 실제 복사된 모드입니다. 라디오를 바꿔도 기존 복사 데이터의 모드는 바뀌지 않습니다.<br><br>"
                       "<b>Alignment (붙여넣기 시 적용)</b><br>Ground Line: 기본값. Aseprite에서 X축 중앙, 이미지 바닥을 캔버스 중앙 가로선 바로 위에 맞춥니다.<br>Center: 이미지 덩어리를 캔버스 중앙에 배치합니다.<br>Absolute: 원본 좌표를 유지합니다.<br>복사 후에도 정렬을 변경할 수 있습니다. Ground Line의 바닥 정렬은 Aseprite Paste용입니다.<br><br>"
                       "<b>Preview / 변환</b><br>여러 프레임은 첫 프레임만 미리 봅니다. 좌우/상하 반전, 90° 회전, Undo/Redo는 복사한 작업 데이터와 Preview에 반영됩니다.<br><br>"
                       "<b>작업상 주의</b><br>대상 문서와 프레임/레이어를 확인하세요. Aseprite Recent Files에 임시 이미지가 추가될 수 있습니다. 작업 파일은 Favorites로 관리할 수 있습니다. 환경 및 권한 준비는 Settings의 초기 설정 가이드에서 확인하세요.",
    },
    "en": {
        "guide_title": "Initial Setup Guide", "guide_reopen": "Reopen Initial Setup Guide",
        "guide_steps": ("1. Photoshop connection", "2. Photoshop script warning", "3. Aseprite permissions", "4. Review and close"),
        "guide_ps_intro": "If the Photoshop version and EXE path match the editor you want to use, select Continue with this version. Photoshop can stay open while you review. Close Photoshop before switching versions to avoid a target mismatch.",
        "guide_ps_edit": "Choose version / change path…",
        "guide_ps_valid": "Selected Photoshop: {product} ({version})",
        "guide_ps_missing": "Photoshop connection unverified: check the EXE path and version in connection settings.",
        "guide_warning_intro": "Skip the repeated JSX confirmation during Copy and Paste. You can turn off script warnings for the selected Photoshop version if you choose.",
        "guide_warning_caution": "Before changing warnings",
        "guide_warning_optional": "This affects all external JSX in the selected version. Keeping warnings is recommended; the app cannot verify individual approvals. To apply, close Photoshop, review the target and explicitly confirm. Existing files are backed up. Restart Photoshop afterward.",
        "guide_warning_edit": "Review script warning change…",
        "guide_warning_keep": "Warning setting: default or warnings kept · actual approval unverified",
        "guide_warning_disabled": "Warning setting: WarnRunningScripts 0 found · restart after applying · actual approval unverified",
        "guide_warning_unknown": "Warning setting unverified: check the selected version's preferences folder.",
        "guide_ase_intro": "1. Close Aseprite, install the scripts and shortcuts, then reopen it.\n2. Run aseprite_paste and aseprite_copy separately from File > Scripts and approve Trust yourself.\n3. In a test document, try F5 Copy and F4 Paste with valid Photoshop copy data. Installed files do not prove Trust or shortcut operation.",
        "guide_ase_open": "Aseprite installation / Trust guide…", "guide_hotkeys_check": "I tested F4 and F5.",
        "guide_files_ok": "Aseprite scripts: installed files match the bundled files",
        "guide_files_pending": "Aseprite scripts: installation or update needs checking",
        "guide_keys_ok": "Hotkey file: F4 Paste / F5 Copy registered",
        "guide_keys_pending": "Hotkey file: unverified or reinstall required",
        "guide_trust_yes": "Trust: user completion recorded (not independently verified by Bridge)",
        "guide_trust_no": "Trust: no user completion recorded · approve manually in Aseprite",
        "guide_keys_tested": "Actual hotkey operation: user confirmation recorded",
        "guide_keys_untested": "Actual hotkey operation: unverified",
        "guide_summary_intro": "Review the status below. Closing this guide does not approve external permissions or certify a connection test. You can revisit unchecked items later in Settings.",
        "guide_dont_show": "Don't show this guide on startup",
        "guide_back": "Back", "guide_next": "Next", "guide_finish": "Close guide", "guide_later": "Set up later",
        "guide_tutorial": "Open How to Use", "guide_close": "OK",
        "guide_ps_continue": "Continue with this version",
        "guide_ps_running": "Selected version running",
        "guide_ps_closed": "Selected version closed",
        "guide_ps_other": "A different Photoshop is running. Close the other version before transferring.",
        "guide_ps_runtime_unknown": "Running status unverified",
        "guide_warning_continue": "Continue without changing warnings",
        "diag_toggle": "Diagnostics",
        "preview_empty": "No copied layers",
        "tut_content": "<b>Photoshop → Aseprite</b><br>Choose the frame mode and select Photoshop layers/folders, then click Copy in this row. Switch to the target Aseprite canvas and use Paste · F4.<br><br>"
                       "<b>Aseprite → Photoshop</b><br>Select layers in Aseprite and use Copy · F5 in this row, then click Paste in the target Photoshop document.<br><br>"
                       "<b>Copy Mode (applies to the next Photoshop copy)</b><br>Normal: paste the existing layer/folder structure.<br>Folder → Frames: paste folders into consecutive frames, including directly selected nested folders. Matching layer positions reuse the same rows, starting at the active Aseprite layer and continuing downward.<br>Layer → Frames: each selected pixel layer becomes a frame on one active Aseprite layer row. Selecting groups is not supported.<br>Frames follow Photoshop panel top-to-bottom order and start at the active Aseprite frame. The clipboard mode shows how the data was copied; changing a radio does not reinterpret existing data.<br><br>"
                       "<b>Alignment (applies at paste time)</b><br>Ground Line: default. In Aseprite, center horizontally and put the image bottom just above the canvas horizontal center line.<br>Center: center the content bounding box on the canvas.<br>Absolute: keep original coordinates.<br>Alignment can change after copying. Ground Line bottom alignment is for Aseprite Paste.<br><br>"
                       "<b>Preview / transforms</b><br>Multi-frame data previews the first frame only. Flip Horizontal/Vertical, Rotate 90°, Undo and Redo update copied job data and Preview.<br><br>"
                       "<b>Working notes</b><br>Check the target document, frame and layer. Temporary images may appear in Aseprite Recent Files; Favorites can help organize your work files. For environment and permissions, open the Initial Setup Guide in Settings.",
    },
    "ja": {
        "guide_title": "初期設定ガイド", "guide_reopen": "初期設定ガイドを再表示",
        "guide_steps": ("1. Photoshop の接続", "2. Photoshop の実行警告", "3. Aseprite の権限", "4. 確認と終了"),
        "guide_ps_intro": "使用する Photoshop のバージョンと EXE パスが正しければ「このバージョンで続ける」を選びます。確認だけなら終了は不要です。別のバージョンへ切り替える前に Photoshop を終了してください。",
        "guide_ps_edit": "バージョン選択 / パス変更…",
        "guide_ps_valid": "選択中の Photoshop: {product} ({version})",
        "guide_ps_missing": "Photoshop の接続は未確認です。接続設定で EXE パスとバージョンを確認してください。",
        "guide_warning_intro": "コピーや貼り付けのたびに JSX の実行を承認する手間を省けます。希望する場合のみ、選択した Photoshop の警告を無効にできます。",
        "guide_warning_caution": "変更前の確認",
        "guide_warning_optional": "選択したバージョンのすべての外部 JSX に影響します。警告の維持を推奨します。アプリは個別の承認を確認できません。変更する場合は Photoshop をすべて終了し、対象の確認後に同意してください。既存ファイルをバックアップします。適用後は Photoshop を再起動してください。",
        "guide_warning_edit": "実行警告の変更を確認…",
        "guide_warning_keep": "警告設定: 既定値または警告を維持 · 実際の承認は未確認",
        "guide_warning_disabled": "警告設定: WarnRunningScripts 0 を確認 · 適用後に再起動が必要 · 実際の承認は未確認",
        "guide_warning_unknown": "警告設定は未確認です。選択したバージョンの設定フォルダーを確認してください。",
        "guide_ase_intro": "1. Aseprite を終了し、スクリプトとキーをインストールして再起動します。\n2. File > Scripts から aseprite_paste と aseprite_copy を個別に実行し、自分で Trust を承認します。\n3. テスト文書で F5 コピーと、有効な Photoshop データで F4 貼り付けを確認します。インストールだけでは権限やキー動作は確認できません。",
        "guide_ase_open": "Aseprite インストール / Trust 案内…", "guide_hotkeys_check": "F4 / F5 の動作を確認しました。",
        "guide_files_ok": "Aseprite スクリプト: インストール済みファイルが同梱ファイルと一致",
        "guide_files_pending": "Aseprite スクリプト: インストールまたは更新の確認が必要",
        "guide_keys_ok": "キー設定ファイル: F4 貼り付け / F5 コピーの登録を確認",
        "guide_keys_pending": "キー設定ファイル: 未確認または再インストールが必要",
        "guide_trust_yes": "Trust: ユーザーの完了記録あり (Bridge による直接検証ではありません)",
        "guide_trust_no": "Trust: ユーザーの完了記録なし · Aseprite で手動承認が必要",
        "guide_keys_tested": "実際のキー動作: ユーザーの確認記録あり",
        "guide_keys_untested": "実際のキー動作: 未確認",
        "guide_summary_intro": "以下の状態を確認してください。ガイドを閉じても外部権限の承認や接続テストの完了にはなりません。未確認の項目は後で設定から確認できます。",
        "guide_dont_show": "次回起動時に初期設定ガイドを自動表示しない",
        "guide_back": "戻る", "guide_next": "次へ", "guide_finish": "ガイドを閉じる", "guide_later": "後で設定",
        "guide_tutorial": "使い方を開く", "guide_close": "確認",
        "guide_ps_continue": "このバージョンで続ける",
        "guide_ps_running": "選択したバージョンは実行中",
        "guide_ps_closed": "選択したバージョンは停止中",
        "guide_ps_other": "別の Photoshop が実行中です。作業前に終了してください。",
        "guide_ps_runtime_unknown": "実行状態は未確認",
        "guide_warning_continue": "警告を変更せず続ける",
        "diag_toggle": "診断",
        "preview_empty": "コピーされたレイヤーなし",
        "tut_content": "<b>Photoshop → Aseprite</b><br>フレームモードと Photoshop のレイヤー/フォルダーを選択し、この行のコピーを押します。Aseprite の対象キャンバスで貼り付け · F4 を実行します。<br><br>"
                       "<b>Aseprite → Photoshop</b><br>Aseprite でレイヤーを選択し、この行のコピー · F5 を実行してから、対象の Photoshop 文書で貼り付けを押します。<br><br>"
                       "<b>Copy Mode (次の Photoshop コピーから適用)</b><br>Normal: 既存のレイヤー/フォルダー構造で貼り付けます。<br>Folder → Frames: 選択したフォルダーごとに連続フレームへ配置します。直接選択した下位フォルダーにも対応します。同じ順番のレイヤーは、選択した Aseprite レイヤーを含む下方向の同じ行を再利用します。<br>Layer → Frames: 選択したピクセルレイヤーごとに一つのフレームへ配置し、選択中の Aseprite レイヤー一行を使います。グループの選択には対応しません。<br>フレーム順は Photoshop パネルの上から下で、Aseprite の現在のフレームから始まります。クリップボードのモードは実際にコピーした方式です。ラジオを変更しても既存データのモードは変わりません。<br><br>"
                       "<b>Alignment (貼り付け時に適用)</b><br>Ground Line: 既定値。Aseprite で横方向を中央にし、画像の底をキャンバスの中央横線のすぐ上に合わせます。<br>Center: 画像全体の範囲をキャンバス中央に配置します。<br>Absolute: 元の座標を維持します。<br>コピー後でも変更できます。Ground Line の接地配置は Aseprite Paste 用です。<br><br>"
                       "<b>Preview / 変形</b><br>複数フレームでは最初のフレームだけ表示します。左右/上下反転、90° 回転、Undo/Redo はコピーした作業データと Preview に反映されます。<br><br>"
                       "<b>作業上の注意</b><br>対象文書とフレーム/レイヤーを確認してください。Aseprite Recent Files に一時画像が追加されることがあります。作業ファイルの管理には Favorites を利用できます。環境と権限の準備は設定の初期設定ガイドで確認してください。",
    },
}.items():
    LANG[_language].update(_guide)


def diagnostic_event(job_id, component, state, **details):
    return {"timestamp": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "job_id": job_id or "-", "component": component, "state": state, "details": details}


def redact_diagnostic(value):
    if isinstance(value, dict):
        return {str(k): redact_diagnostic(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_diagnostic(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"[A-Za-z]:[\\/][^\r\n\"<>]*", "<local-path>", value)
        value = re.sub(r"\\\\[^\r\n\"<>]+", "<network-path>", value)
        value = re.sub(r"[^\s\"<>]+\.(?:psd|psb)\b", "<document>", value, flags=re.I)
    return value


class DiagnosticLog:
    def __init__(self, directory):
        self.directory = directory
        self.listener = None
        self.handler = None
        self.logger = logging.Logger("bridge-" + uuid.uuid4().hex)
        self.logger.addHandler(logging.NullHandler())
        try:
            os.makedirs(directory, exist_ok=True)
            class SafeFileHandler(logging.handlers.RotatingFileHandler):
                def handleError(self, record):
                    pass
            self.handler = SafeFileHandler(os.path.join(directory, "bridge.log"),
                                           maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
            self.handler.setFormatter(logging.Formatter("%(message)s"))
            self.queue = queue.SimpleQueue()
            self.logger.addHandler(logging.handlers.QueueHandler(self.queue))
            self.listener = logging.handlers.QueueListener(self.queue, self.handler)
            self.listener.start()
        except Exception:
            if self.handler:
                self.handler.close()

    def write(self, event):
        try:
            self.logger.info(json.dumps(redact_diagnostic(event), ensure_ascii=False))
        except Exception:
            pass

    def close(self):
        try:
            if self.listener:
                self.listener.stop()
            if self.handler:
                self.handler.close()
        except Exception:
            pass


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {} # 빈 딕셔너리 반환

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"설정 저장 실패: {e}")

# ==========================================
# 설치 경로 탐색 및 환경 구성 함수들
# ==========================================
def _photoshop_query(command):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + command],
        capture_output=True, encoding="utf-8-sig", errors="strict", timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def photoshop_exe_info(path):
    if not path or not os.path.isfile(path) or os.path.basename(path).lower() != "photoshop.exe":
        raise ValueError("Photoshop.exe path is invalid: " + str(path))
    literal = os.path.abspath(path).replace("'", "''")
    info = _photoshop_query(
        f"(Get-Item -LiteralPath '{literal}').VersionInfo | "
        "Select-Object ProductName,FileVersion,FileMajorPart | ConvertTo-Json -Compress")
    if not info or "photoshop" not in (info.get("ProductName") or "").lower() or not info.get("FileMajorPart"):
        raise ValueError("Cannot verify Photoshop executable version: " + path)
    return {"path": os.path.abspath(path), "version": info["FileVersion"],
            "major": int(info["FileMajorPart"]), "product": info["ProductName"]}


def running_photoshops():
    items = _photoshop_query(
        "@(Get-Process -Name Photoshop -ErrorAction SilentlyContinue | "
        "Select-Object Id,Path) | ConvertTo-Json -Compress") or []
    if isinstance(items, dict):
        items = [items]
    if any(not item.get("Path") for item in items):
        raise RuntimeError("Cannot read a running Photoshop path (check process permissions).")
    return items


def installed_photoshops(extra_path=""):
    paths = {extra_path} if extra_path else set()
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
                                    0, winreg.KEY_READ | view) as key:
                    paths.add(winreg.QueryValueEx(key, "")[0].strip('"'))
            except OSError:
                pass
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Adobe\Photoshop", 0, winreg.KEY_READ | view) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, i)) as version_key:
                                paths.add(os.path.join(winreg.QueryValueEx(version_key, "ApplicationPath")[0], "Photoshop.exe"))
                        except OSError:
                            pass
            except OSError:
                pass
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        adobe = os.path.join(base, "Adobe") if base else ""
        if os.path.isdir(adobe):
            for name in os.listdir(adobe):
                if "photoshop" in name.lower():
                    paths.add(os.path.join(adobe, name, "Photoshop.exe"))
    result = {}
    for path in sorted(paths):
        if os.path.isfile(path):
            info = photoshop_exe_info(path)
            result[os.path.normcase(info["path"])] = info
    return list(result.values())


def resolve_photoshop_target(configured, running, installed):
    # Never substitute a different running version for an explicitly saved path.
    if configured:
        target = photoshop_exe_info(configured)
    elif len(running) == 1:
        target = photoshop_exe_info(running[0]["Path"])
    elif not running and len(installed) == 1:
        target = installed[0]
    else:
        raise ValueError("Select a Photoshop.exe version in Settings before sending a script.")
    expected = os.path.normcase(target["path"])
    if any(os.path.normcase(os.path.abspath(p["Path"])) != expected for p in running):
        raise ValueError("A different Photoshop version is running. Select its executable in Settings, "
                         "or close other Photoshop versions before retrying. Target: " + target["path"])
    return target


def photoshop_config_path(info, appdata=None):
    # A verified EXE's product name is authoritative, not its install folder.
    known_year = {20: 2019, 21: 2020, 22: 2021, 23: 2022, 24: 2023,
                  25: 2024, 26: 2025, 27: 2026}.get(info["major"])
    match = re.fullmatch(r"Adobe Photoshop (20\d{2})", info["product"].strip(), re.IGNORECASE)
    year = int(match.group(1)) if match else known_year
    if known_year and year != known_year:
        raise ValueError("Photoshop product name and executable version disagree.")
    if not year or "beta" in (info["path"] + info["product"]).lower():
        raise ValueError("Cannot identify this Photoshop preferences version safely.")
    adobe = os.path.join(appdata or os.environ["APPDATA"], "Adobe")
    matches = []
    if os.path.isdir(adobe):
        name = f"Adobe Photoshop {year}"
        for entry in os.scandir(adobe):
            if entry.is_dir() and entry.name == name:
                settings = os.path.join(entry.path, name + " Settings")
                if os.path.isdir(settings):
                    matches.append(os.path.join(settings, "PSUserConfig.txt"))
    if len(matches) != 1:
        raise ValueError("Open this Photoshop version once first; its preferences folder was not found uniquely.")
    return matches[0]


def photoshop_warning_config(path):
    raw = b""
    if os.path.isfile(path):
        with open(path, "rb") as stream:
            raw = stream.read()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = raw.decode(encoding)
    values = re.findall(r"(?mi)^\s*WarnRunningScripts\s+([01])\s*(?:#.*)?$", text)
    return raw, encoding, text, values


def disable_photoshop_warning(path):
    # Called only after explicit consent, with Photoshop closed. Preserve all other bytes.
    raw, encoding, text, values = photoshop_warning_config(path)
    option_count = len(re.findall(r"(?mi)^\s*WarnRunningScripts\b", text))
    if option_count > 1:
        raise ValueError("Duplicate WarnRunningScripts options; resolve these manually first.")
    if values == ["0"]:
        return None
    if option_count and not values:
        raise ValueError("Unrecognized WarnRunningScripts option; edit manually.")
    backup = None
    if os.path.exists(path):
        backup = path + "." + uuid.uuid4().hex + ".bak"
        shutil.copy2(path, backup)
    if values:
        # Change only the option's value; preserve comments, encoding and line endings.
        text = re.sub(r"(?mi)^(\s*WarnRunningScripts\s+)1\b", r"\g<1>0", text)
        data = text.encode(encoding)
        if encoding == "utf-16":
            data = raw[:2] + text.encode("utf-16-le" if raw.startswith(b"\xff\xfe") else "utf-16-be")
        if encoding == "utf-8-sig" and not raw.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
    else:
        suffix = ("" if not text or text.endswith(("\n", "\r")) else "\r\n") + "WarnRunningScripts 0\r\n"
        encoded = suffix.encode(encoding)
        if encoding == "utf-16":
            encoded = suffix.encode("utf-16-le" if raw.startswith(b"\xff\xfe") else "utf-16-be")
        elif encoding == "utf-8-sig":
            encoded = suffix.encode("utf-8")
        data = raw + encoded
    temporary = path + "." + uuid.uuid4().hex + ".tmp"
    try:
        with open(temporary, "xb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return backup


def configure_photoshop_warning(parent, lang, settings, target_path):
    try:
        info = photoshop_exe_info(target_path())
        path = photoshop_config_path(info)
        _, _, _, values = photoshop_warning_config(path)
        prompt = lang["ps_warning_info"].format(
            version=info["version"], exe=info["path"], config=path,
            state=", ".join(values) if values else lang["ps_default_warning"])
        answer = QMessageBox.question(parent, lang["ps_warning_title"], prompt,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        if running_photoshops():
            QMessageBox.warning(parent, lang["ps_warning_title"], lang["ps_close_first"])
            return
        # Revalidate the selected version/path after consent; never touch another version.
        if photoshop_config_path(photoshop_exe_info(target_path())) != path:
            raise ValueError("Photoshop preferences target changed.")
        backup = disable_photoshop_warning(path)
        settings["photoshop_warning_choice"] = {"exe": info["path"], "disabled": True}
        save_settings(settings)
        QMessageBox.information(parent, lang["ps_warning_title"],
                                lang["ps_warning_done"].format(backup=backup or lang["ps_no_backup"]))
    except Exception as e:
        QMessageBox.warning(parent, lang["ps_warning_title"], str(e))


def find_photoshop_exe() -> str:
    try:
        running = running_photoshops()
        installed = installed_photoshops()
        return resolve_photoshop_target("", running, installed)["path"]
    except Exception:
        return ""


def find_aseprite_exe() -> str:
    common_paths = [
        r"C:\Program Files (x86)\Steam\steamapps\common\Aseprite\aseprite.exe",
        r"C:\Program Files\Steam\steamapps\common\Aseprite\aseprite.exe",
        r"C:\Program Files\Aseprite\aseprite.exe",
        r"C:\Program Files (x86)\Aseprite\aseprite.exe"
    ]
    for path in common_paths:
        if os.path.exists(path): return path
    which_path = shutil.which("aseprite")
    if which_path and os.path.exists(which_path): return os.path.normpath(which_path)
    return ""

def setup_aseprite_environment(orig_paste_lua: str, orig_copy_lua: str) -> (bool, str):
    appdata = os.environ.get('APPDATA')
    if not appdata: return False, "APPDATA environment variable not found."

    ase_dir = os.path.join(appdata, "Aseprite")
    scripts_dir = os.path.join(ase_dir, "scripts")
    if not os.path.exists(scripts_dir): os.makedirs(scripts_dir)

    target_paste_lua = os.path.join(scripts_dir, "aseprite_paste.lua")
    target_copy_lua = os.path.join(scripts_dir, "aseprite_copy.lua")
    
    import filecmp
    try:
        if not os.path.exists(target_paste_lua) or not filecmp.cmp(orig_paste_lua, target_paste_lua, shallow=False):
            shutil.copy2(orig_paste_lua, target_paste_lua)
        if not os.path.exists(target_copy_lua) or not filecmp.cmp(orig_copy_lua, target_copy_lua, shallow=False):
            shutil.copy2(orig_copy_lua, target_copy_lua)
    except Exception as e:
        return False, f"Script copy failed: {e}"

    keys_file = os.path.join(ase_dir, "user.aseprite-keys")
    if not os.path.exists(keys_file):
        root = ET.Element("keyboard", {"version": "1"})
        commands = ET.SubElement(root, "commands")
        tree = ET.ElementTree(root)
    else:
        try:
            tree = ET.parse(keys_file)
            root = tree.getroot()
            commands = root.find("commands")
            if commands is None: commands = ET.SubElement(root, "commands")
        except Exception as e:
            return False, f"Keyboard settings read failed: {e}"

    scripts_to_register = [(target_paste_lua, "F4"), (target_copy_lua, "F5")]
    modified = False

    for script_path, hotkey in scripts_to_register:
        script_path = os.path.normpath(script_path)
        found_existing = False

        for key_node in commands.findall("key"):
            if key_node.get("shortcut") == hotkey:
                param_node = key_node.find("param")
                if param_node is not None and param_node.get("name") == "filename" and param_node.get("value") == script_path:
                    found_existing = True
                else:
                    key_node.attrib.pop("shortcut", None) 
                    modified = True

        if not found_existing:
            for key_node in commands.findall("key"):
                if key_node.get("command") == "RunScript":
                    param_node = key_node.find("param")
                    if param_node is not None and param_node.get("name") == "filename" and param_node.get("value") == script_path:
                        key_node.set("shortcut", hotkey)
                        found_existing = True
                        modified = True
                        break

        if not found_existing:
            new_key = ET.SubElement(commands, "key", {"command": "RunScript", "shortcut": hotkey})
            ET.SubElement(new_key, "param", {"name": "filename", "value": script_path})
            modified = True

    if modified:
        try:
            tree.write(keys_file, encoding="utf-8", xml_declaration=True)
        except Exception as e:
            return False, f"Settings overwrite failed: {e}"
            
    return True, "F4, F5 Hotkeys registered in Aseprite."

# ==========================================
# Worker Threads & Status Pollers
# ==========================================
def make_photoshop_wrapper(target, body_path, attempt_path, token, started_path, result_path, job_path):
    values = [os.path.dirname(target["path"]), str(target["major"]), body_path,
              attempt_path, token, started_path, result_path, job_path]
    args = ", ".join(json.dumps(value, ensure_ascii=True) for value in values)
    return "#target photoshop\n" + r'''
(function(expectedPath, expectedMajor, body, attempt, token, started, result, job) {
    function read(path) {
        var f = new File(path); f.encoding = "UTF-8";
        if (!f.exists || !f.open("r")) return "";
        var s = f.read(); f.close(); return s;
    }
    function write(path, text) {
        var f = new File(path); f.encoding = "UTF-8";
        if (!f.open("w")) throw new Error("Cannot write status: " + path);
        f.write(text); f.close();
    }
    function normalize(path) { return path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase(); }
    if (read(attempt) !== token) return; // Expired queued launch, not a new success.
    try {
        if (normalize(app.path.fsName) !== normalize(expectedPath) ||
                app.version.split(".")[0] !== expectedMajor) {
            throw new Error("Photoshop target mismatch: " + app.version + " / " + app.path.fsName);
        }
        write(started, app.version + "\n" + app.path.fsName);
        var done = new File(job + "/status_done.json");
        var error = new File(job + "/status_error.txt");
        if (done.exists) done.remove();
        if (error.exists) error.remove();
        $.evalFile(new File(body));
        if (read(attempt) !== token) return;
        if (error.exists) write(result, "error\n" + read(error.fsName));
        else if (done.exists) write(result, "done");
        else write(result, "error\nScript returned without a completion response.");
    } catch (e) {
        if (read(attempt) === token) write(result, "error\n" + e.toString());
    }
})(ARGS);
'''.replace("ARGS", args)


class PhotoshopCLIWorker(QThread):
    RESPONSE_TIMEOUT = 30
    POLL_INTERVAL = 0.5
    result_ready = Signal(bool, str)
    log = Signal(str)
    diagnostic = Signal(object)

    def __init__(self, jsx_template_path, ps_exe_path, job_id, temp_dir, align_mode, frame_mode="normal", language="ko", debug=False):
        super().__init__()
        self.jsx_template_path = jsx_template_path
        self.ps_exe_path = ps_exe_path
        self.job_id = job_id
        self.temp_dir = temp_dir
        self.align_mode = align_mode
        self.frame_mode = frame_mode
        self.debug = bool(debug)
        self.messages = LANG.get(language, LANG["ko"])
        self.job_path = os.path.join(self.temp_dir, self.job_id)
        self.outcome = None
        self.event_offset = 0

    def trace(self, state, **details):
        try:
            self.diagnostic.emit(diagnostic_event(self.job_id, "PhotoshopWorker", state, **details))
        except Exception:
            pass

    def complete(self, success, message, state):
        self.outcome = (success, message)
        self.trace(state)
        self.result_ready.emit(success, message)

    def read_script_events(self, path):
        try:
            if not os.path.isfile(path):
                return
            with open(path, "rb") as stream:
                stream.seek(self.event_offset)
                for _ in range(100):
                    line = stream.readline(65536)
                    if not line.endswith(b"\n"):
                        break
                    self.event_offset = stream.tell()
                    try:
                        event = json.loads(line.decode("utf-8-sig"))
                        if event.get("attempt") != self.attempt_token:
                            continue
                        self.diagnostic.emit(diagnostic_event(
                            self.job_id, "PhotoshopJSX", event["state"],
                            script_timestamp_ms=event.get("timestamp_ms"), data=event.get("details")))
                    except Exception:
                        self.trace("DIAGNOSTIC_READ_FAILED")
        except Exception:
            self.trace("DIAGNOSTIC_READ_FAILED")

    def trace_render_outputs(self):
        try:
            layers = os.path.join(self.job_path, "layers")
            files = sorted(p for p in os.listdir(layers) if p.lower().endswith(".png")) if os.path.isdir(layers) else []
            samples = []
            for filename in files[:8]:
                try:
                    with Image.open(os.path.join(layers, filename)) as image:
                        sample = {"file": filename, "size": list(image.size)}
                        if image.width * image.height <= 4_000_000:
                            sample["alpha_bbox"] = image.getchannel("A").getbbox() if "A" in image.getbands() else [0, 0, image.width, image.height]
                        else:
                            sample["alpha_measurement"] = "skipped_size_limit"
                        samples.append(sample)
                except Exception:
                    samples.append({"file": filename, "alpha_measurement": "unavailable"})
            self.trace("RENDER_OUTPUT_CHECK", png_count=len(files), samples=samples,
                       alpha_measurement="sampled_pngs" if files else "no_exported_pngs")
        except Exception:
            self.trace("DIAGNOSTIC_READ_FAILED")

    def run(self):
        attempt_path = None
        try:
            self.trace("STARTING")
            running = running_photoshops()
            target = resolve_photoshop_target(
                self.ps_exe_path, running, installed_photoshops() if not self.ps_exe_path else [])
            self.ps_exe_path = target["path"]
            self.trace("TARGET_VALIDATED", version=target["version"], executable=target["path"])
            self.log.emit(f"[Photoshop] {target['version']} | {self.ps_exe_path}")
            if not os.path.exists(self.job_path):
                os.makedirs(self.job_path)

            done_file = os.path.join(self.job_path, "status_done.json")
            error_file = os.path.join(self.job_path, "status_error.txt")
            if os.path.exists(done_file): os.remove(done_file)
            if os.path.exists(error_file): os.remove(error_file)

            with open(self.jsx_template_path, "r", encoding="utf-8") as f:
                script_content = f.read()

            safe_job_path = self.job_path.replace("\\", "\\\\")
            script_content = script_content.replace('"REPLACE_ME_JOB_PATH"', f'"{safe_job_path}"')
            script_content = script_content.replace('"REPLACE_ME_ALIGN_MODE"', f'"{self.align_mode}"')
            script_content = script_content.replace('"REPLACE_ME_FRAME_MODE"', f'"{self.frame_mode}"')
            script_content = script_content.replace('"REPLACE_ME_DEBUG_ENABLED"', "true" if self.debug else "false")

            token = uuid.uuid4().hex
            self.attempt_token = token
            attempt_path = os.path.join(self.job_path, "active_ps_attempt.txt")
            started_path = os.path.join(self.job_path, "ps_started_" + token + ".txt")
            result_path = os.path.join(self.job_path, "ps_result_" + token + ".txt")
            body_path = os.path.join(self.job_path, "ps_body_" + token + ".jsx")
            wrapper_jsx_path = os.path.join(self.job_path, "run_bridge_" + token + ".jsx")
            events_path = os.path.join(self.job_path, "ps_events_" + token + ".jsonl")
            script_content = script_content.replace('"REPLACE_ME_DIAGNOSTICS_PATH"', json.dumps(events_path))
            script_content = script_content.replace('"REPLACE_ME_ATTEMPT_TOKEN"', json.dumps(token))
            with open(attempt_path, "w", encoding="utf-8") as f:
                f.write(token)
            with open(body_path, "w", encoding="utf-8") as f:
                f.write(re.sub(r"(?m)^\s*#target[^\r\n]*", "", script_content))
            with open(wrapper_jsx_path, "w", encoding="utf-8") as f:
                f.write(make_photoshop_wrapper(target, body_path, attempt_path, token,
                                               started_path, result_path, self.job_path))
            self.trace("COMMAND_PREPARED", frame_mode=self.frame_mode, align_mode=self.align_mode, debug=self.debug)

            self.log.emit("🔄 [CLI] 전송 중... (Sending command...)")

            subprocess.Popen([self.ps_exe_path, wrapper_jsx_path], creationflags=subprocess.CREATE_NO_WINDOW)
            self.trace("PROCESS_LAUNCHED")
            
            timeout = self.RESPONSE_TIMEOUT
            start_time = time.time()
            script_started = False
            
            while time.time() - start_time < timeout:
                if getattr(self, "isInterruptionRequested", lambda: False)():
                    self.complete(False, self.messages["diag_cancelled"], "CANCELLED")
                    return
                if not script_started and os.path.exists(started_path):
                    script_started = True
                    self.trace("SCRIPT_STARTED")
                self.read_script_events(events_path)
                if os.path.exists(result_path):
                    with open(result_path, "r", encoding="utf-8-sig") as f:
                        response = f.read()
                    if response == "done":
                        self.trace("RESPONSE_RECEIVED", response="done")
                        if os.path.basename(self.jsx_template_path) == "photoshop_copy.jsx":
                            self.trace_render_outputs()
                        if os.path.basename(self.jsx_template_path) == "photoshop_copy.jsx":
                            with open(os.path.join(self.job_path, "ps_copy_accepted.txt"), "w", encoding="utf-8") as f:
                                f.write(token)
                        self.complete(True, "Success", "COMPLETED")
                        return
                    if response.startswith("error\n"):
                        self.trace("RESPONSE_RECEIVED", response="error", script_error=response[6:])
                        if os.path.basename(self.jsx_template_path) == "photoshop_copy.jsx":
                            self.trace_render_outputs()
                        self.complete(False, self.messages["ps_script_error"] + response[6:], "FAILED")
                        return
                    
                time.sleep(self.POLL_INTERVAL)

            try:
                remaining = running_photoshops()
                alive = any(os.path.normcase(p["Path"]) == os.path.normcase(self.ps_exe_path)
                            for p in remaining)
                reason = "ps_timeout_running" if os.path.exists(started_path) else "ps_timeout_pending"
                if not alive:
                    reason = "ps_timeout_closed"
            except Exception:
                reason = "ps_timeout_unknown"
            self.complete(False, self.messages[reason], "TIMEOUT")

        except Exception as e:
            self.trace("PYTHON_EXCEPTION", traceback=traceback.format_exc())
            self.complete(False, f"시스템 에러 (System error): {str(e)}", "FAILED")
        finally:
            self.trace("CLEANUP_STARTED")
            if attempt_path:
                try:
                    with open(attempt_path, "w", encoding="utf-8") as f:
                        f.write("")
                except Exception:
                    self.trace("CLEANUP_WARNING", traceback=traceback.format_exc())
            self.trace("CLEANUP_COMPLETED")

class AsepriteWorker(QThread):
    finished = Signal()
    error = Signal(str)
    log = Signal(str)

    def __init__(self, ase_exe, lua_path=None, trigger_hotkey=False):
        super().__init__()
        self.ase_exe = ase_exe
        self.lua_path = lua_path
        self.trigger_hotkey = trigger_hotkey

    def run(self):
        try:
            if self.trigger_hotkey:
                import win32gui
                import win32con
                import time
                hwnd = win32gui.FindWindow("Aseprite", None)
                if hwnd == 0:
                    def callback(h, hwnds):
                        title = win32gui.GetWindowText(h)
                        if "Aseprite" in title: hwnds.append(h)
                        return True
                    hwnds = []
                    win32gui.EnumWindows(callback, hwnds)
                    if hwnds: hwnd = hwnds[0]

                if hwnd == 0:
                    raise Exception("Aseprite가 실행 중이 아닙니다. (Aseprite is not running)")

                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)

                import ctypes
                VK_F4 = 0x73
                VK_F5 = 0x74
                KEYEVENTF_KEYUP = 0x0002
                
                vk_code = VK_F5 if "copy" in (self.lua_path or "") else VK_F4
                hotkey_name = "F5" if "copy" in (self.lua_path or "") else "F4"
                
                ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
                
                self.log.emit(f"단축키({hotkey_name}) 전송 완료. (Hotkey sent)")
            else:
                cmd = f'start "" "{self.ase_exe}" --script "{self.lua_path}"'
                subprocess.run(cmd, shell=True)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# ==========================================
# Settings Dialog
# ==========================================
class SettingsDialog(QDialog):
    def __init__(self, current_settings, lang_dict, parent=None, photoshop_only=False):
        super().__init__(parent)
        self.lang = lang_dict
        self.setWindowTitle(f'{PRODUCT_NAME} | {self.lang["set_title"]}')
        self.setStyleSheet(WORKSPACE_STYLE)
        self.setMinimumSize(560, 470)
        self.current_settings = current_settings
        self.photoshop_only = photoshop_only
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        # Photoshop 경로
        self.ps_path_input = QLineEdit(self.current_settings.get("photoshop_exe", ""))
        ps_btn = QPushButton(self.lang["set_find"])
        ps_btn.clicked.connect(lambda: self.browse_exe(self.ps_path_input))
        ps_layout = QHBoxLayout()
        ps_layout.addWidget(self.ps_path_input)
        ps_layout.addWidget(ps_btn)
        form_layout.addRow(self.lang["set_ps_path"], ps_layout)

        self.ps_versions = QComboBox()
        self.ps_versions.addItem(self.lang["ps_versions"], "")
        try:
            running = running_photoshops()
            for info in installed_photoshops(self.ps_path_input.text()):
                pids = [str(p["Id"]) for p in running
                        if os.path.normcase(p["Path"]) == os.path.normcase(info["path"])]
                label = f"{info['product']} ({info['version']})"
                if pids:
                    label += " [PID " + ", ".join(pids) + "]"
                self.ps_versions.addItem(label, info["path"])
                self.ps_versions.setItemData(self.ps_versions.count() - 1, info["path"], Qt.ToolTipRole)
        except Exception as e:
            self.ps_versions.setToolTip(str(e))
        self.ps_path_input.textChanged.connect(self.sync_photoshop_version_selection)
        self.sync_photoshop_version_selection()
        self.ps_versions.activated.connect(self.select_photoshop_version)
        form_layout.addRow(self.lang["ps_versions"], self.ps_versions)
        if photoshop_only:
            self.setWindowTitle(f'{PRODUCT_NAME} | {self.lang["guide_steps"][0]}')
            layout.addLayout(form_layout)
            self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            self.button_box.accepted.connect(self.accept)
            self.button_box.rejected.connect(self.reject)
            layout.addWidget(self.button_box)
            return
        ps_warning_btn = QPushButton(self.lang["ps_warning"])
        ps_warning_btn.clicked.connect(self.configure_photoshop_warning)
        form_layout.addRow("", ps_warning_btn)
        
        # Aseprite 경로
        self.ase_path_input = QLineEdit(self.current_settings.get("aseprite_exe", ""))
        ase_btn = QPushButton(self.lang["set_find"])
        ase_btn.clicked.connect(lambda: self.browse_exe(self.ase_path_input))
        ase_layout = QHBoxLayout()
        ase_layout.addWidget(self.ase_path_input)
        ase_layout.addWidget(ase_btn)
        form_layout.addRow(self.lang["set_ase_path"], ase_layout)
        
        # Alignment 기본값
        self.align_combo = QButtonGroup(self)
        align_hlayout = QHBoxLayout()
        self.rb_center = QRadioButton(self.lang["align_center"])
        self.rb_absolute = QRadioButton(self.lang["align_abs"])
        self.rb_ground_line = QRadioButton(self.lang["align_ground_line"])
        self.align_combo.addButton(self.rb_center, 1)
        self.align_combo.addButton(self.rb_absolute, 2)
        self.align_combo.addButton(self.rb_ground_line, 3)
        
        current_alignment = self.current_settings.get("default_alignment", "ground_line")
        if current_alignment == "absolute":
            self.rb_absolute.setChecked(True)
        elif current_alignment == "center":
            self.rb_center.setChecked(True)
        else:
            self.rb_ground_line.setChecked(True)
            
        align_hlayout.addWidget(self.rb_ground_line)
        align_hlayout.addWidget(self.rb_center)
        align_hlayout.addWidget(self.rb_absolute)
        form_layout.addRow(self.lang["set_align"], align_hlayout)
        
        # 언어 설정 (Language)
        self.lang_combo = QButtonGroup(self)
        lang_hlayout = QHBoxLayout()
        self.rb_ko = QRadioButton("한국어")
        self.rb_en = QRadioButton("English")
        self.rb_ja = QRadioButton("日本語")
        self.lang_combo.addButton(self.rb_ko, 1)
        self.lang_combo.addButton(self.rb_en, 2)
        self.lang_combo.addButton(self.rb_ja, 3)
        
        current_lang = self.current_settings.get("language", "ko")
        if current_lang == "en":
            self.rb_en.setChecked(True)
        elif current_lang == "ja":
            self.rb_ja.setChecked(True)
        else:
            self.rb_ko.setChecked(True)
            
        lang_hlayout.addWidget(self.rb_ko)
        lang_hlayout.addWidget(self.rb_en)
        lang_hlayout.addWidget(self.rb_ja)
        form_layout.addRow(self.lang["set_lang"], lang_hlayout)
        
        layout.addLayout(form_layout)
        
        # 단축키 상태 표시
        self.hotkey_status = QLabel(self.current_settings.get("hotkey_status", "Unknown"))
        self.hotkey_status.setStyleSheet("color: #059669; font-weight: bold;")
        layout.addWidget(QLabel(f"<b>{self.lang['set_hotkey']}</b>"))
        layout.addWidget(self.hotkey_status)

        # 재설정 버튼
        btn_reconfigure = QPushButton(self.lang["set_force_reinstall"])
        btn_reconfigure.clicked.connect(self.force_reconfigure)
        layout.addWidget(btn_reconfigure)

        self.btn_setup_guide = QPushButton(self.lang["guide_reopen"])
        self.btn_setup_guide.clicked.connect(self.show_initial_setup)
        layout.addWidget(self.btn_setup_guide)
        
        # 확인/취소
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def browse_exe(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select Executable", "C:\\", "Executables (*.exe)")
        if path:
            line_edit.setText(path)

    def sync_photoshop_version_selection(self):
        path = self.ps_path_input.text()
        matches = []
        if path and os.path.isfile(path):
            expected = os.path.normcase(os.path.abspath(path))
            for index in range(1, self.ps_versions.count()):
                candidate = self.ps_versions.itemData(index)
                if candidate and os.path.normcase(os.path.abspath(candidate)) == expected:
                    matches.append(index)
        self.ps_versions.setCurrentIndex(matches[0] if len(matches) == 1 else 0)

    def select_photoshop_version(self, index):
        path = self.ps_versions.itemData(index)
        if path:
            self.ps_path_input.setText(path)
        self.sync_photoshop_version_selection()

    def configure_photoshop_warning(self):
        configure_photoshop_warning(self, self.lang, self.current_settings, self.ps_path_input.text)

    def force_reconfigure(self):
        ase_paste_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_paste.lua"))
        ase_copy_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_copy.lua"))
        success, msg = setup_aseprite_environment(ase_paste_lua_orig, ase_copy_lua_orig)
        if success:
            QMessageBox.information(self, "Success", msg)
            self.hotkey_status.setText("✅ 정상 (F4=Paste, F5=Copy)")
        else:
            QMessageBox.critical(self, "Failed", msg)
            self.hotkey_status.setText(f"❌ Failed: {msg}")

    def show_aseprite_setup(self):
        parent_app = self.parent()
        if parent_app and hasattr(parent_app, "show_aseprite_setup"):
            parent_app.show_aseprite_setup()

    def show_initial_setup(self):
        app = self.parent()
        if app and hasattr(app, "settings"):
            previous_path = app.settings.get("photoshop_exe", "")
            dialog = InitialSetupDialog(self.lang, app, self)
            dialog.exec()
            self.hotkey_status.setText(self.current_settings.get("hotkey_status", ""))
            if app.settings.get("photoshop_exe", "") != previous_path:
                self.ps_path_input.setText(app.settings.get("photoshop_exe", ""))
            if dialog.open_tutorial_requested:
                TutorialDialog(self.lang, self, app=app).exec()

    def get_settings(self):
        settings = dict(self.current_settings)
        if self.photoshop_only:
            settings["photoshop_exe"] = self.ps_path_input.text()
            return settings
        lang = "ko"
        if self.rb_en.isChecked():
            lang = "en"
        elif self.rb_ja.isChecked():
            lang = "ja"
            
        settings.update({
            "photoshop_exe": self.ps_path_input.text(),
            "aseprite_exe": self.ase_path_input.text(),
            "default_alignment": "ground_line" if self.rb_ground_line.isChecked() else ("center" if self.rb_center.isChecked() else "absolute"),
            "language": lang,
            "hotkey_status": self.hotkey_status.text(),
            "aseprite_trust_confirmed": self.current_settings.get("aseprite_trust_confirmed", False)
        })
        return settings

# ==========================================
# Tutorial Dialog
# ==========================================
from PySide6.QtWidgets import QCheckBox

class DialogInputTrace(QObject):
    """Observe input without consuming events or moving focus; log through the async sink."""
    def __init__(self, dialog, app):
        super().__init__(dialog)
        self.dialog = dialog
        self.app = app
        self.shown_ns = None
        self.native_window = None
        self.paint_seen = False
        self.expose_seen = False
        self.buttons = set()
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(50)
        self.heartbeat.timeout.connect(self.tick)
        self.last_tick_ns = None
        self.native_clock = None
        if sys.platform == "win32":
            import ctypes
            self.native_clock = ctypes.WinDLL("kernel32").GetTickCount64
            self.native_clock.restype = ctypes.c_ulonglong
        dialog.installEventFilter(self)
        dialog.finished.connect(lambda result: self.mark("FINISHED", result=result))
        self.watch_buttons()

    def watch_buttons(self):
        for button in self.dialog.findChildren(QPushButton):
            if button not in self.buttons:
                self.buttons.add(button)
                button.installEventFilter(self)
                button.clicked.connect(lambda checked=False, b=button: self.mark("CLICKED", button=b.text()))

    def mark(self, phase, **details):
        try:
            now = time.perf_counter_ns()
            self.app.trace_job("-", "STARTUP_DIALOG_INPUT", dialog_type=type(self.dialog).__name__,
                               phase=phase, monotonic_ms=now // 1_000_000,
                               since_show_ms=round((now - self.shown_ns) / 1_000_000, 3) if self.shown_ns else None,
                               active=self.dialog.isActiveWindow(), enabled=self.dialog.isEnabled(),
                               active_modal=QApplication.activeModalWidget() is self.dialog,
                               modality=str(self.dialog.windowModality()), **details)
        except Exception:
            pass

    def tick(self):
        now = time.perf_counter_ns()
        gap = (now - self.last_tick_ns) / 1_000_000
        self.last_tick_ns = now
        if gap > 150:
            self.mark("GUI_STALL", gap_ms=round(gap, 3))

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.dialog:
            if kind == QEvent.Show:
                self.shown_ns = self.last_tick_ns = time.perf_counter_ns()
                self.paint_seen = self.expose_seen = False
                self.native_window = self.dialog.windowHandle()
                if self.native_window:
                    self.native_window.installEventFilter(self)
                self.watch_buttons()
                self.heartbeat.start()
                self.mark("SHOWN", flags=int(self.dialog.windowFlags()))
            elif kind == QEvent.Paint and not self.paint_seen:
                self.paint_seen = True
                self.mark("FIRST_PAINT")
            elif kind == QEvent.Hide:
                self.heartbeat.stop()
                self.mark("HIDDEN")
            elif kind in (QEvent.WindowActivate, QEvent.WindowDeactivate):
                self.mark("ACTIVATE" if kind == QEvent.WindowActivate else "DEACTIVATE")
        elif watched is self.native_window and kind == QEvent.Expose:
            if watched.isExposed() and not self.expose_seen:
                self.expose_seen = True
                self.mark("FIRST_EXPOSED")
        elif watched in self.buttons and kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            native_now = self.native_clock() if self.native_clock else None
            native_age = ((native_now - event.timestamp()) & 0xffffffff) if native_now is not None else None
            self.mark("PRESS" if kind == QEvent.MouseButtonPress else "RELEASE", button=watched.text(),
                      spontaneous=event.spontaneous(), native_timestamp_ms=event.timestamp(),
                      native_now_ms=native_now, native_event_age_ms=native_age)
        return False


class AsepriteSetupDialog(QDialog):
    def __init__(self, lang_dict, parent=None, app=None):
        super().__init__(parent)
        self.lang = lang_dict
        self.parent_app = app or parent
        self.setWindowTitle(f'{PRODUCT_NAME} | {self.lang["ase_setup_title"]}')
        self.setMinimumSize(460, 360)

        layout = QVBoxLayout(self)

        content_label = QLabel(self.lang["ase_setup_content"])
        content_label.setWordWrap(True)
        content_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        layout.addWidget(content_label)

        btn_install = QPushButton(self.lang["ase_setup_install"])
        btn_install.clicked.connect(self.install_scripts)
        layout.addWidget(btn_install)

        self.cb_done = QCheckBox(self.lang["ase_setup_done"])
        layout.addWidget(self.cb_done)

        self.button_box = QDialogButtonBox()
        self.btn_complete = self.button_box.addButton(self.lang["ase_setup_complete"], QDialogButtonBox.AcceptRole)
        self.btn_later = self.button_box.addButton(self.lang["ase_setup_later"], QDialogButtonBox.RejectRole)
        self.input_trace = DialogInputTrace(self, self.parent_app) if self.parent_app else None
        self.btn_complete.clicked.connect(self.accept)
        self.btn_later.clicked.connect(self.reject)
        layout.addWidget(self.button_box)

    def install_scripts(self):
        ase_paste_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_paste.lua"))
        ase_copy_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_copy.lua"))
        success, msg = setup_aseprite_environment(ase_paste_lua_orig, ase_copy_lua_orig)
        if self.parent_app and hasattr(self.parent_app, "settings"):
            self.parent_app.settings["hotkey_status"] = "✅ 정상 (F4=Paste, F5=Copy)" if success else f"❌ {msg}"
            save_settings(self.parent_app.settings)
        if success:
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Failed", msg)

    def accept(self):
        if not self.cb_done.isChecked():
            QMessageBox.warning(self, self.lang["ase_setup_title"], self.lang["ase_setup_need_check"])
            return
        if self.parent_app and hasattr(self.parent_app, "settings"):
            self.parent_app.settings["aseprite_trust_confirmed"] = True
            save_settings(self.parent_app.settings)
            if hasattr(self.parent_app, "log_message"):
                self.parent_app.log_message(self.lang["ase_setup_saved"])
        super().accept()

class InitialSetupDialog(QDialog):
    """Guide completion, auto-display, and external security confirmations stay independent."""
    def __init__(self, lang_dict, app, parent=None):
        super().__init__(parent or app)
        self.lang = lang_dict
        self.app = app
        self.open_tutorial_requested = False
        self.setWindowTitle(f'{PRODUCT_NAME} | {self.lang["guide_title"]}')
        self.setStyleSheet(WORKSPACE_STYLE)
        self.setMinimumSize(330, 290)
        available = self.screen().availableGeometry()
        self.resize(min(500, available.width() - 24), min(400, available.height() - 64))
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(self.lang["guide_title"]))
        header.addStretch()
        self.step_count = QLabel()
        self.step_count.setProperty("uiMuted", True)
        header.addWidget(self.step_count)
        layout.addLayout(header)
        self.step_progress = QProgressBar()
        self.step_progress.setRange(0, 4)
        self.step_progress.setTextVisible(False)
        self.step_progress.setFixedHeight(5)
        layout.addWidget(self.step_progress)
        self.step_title = QLabel()
        self.step_title.setWordWrap(True)
        self.step_title.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(self.step_title)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        for step in range(4):
            page = QWidget()
            page.setObjectName("guidePage")
            content = QVBoxLayout(page)
            if step == 0:
                self.add_text(content, self.lang["guide_ps_intro"])
                self.ps_status = self.add_status(content, "")
                self.ps_edit = QPushButton(self.lang["guide_ps_edit"])
                self.ps_edit.clicked.connect(self.edit_photoshop)
                content.addWidget(self.ps_edit)
            elif step == 1:
                self.add_text(content, self.lang["guide_warning_intro"])
                self.warning_status = self.add_status(content, "")
                note = QWidget()
                note.setObjectName("warningNote")
                note.setAttribute(Qt.WA_StyledBackground)
                note_layout = QVBoxLayout(note)
                note_layout.setContentsMargins(8, 7, 8, 7)
                caution = self.add_text(note_layout, self.lang["guide_warning_caution"])
                caution.setObjectName("warningHeading")
                self.add_text(note_layout, self.lang["guide_warning_optional"])
                content.addWidget(note)
                self.warning_edit = QPushButton(self.lang["guide_warning_edit"])
                self.warning_edit.clicked.connect(self.edit_warning)
                content.addWidget(self.warning_edit)
            elif step == 2:
                self.add_text(content, self.lang["guide_ase_intro"])
                self.ase_status = self.add_status(content, "")
                self.ase_edit = QPushButton(self.lang["guide_ase_open"])
                self.ase_edit.clicked.connect(self.edit_aseprite)
                content.addWidget(self.ase_edit)
                self.hotkeys_confirmed = QCheckBox(self.lang["guide_hotkeys_check"])
                self.hotkeys_confirmed.setChecked(self.app.settings.get("aseprite_hotkeys_confirmed") is True)
                self.hotkeys_confirmed.toggled.connect(self.update_summary)
                content.addWidget(self.hotkeys_confirmed)
            else:
                self.add_text(content, self.lang["guide_summary_intro"])
                self.summary = self.add_status(content, "")
                self.btn_tutorial = QPushButton(self.lang["guide_tutorial"])
                self.btn_tutorial.clicked.connect(self.finish_with_tutorial)
                content.addWidget(self.btn_tutorial)
            content.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)

        self.cb_dont_show = QCheckBox(self.lang["guide_dont_show"])
        self.cb_dont_show.setChecked(self.app.settings.get("show_initial_setup") is False)
        layout.addWidget(self.cb_dont_show)
        buttons = QHBoxLayout()
        self.btn_later = QPushButton(self.lang["guide_later"])
        self.btn_back = QPushButton(self.lang["guide_back"])
        self.btn_next = QPushButton()
        self.btn_next.setObjectName("setup_guide_next")
        self.btn_next.setProperty("uiRole", "primary")
        for button in (self.btn_later, self.btn_back, self.btn_next):
            button.setAutoDefault(False)
        buttons.addWidget(self.btn_later)
        buttons.addStretch()
        buttons.addWidget(self.btn_back)
        layout.addLayout(buttons)
        self.btn_next.setMinimumHeight(32)
        layout.addWidget(self.btn_next)
        self.input_trace = DialogInputTrace(self, app)
        self.btn_later.clicked.connect(self.reject)
        self.btn_back.clicked.connect(lambda: self.set_step(self.pages.currentIndex() - 1))
        self.btn_next.clicked.connect(self.next_step)
        # Read-only queries finish before this dialog becomes visible, never after its first paint.
        self.refresh_status()
        self.set_step(0)

    @staticmethod
    def add_text(layout, text):
        label = QLabel(text)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        policy.setHeightForWidth(True)
        label.setSizePolicy(policy)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)
        return label

    @classmethod
    def add_status(cls, layout, text):
        label = cls.add_text(layout, text)
        label.setObjectName("guideStatus")
        return label

    def refresh_status(self):
        path = self.app.settings.get("photoshop_exe", "")
        connection = self.lang["guide_ps_missing"]
        warning = self.lang["guide_warning_unknown"]
        runtime = "guide_ps_runtime_unknown"
        info = None
        try:
            info = photoshop_exe_info(path)
            connection = self.lang["guide_ps_valid"].format(**info)
            config = photoshop_config_path(info)
            _, _, text, values = photoshop_warning_config(config)
            count = len(re.findall(r"(?mi)^\s*WarnRunningScripts\b", text))
            if values == ["0"] and count == 1:
                warning = self.lang["guide_warning_disabled"]
            elif count == 0 or (values == ["1"] and count == 1):
                warning = self.lang["guide_warning_keep"]
        except Exception:
            pass
        if info:
            try:
                running = running_photoshops()
                selected = os.path.normcase(info["path"])
                if any(os.path.normcase(p["Path"]) != selected for p in running):
                    runtime = "guide_ps_other"
                else:
                    runtime = "guide_ps_running" if running else "guide_ps_closed"
            except Exception:
                pass
        self.ps_target_valid = info is not None
        self.ps_status.setText("\n".join(filter(None, (connection, path, self.lang[runtime]))))
        self.warning_state = warning
        self.warning_status.setText("\n".join((connection, self.lang[runtime], warning)))
        self.warning_edit.setEnabled(self.ps_target_valid)
        if self.pages.currentIndex() == 0:
            self.update_next_text(0)

        scripts_current, keys_registered = False, False
        try:
            import filecmp
            folder = os.path.join(os.environ["APPDATA"], "Aseprite")
            pairs = [(self.app.ase_paste_lua_orig, "aseprite_paste.lua", "F4"),
                     (self.app.ase_copy_lua_orig, "aseprite_copy.lua", "F5")]
            scripts_current = all(filecmp.cmp(source, os.path.join(folder, "scripts", name), shallow=False)
                                  for source, name, _ in pairs)
            root = ET.parse(os.path.join(folder, "user.aseprite-keys")).getroot()
            keys_registered = True
            for _, name, shortcut in pairs:
                expected = os.path.normcase(os.path.abspath(os.path.join(folder, "scripts", name)))
                matches = root.findall("./commands/key[@shortcut='" + shortcut + "']")
                keys_registered = keys_registered and len(matches) == 1 and matches[0].get("command") == "RunScript" and any(
                    p.get("name") == "filename" and os.path.normcase(os.path.abspath(p.get("value", ""))) == expected
                    for p in matches[0].findall("param"))
        except Exception:
            pass
        self.ase_status.setText(self.lang["guide_files_ok" if scripts_current else "guide_files_pending"] + "\n" +
                                self.lang["guide_keys_ok" if keys_registered else "guide_keys_pending"])
        self.update_summary()

    def update_summary(self):
        if not hasattr(self, "summary"):
            return
        trust_key = "guide_trust_yes" if self.app.settings.get("aseprite_trust_confirmed") is True else "guide_trust_no"
        keys_key = "guide_keys_tested" if self.hotkeys_confirmed.isChecked() else "guide_keys_untested"
        self.summary.setText("\n\n".join((self.ps_status.text(), self.warning_state,
                                          *self.ase_status.text().splitlines(), self.lang[trust_key], self.lang[keys_key])))

    def edit_photoshop(self):
        dialog = SettingsDialog(self.app.settings, self.lang, self, photoshop_only=True)
        if dialog.exec():
            self.app.settings.update(dialog.get_settings())
            save_settings(self.app.settings)
        self.refresh_status()

    def edit_warning(self):
        configure_photoshop_warning(self, self.lang, self.app.settings,
                                    lambda: self.app.settings.get("photoshop_exe", ""))
        self.refresh_status()

    def edit_aseprite(self):
        dialog = AsepriteSetupDialog(self.lang, self, app=self.app)
        dialog.exec()
        self.refresh_status()

    def set_step(self, index):
        self.pages.setCurrentIndex(index)
        self.step_count.setText(f"{index + 1} / {self.pages.count()}")
        self.step_progress.setValue(index + 1)
        self.step_title.setText(self.lang["guide_steps"][index])
        self.btn_back.setEnabled(index > 0)
        self.update_next_text(index)
        self.update_summary()

    def update_next_text(self, index):
        key = {1: "guide_warning_continue", 3: "guide_finish"}.get(index, "guide_next")
        if index == 0 and self.ps_target_valid:
            key = "guide_ps_continue"
        self.btn_next.setText(self.lang[key])

    def next_step(self):
        if self.pages.currentIndex() == 3:
            self.accept()
        else:
            self.set_step(self.pages.currentIndex() + 1)

    def finish_with_tutorial(self):
        self.open_tutorial_requested = True
        self.accept()

    def done(self, result):
        self.input_trace.mark("ACCEPT_BEGIN" if result == QDialog.Accepted else "REJECT_BEGIN")
        try:
            self.app.settings["initial_setup_seen"] = True
            self.app.settings["show_initial_setup"] = not self.cb_dont_show.isChecked()
            self.app.settings["aseprite_hotkeys_confirmed"] = self.hotkeys_confirmed.isChecked()
            save_settings(self.app.settings)
            super().done(result)
        finally:
            self.input_trace.mark("ACCEPT_END" if result == QDialog.Accepted else "REJECT_END")


class TutorialDialog(QDialog):
    def __init__(self, lang_dict, parent=None, app=None):
        super().__init__(parent)
        self.setWindowTitle(f'{PRODUCT_NAME} | {lang_dict["tut_title"]}')
        self.setMinimumSize(440, 400)
        self.resize(560, 580)
        self.parent_app = app or parent
        
        layout = QVBoxLayout(self)
        
        content_label = QLabel(lang_dict["tut_content"])
        content_label.setWordWrap(True)
        content_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content_label)
        layout.addWidget(scroll, 1)
        
        self.btn_close = QPushButton(lang_dict["guide_close"])
        self.btn_close.setObjectName("tutorial_confirm")
        layout.addWidget(self.btn_close, alignment=Qt.AlignCenter)
        self.input_trace = DialogInputTrace(self, self.parent_app) if self.parent_app else None
        self.btn_close.clicked.connect(self.accept)

    def accept(self):
        if self.input_trace:
            self.input_trace.mark("ACCEPT_BEGIN")
        try:
            super().accept()
        finally:
            if self.input_trace:
                self.input_trace.mark("ACCEPT_END")

# ==========================================
# Main UI Window
# ==========================================
class BridgeApp(QMainWindow):
    diagnostic_received = Signal(object)

    def __init__(self, startup_progress=None):
        super().__init__()
        self._startup_ui_ready = False
        self._startup_dialogs_running = False
        self._startup_dialogs_complete = False
        self._startup_closing = False
        self._startup_interaction_ready = startup_progress is None
        self._active_ps_job_id = None
        self.diagnostic_records = deque(maxlen=2000)
        self.diagnostic_log = DiagnosticLog(os.path.join(BRIDGE_DATA_DIR, "logs"))
        self.diagnostic_received.connect(self.record_diagnostic, Qt.QueuedConnection)

        self.setMinimumSize(390, 380)
        self.resize(460, 620)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Window)

        # 경로 캐싱
        self.ps_copy_jsx = get_resource_path(os.path.join("scripts", "photoshop_copy.jsx"))
        self.ps_paste_jsx = get_resource_path(os.path.join("scripts", "photoshop_paste.jsx"))
        self.ase_copy_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_copy.lua"))
        self.ase_paste_lua_orig = get_resource_path(os.path.join("scripts", "aseprite_paste.lua"))
        self.temp_dir = os.path.join(BASE_DIR, "temp")
        
        self.last_job_id = None
        self.current_job_path = None
        self.clipboard_source = None 
        self.clipboard_count = 0
        self.clipboard_frame_mode = None
        
        # 변환 상태 관리
        self.cur_h = False
        self.cur_v = False
        self.cur_angle = 0
        self.undo_stack = []
        self.redo_stack = []
        
        self.processed_jobs = set()
        self.clipboard_empty_count = 0
        self.ui_busy_transform = False
        self.ui_busy_preview = False
        self.ui_busy_transfer = False
        self.pending_preview_path = None
        self.pending_preview_id = None
        
        # 설정 불러오기 및 초기화
        if startup_progress:
            startup_progress("startup_settings")
        is_first_run = not os.path.exists(SETTINGS_FILE)
        self.settings = load_settings()
        self._needs_language_selection = is_first_run or self.settings.get("language_selection_pending") is True
        if self._needs_language_selection:
            self.settings["language_selection_pending"] = True

        self.current_lang = self.settings.get("language", "en") # 기본값 fallback 보장
        if self.current_lang not in LANG:
            self.current_lang = "en"
            
        self.t = LANG[self.current_lang]
        
        self.setWindowTitle(self.t["title"])
        if startup_progress:
            startup_progress("startup_environment", self.current_lang)
        self.init_environment()

        if startup_progress:
            startup_progress("startup_ui", self.current_lang)
        self.init_ui()
        self.init_timers()
        self.log_message(self.t["msg_started"])
        self.install_exception_logging()
        
    def show_startup_dialogs(self):
        if self._startup_closing or not self._startup_ui_ready or self._startup_dialogs_running or self._startup_dialogs_complete:
            return
        self._startup_dialogs_running = True
        try:
            if self._needs_language_selection:
                from PySide6.QtWidgets import QInputDialog
                QTimer.singleShot(0, self.trace_startup_modal)
                item, ok = QInputDialog.getItem(self, "Language / 언어 / 言語", "Select Language:",
                                                ["English", "한국어", "日本語"], 0, False)
                self.current_lang = {"한국어": "ko", "日本語": "ja"}.get(item, "en") if ok else "en"
                self.settings["language"] = self.current_lang
                self.settings["language_selection_pending"] = False
                self._needs_language_selection = False
                save_settings(self.settings)
                self.refresh_ui_language()
            if self.settings.get("show_initial_setup") is True:
                self.show_initial_setup()
            self._startup_dialogs_complete = True
        except Exception:
            self.trace_job("-", "STARTUP_DIALOG_FAILED", traceback=traceback.format_exc())
            QMessageBox.critical(self, PRODUCT_NAME, self.t["startup_failed"])
            self.close()
            return
        finally:
            self._startup_dialogs_running = False
        self._startup_interaction_ready = True
        self.update_ui_state()
        if not self.clip_timer.isActive():
            self.clip_timer.start(1000)
        self.trace_job("-", "STARTUP_INTERACTIVE")

    def trace_startup_modal(self):
        modal = QApplication.activeModalWidget()
        if modal:
            self.trace_job("-", "STARTUP_MODAL_READY", dialog_type=type(modal).__name__,
                           owned_by_main=modal.parentWidget() is self, enabled=modal.isEnabled(),
                           active=modal.isActiveWindow(), modal=modal.isModal())

    def init_environment(self):
        updated = False

        if "show_initial_setup" not in self.settings:
            # Existing completed users keep their no-popup startup; this is not a Trust grant.
            self.settings["show_initial_setup"] = self._needs_language_selection or self.settings.get("aseprite_trust_confirmed") is not True
            updated = True
        
        if self.settings.get("active_temp_path") != self.temp_dir:
            self.settings["active_temp_path"] = self.temp_dir
            updated = True
            
        if not self.settings.get("photoshop_exe"):
            self.settings["photoshop_exe"] = find_photoshop_exe()
            updated = True
            
        if not self.settings.get("aseprite_exe"):
            self.settings["aseprite_exe"] = find_aseprite_exe()
            updated = True

        success, msg = setup_aseprite_environment(self.ase_paste_lua_orig, self.ase_copy_lua_orig)
        hotkey_status = "✅ 정상 (F4=Paste, F5=Copy)" if success else f"❌ {msg}"
        if self.settings.get("hotkey_status") != hotkey_status:
            self.settings["hotkey_status"] = hotkey_status
            updated = True

        if not self.settings.get("ground_line_default_migrated"):
            self.settings["default_alignment"] = "ground_line"
            self.settings["ground_line_default_migrated"] = True
            updated = True
            
        if not self.settings.get("language"):
            self.settings["language"] = "en"
            updated = True

        if updated:
            save_settings(self.settings)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        # 상단 상태바 및 세팅 버튼, 클린업 버튼
        top_layout = QHBoxLayout()
        self.status_label = QLabel(self.t["clip_empty"])
        self.status_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.update_status(self.t["clip_empty"], "#f3f4f6", "#374151")
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(5)
        
        self.btn_clean = QPushButton(self.t["btn_clean"])
        self.btn_clean.clicked.connect(self.clean_temp_folder)
        
        settings_tut_layout = QHBoxLayout()
        self.btn_tutorial = QPushButton(self.t["btn_tutorial"])
        self.btn_tutorial.clicked.connect(self.show_tutorial)
        
        self.btn_settings = QPushButton(self.t["btn_settings"])
        self.btn_settings.clicked.connect(self.open_settings)
        for button in (self.btn_tutorial, self.btn_settings, self.btn_clean):
            button.setProperty("uiRole", "quiet")
        
        settings_tut_layout.addWidget(self.btn_tutorial)
        settings_tut_layout.addWidget(self.btn_settings)
        
        btn_layout.addLayout(settings_tut_layout)
        
        self.workspace_heading = QLabel(self.t["workspace_heading"])
        self.workspace_heading.setStyleSheet("font-weight: 700; font-size: 15px;")
        top_layout.addWidget(self.workspace_heading, 1)
        top_layout.addLayout(btn_layout)
        layout.addLayout(top_layout)

        # === 썸네일 Preview 영역 ===
        self.preview_panel = QWidget()
        self.preview_panel.setProperty("uiSurface", True)
        self.preview_panel.setAttribute(Qt.WA_StyledBackground)
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)
        preview_layout.addWidget(self.status_label)
        self.preview_label = QLabel(self.t["preview_empty"])
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedSize(340, 160)
        self.preview_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.preview_label.setScaledContents(False)
        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignCenter)

        # === 🔄 변환(Transform) 컨트롤 영역 ===
        self.transform_bar = QWidget()
        self.transform_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        flip_layout = QHBoxLayout(self.transform_bar)
        flip_layout.setContentsMargins(0, 0, 0, 0)
        flip_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.btn_flip_h = QPushButton(self.t.get("btn_flip_h", "↔ 좌우 반전"))
        self.btn_flip_v = QPushButton(self.t.get("btn_flip_v", "↕ 상하 반전"))
        self.btn_rotate = QPushButton(self.t.get("btn_rotate", "↻ 90° 회전"))
        
        self.btn_flip_h.setEnabled(False)
        self.btn_flip_v.setEnabled(False)
        self.btn_rotate.setEnabled(False)
        
        # Undo/Redo 버튼
        self.btn_undo = QPushButton(self.t.get("btn_undo", "↩ Undo"))
        self.btn_redo = QPushButton(self.t.get("btn_redo", "↪ Redo"))
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)

        # 클릭 이벤트 연결 (Lambda 제거)
        self.btn_flip_h.clicked.connect(self.handle_flip_h)
        self.btn_flip_v.clicked.connect(self.handle_flip_v)
        self.btn_rotate.clicked.connect(self.handle_rotate)
        self.btn_undo.clicked.connect(self.handle_undo)
        self.btn_redo.clicked.connect(self.handle_redo)

        flip_layout.addWidget(self.btn_undo)
        flip_layout.addWidget(self.btn_flip_h)
        flip_layout.addWidget(self.btn_flip_v)
        flip_layout.addWidget(self.btn_rotate)
        flip_layout.addWidget(self.btn_redo)
        self.transform_actions = (
            (self.btn_undo, "↶", "btn_undo"), (self.btn_flip_h, "↔", "btn_flip_h"),
            (self.btn_flip_v, "↕", "btn_flip_v"), (self.btn_rotate, "⟳", "btn_rotate"),
            (self.btn_redo, "↷", "btn_redo"))
        for button, _, _ in self.transform_actions:
            button.setFixedSize(48, 28)
        self.refresh_transform_labels()
        preview_layout.addWidget(self.transform_bar)
        layout.addWidget(self.preview_panel)

        # 정렬 모드
        align_layout = QHBoxLayout()
        self.radio_center = QRadioButton(self.t["align_center"])
        self.radio_absolute = QRadioButton(self.t["align_abs"])
        self.radio_ground_line = QRadioButton(self.t["align_ground_line"])
        
        current_alignment = self.settings.get("default_alignment")
        if current_alignment == "absolute":
            self.radio_absolute.setChecked(True)
        elif current_alignment == "center":
            self.radio_center.setChecked(True)
        else:
            self.radio_ground_line.setChecked(True)
            
        self.align_group = QButtonGroup()
        self.align_group.addButton(self.radio_center, 1)
        self.align_group.addButton(self.radio_absolute, 2)
        self.align_group.addButton(self.radio_ground_line, 3)
        self.align_group.buttonClicked.connect(lambda _: self.update_clipboard_align_mode())
        
        self.align_label = QLabel(self.t["align_label"])
        self.align_label.setProperty("uiHeading", True)
        options_layout = workspace_section(layout)
        options_layout.addWidget(self.align_label)
        align_layout.addWidget(self.radio_ground_line)
        align_layout.addWidget(self.radio_center)
        align_layout.addWidget(self.radio_absolute)
        options_layout.addLayout(align_layout)

        # Photoshop -> Aseprite 프레임 모드
        frame_mode_layout = QHBoxLayout()
        self.radio_frame_normal = QRadioButton(self.t["frame_mode_normal"])
        self.radio_frame_folder = QRadioButton(self.t["frame_mode_folder_frames"])
        self.radio_frame_layer = QRadioButton(self.t["frame_mode_layer_frames"])
        self.radio_frame_normal.setChecked(True)

        self.frame_mode_group = QButtonGroup()
        self.frame_mode_group.addButton(self.radio_frame_normal, 1)
        self.frame_mode_group.addButton(self.radio_frame_folder, 2)
        self.frame_mode_group.addButton(self.radio_frame_layer, 3)
        self.frame_mode_group.buttonClicked.connect(lambda _: self.update_clipboard_mode_label())
        for group in (self.align_group, self.frame_mode_group):
            for button in group.buttons():
                button.setProperty("uiSegment", True)
                button.setMinimumHeight(28)

        self.frame_mode_label = QLabel(self.t["frame_mode_label"])
        self.frame_mode_info_label = QLabel()
        self.frame_mode_info_label.setWordWrap(True)
        self.frame_mode_info_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.frame_mode_label.setProperty("uiHeading", True)
        self.frame_mode_info_label.setProperty("uiMuted", True)
        options_layout.addWidget(self.frame_mode_label)
        frame_mode_layout.addWidget(self.radio_frame_normal)
        frame_mode_layout.addWidget(self.radio_frame_folder)
        frame_mode_layout.addWidget(self.radio_frame_layer)
        options_layout.addLayout(frame_mode_layout)
        options_layout.addWidget(self.frame_mode_info_label)

        # === 정방향 ===
        self.btn_ps_copy = QPushButton(self.t["btn_ps_copy"])
        self.btn_ps_copy.setMinimumHeight(40)
        self.btn_ps_copy.clicked.connect(self.run_ps_copy)

        self.btn_ase_paste = QPushButton(self.t["btn_ase_paste"])
        self.btn_ase_paste.setMinimumHeight(40)
        self.btn_ase_paste.setEnabled(False)
        self.btn_ase_paste.clicked.connect(self.run_ase_paste)

        # === 역방향 ===
        self.btn_ase_copy = QPushButton(self.t["btn_ase_copy"])
        self.btn_ase_copy.setMinimumHeight(40)
        self.btn_ase_copy.clicked.connect(self.run_ase_copy)

        self.btn_ps_paste = QPushButton(self.t["btn_ps_paste"])
        self.btn_ps_paste.setMinimumHeight(40)
        self.btn_ps_paste.setEnabled(False)
        self.btn_ps_paste.clicked.connect(self.run_ps_paste)
        for title, copy, paste in (
            ("Photoshop → Aseprite", self.btn_ps_copy, self.btn_ase_paste),
            ("Aseprite → Photoshop", self.btn_ase_copy, self.btn_ps_paste),
        ):
            transfer_layout = workspace_section(layout)
            heading = QLabel(title)
            heading.setProperty("uiHeading", True)
            transfer_layout.addWidget(heading)
            row = QHBoxLayout()
            copy.setProperty("uiRole", "copy")
            paste.setProperty("uiRole", "primary")
            row.addWidget(copy, 1)
            row.addWidget(paste, 1)
            transfer_layout.addLayout(row)

        # 로그 콘솔
        self.diagnostics_toggle = QPushButton(self.t["diag_toggle"])
        self.diagnostics_toggle.setProperty("uiRole", "quiet")
        self.diagnostics_toggle.setCheckable(True)
        utility_row = QHBoxLayout()
        utility_row.addWidget(self.diagnostics_toggle)
        utility_row.addStretch()
        utility_row.addWidget(self.btn_clean)
        layout.addLayout(utility_row)
        self.diagnostics_panel = QWidget()
        self.diagnostics_panel.setProperty("uiSurface", True)
        self.diagnostics_panel.setAttribute(Qt.WA_StyledBackground)
        panel_layout = QVBoxLayout(self.diagnostics_panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 8))
        self.log_console.setMinimumHeight(120)
        self.log_console.setObjectName("diagnosticConsole")
        self.log_console.document().setMaximumBlockCount(2000)
        diagnostic_toolbar = QHBoxLayout()
        self.diagnostic_heading = QLabel(self.t["diag_toggle"])
        self.diagnostic_heading.setProperty("uiHeading", True)
        diagnostic_toolbar.addWidget(self.diagnostic_heading)
        diagnostic_toolbar.addStretch()
        self.debug_checkbox = QCheckBox(self.t["diag_debug"])
        self.debug_checkbox.toggled.connect(self.refresh_diagnostic_display)
        diagnostic_toolbar.addWidget(self.debug_checkbox)
        diagnostic_toolbar.addStretch()
        self.diagnostic_buttons = []
        for key, icon, callback in (
            ("diag_copy", QStyle.SP_FileIcon, self.copy_diagnostic_logs),
            ("diag_folder", QStyle.SP_DirOpenIcon, self.open_diagnostic_folder),
            ("diag_clear", QStyle.SP_DialogResetButton, self.clear_diagnostic_display),
        ):
            button = QPushButton()
            button.setIcon(self.style().standardIcon(icon))
            button.setToolTip(self.t[key])
            button.setAccessibleName(self.t[key])
            button.setFixedSize(32, 28)
            button.clicked.connect(callback)
            diagnostic_toolbar.addWidget(button)
            self.diagnostic_buttons.append((key, button))
        panel_layout.addLayout(diagnostic_toolbar)
        panel_layout.addWidget(self.log_console)
        layout.addWidget(self.diagnostics_panel)
        layout.addStretch()
        self.diagnostics_panel.hide()
        self.diagnostics_toggle.toggled.connect(self.diagnostics_panel.setVisible)

        container = QWidget()
        container.setObjectName("bridgeWorkspace")
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        container.setLayout(layout)
        self.content_scroll = QScrollArea()
        self.content_scroll.setStyleSheet(WORKSPACE_STYLE)
        self.content_scroll.setFrameShape(QScrollArea.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setWidget(container)
        self.setCentralWidget(self.content_scroll)
        
    def show_tutorial(self):
        dlg = TutorialDialog(self.t, self)
        if self._startup_dialogs_running:
            QTimer.singleShot(0, self.trace_startup_modal)
        dlg.exec()

    def show_initial_setup(self):
        dlg = InitialSetupDialog(self.t, self)
        if self._startup_dialogs_running:
            QTimer.singleShot(0, self.trace_startup_modal)
        dlg.exec()
        if dlg.open_tutorial_requested:
            self.show_tutorial()

    def show_aseprite_setup(self):
        dlg = AsepriteSetupDialog(self.t, self)
        if self._startup_dialogs_running:
            QTimer.singleShot(0, self.trace_startup_modal)
        dlg.exec()
        
    def refresh_transform_labels(self):
        for button, symbol, key in self.transform_actions:
            button.setText(symbol)
            button.setToolTip(self.t[key])
            button.setAccessibleName(self.t[key])

    def refresh_ui_language(self):
        self.t = LANG[self.current_lang]
        self.workspace_heading.setText(self.t["workspace_heading"])
        self.align_label.setText(self.t["align_label"])
        self.debug_checkbox.setText(self.t["diag_debug"])
        self.diagnostics_toggle.setText(self.t["diag_toggle"])
        self.diagnostic_heading.setText(self.t["diag_toggle"])
        if self.preview_label.text() in {lang["preview_empty"] for lang in LANG.values()}:
            self.preview_label.setText(self.t["preview_empty"])
        for key, button in self.diagnostic_buttons:
            button.setToolTip(self.t[key])
            button.setAccessibleName(self.t[key])
        self.setWindowTitle(self.t["title"])
        self.radio_center.setText(self.t["align_center"])
        self.radio_absolute.setText(self.t["align_abs"])
        self.radio_ground_line.setText(self.t["align_ground_line"])
        self.frame_mode_label.setText(self.t["frame_mode_label"])
        self.radio_frame_normal.setText(self.t["frame_mode_normal"])
        self.radio_frame_folder.setText(self.t["frame_mode_folder_frames"])
        self.radio_frame_layer.setText(self.t["frame_mode_layer_frames"])
        self.update_clipboard_mode_label()
        self.btn_ps_copy.setText(self.t["btn_ps_copy"])
        self.btn_ase_paste.setText(self.t["btn_ase_paste"])
        self.btn_ase_copy.setText(self.t["btn_ase_copy"])
        self.btn_ps_paste.setText(self.t["btn_ps_paste"])
        
        # 추가된 버튼들의 텍스트 갱신
        self.btn_clean.setText(self.t["btn_clean"])
        self.btn_tutorial.setText(self.t["btn_tutorial"])
        self.btn_settings.setText(self.t["btn_settings"])
        
        # 변환 버튼 텍스트 갱신
        self.refresh_transform_labels()

        if not self.last_job_id:
            self.update_status(self.t["clip_empty"], "#f3f4f6", "#374151")
        else:
            if getattr(self, "clipboard_source", "") == "photoshop":
                msg = self.t["clip_ready"].format(src="PS", dst="Ase", count=getattr(self, "clipboard_count", 0))
                self.update_status(msg, "#dbeafe", "#1e40af")
            elif getattr(self, "clipboard_source", "") == "aseprite":
                msg = self.t["clip_ready"].format(src="Ase", dst="PS", count=getattr(self, "clipboard_count", 0))
                self.update_status(msg, "#fef3c7", "#b45309")

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.t, self)
        if dlg.exec():
            self.settings = dlg.get_settings()
            save_settings(self.settings)
            
            current_alignment = self.settings.get("default_alignment")
            if current_alignment == "absolute":
                self.radio_absolute.setChecked(True)
            elif current_alignment == "center":
                self.radio_center.setChecked(True)
            else:
                self.radio_ground_line.setChecked(True)
                
            new_lang = self.settings.get("language", "ko")
            if new_lang != self.current_lang:
                self.current_lang = new_lang
                self.refresh_ui_language()
                
            self.log_message(self.t["msg_settings_saved"])
            
    def clean_temp_folder(self):
        if self.is_transferring() or self.is_transforming() or self.is_previewing():
            self.log_message(self.t["diag_wait"])
            return
        try:
            if not os.path.exists(self.temp_dir):
                return
                
            total_size = 0
            for item in os.listdir(self.temp_dir):
                item_path = os.path.join(self.temp_dir, item)
                if os.path.isdir(item_path):
                    for dirpath, _, filenames in os.walk(item_path):
                        for f in filenames:
                            fp = os.path.join(dirpath, f)
                            if not os.path.islink(fp):
                                total_size += os.path.getsize(fp)
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    total_size += os.path.getsize(item_path)
                    os.remove(item_path)
            
            # Reset UI states
            self.last_job_id = None
            self.current_job_path = None
            self.clipboard_source = None 
            self.clipboard_count = 0
            self.clipboard_frame_mode = None
            self.processed_jobs = set()
            
            # 🌟 [추가] 변환 및 프리뷰 플래그/예약 상태 초기화
            self.ui_busy_transform = False
            self.ui_busy_preview = False
            self.pending_preview_path = None
            self.pending_preview_id = None
            
            self.update_status(self.t["clip_empty"], "#f3f4f6", "#374151")
            self.update_clipboard_mode_label()
            self.btn_ase_paste.setEnabled(False)
            self.btn_ps_paste.setEnabled(False)
            self.clear_preview()
            
            # 실제 윈도우 클립보드도 완전히 비워서 QTimer가 다시 읽어오는 것을 방지
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.CloseClipboard()
            except:
                pass
            
            size_mb = round(total_size / (1024 * 1024), 2)
            self.log_message(self.t["msg_clean_success"].format(size=size_mb))
            
        except Exception as e:
            self.log_message(self.t["msg_clean_fail"].format(error=str(e)))

    def init_timers(self):
        self.clip_timer = QTimer(self)
        self.clip_timer.timeout.connect(self.poll_clipboard)
        if self._startup_interaction_ready:
            self.clip_timer.start(1000)

    def poll_clipboard(self):
        if not self._startup_interaction_ready or QApplication.activeModalWidget() is not None:
            return
        started = time.perf_counter()
        self.check_clipboard()
        self.check_temp_folder()
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms > 100:
            self.trace_job("-", "GUI_POLL_SLOW", elapsed_ms=round(elapsed_ms, 3))

    @Slot(str)
    def log_message(self, message):
        self.record_diagnostic(diagnostic_event(self._active_ps_job_id, "GUI", "LOG", message=message))

    def trace_job(self, job_id, state, **details):
        try:
            self.record_diagnostic(diagnostic_event(job_id, "GUI", state, **details))
        except Exception:
            pass

    @Slot(object)
    def record_diagnostic(self, event):
        try:
            event = redact_diagnostic(event)
            try:
                self.diagnostic_log.write(event)
            except Exception:
                pass
            self.diagnostic_records.append(event)
            if event.get("state") == "LOG" or event.get("level") == "ERROR" or self.debug_checkbox.isChecked():
                self.append_diagnostic_line(self.format_diagnostic(event))
        except Exception:
            pass

    def format_diagnostic(self, event):
        level = event.get("level", "INFO" if event["state"] == "LOG" else "DEBUG")
        return (f"[{event['timestamp']}] [{level}] [{event['job_id']}] "
                f"{event['component']}:{event['state']} "
                + json.dumps(event.get("details", {}), ensure_ascii=False))

    def append_diagnostic_line(self, line):
        bar = self.log_console.verticalScrollBar()
        position = bar.value()
        follow = position >= bar.maximum() - 2
        self.log_console.append(line)
        bar.setValue(bar.maximum() if follow else position)

    def refresh_diagnostic_display(self):
        position = self.log_console.verticalScrollBar().value()
        follow = position >= self.log_console.verticalScrollBar().maximum() - 2
        visible = [self.format_diagnostic(e) for e in self.diagnostic_records
                   if e.get("state") == "LOG" or e.get("level") == "ERROR" or self.debug_checkbox.isChecked()]
        self.log_console.setPlainText("\n".join(visible))
        bar = self.log_console.verticalScrollBar()
        bar.setValue(bar.maximum() if follow else position)

    def copy_diagnostic_logs(self):
        QApplication.clipboard().setText(self.log_console.toPlainText())

    def open_diagnostic_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.diagnostic_log.directory))

    def clear_diagnostic_display(self):
        self.diagnostic_records.clear()
        self.log_console.clear()

    def install_exception_logging(self):
        self._old_excepthook = sys.excepthook
        self._old_thread_excepthook = threading.excepthook
        def record_exception(kind, value, tb):
            event = diagnostic_event(self._active_ps_job_id, "Python", "UNHANDLED_EXCEPTION",
                                     traceback="".join(traceback.format_exception(kind, value, tb)))
            event["level"] = "ERROR"
            try:
                self.diagnostic_log.write(event)
            except Exception:
                pass
            try:
                self.diagnostic_received.emit(event)
            except Exception:
                pass
        self._exception_hook = record_exception
        self._thread_exception_hook = lambda args: record_exception(args.exc_type, args.exc_value, args.exc_traceback)
        sys.excepthook = self._exception_hook
        threading.excepthook = self._thread_exception_hook

    def get_align_mode(self):
        if self.radio_absolute.isChecked():
            return "absolute"
        if self.radio_ground_line.isChecked():
            return "ground_line"
        return "center"

    def update_clipboard_align_mode(self):
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                payload = json.loads(data)
                if payload.get("signature") != "ase_ps_bridge_payload":
                    return
                if "settings" not in payload or not isinstance(payload["settings"], dict):
                    payload["settings"] = {}
                align_mode = self.get_align_mode()
                payload["settings"]["align_mode"] = align_mode
                payload_str = json.dumps(payload, ensure_ascii=False)
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(payload_str, win32clipboard.CF_UNICODETEXT)
                self.log_message(f"Alignment updated: {align_mode}")
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass

    def get_frame_mode(self):
        if self.radio_frame_folder.isChecked():
            return "folder_frames"
        if self.radio_frame_layer.isChecked():
            return "layer_frames"
        return "normal"

    def get_frame_mode_display(self, mode):
        if mode == "folder_frames":
            return self.t["frame_mode_folder_frames"]
        if mode == "layer_frames":
            return self.t["frame_mode_layer_frames"]
        if mode == "normal":
            return self.t["frame_mode_normal"]
        return None

    def read_job_frame_mode(self, job_path):
        try:
            if not job_path:
                return None
            meta_path = os.path.join(job_path, "metadata.json")
            if not os.path.exists(meta_path):
                return None
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            return metadata.get("frame_mode") or "normal"
        except Exception:
            return "unknown"

    def update_clipboard_mode_label(self):
        if not hasattr(self, "frame_mode_info_label"):
            return
        if self.clipboard_source != "photoshop" or not self.clipboard_frame_mode:
            clip_text = self.t["clipboard_mode_none"]
            self.frame_mode_info_label.setText(f"{self.t['frame_mode_hint']} · {clip_text}")
            return
        display = self.get_frame_mode_display(self.clipboard_frame_mode)
        if not display:
            clip_text = self.t["clipboard_mode_unknown"]
            self.frame_mode_info_label.setText(f"{self.t['frame_mode_hint']} · {clip_text}")
            return
        if self.clipboard_frame_mode != self.get_frame_mode():
            clip_text = self.t["clipboard_mode_mismatch"].format(clip_mode=display)
        else:
            clip_text = self.t["clipboard_mode_current"].format(mode=display)
        self.frame_mode_info_label.setText(f"{self.t['frame_mode_hint']} · {clip_text}")

    def check_temp_folder(self):
        try:
            if not os.path.exists(self.temp_dir): return
            for job_id in os.listdir(self.temp_dir):
                if job_id in self.processed_jobs: continue
                job_path = os.path.join(self.temp_dir, job_id)
                if not os.path.isdir(job_path): continue
                
                trigger_path = os.path.join(job_path, "trigger_copy.json")
                if os.path.exists(trigger_path):
                    try:
                        with open(trigger_path, "r", encoding="utf-8") as f:
                            payload = json.load(f)

                        # A late timed-out Photoshop launch must not replace the current clipboard.
                        if (payload.get("source_app") == "photoshop"
                                and os.path.exists(os.path.join(job_path, "active_ps_attempt.txt"))
                                and not os.path.exists(os.path.join(job_path, "ps_copy_accepted.txt"))):
                            continue
                            
                        payload["settings"] = {"align_mode": self.get_align_mode()}
                            
                        import win32clipboard
                        payload_str = json.dumps(payload, ensure_ascii=False)
                        win32clipboard.OpenClipboard()
                        win32clipboard.EmptyClipboard()
                        win32clipboard.SetClipboardText(payload_str, win32clipboard.CF_UNICODETEXT)
                        win32clipboard.CloseClipboard()

                        if payload.get("source_app") == "photoshop":
                            self.clipboard_frame_mode = self.read_job_frame_mode(job_path)
                            self.update_clipboard_mode_label()
                        
                        self.processed_jobs.add(job_id)
                    except Exception as parse_err:
                        pass
        except Exception:
            pass

    # 🌟 [신규 추가] Preview 처리 메서드
    def set_preview_image(self, img_bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes, "PNG")
        available = self.preview_label.contentsRect().size()
        if pixmap.width() > available.width() or pixmap.height() > available.height():
            pixmap = pixmap.scaled(available, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.preview_label.setPixmap(pixmap)

    def is_transforming(self):
        return self.ui_busy_transform or (hasattr(self, "transform_worker") and self.transform_worker.isRunning())

    def is_previewing(self):
        return self.ui_busy_preview or (hasattr(self, "preview_worker") and self.preview_worker.isRunning())

    def is_transferring(self):
        return getattr(self, "ui_busy_transfer", False) or \
               (hasattr(self, "ps_worker") and self.ps_worker.isRunning()) or \
               (hasattr(self, "ase_worker") and self.ase_worker.isRunning())

    def update_ui_state(self):
        """Job 유효성 및 모든 워커 상태를 검증하여 일관된 UI 상태 유지"""
        if self.centralWidget():
            self.centralWidget().setEnabled(self._startup_interaction_ready)
        valid_job = (self.last_job_id is not None) and \
                    (self.current_job_path is not None) and \
                    (os.path.exists(self.current_job_path))
        
        transforming = self.is_transforming()
        previewing = self.is_previewing()
        transferring = self.is_transferring() or not self._startup_interaction_ready
        self.btn_clean.setEnabled(not (transferring or transforming or previewing))
        
        # [변환 버튼군] - 파일 수정 작업, 프리뷰 합성, 전송 작업 중일 때 잠금
        can_transform = valid_job and not transforming and not previewing and not transferring
        self.btn_flip_h.setEnabled(can_transform)
        self.btn_flip_v.setEnabled(can_transform)
        self.btn_rotate.setEnabled(can_transform)
        self.btn_undo.setEnabled(can_transform and len(self.undo_stack) > 0)
        self.btn_redo.setEnabled(can_transform and len(self.redo_stack) > 0)
        
        # [복사/붙여넣기 버튼군] - 전송 및 변환 작업 중에는 잠금
        can_transfer = not transferring and not transforming
        self.btn_ps_copy.setEnabled(can_transfer)
        self.btn_ase_copy.setEnabled(can_transfer)
        
        can_paste = valid_job and can_transfer
        self.btn_ase_paste.setEnabled(can_paste and self.clipboard_source == "photoshop")
        self.btn_ps_paste.setEnabled(can_paste and self.clipboard_source == "aseprite")

    def clear_preview(self):
        self.preview_label.clear()
        self.preview_label.setText(self.t["preview_empty"])
        self.update_ui_state()

    def start_preview_generation(self, job_path):
        if not job_path or not os.path.exists(job_path): return
        
        # 이미 실행 중이면 예약만 하고 리턴
        if self.is_previewing():
            self.pending_preview_path = job_path
            self.pending_preview_id = self.last_job_id
            return

        self.ui_busy_preview = True
        self.pending_preview_path = None
        self.pending_preview_id = None
        
        try:
            self.trace_job(os.path.basename(job_path), "PREVIEW_STARTED")
            self.preview_label.setText(self.t.get("msg_generating_preview", "Generating Preview..."))
            self.preview_worker = PreviewGeneratorWorker(job_path, self.last_job_id)
            self.preview_worker.preview_ready.connect(self.on_preview_success)
            self.preview_worker.preview_failed.connect(self.on_preview_failed)
            self.preview_worker.start()
            self.update_ui_state()
        except Exception as e:
            self.log_message(f"⚠️ Preview start failed: {e}")
            self.finish_preview_job()

    def on_preview_success(self, img_bytes, worker_job_id):
        try:
            if worker_job_id == self.last_job_id:
                self.set_preview_image(img_bytes)
        finally:
            self.finish_preview_job()

    def on_preview_failed(self, msg):
        try:
            self.preview_label.setText(self.t.get("msg_preview_failed", "Preview Failed"))
            self.log_message(f"⚠️ Preview error: {msg}")
        finally:
            self.finish_preview_job()

    def finish_preview_job(self):
        self.ui_busy_preview = False
        self.update_ui_state()

        p_path = self.pending_preview_path
        p_id = self.pending_preview_id
        self.pending_preview_path = None
        self.pending_preview_id = None

        if p_path and p_id == self.last_job_id:
            self.start_preview_generation(p_path)

    def check_clipboard(self):
        import win32clipboard
        try:
            win32clipboard.OpenClipboard()
            data = None
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()

            if data:
                try:
                    payload = json.loads(data)
                    if payload.get("signature") == "ase_ps_bridge_payload":
                        self.clipboard_empty_count = 0
                        job_id = payload.get("job_id")
                        source = payload.get("source_app", "unknown")
                        count = payload.get("summary", {}).get("layer_count", 0)

                        if job_id != self.last_job_id:
                            self.last_job_id = job_id
                            self.clipboard_source = source
                            self.clipboard_count = count
                            self.current_job_path = payload.get("job_path")
                            self.clipboard_frame_mode = self.read_job_frame_mode(self.current_job_path) if source == "photoshop" else None

                            self.undo_stack.clear()
                            self.redo_stack.clear()
                            self.cur_h, self.cur_v, self.cur_angle = False, False, 0

                            if self.current_job_path and os.path.exists(self.current_job_path):
                                self.start_preview_generation(self.current_job_path)

                            self.update_ui_state()

                            if source == "photoshop":
                                msg = self.t["clip_ready"].format(src="PS", dst="Ase", count=count)
                                self.update_status(msg, "#dbeafe", "#1e40af")
                            elif source == "aseprite":
                                msg = self.t["clip_ready"].format(src="Ase", dst="PS", count=count)
                                self.update_status(msg, "#fef3c7", "#b45309")
                            self.update_clipboard_mode_label()

                            self.log_message(self.t["msg_clip_update"].format(count=count))
                        return
                except: pass
        except Exception:
            pass

        if self.last_job_id is not None:
            self.clipboard_empty_count += 1
            path_missing = self.current_job_path and not os.path.exists(self.current_job_path)
            
            if self.clipboard_empty_count >= 5 or path_missing:
                self.last_job_id = None
                self.current_job_path = None
                self.clipboard_source = None
                self.clipboard_count = 0
                self.clipboard_frame_mode = None
                self.undo_stack.clear()
                self.redo_stack.clear()
                self.cur_h, self.cur_v, self.cur_angle = False, False, 0
                self.clipboard_empty_count = 0
                
                self.ui_busy_transform = False
                self.ui_busy_preview = False
                self.pending_preview_path = None
                self.pending_preview_id = None
                
                self.update_status(self.t["clip_empty"], "#f3f4f6", "#374151")
                self.update_clipboard_mode_label()
                self.clear_preview()
                self.log_message("Stale job state cleared.")

    def update_status(self, text, bg_color, text_color):
        self.status_label.setText(text)
        bg, fg = {
            "#f3f4f6": ("#2b313a", "#dce3ea"),
            "#dbeafe": ("#203c39", "#cbefe8"),
            "#fef3c7": ("#3c3224", "#f4d59a"),
        }.get(bg_color, (bg_color, text_color))
        self.status_label.setStyleSheet(
            f"padding: 4px 8px; background-color: {bg}; color: {fg}; border-radius: 5px; font-weight: bold;")

    # === 변환(Transform) 안정성 패치 영역 ===
    def handle_flip_h(self):
        if self.is_transforming() or not self.current_job_path: return
        self.undo_stack.append((self.cur_h, self.cur_v, self.cur_angle))
        self.redo_stack.clear()
        self.cur_h = not self.cur_h
        self.execute_worker()

    def handle_flip_v(self):
        if self.is_transforming() or not self.current_job_path: return
        self.undo_stack.append((self.cur_h, self.cur_v, self.cur_angle))
        self.redo_stack.clear()
        self.cur_v = not self.cur_v
        self.execute_worker()

    def handle_rotate(self):
        if self.is_transforming() or not self.current_job_path: return
        self.undo_stack.append((self.cur_h, self.cur_v, self.cur_angle))
        self.redo_stack.clear()
        self.cur_angle = (self.cur_angle + 90) % 360
        self.execute_worker()

    def handle_undo(self):
        if self.is_transforming() or not self.undo_stack: return
        self.redo_stack.append((self.cur_h, self.cur_v, self.cur_angle))
        self.cur_h, self.cur_v, self.cur_angle = self.undo_stack.pop()
        self.execute_worker()

    def handle_redo(self):
        if self.is_transforming() or not self.redo_stack: return
        self.undo_stack.append((self.cur_h, self.cur_v, self.cur_angle))
        self.cur_h, self.cur_v, self.cur_angle = self.redo_stack.pop()
        self.execute_worker()

    def execute_worker(self):
        if not self.current_job_path or not os.path.exists(self.current_job_path): return
        if self.is_transforming(): return

        self.ui_busy_transform = True
        self.update_ui_state()
        
        try:
            self.preview_label.setText(self.t.get("msg_transforming", "Transforming..."))

            self.transform_worker = JobTransformWorker(
                self.current_job_path, 
                self.cur_h, 
                self.cur_v, 
                self.cur_angle
            )
            self.transform_worker.transform_done.connect(self.on_transform_success)
            self.transform_worker.error.connect(self.on_transform_error)
            self.transform_worker.log.connect(self.log_message)
            self.transform_worker.start()
        except Exception as e:
            self.ui_busy_transform = False
            self.update_ui_state()
            self.log_message(f"❌ Transform start failed: {e}")

    def on_transform_success(self):
        """연속적인 Busy 상태 유지를 위해 순서 조정"""
        try:
            # 1. 프리뷰 생성을 먼저 시작 (ui_busy_preview가 True가 됨)
            if self.current_job_path:
                self.start_preview_generation(self.current_job_path)
            
            msg = self.t.get("msg_transform_success", "✅ Transform applied").format(
                h=self.cur_h, v=self.cur_v, a=self.cur_angle
            )
            self.log_message(msg)
        finally:
            # 2. 그 다음 트랜스폼 점유 해제
            self.ui_busy_transform = False
            
            # 3. 마지막으로 UI 갱신 (프리뷰 때문에 변환 버튼은 계속 비활성 유지됨)
            self.update_ui_state()

    def on_transform_error(self, msg):
        self.ui_busy_transform = False
        try:
            err_msg = self.t.get("msg_transform_fail", "❌ Transform failed").format(error=msg)
            self.log_message(err_msg)
            # 하드코딩 제거: 다국어 지원되는 msg_transform_failed 사용
            self.preview_label.setText(self.t.get("msg_transform_failed", "Transform Failed"))
        finally:
            self.update_ui_state()

    # === Actions ===
    def run_ps_copy(self):
        job_id = "bridge_job_" + time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex
        self.trace_job(job_id, "COPY_CLICKED")
        if self.is_transferring() or self.is_transforming():
            self.trace_job(job_id, "COPY_BLOCKED", active_job=self._active_ps_job_id,
                           busy_transfer=self.ui_busy_transfer,
                           ps_running=hasattr(self, "ps_worker") and self.ps_worker.isRunning(),
                           transforming=self.is_transforming())
            self.log_message(self.t["diag_blocked"].format(reason=self.t["diag_wait"]))
            return
        self._active_ps_job_id = job_id
        self._ps_operation = "copy"
        self.trace_job(job_id, "IDLE_TO_STARTING")
        previous = bool(self.last_job_id and self.current_job_path and os.path.isdir(self.current_job_path))
        self.update_status(self.t["copy_previous_preview" if previous else "copy_pending"], "#fef3c7", "#92400e")
        self.ui_busy_transfer = True
        self.update_ui_state()
        
        try:
            self.log_message(self.t["msg_ps_copying"])
            
            self.ps_worker = PhotoshopCLIWorker(
                self.ps_copy_jsx, 
                self.settings.get("photoshop_exe"), 
                job_id, 
                self.temp_dir, 
                self.get_align_mode(),
                self.get_frame_mode(),
                language=self.settings.get("language", "ko"),
                debug=self.debug_checkbox.isChecked()
            )
            self.ps_worker.result_ready.connect(self.on_ps_copy_finished, Qt.QueuedConnection)
            self.ps_worker.finished.connect(self.on_ps_thread_finished, Qt.QueuedConnection)
            self.ps_worker.log.connect(self.log_message, Qt.QueuedConnection)
            self.ps_worker.diagnostic.connect(self.record_diagnostic, Qt.QueuedConnection)
            self.ps_worker.start()
        except Exception as e:
            self.ps_start_failed(e)

    @Slot(bool, str)
    def on_ps_copy_finished(self, success, msg):
        try:
            self.show_copy_result_status(success)
            if not success:
                self.log_message(f"❌ [PS Error] {msg}")
        except Exception:
            pass
        finally:
            self.update_ui_state()

    def show_copy_result_status(self, success):
        previous = bool(self.last_job_id and self.current_job_path and os.path.isdir(self.current_job_path))
        key = "copy_preview_pending" if success else ("copy_failed_retained" if previous else "copy_failed_empty")
        self.update_status(self.t[key], "#dbeafe" if success else "#fef3c7", "#1e40af" if success else "#92400e")

    def ps_start_failed(self, error):
        try:
            if getattr(self, "_ps_operation", None) == "copy":
                self.show_copy_result_status(False)
            self.trace_job(self._active_ps_job_id, "FAILED", traceback=traceback.format_exc())
            self.log_message(f"[PS Error] {error}")
        except Exception:
            pass
        finally:
            worker = getattr(self, "ps_worker", None)
            if worker is None or not worker.isRunning():
                self.trace_job(self._active_ps_job_id, "CLEANUP_STARTED")
                self.ui_busy_transfer = False
                self.trace_job(self._active_ps_job_id, "CLEANUP_COMPLETED")
                self.trace_job(self._active_ps_job_id, "READY_FOR_NEXT_JOB")
                self._active_ps_job_id = None
                if worker is not None:
                    del self.ps_worker
                    worker.deleteLater()
            self.update_ui_state()

    @Slot()
    def on_ps_thread_finished(self):
        worker = self.sender()
        if worker is not getattr(self, "ps_worker", None):
            return
        try:
            if worker.outcome is None:
                self.trace_job(worker.job_id, "FAILED", reason="worker exited without result")
        finally:
            # Native QThread.finished, not the earlier result_ready, owns the busy flag.
            del self.ps_worker
            self.ui_busy_transfer = False
            self._active_ps_job_id = None
            try:
                self.trace_job(worker.job_id, "READY_FOR_NEXT_JOB")
            finally:
                self.update_ui_state()
                worker.deleteLater()

    def run_ase_paste(self):
        if self.is_transferring() or self.is_transforming(): return
        self.ui_busy_transfer = True
        self.update_ui_state()
        
        try:
            self.update_clipboard_align_mode()
            self.log_message(self.t["msg_ase_pasting"])
            self.ase_worker = AsepriteWorker(self.settings.get("aseprite_exe"), self.ase_paste_lua_orig, trigger_hotkey=True)
            self.ase_worker.finished.connect(self.on_ase_paste_finished)
            self.ase_worker.error.connect(self.on_ase_paste_error)
            self.ase_worker.log.connect(self.log_message)
            self.ase_worker.start()
        except Exception as e:
            self.ui_busy_transfer = False
            self.update_ui_state()
            self.log_message(f"❌ [Ase Error] {e}\n{self.t.get('msg_ase_trust_err', '')}")

    def on_ase_paste_finished(self):
        self.ui_busy_transfer = False
        self.update_ui_state()
        
    def on_ase_paste_error(self, e):
        self.ui_busy_transfer = False
        try:
            self.log_message(f"❌ [Ase Error] {e}\n{self.t.get('msg_ase_trust_err', '')}")
        finally:
            self.update_ui_state()

    def run_ase_copy(self):
        if self.is_transferring() or self.is_transforming(): return
        self.ui_busy_transfer = True
        self.update_ui_state()
        
        try:
            self.log_message(self.t["msg_ase_copying"])
            self.ase_worker = AsepriteWorker(self.settings.get("aseprite_exe"), self.ase_copy_lua_orig, trigger_hotkey=True)
            self.ase_worker.finished.connect(self.on_ase_copy_finished)
            self.ase_worker.error.connect(self.on_ase_copy_error)
            self.ase_worker.log.connect(self.log_message)
            self.ase_worker.start()
        except Exception as e:
            self.ui_busy_transfer = False
            self.update_ui_state()
            self.log_message(f"❌ [Ase Error] {e}\n{self.t.get('msg_ase_trust_err', '')}")

    def on_ase_copy_finished(self):
        self.ui_busy_transfer = False
        self.update_ui_state()
        
    def on_ase_copy_error(self, e):
        self.ui_busy_transfer = False
        try:
            self.log_message(f"❌ [Ase Error] {e}\n{self.t.get('msg_ase_trust_err', '')}")
        finally:
            self.update_ui_state()

    def run_ps_paste(self):
        if self.is_transferring() or self.is_transforming():
            self.log_message(self.t["diag_wait"])
            return
        if not self.last_job_id:
            self.log_message(self.t["err_no_ase_clip"])
            return

        self.ui_busy_transfer = True
        self._ps_operation = "paste"
        self._active_ps_job_id = self.last_job_id
        self.update_ui_state()
        
        try:
            self.log_message(self.t["msg_ps_pasting"])

            self.ps_worker = PhotoshopCLIWorker(
                self.ps_paste_jsx, 
                self.settings.get("photoshop_exe"), 
                self.last_job_id, 
                self.temp_dir, 
                self.get_align_mode(),
                language=self.settings.get("language", "ko")
            )
            self.ps_worker.result_ready.connect(self.on_ps_paste_finished, Qt.QueuedConnection)
            self.ps_worker.finished.connect(self.on_ps_thread_finished, Qt.QueuedConnection)
            self.ps_worker.log.connect(self.log_message, Qt.QueuedConnection)
            self.ps_worker.diagnostic.connect(self.record_diagnostic, Qt.QueuedConnection)
            self.ps_worker.start()
        except Exception as e:
            self.ps_start_failed(e)

    @Slot(bool, str)
    def on_ps_paste_finished(self, success, msg):
        try:
            if success:
                self.log_message(self.t["msg_ps_success"])
            else:
                self.log_message(f"❌ [PS Error] {msg}")
        except Exception:
            pass
        finally:
            self.update_ui_state()

    def closeEvent(self, event):
        """종료 시 실행 중인 워커 안전하게 종료"""
        if hasattr(self, "ps_worker") and self.ps_worker.isRunning():
            self.log_message(self.t["diag_wait"])
            event.ignore()
            return
        self._startup_closing = True
        if hasattr(self, "_startup_handoff_timer"):
            self._startup_handoff_timer.stop()
        if hasattr(self, "_startup_dialog_timer"):
            self._startup_dialog_timer.stop()
        if hasattr(self, "transform_worker") and self.transform_worker.isRunning():
            self.transform_worker.wait(1000)
        if hasattr(self, "preview_worker") and self.preview_worker.isRunning():
            self.preview_worker.wait(1000)
        if sys.excepthook is getattr(self, "_exception_hook", None):
            sys.excepthook = self._old_excepthook
        if threading.excepthook is getattr(self, "_thread_exception_hook", None):
            threading.excepthook = self._old_thread_excepthook
        self.diagnostic_log.close()
        super().closeEvent(event)

class SourceStartupWindow(QWidget):
    """A layout-based Qt splash without QSplashScreen's mapped-window wait."""
    def __init__(self, pixmap):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setWindowTitle(PRODUCT_NAME)
        self.setFixedSize(pixmap.size())
        self.setStyleSheet("background-color: #24272b; color: #e5e7eb;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)
        image = QLabel()
        image.setPixmap(pixmap.copy(0, 0, pixmap.width(), 140))
        layout.addWidget(image)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status, 1)

    def showMessage(self, text, alignment=None, color=None):
        self.status.setText(text)

    def message(self):
        return self.status.text()


class StartupSplash:
    """Use the onefile bootloader window, or a Qt fallback for source runs."""
    def __init__(self, app):
        self.app = app
        self.language = QLocale.system().name().split("_")[0]
        self.boot = None
        self.widget = None
        self.closed = False
        try:
            import pyi_splash
            if pyi_splash.is_alive():
                self.boot = pyi_splash
        except Exception:
            pass
        if self.boot is None:
            pixmap = QPixmap(get_resource_path("bridge_splash.png"))
            if pixmap.isNull():
                pixmap = QPixmap(460, 200)
                pixmap.fill(QColor("#24272b"))
            self.widget = SourceStartupWindow(pixmap)
            self.widget.show()
            screen = self.widget.screen() or app.primaryScreen()
            if screen:
                self.widget.move(screen.availableGeometry().center() - self.widget.rect().center())
        self.update("startup_starting")

    def update(self, stage, language=None):
        if stage is None:
            self.close()
            return
        if self.closed:
            return
        if language:
            self.language = language
        text = LANG.get(self.language, LANG["en"])[stage]
        if self.widget:
            self.widget.showMessage(text, Qt.AlignBottom | Qt.AlignHCenter, QColor("#e5e7eb"))
            self.app.processEvents(QEventLoop.ExcludeUserInputEvents)
        # The bootloader bitmap uses a single honest 'Starting...' message;
        # no extracted file names, fake percentage, or second splash window.

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.boot:
            try:
                self.boot.close()
            except Exception:
                pass
        if self.widget:
            self.widget.close()
            self.widget.deleteLater()

    def finish(self, window):
        self.close()
        started = time.perf_counter()
        timer = QTimer(window)
        window._startup_handoff_timer = timer

        def handoff():
            # pyi_splash.close() sends IPC; the other process may not have
            # destroyed its Tk window yet. Poll actual ownership, not a delay.
            try:
                pending = self.boot is not None and bootloader_splash_visible()
                if pending:
                    if time.perf_counter() - started > 5:
                        raise RuntimeError("Bootloader splash did not close")
                    return
                timer.stop()
                window._startup_ui_ready = True
                window.trace_job("-", "STARTUP_SPLASH_CLOSED")
                dialog_timer = QTimer(window)
                window._startup_dialog_timer = dialog_timer
                dialog_timer.setSingleShot(True)
                dialog_timer.timeout.connect(lambda: window.show_startup_dialogs())
                dialog_timer.start(0)
            except Exception:
                timer.stop()
                window.trace_job("-", "STARTUP_HANDOFF_FAILED", traceback=traceback.format_exc())
                QMessageBox.critical(window, PRODUCT_NAME, window.t["startup_failed"])
                window.close()

        timer.timeout.connect(handoff)
        timer.start(0)


def bootloader_splash_visible():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    parent_pid = os.getppid()
    found = []

    def visit(hwnd, unused):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == parent_pid and user.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(128)
            user.GetClassNameW(hwnd, name, len(name))
            if name.value.startswith("Tk"):
                found.append(True)
        return True

    user.EnumWindows(callback_type(visit), 0)
    return bool(found)


def create_main_window(app):
    splash = StartupSplash(app)
    try:
        window = BridgeApp(startup_progress=splash.update)
        window.update_ui_state()
        window.show()
        splash.finish(window)
        window.trace_job("-", "STARTUP_READY",
                         script_entry_to_window_ms=round((time.perf_counter() - _STARTUP_ENTERED) * 1000, 1))
        return window
    finally:
        splash.close()


if __name__ == "__main__":
    # 윈도우 작업표시줄 아이콘 강제 적용 (Python 기본 아이콘 덮어쓰기)
    import ctypes
    myappid = 'southpawgames.bridgepro.1.1'
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass

    app = QApplication(sys.argv)
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setStyle("Fusion")
    
    # 앱 전체 기본 아이콘 설정 (Taskbar 및 모든 창)
    from PySide6.QtGui import QIcon
    icon_path = get_resource_path("bridge_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    try:
        window = create_main_window(app)
    except Exception:
        traceback.print_exc()
        language = QLocale.system().name().split("_")[0]
        QMessageBox.critical(None, PRODUCT_NAME, LANG.get(language, LANG["en"])["startup_failed"])
        sys.exit(1)
    sys.exit(app.exec())
