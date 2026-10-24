import os
import sys
import time
import html
import ctypes
from typing import Optional, List
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextBrowser, QProgressBar, QFileDialog,
    QMessageBox, QFrame, QSplitter, QScrollArea, QMenu, QSizeGrip
)
from PyQt6.QtGui import (
    QMouseEvent, QColor, QFont, QPixmap, QIcon, QTextCursor, QGuiApplication
)
from PyQt6.QtCore import (
    Qt, QRect, QPoint, QTimer, pyqtSignal
)

from config import config_manager
from utils.display_affinity import set_window_display_affinity, get_current_affinity
from core.screen_capture import ScreenCapture, multi_page_queue
from core.ai_client import AIStreamWorker, VisionExtractorWorker
from core.keyboard_typer import AutoTyperWorker
from core.audio_capture import InterviewAudioListener
from core.history_manager import history_manager
from ui.selection_overlay import SelectionOverlay
from ui.settings_dialog import SettingsDialog

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9
SW_SHOW = 5

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

def force_activate_window(hwnd: int):
    """穿透 Windows 前台限制，强制将窗口唤起至最顶层并聚焦"""
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        cur_tid = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        
        if cur_tid != fg_tid and fg_tid != 0:
            user32.AttachThreadInput(cur_tid, fg_tid, True)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        else:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
    except Exception as e:
        print(f"[force_activate_window] 异常: {e}")

