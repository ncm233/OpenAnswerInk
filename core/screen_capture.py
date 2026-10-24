import io
import base64
from typing import List, Tuple, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QGuiApplication, QPixmap, QPainter, QImage
from PyQt6.QtCore import Qt, QRect, QBuffer, QIODevice, QPoint

class MultiPageQueue:
    """多页截图累积暂存队列"""
    def __init__(self):
        self._pages_b64: List[str] = []
        self._thumbnails: List[QPixmap] = []

    def add_page(self, b64_str: str, pixmap: QPixmap):
        self._pages_b64.append(b64_str)
        thumb = pixmap.scaled(120, 80)
        self._thumbnails.append(thumb)

    def get_pages(self) -> List[str]:
        return list(self._pages_b64)

    def get_thumbnails(self) -> List[QPixmap]:
        return list(self._thumbnails)

    def clear(self):
        self._pages_b64.clear()
        self._thumbnails.clear()

    def count(self) -> int:
        return len(self._pages_b64)

multi_page_queue = MultiPageQueue()

class ScreenCapture:
    """高精度跨屏幕 DPI 自适应截图管理器"""
    
    @staticmethod
    def get_virtual_desktop_rect() -> QRect:
        """获取包含所有物理显示器的虚拟屏幕大矩形"""
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)
        total_rect = QRect()
        for s in screens:
            total_rect = total_rect.united(s.geometry())
        return total_rect

    @classmethod
    def capture_fullscreen(cls) -> Tuple[QPixmap, str]:
        """抓取全屏 (QPixmap, Base64_JPEG_DataURL)"""
        screens = QGuiApplication.screens()
        if not screens:
            raise RuntimeError("未检测到可用显示设备")

        if len(screens) == 1:
            pixmap = screens[0].grabWindow(0)
        else:
            virtual_rect = cls.get_virtual_desktop_rect()
            pixmap = QPixmap(virtual_rect.size())
            pixmap.fill()
            painter = QPainter(pixmap)
            for s in screens:
                screen_pix = s.grabWindow(0)
                geo = s.geometry()
                offset_x = geo.x() - virtual_rect.x()
                offset_y = geo.y() - virtual_rect.y()
                painter.drawPixmap(offset_x, offset_y, screen_pix)
            painter.end()

        b64 = cls.pixmap_to_base64(pixmap)
        return pixmap, b64

    @classmethod
    def capture_fullscreen_hq(cls) -> Tuple[QPixmap, str]:
        """抓取精细全屏截图（行测图形推理微观拓扑，尺寸优化在 1440 像素以内，大幅减少 ViT Tokens）"""
        full_pix, _ = cls.capture_fullscreen()
        b64 = cls.pixmap_to_base64(full_pix, format="JPEG", quality=85, max_dimension=1440)
        return full_pix, b64

    @classmethod
    def capture_region(cls, rect: QRect) -> Tuple[QPixmap, str]:
        """抓取指定物理选区"""
        screens = QGuiApplication.screens()
        if not screens:
            raise RuntimeError("未检测到可用显示设备")

        full_pix, _ = cls.capture_fullscreen()
        virtual_rect = cls.get_virtual_desktop_rect()

        rel_x = rect.x() - virtual_rect.x()
        rel_y = rect.y() - virtual_rect.y()
        rel_w = rect.width()
        rel_h = rect.height()

        rel_x = max(0, min(rel_x, full_pix.width() - 1))
        rel_y = max(0, min(rel_y, full_pix.height() - 1))
        rel_w = max(10, min(rel_w, full_pix.width() - rel_x))
        rel_h = max(10, min(rel_h, full_pix.height() - rel_y))

        cropped = full_pix.copy(rel_x, rel_y, rel_w, rel_h)
        b64 = cls.pixmap_to_base64(cropped)
        return cropped, b64

    @staticmethod
    def pixmap_to_base64(pixmap: QPixmap, format: str = "JPEG", quality: int = 80, max_dimension: int = 1280) -> str:
        """将 QPixmap 转为 base64 Data URL（尺寸上限 1280px，质量 80，兼顾 100% OCR 清晰度与极速上传）"""
        if pixmap.isNull():
            return ""

        target_pix = pixmap
        w, h = pixmap.width(), pixmap.height()

        if w < 32 or h < 32:
            target_pix = pixmap.scaled(max(32, w), max(32, h), Qt.AspectRatioMode.IgnoreAspectRatio)
            w, h = target_pix.width(), target_pix.height()

        # 尺寸限制在 max_dimension（1280），将 Vision Tokens 压缩 70% 以上，显著加速大模型 Prefill
        if w > max_dimension or h > max_dimension:
            target_pix = target_pix.scaled(
                max_dimension,
                max_dimension,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        target_pix.save(buffer, format, quality)
        raw_bytes = buffer.data().data()
        encoded = base64.b64encode(raw_bytes).decode("ascii")
        mime = "image/jpeg" if format.upper() in ("JPEG", "JPG") else "image/png"
        return f"data:{mime};base64,{encoded}"
