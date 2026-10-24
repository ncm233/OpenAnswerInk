import time
import random
import ctypes
from ctypes import wintypes
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal

user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t)
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT)
    ]

def send_unicode_char(char: str):
    """通过 Win32 SendInput 发送单个 Unicode 字符（支持中英文与符号）"""
    code = ord(char)
    
    # 特殊处理换行符 \n
    if char == '\n':
        # VK_RETURN = 0x0D
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki.wVk = 0x0D
        inputs[0].ki.dwFlags = 0
        
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki.wVk = 0x0D
        inputs[1].ki.dwFlags = KEYEVENTF_KEYUP
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        return

    # 按下
    inp_down = INPUT()
    inp_down.type = INPUT_KEYBOARD
    inp_down.ki.wVk = 0
    inp_down.ki.wScan = code
    inp_down.ki.dwFlags = KEYEVENTF_UNICODE
    
    # 释放
    inp_up = INPUT()
    inp_up.type = INPUT_KEYBOARD
    inp_up.ki.wVk = 0
    inp_up.ki.wScan = code
    inp_up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
    
    inputs = (INPUT * 2)(inp_down, inp_up)
    user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

class AutoTyperWorker(QThread):
    """后台模拟打字工作线程，带拟人化节奏随机抖动"""
    signal_progress = pyqtSignal(int, int)  # (current, total)
    signal_finished = pyqtSignal()
    signal_cancelled = pyqtSignal()

    def __init__(self, text: str, wpm: int = 80, jitter_ms: int = 25, parent=None):
        super().__init__(parent)
        self.text = text
        self.wpm = max(20, min(240, wpm))
        self.jitter_ms = jitter_ms
        self._is_cancelled = False
        self._is_paused = False

    def cancel(self):
        self._is_cancelled = True

    def toggle_pause(self):
        self._is_paused = not self._is_paused

    def run(self):
        # 根据 WPM 计算平均每字符击键延迟 (通常一个单词约 5 个字符)
        # CPM = WPM * 5; 每字符平均毫秒数 = 60000 / CPM
        cpm = self.wpm * 5
        base_delay_sec = 60.0 / cpm

        total = len(self.text)
        for i, char in enumerate(self.text):
            if self._is_cancelled:
                self.signal_cancelled.emit()
                return

            while self._is_paused and not self._is_cancelled:
                time.sleep(0.1)

            send_unicode_char(char)
            self.signal_progress.emit(i + 1, total)

            # 拟人化抖动：高斯或均匀分布微调延迟
            jitter = (random.randint(-self.jitter_ms, self.jitter_ms)) / 1000.0
            actual_delay = max(0.015, base_delay_sec + jitter)
            
            # 遇到标点符号或换行适度停顿更长一点，模仿人工思索
            if char in ('\n', '。', '.', ';', '；', '}'):
                actual_delay += random.uniform(0.1, 0.25)

            time.sleep(actual_delay)

        self.signal_finished.emit()
