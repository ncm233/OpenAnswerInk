import keyboard
from PyQt6.QtCore import QObject, pyqtSignal
from config import config_manager

class HotkeyManager(QObject):
    """全局热键监听与 Qt 线程安全分发器"""
    signal_region_capture = pyqtSignal()
    signal_full_capture = pyqtSignal()
    signal_fine_capture = pyqtSignal()
    signal_multipage_capture = pyqtSignal()
    signal_interview_toggle = pyqtSignal()
    signal_auto_type = pyqtSignal()
    signal_toggle_window = pyqtSignal()
    signal_toggle_click_through = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._registered = False

    def start(self):
        if self._registered:
            return
        
        try:
            hk_region = config_manager.get("hotkey_region_capture", "alt+a")
            hk_full = config_manager.get("hotkey_full_capture", "alt+s")
            hk_fine = config_manager.get("hotkey_fine_capture", "alt+w")
            hk_multi = config_manager.get("hotkey_multipage_capture", "alt+d")
            hk_interview = config_manager.get("hotkey_interview_toggle", "alt+m")
            hk_typer = config_manager.get("hotkey_auto_type", "alt+t")
            hk_toggle = config_manager.get("hotkey_toggle_window", "alt+h")
            hk_click_through = config_manager.get("hotkey_toggle_click_through", "alt+c")

            keyboard.add_hotkey(hk_region, lambda: self.signal_region_capture.emit())
            keyboard.add_hotkey(hk_full, lambda: self.signal_full_capture.emit())
            keyboard.add_hotkey(hk_fine, lambda: self.signal_fine_capture.emit())
            keyboard.add_hotkey(hk_multi, lambda: self.signal_multipage_capture.emit())
            keyboard.add_hotkey(hk_interview, lambda: self.signal_interview_toggle.emit())
            keyboard.add_hotkey(hk_typer, lambda: self.signal_auto_type.emit())
            keyboard.add_hotkey(hk_toggle, lambda: self.signal_toggle_window.emit())
            keyboard.add_hotkey(hk_click_through, lambda: self.signal_toggle_click_through.emit())

            self._registered = True
            print(f"[HotkeyManager] 全局热键已注册: 选区({hk_region}), 全屏({hk_full}), 精细({hk_fine}), 多页({hk_multi}), 面试({hk_interview}), 键入({hk_typer}), 穿透({hk_click_through})")
        except Exception as e:
            print(f"[HotkeyManager] 注册热键失败: {e}")

    def stop(self):
        if self._registered:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            self._registered = False