def start_native_drag(hwnd: int):
    """使用 Windows 原生 Win32 消息启动无边框窗口平滑拖拽"""
    try:
        user32.ReleaseCapture()
        user32.SendMessageW(hwnd, 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
    except Exception as e:
        print(f"[start_native_drag] 异常: {e}")

class CustomTitleBar(QWidget):
    """可拖拽的精简透明风格标题栏"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(245, 247, 250, 0.75);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.08);
            }
            QLabel {
                color: #0f172a;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.6);
                border: 1px solid rgba(0, 0, 0, 0.12);
                color: #334155;
                font-size: 12px;
                padding: 3px 8px;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.95);
                color: #0284c7;
                border-color: #0284c7;
            }
            QPushButton#closeBtn:hover {
                background-color: #ef4444;
                color: #ffffff;
                border-color: #dc2626;
            }
            QPushButton#pinBtnActive {
                color: #0284c7;
                font-weight: bold;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        # 标题与拖动手柄
        self.lbl_title = QLabel("⚡ OpenAnswerInk")
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.lbl_title)

        self.lbl_drag_hint = QLabel("✥ 拖动")
        self.lbl_drag_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_drag_hint.setStyleSheet("color: #0284c7; font-size: 11px; font-weight: bold; background: rgba(2, 132, 199, 0.12); padding: 2px 6px; border-radius: 3px;")
        self.lbl_drag_hint.setToolTip("按住此处或标题栏/工具栏任意空白区域可拖动整个窗口")
        layout.addWidget(self.lbl_drag_hint)

        self.lbl_stealth = QLabel("🛡️ 防录屏: ON")
        self.lbl_stealth.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_stealth.setStyleSheet("color: #0284c7; font-size: 11px; margin-left: 2px; font-weight: bold;")
        layout.addWidget(self.lbl_stealth)

        # 穿透指示切换按钮
        self.btn_click_through = QPushButton("🖱️ 穿透: OFF")
        self.btn_click_through.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_click_through.setToolTip("一键开启/关闭鼠标点击穿透与防失焦模式 (Alt+C)")
        layout.addWidget(self.btn_click_through)

        layout.addStretch()

        # 置顶按钮
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setToolTip("切换窗口置顶")
        layout.addWidget(self.btn_pin)

        # 最小化与关闭
        self.btn_min = QPushButton("－")
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setToolTip("最小化")
        layout.addWidget(self.btn_min)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("退出")
        layout.addWidget(self.btn_close)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            start_native_drag(int(self.window().winId()))
            event.accept()
        else:
            super().mousePressEvent(event)

class MainWindow(QMainWindow):
    """主答题与面试领航窗口"""
    def __init__(self):
        super().__init__()
        # 使用 Window 而不是 Tool，确保任务栏可见图标，方便用户随时找回
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("OpenAnswerInk 领航助手")
        self.resize(580, 720)

        # 移动到主屏幕右侧显著位置
        screens = QGuiApplication.screens()
        if screens:
            primary_geo = screens[0].geometry()
            pos_x = max(50, primary_geo.width() - 610)
            pos_y = max(50, min(100, primary_geo.height() - 750))
            self.move(pos_x, pos_y)

        # 状态对象
        self._current_ai_worker: Optional[AIStreamWorker] = None
        self._current_vision_worker: Optional[VisionExtractorWorker] = None
        self._current_typer_worker: Optional[AutoTyperWorker] = None
        self._audio_listener: Optional[InterviewAudioListener] = None
        self._last_question_text = ""
        self._last_reasoning_text = ""
        self._last_answer_text = ""
        self._last_pixmaps: List[QPixmap] = []
        self._interview_turn_count = 0
        self._is_first_interview_turn = True
        self._click_through_enabled = False

        self.overlay = SelectionOverlay()
        self.overlay.signal_selected.connect(self._on_region_selected)

        self._init_ui()
        self._apply_styles()
        self._apply_anti_capture()
        self._init_window_styles()
        self._refresh_toggle_buttons()

        # 置顶看门狗
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._keep_topmost)
        self._topmost_timer.start(2000)

        # 异步预热 Whisper 引擎，确保开启面试时毫秒级极速响应
        QTimer.singleShot(500, self._preload_whisper)

    def _preload_whisper(self):
        import threading
        def _loader():
            try:
                from faster_whisper import WhisperModel
                WhisperModel("tiny", device="cpu", compute_type="int8")
            except Exception:
                pass
        threading.Thread(target=_loader, daemon=True).start()

    def _init_ui(self):
        central = QWidget(self)
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. 顶部自定义标题栏
        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_click_through.clicked.connect(self.toggle_click_through)
        self.title_bar.btn_pin.clicked.connect(self._toggle_pin)
        self.title_bar.btn_min.clicked.connect(self.showMinimized)
        self.title_bar.btn_close.clicked.connect(self.close)
        main_layout.addWidget(self.title_bar)

        # 2. 快捷功能工具栏 (两行规整排布，防拥挤且支持整块拖动)
        tool_widget = QWidget()
        tool_widget.setObjectName("toolWidget")
        tool_widget.mousePressEvent = lambda e: (start_native_drag(int(self.winId())) if e.button() == Qt.MouseButton.LeftButton else None)
        tool_layout = QVBoxLayout(tool_widget)
        tool_layout.setContentsMargins(8, 6, 8, 6)
        tool_layout.setSpacing(5)

        # 第 1 行：核心答题与操作
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(5)

        self.btn_capture_region = QPushButton("📸 选区")
        self.btn_capture_region.setToolTip("区域截屏并提交 AI (Alt+A)")
        self.btn_capture_region.clicked.connect(self.trigger_region_capture)
        row1_layout.addWidget(self.btn_capture_region)

        self.btn_capture_full = QPushButton("🖥️ 全屏速答")
        self.btn_capture_full.setToolTip("全屏截屏快速提取题干并解答 (Alt+S)")
        self.btn_capture_full.clicked.connect(self.trigger_fullscreen_capture)
        row1_layout.addWidget(self.btn_capture_full)

        self.btn_fine_capture = QPushButton("🧩 精细答题 (全屏)")
        self.btn_fine_capture.setToolTip("【行测图形推理/复杂图表专用】直接超清全屏截屏，调用 32B 深度视觉大模型拆解微观图形与选项，交由 DeepSeek 快速秒杀 (Alt+W)")
        self.btn_fine_capture.clicked.connect(self.trigger_fine_visual_capture)
        self.btn_fine_capture.setStyleSheet("color: #6d28d9; font-weight: bold; border-color: rgba(124, 58, 237, 0.4);")
        row1_layout.addWidget(self.btn_fine_capture)

        self.btn_multi_page = QPushButton("📑 累加页 (0)")
        self.btn_multi_page.setToolTip("多页长题累加截图 (Alt+D)")
        self.btn_multi_page.clicked.connect(self.trigger_multipage_capture)
        row1_layout.addWidget(self.btn_multi_page)

        self.btn_interview = QPushButton("🎙️ 面试")
        self.btn_interview.setToolTip("监听系统扬声器，实时转写面试官提问 (Alt+M)")
        self.btn_interview.clicked.connect(self._toggle_interview_listener)
        row1_layout.addWidget(self.btn_interview)

        self.btn_typer = QPushButton("⌨️ 键入")
        self.btn_typer.setToolTip("在光标所在输入框模拟自然人工键入 (Alt+T)")
        self.btn_typer.clicked.connect(self._start_auto_typing)
        row1_layout.addWidget(self.btn_typer)

        tool_layout.addLayout(row1_layout)

        # 第 2 行：主模型模式与控制
        row2_layout = QHBoxLayout()
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(5)

        self.btn_toggle_thinking = QPushButton("🧠 思考: ON")
        self.btn_toggle_thinking.setToolTip("主模型深度思考 (Chain of Thought 思维链推导): 点击一键开启/关闭")
        self.btn_toggle_thinking.clicked.connect(self._toggle_thinking_mode)
        row2_layout.addWidget(self.btn_toggle_thinking)

        self.btn_toggle_web_search = QPushButton("🌐 联网: OFF")
        self.btn_toggle_web_search.setToolTip("主模型联网思考检索 (实时搜索最新知识与动态): 点击一键开启/关闭")
        self.btn_toggle_web_search.clicked.connect(self._toggle_web_search_mode)
        row2_layout.addWidget(self.btn_toggle_web_search)

        self.btn_click_through = QPushButton("🖱️ 穿透 (Alt+C)")
        self.btn_click_through.setToolTip("开启后鼠标直接穿透浮窗点击底层考卷，绝不失焦 (Alt+C)")
        self.btn_click_through.clicked.connect(self.toggle_click_through)
        row2_layout.addWidget(self.btn_click_through)

        self.btn_export = QPushButton("📄 导出")
        self.btn_export.setToolTip("导出全部历史记录到 Word (.docx)")
        self.btn_export.clicked.connect(self._export_history_docx)
        row2_layout.addWidget(self.btn_export)

        self.btn_clear = QPushButton("🧹 清屏")
        self.btn_clear.setToolTip("清空当前悬浮窗上的所有转写与回答记录")
        self.btn_clear.clicked.connect(self._clear_screen_history)
        row2_layout.addWidget(self.btn_clear)

        self.btn_settings = QPushButton("⚙️ 设置")
        self.btn_settings.setToolTip("打开配置")
        self.btn_settings.clicked.connect(self._open_settings)
        row2_layout.addWidget(self.btn_settings)

        tool_layout.addLayout(row2_layout)

        main_layout.addWidget(tool_widget)

        # 3. 多页暂存提醒条 (默认隐藏)
        self.multipage_bar = QWidget()
        self.multipage_bar.setObjectName("multipageBar")
        bar_layout = QHBoxLayout(self.multipage_bar)
        bar_layout.setContentsMargins(10, 4, 10, 4)
        self.lbl_multipage_info = QLabel("已累加 0 张题目图片")
        bar_layout.addWidget(self.lbl_multipage_info)
        btn_send_multi = QPushButton("🚀 立即合并发送")
        btn_send_multi.clicked.connect(self._send_multipage_query)
        bar_layout.addWidget(btn_send_multi)
        btn_clear_multi = QPushButton("清空")
        btn_clear_multi.clicked.connect(self._clear_multipage)
        bar_layout.addWidget(btn_clear_multi)
        self.multipage_bar.setVisible(False)
        main_layout.addWidget(self.multipage_bar)

        # 4. 深度思考过程折叠条 (默认隐藏)
        self.thinking_header = QWidget()
        self.thinking_header.setObjectName("thinkingHeader")
        th_layout = QHBoxLayout(self.thinking_header)
        th_layout.setContentsMargins(10, 4, 10, 4)
        self.lbl_thinking_title = QLabel("🧠 深度思考过程 (点击展开/折叠)")
        th_layout.addWidget(self.lbl_thinking_title)
        self.thinking_header.mousePressEvent = lambda e: self._toggle_thinking_box()
        self.thinking_header.setVisible(False)
        main_layout.addWidget(self.thinking_header)

        self.browser_thinking = QTextBrowser()
        self.browser_thinking.setObjectName("thinkingBrowser")
        self.browser_thinking.setMaximumHeight(140)
        self.browser_thinking.setVisible(False)  # 默认折叠
        main_layout.addWidget(self.browser_thinking)

        # 5. 主答案显示区（强制单屏显示，关闭滚轮滑动）
        self.browser_answer = QTextBrowser()
        self.browser_answer.setObjectName("answerBrowser")
        self.browser_answer.setOpenExternalLinks(True)
        self.browser_answer.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser_answer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser_answer.viewport().installEventFilter(self)
        main_layout.addWidget(self.browser_answer)

        # 6. 底部状态指示条
        status_bar = QWidget()
        status_bar.setObjectName("statusBar")
        status_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        status_bar.mousePressEvent = lambda e: (start_native_drag(int(self.winId())) if e.button() == Qt.MouseButton.LeftButton else None)
        st_layout = QHBoxLayout(status_bar)
        st_layout.setContentsMargins(10, 4, 10, 4)

        self.lbl_status = QLabel("就绪 | 快捷键: Alt+A 选区 / Alt+S 全屏 / Alt+W 精细全屏 / Alt+C 穿透")
        self.lbl_status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        st_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedWidth(80)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setVisible(False)
        st_layout.addWidget(self.progress_bar)

        # 右下角窗口缩放手柄
        size_grip = QSizeGrip(status_bar)
        size_grip.setStyleSheet("background: transparent;")
        st_layout.addWidget(size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(status_bar)

    def _apply_styles(self):
        # 默认透明背景，纯黑文字（隐形题词/考卷融合模式）
        self.setStyleSheet("""
            QWidget#centralWidget {
                background-color: transparent;
                border: 1px solid rgba(0, 0, 0, 0.15);
                border-radius: 8px;
            }
            QWidget#toolWidget {
                background-color: rgba(245, 247, 250, 0.65);
                border-bottom: 1px solid rgba(0, 0, 0, 0.08);
            }
            QWidget#toolWidget QPushButton {
                background-color: rgba(255, 255, 255, 0.75);
                color: #0f172a;
                border: 1px solid rgba(0, 0, 0, 0.15);
                border-radius: 5px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QWidget#toolWidget QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.95);
                border-color: #0284c7;
                color: #0284c7;
            }
            QWidget#multipageBar {
                background-color: rgba(241, 245, 249, 0.75);
                border-bottom: 1px solid rgba(0, 0, 0, 0.1);
            }
            QWidget#multipageBar QLabel {
                color: #0284c7;
                font-size: 12px;
                font-weight: bold;
            }
            QWidget#multipageBar QPushButton {
                background-color: #0284c7;
                color: white;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QWidget#thinkingHeader {
                background-color: rgba(248, 250, 252, 0.5);
                border-top: 1px solid rgba(0, 0, 0, 0.08);
                border-bottom: 1px solid rgba(0, 0, 0, 0.08);
            }
            QWidget#thinkingHeader QLabel {
                color: #334155;
                font-size: 11px;
                font-weight: 600;
            }
            QTextBrowser#thinkingBrowser {
                background-color: rgba(255, 255, 255, 0.6);
                color: #334155;
                border: 1px dashed rgba(0, 0, 0, 0.15);
                font-size: 12px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                padding: 8px;
            }
            QTextBrowser#answerBrowser {
                background-color: transparent;
                color: #000000;
                border: none;
                font-size: 13.5px;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-weight: 600;
                padding: 6px 8px;
                line-height: 1.35;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
            QWidget#statusBar {
                background-color: rgba(248, 250, 252, 0.7);
                border-top: 1px solid rgba(0, 0, 0, 0.08);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QWidget#statusBar QLabel {
                color: #1e293b;
                font-size: 11px;
                font-weight: 500;
            }
        """)

    def _init_window_styles(self):
        """注入底层 Win32 扩展样式：WS_EX_NOACTIVATE，防止点击悬浮窗窃取考场全屏焦点"""
        try:
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = ex_style | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception as e:
            print(f"[_init_window_styles] 异常: {e}")

    def toggle_click_through(self):
        """一键切换鼠标穿透/防失焦无感模式 (Alt+C)"""
        self.set_click_through(not self._click_through_enabled)

    def set_click_through(self, enable: bool):
        self._click_through_enabled = enable
        hwnd = int(self.winId())
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        
        if enable:
            # 开启鼠标穿透：注入 WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE
            new_style = ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            
            # UI 状态提示
            self.title_bar.btn_click_through.setText("🔒 穿透: ON")
            self.title_bar.btn_click_through.setStyleSheet("color: #92400e; font-weight: bold; background-color: rgba(254, 243, 199, 0.95); border: 1px solid #d97706;")
            self.btn_click_through.setText("🔒 穿透中 (Alt+C)")
            self.btn_click_through.setStyleSheet("background-color: #fef3c7; border: 1px solid #d97706; color: #92400e; font-weight: bold;")
            self.lbl_status.setText("⚡ [鼠标穿透已锁定] 点击直接穿透至背后页面，绝不失焦 | 按 Alt+C 解锁")
        else:
            # 关闭鼠标穿透：移除 WS_EX_TRANSPARENT，保留 WS_EX_NOACTIVATE
            new_style = (ex_style & ~WS_EX_TRANSPARENT) | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            
            # 恢复普通交互状态
            self.title_bar.btn_click_through.setText("🖱️ 穿透: OFF")
            self.title_bar.btn_click_through.setStyleSheet("color: #334155; background-color: rgba(255, 255, 255, 0.6);")
            self.btn_click_through.setText("🖱️ 穿透 (Alt+C)")
            self.btn_click_through.setStyleSheet("")
            self.lbl_status.setText("就绪 | 快捷键: Alt+A 选区 / Alt+S 全屏 / Alt+W 精细全屏 / Alt+C 穿透")

        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    def _apply_anti_capture(self):
        """应用 Windows 防捕获亲和性"""
        enabled = config_manager.get("anti_capture_enabled", True)
        hwnd = int(self.winId())
        ok = set_window_display_affinity(hwnd, enabled)
        if enabled and ok:
            self.title_bar.lbl_stealth.setText("🛡️ 防录屏: ON (隐形)")
            self.title_bar.lbl_stealth.setStyleSheet("color: #0284c7; font-size: 11px; font-weight: bold;")
        elif enabled and not ok:
            self.title_bar.lbl_stealth.setText("⚠️ 防录屏: 失败")
            self.title_bar.lbl_stealth.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        else:
            self.title_bar.lbl_stealth.setText("防录屏: OFF")
            self.title_bar.lbl_stealth.setStyleSheet("color: #64748b; font-size: 11px;")

    def wake_up_or_toggle(self):
        """Alt+H 专用的智能一键唤起逻辑：
        1. 窗口若隐藏、最小化或被其他应用遮挡（非前台聚焦），一键强制拉到屏幕最前面置顶并激活！
        2. 仅当窗口已经处于当前屏幕最前激活状态时，再次按 Alt+H 才是快速隐藏。
        """
        hwnd = int(self.winId())
        fg_hwnd = user32.GetForegroundWindow()

        # 检查是否已经在前台激活
        is_front_active = (self.isVisible() and not self.isMinimized() and fg_hwnd == hwnd)

        if not is_front_active:
            self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
            force_activate_window(hwnd)
            self._keep_topmost()
            self.lbl_status.setText("⚡ 已通过 Alt+H 一键唤起置顶 | 就绪")
        else:
            self.hide()

    def _keep_topmost(self):
        """保持置顶守护"""
        if config_manager.get("stays_on_top", True):
            hwnd = int(self.winId())
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _toggle_pin(self):
        stays = not config_manager.get("stays_on_top", True)
        config_manager.set("stays_on_top", stays)
        if stays:
            self.title_bar.btn_pin.setStyleSheet("color: #0284c7; font-weight: bold;")
            self._keep_topmost()
        else:
            self.title_bar.btn_pin.setStyleSheet("color: #475569;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            start_native_drag(int(self.winId()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        if hasattr(self, 'browser_answer') and watched == self.browser_answer.viewport():
            if event.type() == event.Type.MouseButtonPress:
                # 允许在正文区域使用鼠标中键、或按住 Alt/Ctrl+左键直接拖动整个窗口
                if event.button() == Qt.MouseButton.MiddleButton or (
                    event.button() == Qt.MouseButton.LeftButton and 
                    event.modifiers() & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier)
                ):
                    start_native_drag(int(self.winId()))
                    return True
        return super().eventFilter(watched, event)

    def _toggle_thinking_box(self):
        is_visible = self.browser_thinking.isVisible()
        self.browser_thinking.setVisible(not is_visible)
        arrow = "▲" if not is_visible else "▼"
        self.lbl_thinking_title.setText(f"🧠 深度思考过程 ({arrow} 点击展开/折叠)")

    def _toggle_thinking_mode(self):
        """一键切换主模型深度思考 (Chain of Thought)"""
        cur = config_manager.get("enable_thinking", False)
        new_val = not cur
        config_manager.set("enable_thinking", new_val)
        self._refresh_toggle_buttons()
        if new_val:
            self.lbl_status.setText("🧠 主模型深度思考已【开启】(展示思维链推理推导)")
        else:
            self.lbl_status.setText("⚡ 主模型深度思考已【关闭】(直接毫秒级秒出最终答案)")

    def _toggle_web_search_mode(self):
        """一键切换主模型联网思考检索"""
        cur = config_manager.get("enable_web_search", False)
        new_val = not cur
        config_manager.set("enable_web_search", new_val)
        self._refresh_toggle_buttons()
        if new_val:
            self.lbl_status.setText("🌐 主模型联网思考已【开启】(实时结合互联网最新知识推导)")
        else:
            self.lbl_status.setText("🔒 主模型联网思考已【关闭】(仅依靠原生模型知识库)")

    def _refresh_toggle_buttons(self):
        """同步刷新工具栏上的深度思考和联网按钮状态样式"""
        thinking_on = config_manager.get("enable_thinking", False)
        if thinking_on:
            self.btn_toggle_thinking.setText("🧠 思考: ON")
            self.btn_toggle_thinking.setStyleSheet("background-color: rgba(224, 242, 254, 0.95); border: 1px solid #0284c7; color: #0369a1; font-weight: bold;")
            self.thinking_header.setVisible(True)
        else:
            self.btn_toggle_thinking.setText("🧠 思考: OFF")
            self.btn_toggle_thinking.setStyleSheet("background-color: rgba(241, 245, 249, 0.7); border: 1px solid rgba(0, 0, 0, 0.15); color: #64748b; font-weight: 500;")
            self.thinking_header.setVisible(False)
            self.browser_thinking.setVisible(False)

        search_on = config_manager.get("enable_web_search", False)
        if search_on:
            self.btn_toggle_web_search.setText("🌐 联网: ON")
            self.btn_toggle_web_search.setStyleSheet("background-color: rgba(220, 252, 231, 0.95); border: 1px solid #16a34a; color: #15803d; font-weight: bold;")
        else:
            self.btn_toggle_web_search.setText("🌐 联网: OFF")
            self.btn_toggle_web_search.setStyleSheet("background-color: rgba(241, 245, 249, 0.7); border: 1px solid rgba(0, 0, 0, 0.15); color: #64748b; font-weight: 500;")

    def trigger_region_capture(self):
        """触发区域截屏选区"""
        self.lbl_status.setText("请在屏幕上拖拽或点击选区，按 Esc 取消...")
        self.overlay.start_selection()

    def _on_region_selected(self, rect: QRect):
        try:
            pixmap, b64 = ScreenCapture.capture_region(rect)
            self._last_pixmaps = [pixmap]
            self._execute_ai_query([b64])
        except Exception as e:
            self.lbl_status.setText(f"截图失败: {e}")

    def trigger_fullscreen_capture(self):
        """触发全屏截屏"""
        try:
            self.lbl_status.setText("正在捕获全屏...")
            pixmap, b64 = ScreenCapture.capture_fullscreen()
            self._last_pixmaps = [pixmap]
            self._execute_ai_query([b64])
        except Exception as e:
            self.lbl_status.setText(f"全屏截图失败: {e}")

    def trigger_fine_visual_capture(self):
        """行测图形推理 / 复杂图表专用超清全屏精细识别解题 (Alt+W)：
        1. 直接全屏截图（无需手动划选），保留原生更高清细节质量；
        2. 调用 32B 深度多模态视觉模型深度拆解图形微观拓扑、数量关系与选项对比；
        3. 结构化视觉数据自动交由 DeepSeek 深度推导，秒杀客观题选项！
        """
        try:
            self.lbl_status.setText("正在捕获超清全屏进行行测精细图形分析...")
            pixmap, b64 = ScreenCapture.capture_fullscreen_hq()
            self._last_pixmaps = [pixmap]
            self._execute_fine_visual_query(b64)
        except Exception as e:
            self.lbl_status.setText(f"精细全屏截图失败: {e}")

    def trigger_multipage_capture(self):
        """多页截图：将当前选区加入累积队列"""
        def _add_page(rect: QRect):
            pixmap, b64 = ScreenCapture.capture_region(rect)
            multi_page_queue.add_page(b64, pixmap)
            count = multi_page_queue.count()
            self.btn_multi_page.setText(f"📑 累加页 ({count})")
            self.multipage_bar.setVisible(True)
            self.lbl_multipage_info.setText(f"已累加 {count} 张题目图片")
            self.lbl_status.setText(f"已加入第 {count} 页截图，可继续截图或点击立即发送")

        self.overlay.signal_selected.disconnect()
        self.overlay.signal_selected.connect(_add_page)
        self.overlay.start_selection()

    def _send_multipage_query(self):
        pages = multi_page_queue.get_pages()
        if not pages:
            return
        self._last_pixmaps = multi_page_queue.get_thumbnails()
        self._execute_ai_query(pages)
        self._clear_multipage()

    def _clear_multipage(self):
        multi_page_queue.clear()
        self.btn_multi_page.setText("📑 累加页 (0)")
        self.multipage_bar.setVisible(False)
        self.overlay.signal_selected.disconnect()
        self.overlay.signal_selected.connect(self._on_region_selected)

    def _clear_screen_history(self):
        """清空当前屏幕上的所有转写与回答记录"""
        if self._current_vision_worker and self._current_vision_worker.isRunning():
            self._current_vision_worker.cancel()
        if self._current_ai_worker and self._current_ai_worker.isRunning():
            self._current_ai_worker.cancel()
        self.browser_answer.clear()
        self.browser_thinking.clear()
        self.browser_thinking.setVisible(False)
        self.progress_bar.setVisible(False)
        self._interview_turn_count = 0
        self._is_first_interview_turn = True
        self.lbl_status.setText("已清空屏幕记录 | 随时可按快捷键开始下一题")

    def _execute_ai_query(self, images_b64: Optional[List[str]] = None, text_query: str = "", header_html: str = "", append_mode: bool = False):
        """核心 AI 请求调度：支持单阶段直出与两阶段双模型流水线联动"""
        base_url = config_manager.get("api_base_url", "")
        api_key = config_manager.get("api_key", "")
        vision_model = config_manager.get("vision_model_name", "Qwen/Qwen3-VL-8B-Instruct")
        main_model = config_manager.get("model_name", "deepseek-ai/DeepSeek-V4.1-Flash")
        use_two_stage = config_manager.get("use_two_stage_pipeline", True)

        # 获取当前预设提示词 (面试提问优先采用 interview_copilot)
        if not images_b64 and text_query:
            preset_key = "interview_copilot"
        else:
            preset_key = config_manager.get("active_prompt_preset", "exam_general")
        system_prompt = config_manager.get("prompts", {}).get(preset_key, "")

        # 清空上轮状态与思考区
        self.browser_thinking.clear()
        self.browser_thinking.setVisible(False)
        self._last_reasoning_text = ""
        self._last_answer_text = ""

        # 未配置 API Key 处理
        if not api_key:
            if not header_html:
                self.browser_answer.setHtml("<span style='color: #b45309; font-weight: bold;'>⚠️ 提示：尚未配置 API Key！请点击右上角 ⚙️ 设置按钮填入大模型凭证。</span>")
                self._open_settings()
            else:
                self.browser_answer.append("<div style='color: #475569; font-size: 12px; margin: 4px 0 8px 0;'>（提问已完整记录在屏，等待下一句...）</div><hr style='border: 0; border-top: 1px dashed rgba(0, 0, 0, 0.25); margin: 12px 0;'>")
                self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)
                history_manager.save_record(
                    record_type="interview",
                    question_text=text_query or "语音提问",
                    answer_text="[仅语音转写上屏，未配置 API Key]",
                    reasoning_text=""
                )
            return

        # 场景 A: 包含截图 且 启用了双模型黄金组合流水线
        if images_b64 and use_two_stage and vision_model:
            self._start_two_stage_pipeline(
                images_b64=images_b64,
                base_url=base_url,
                api_key=api_key,
                vision_model=vision_model,
                main_model=main_model,
                system_prompt=system_prompt,
                header_html=header_html,
                append_mode=append_mode
            )
        else:
            # 场景 B: 纯文本查询 或 单模型直出
            self._start_direct_ai_worker(
                base_url=base_url,
                api_key=api_key,
                model=vision_model if images_b64 else main_model,
                system_prompt=system_prompt,
                user_text=text_query or "请仔细审视题目截图，第一行直接给出【最终答案：选项】，随后给出两句话以内的秒杀逻辑。严禁生成代码（除非明确要求写程序），严格控制在3~4行以内！",
                images_b64=images_b64,
                header_html=header_html,
                append_mode=append_mode
            )

    def _start_two_stage_pipeline(
        self,
        images_b64: List[str],
        base_url: str,
        api_key: str,
        vision_model: str,
        main_model: str,
        system_prompt: str,
        header_html: str = "",
        append_mode: bool = False
    ):
        """双模型黄金组合流水线：
        第 1 步: 视觉大模型 (vision_model) 秒级高精提取图文与数学公式；
        第 2 步: 提取结果自动无缝交由主模型 (main_model) 展开秒杀作答 (答案置顶)。
        """
        if self._current_vision_worker and self._current_vision_worker.isRunning():
            self._current_vision_worker.cancel()
        if self._current_ai_worker and self._current_ai_worker.isRunning():
            self._current_ai_worker.cancel()

        self.lbl_status.setText(f"🔍 [第1阶段] 视觉大模型正在提取图文与公式 ({vision_model})...")
        self.progress_bar.setVisible(True)

        step1_hint = f"""
        <div style="color: #0284c7; font-size: 11px; font-weight: bold; padding: 2px 5px; background: rgba(224, 242, 254, 0.6); border-radius: 3px; margin-bottom: 3px;">
            🔍 视觉模型极速提干中 ({vision_model})...
        </div>
        """
        if append_mode and header_html:
            self.browser_answer.append(header_html + step1_hint)
        else:
            self.browser_answer.setHtml((header_html + step1_hint) if header_html else step1_hint)
        self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)

        def _on_extracted(extracted_text: str):
            self._last_question_text = extracted_text
            clean_q = extracted_text.replace("\n", " ").strip()
            if len(clean_q) > 35:
                clean_q = clean_q[:35] + "..."
            question_badge = f"""
            <div style="color: #475569; font-size: 11px; margin-bottom: 3px; padding: 2px 5px; background: rgba(241, 245, 249, 0.7); border-radius: 3px;">
                <b>[题干]</b> {html.escape(clean_q)}
            </div>
            """
            if append_mode and header_html:
                self.browser_answer.append(question_badge)
            else:
                self.browser_answer.setHtml(question_badge)
            self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)

            # Step 2: 移交主模型极速作答 (答案置顶，绝不滚轮)
            self._start_direct_ai_worker(
                base_url=base_url,
                api_key=api_key,
                model=main_model,
                system_prompt=system_prompt,
                user_text=extracted_text,
                images_b64=None,
                append_to_existing=True
            )

        def _on_extract_error(err_msg: str):
            self.lbl_status.setText(f"⚠️ 视觉提干失败，自动降级为单模型直出: {err_msg}")
            self._start_direct_ai_worker(
                base_url=base_url,
                api_key=api_key,
                model=vision_model or main_model,
                system_prompt=system_prompt,
                user_text="请审视题目截图，第一行直接给出【最终答案：选项】，随后给出两句话以内的秒杀逻辑。严禁生成代码，控制在3~4行以内。",
                images_b64=images_b64,
                header_html=header_html,
                append_mode=append_mode
            )

        self._current_vision_worker = VisionExtractorWorker(
            base_url=base_url,
            api_key=api_key,
            vision_model=vision_model,
            images_b64=images_b64,
            mode="ocr",
            parent=self
        )
        self._current_vision_worker.signal_extracted.connect(_on_extracted)
        self._current_vision_worker.signal_error.connect(_on_extract_error)
        self._current_vision_worker.start()

    def _execute_fine_visual_query(self, image_b64: str):
        """执行行测图形推理 / 复杂图表专属全屏流水线：
        1. 直接全屏超清捕获，调用 32B 深度视觉模型深度剖析微观图形拓扑、对称轴、数量规律及选项差异；
        2. 结构化特征自动交由 DeepSeek 展开逻辑推理与破题（严格遵守精简输出规范，非编程题绝不写代码）。
        """
        base_url = config_manager.get("api_base_url", "")
        api_key = config_manager.get("api_key", "")
        fine_vision_model = config_manager.get("fine_vision_model_name", "Qwen/Qwen3-VL-32B-Instruct")
        main_model = config_manager.get("model_name", "deepseek-ai/DeepSeek-V4.1-Flash")

        # 清空上轮状态与思考区
        self.browser_thinking.clear()
        self.browser_thinking.setVisible(False)
        self._last_reasoning_text = ""
        self._last_answer_text = ""

        if not api_key:
            self.browser_answer.setHtml("<span style='color: #b45309; font-weight: bold;'>⚠️ 提示：尚未配置 API Key！请点击右上角 ⚙️ 设置按钮填入大模型凭证。</span>")
            self._open_settings()
            return

        if self._current_vision_worker and self._current_vision_worker.isRunning():
            self._current_vision_worker.cancel()
        if self._current_ai_worker and self._current_ai_worker.isRunning():
            self._current_ai_worker.cancel()

        self.lbl_status.setText(f"🧩 [精细阶段 1/2] 32B 视觉大模型深度剖析微观图形细节 ({fine_vision_model})...")
        self.progress_bar.setVisible(True)

        step1_banner = f"""
        <div style="color: #6d28d9; font-size: 11px; font-weight: bold; padding: 2px 5px; background: rgba(245, 243, 255, 0.7); border-radius: 3px; margin-bottom: 3px;">
            🧩 32B 深度视觉分析图形拓扑中...
        </div>
        """
        self.browser_answer.setHtml(step1_banner)
        self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)

        def _on_fine_extracted(visual_analysis_text: str):
            self._last_question_text = visual_analysis_text
            card_html = f"""
            <div style="color: #6d28d9; font-size: 11px; margin-bottom: 3px; padding: 2px 5px; background: rgba(245, 243, 255, 0.75); border-radius: 3px;">
                <b>[32B 特征拆解完成]</b> 正在秒杀答案:
            </div>
            """
            self.browser_answer.setHtml(card_html)
            self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)

            # DeepSeek 行测专用逻辑推导 Prompt (严格3~4行以内，答案置顶，绝不滚轮)
            deepseek_system = (
                "你是一位国家级公务员行测与图形推理专家。\n"
                "请仔细根据 32B 视觉模型提取的图形微观特征与选项对比，推导出唯一正确规律与答案。\n"
                "【强制单屏完全显示规范（绝不滑动滚轮）】：\n"
                "1. 第一行必须直接置顶输出：【最终答案：选项】（例如：【最终答案：C】）；\n"
                "2. 随后仅用 1~2 句话（60字以内）写出核心图形规律与秒杀依据；\n"
                "3. 严禁生成代码，严禁废话；全文严格控制在 3 行以内，绝不超出当前窗口！"
            )

            self._start_direct_ai_worker(
                base_url=base_url,
                api_key=api_key,
                model=main_model,
                system_prompt=deepseek_system,
                user_text=f"以下是 Qwen 视觉模型提取的图形微观特征结构化 JSON 数据：\n{visual_analysis_text}\n\n请直接基于上述结构化特征推导规律，第一行置顶输出【最终答案：选项】，随后给出两句话以内的秒杀依据：",
                images_b64=None,
                append_to_existing=True
            )

        def _on_fine_error(err_msg: str):
            self.lbl_status.setText(f"⚠️ 32B 精细视觉分析失败: {err_msg}，正在自动降级...")
            # 降级：直接以全屏图片请求 DeepSeek / 视觉模型
            self._start_direct_ai_worker(
                base_url=base_url,
                api_key=api_key,
                model=fine_vision_model or main_model,
                system_prompt="你是一位行测与逻辑推理专家。第一行直接给出【最终答案：选项】，随后给出两句话以内的秒杀规律。严禁生成代码，控制在3行以内。",
                user_text="请审视截图中题目，第一行直接给出【最终答案：选项】，随后给出两句话以内的秒杀规律：",
                images_b64=[image_b64],
                append_mode=False
            )

        self._current_vision_worker = VisionExtractorWorker(
            base_url=base_url,
            api_key=api_key,
            vision_model=fine_vision_model,
            images_b64=[image_b64],
            mode="fine_visual",
            parent=self
        )
        self._current_vision_worker.signal_extracted.connect(_on_fine_extracted)
        self._current_vision_worker.signal_error.connect(_on_fine_error)
        self._current_vision_worker.start()

    def _start_direct_ai_worker(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_text: str,
        images_b64: Optional[List[str]] = None,
        header_html: str = "",
        append_mode: bool = False,
        append_to_existing: bool = False
    ):
        self._last_question_text = user_text

        if not append_to_existing:
            if append_mode:
                if header_html:
                    self.browser_answer.append(header_html)
            else:
                if header_html:
                    self.browser_answer.setHtml(header_html)
                else:
                    self.browser_answer.clear()

            if append_mode:
                self.browser_answer.append("<div style='color: #0369a1; font-size: 12.5px; font-weight: bold; margin: 6px 0 4px 0;'>💡 AI 应对要点：</div>")
            self.browser_answer.moveCursor(QTextCursor.MoveOperation.End)

        enable_thinking = config_manager.get("enable_thinking", True)
        enable_web_search = config_manager.get("enable_web_search", False)

        mode_tags = []
        if enable_thinking:
            mode_tags.append("🧠思考")
        if enable_web_search:
            mode_tags.append("🌐联网")
        tag_str = f" [{'+'.join(mode_tags)}]" if mode_tags else " [⚡极速]"

        self.lbl_status.setText(f"🚀 AI 正在运算中 ({model}){tag_str}...")
        self.progress_bar.setVisible(True)

        if self._current_ai_worker and self._current_ai_worker.isRunning():
            self._current_ai_worker.cancel()

        self._current_ai_worker = AIStreamWorker(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_text=user_text,
            images_b64=images_b64,
            enable_thinking=enable_thinking,
            enable_web_search=enable_web_search,
            parent=self
        )
        self._current_ai_worker.signal_reasoning.connect(self._on_ai_reasoning)
        self._current_ai_worker.signal_content.connect(self._on_ai_content)
        self._current_ai_worker.signal_finished.connect(self._on_ai_finished)
        self._current_ai_worker.signal_error.connect(self._on_ai_error)
        self._current_ai_worker.start()

    def _on_ai_reasoning(self, chunk: str):
        if not config_manager.get("enable_thinking", False):
            return
        if not self.browser_thinking.isVisible():
            self.browser_thinking.setVisible(True)
            self.thinking_header.setVisible(True)
            self.lbl_thinking_title.setText("🧠 深度思考过程 (▲ 点击折叠)")
        self._last_reasoning_text += chunk
        self.browser_thinking.moveCursor(QTextCursor.MoveOperation.End)
        self.browser_thinking.insertPlainText(chunk)

    def _on_ai_content(self, chunk: str):
        self._last_answer_text += chunk
        cursor = self.browser_answer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        # 始终锁定视图置顶，答案首行始终可见，绝不因光标后移发生滚轮下移
        self.browser_answer.verticalScrollBar().setValue(0)

    def _on_ai_finished(self):
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("✅ 回答完成 | 答案已置顶呈现")
        # 确保视图严格置顶，无需滑动滚轮
        self.browser_answer.verticalScrollBar().setValue(0)
        # 保存至历史记录
        rec_type = "exam" if self._last_pixmaps else "interview"
        history_manager.save_record(
            record_type=rec_type,
            question_text=self._last_question_text,
            answer_text=self._last_answer_text,
            reasoning_text=self._last_reasoning_text,
            image_pixmaps=self._last_pixmaps
        )

    def _on_ai_error(self, err_msg: str):
        self.lbl_status.setText(f"❌ 请求失败: {err_msg}")
        self.progress_bar.setVisible(False)
        self.browser_answer.append(f"\n\n<span style='color: #dc2626; font-weight: bold;'>[错误详情] {err_msg}</span>")

    def _toggle_interview_listener(self):
        """开启/关闭面试内录监听"""
        if self._audio_listener and self._audio_listener.isRunning():
            self._audio_listener.stop()
            self._audio_listener.wait()
            self._audio_listener = None
            self.btn_interview.setText("🎙️ 面试内录")
            self.btn_interview.setStyleSheet("")
            self.lbl_status.setText("已停止面试内录监听")
        else:
            self._audio_listener = InterviewAudioListener(parent=self)
            self._audio_listener.signal_status.connect(lambda s: self.lbl_status.setText(s))
            self._audio_listener.signal_rms.connect(self._on_audio_rms)
            self._audio_listener.signal_transcript.connect(self._on_interview_question)
            self._audio_listener.start()
            self.btn_interview.setText("🛑 监听中...")
            self.btn_interview.setStyleSheet("background-color: #0284c7; color: #ffffff; border: 1px solid #0369a1; font-weight: bold;")
            
            # 首次开启且屏幕为空时展示说明卡片
            if not self.browser_answer.toPlainText().strip():
                self.browser_answer.setHtml("""
                <div style="border: 1px solid rgba(0, 0, 0, 0.12); background: rgba(255, 255, 255, 0.6); border-radius: 8px; padding: 14px; margin-top: 8px;">
                    <div style="color: #0284c7; font-size: 14px; font-weight: bold; margin-bottom: 6px;">
                        🎧 面试内录实时监听 (透明黑字题词模式)
                    </div>
                    <div style="color: #000000; font-size: 12.5px; line-height: 1.7; font-weight: 500;">
                        • <b>界面完全透明</b>：背景隐形透光，纯黑文字浮现，无缝贴合考卷与网页。<br>
                        • <b>鼠标无感穿透</b>：按 <b>Alt+C</b> 开启穿透，鼠标直接点击背后试卷，绝不失焦；再按 <b>Alt+C</b> 解锁。<br>
                        • <b>多轮连续保留</b>：每次转录依次追加在屏，绝不覆盖上一题。
                    </div>
                </div>
                """)

    def _on_audio_rms(self, rms: float):
        """实时显示声卡回环内录的音量跳动，给用户直观的听觉反馈"""
        if self._audio_listener and self._audio_listener.isRunning():
            if rms > 0.002:
                level = min(10, max(1, int(rms * 500)))
                bars = "█" * level + "░" * (10 - level)
                self.lbl_status.setText(f"🎙️ 正在收听对方发言: [{bars}]")

    def _on_interview_question(self, question_text: str):
        """当系统内录识别出面试官新提问时自动触发（多轮持续累加保留）"""
        self._interview_turn_count += 1
        time_str = time.strftime("%H:%M:%S")
        self.lbl_status.setText(f"✅ 转录完成 #{self._interview_turn_count} [{time_str}]: {question_text}")
        self._last_pixmaps = []

        # 如果是首次听到提问，清空初始的使用提示文字
        if self._is_first_interview_turn:
            self.browser_answer.clear()
            self._is_first_interview_turn = False

        card_html = f"""
        <div style="border-left: 4px solid #0284c7; background: rgba(240, 244, 248, 0.5); padding: 8px 12px; border-radius: 5px; margin: 10px 0 6px 0;">
            <div style="color: #0369a1; font-size: 11px; font-weight: bold; margin-bottom: 3px;">
                🎙️ 面试提问 #{self._interview_turn_count} [{time_str}]
            </div>
            <div style="color: #000000; font-size: 15px; font-weight: bold; line-height: 1.5;">
                {question_text}
            </div>
        </div>
        """
        self._execute_ai_query(
            images_b64=None,
            text_query=f"面试官实时提问：{question_text}",
            header_html=card_html,
            append_mode=True
        )

    def _start_auto_typing(self):
        """开始自动模拟打字输入"""
        # 优先读取用户选中的文本，若无选中则使用全部答案文本
        cursor = self.browser_answer.textCursor()
        target_text = cursor.selectedText().strip()
        if not target_text:
            target_text = self._last_answer_text.strip()

        if not target_text:
            QMessageBox.information(self, "提示", "当前没有可供键入的答案文本！")
            return

        wpm = config_manager.get("auto_type_wpm", 85)
        jitter = config_manager.get("auto_type_jitter_ms", 25)

        self.lbl_status.setText("⌨️ 请在 3 秒内将鼠标光标切换并聚焦到目标输入框...")
        
        # 延迟 3 秒给用户时间切换光标到目标输入框
        QTimer.singleShot(3000, lambda: self._do_type_worker(target_text, wpm, jitter))

    def _do_type_worker(self, text: str, wpm: int, jitter: int):
        self.lbl_status.setText(f"正在以 {wpm} WPM 速率模拟人工键入中...")
        self.progress_bar.setVisible(True)

        if self._current_typer_worker and self._current_typer_worker.isRunning():
            self._current_typer_worker.cancel()

        self._current_typer_worker = AutoTyperWorker(text, wpm, jitter, parent=self)
        self._current_typer_worker.signal_progress.connect(
            lambda cur, tot: self.lbl_status.setText(f"键入进度: {cur}/{tot} 字...")
        )
        self._current_typer_worker.signal_finished.connect(
            lambda: [self.lbl_status.setText("✅ 模拟打字输入完成"), self.progress_bar.setVisible(False)]
        )
        self._current_typer_worker.signal_cancelled.connect(
            lambda: [self.lbl_status.setText("已取消键入"), self.progress_bar.setVisible(False)]
        )
        self._current_typer_worker.start()

    def _export_history_docx(self):
        """导出 Word 文档"""
        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出历史答题报告为 Word", "OpenAnswerInk_History.docx", "Word Documents (*.docx)"
        )
        if save_path:
            ok = history_manager.export_to_docx(save_path)
            if ok:
                QMessageBox.information(self, "导出成功", f"历史记录已成功导出至:\n{save_path}")

    def _open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self._apply_styles()
            self._apply_anti_capture()
            self._refresh_toggle_buttons()
