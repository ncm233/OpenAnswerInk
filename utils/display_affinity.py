import sys
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

WDA_NONE = 0x00
WDA_MONITOR = 0x01
WDA_EXCLUDEFROMCAPTURE = 0x11

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000

def get_windows_build() -> int:
    return sys.getwindowsversion().build

def set_window_display_affinity(hwnd: int, enable: bool = True) -> bool:
    """
    Sets window display affinity to exclude it from capture/recordings.
    Uses WDA_EXCLUDEFROMCAPTURE (0x11) on Windows 10 build 19041+,
    with fallback to WDA_MONITOR (0x01).
    """
    if not hwnd:
        return False

    target_affinity = WDA_EXCLUDEFROMCAPTURE if enable else WDA_NONE
    build = get_windows_build()

    # For layered transparent windows, temporarily clear WS_EX_LAYERED if needed
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    has_layered = bool(ex_style & WS_EX_LAYERED)
    if has_layered and enable:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_LAYERED)

    success = False
    if build >= 19041 and enable:
        res = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        if res != 0:
            success = True

    if not success and enable:
        # Fallback to WDA_MONITOR
        res = user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
        success = bool(res != 0)
    elif not enable:
        res = user32.SetWindowDisplayAffinity(hwnd, WDA_NONE)
        success = bool(res != 0)

    # Restore WS_EX_LAYERED if it was present
    if has_layered and enable:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        # Redraw
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027) # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED

    # Verify
    current_affinity = wintypes.DWORD()
    if user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(current_affinity)):
        actual = current_affinity.value
        return actual == target_affinity or (enable and actual in (WDA_EXCLUDEFROMCAPTURE, WDA_MONITOR))

    return success

def get_current_affinity(hwnd: int) -> int:
    current = wintypes.DWORD()
    if user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(current)):
        return current.value
    return -1
