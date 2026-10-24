import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow
from core.hotkey_manager import HotkeyManager

def main():
    # 针对 Windows 高 DPI 屏幕适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("OpenAnswerInk")

    window = MainWindow()
    window.show()

    # 初始化并连接全局热键
    hotkey_mgr = HotkeyManager()
    hotkey_mgr.signal_region_capture.connect(window.trigger_region_capture)
    hotkey_mgr.signal_full_capture.connect(window.trigger_fullscreen_capture)
    hotkey_mgr.signal_fine_capture.connect(window.trigger_fine_visual_capture)
    hotkey_mgr.signal_multipage_capture.connect(window.trigger_multipage_capture)
    hotkey_mgr.signal_interview_toggle.connect(window._toggle_interview_listener)
    hotkey_mgr.signal_auto_type.connect(window._start_auto_typing)
    
    # 连接 Alt+H 一键唤起 / 老板键隐藏
    hotkey_mgr.signal_toggle_window.connect(window.wake_up_or_toggle)
    
    # 连接 Alt+C 鼠标点击穿透 / 防失焦无感切换
    hotkey_mgr.signal_toggle_click_through.connect(window.toggle_click_through)
    
    hotkey_mgr.start()

    app.aboutToQuit.connect(hotkey_mgr.stop)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
