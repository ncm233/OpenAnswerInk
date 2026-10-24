from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from utils.display_affinity import set_window_display_affinity
from core.screen_capture import ScreenCapture

class SelectionOverlay(QWidget):
    """
    全屏透明截图选区窗口。
    具备防录屏亲和性（WDA_EXCLUDEFROMCAPTURE），自身在屏幕共享与录屏软件中同样隐形。
    支持鼠标拖拽选区或两次点击选区。
    """
    signal_selected = pyqtSignal(QRect)
    signal_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start_pos: QPoint = QPoint()
        self._current_pos: QPoint = QPoint()
        self._is_selecting: bool = False

    def start_selection(self):
        # 覆盖所有虚拟显示器区域
        total_rect = ScreenCapture.get_virtual_desktop_rect()
        self.setGeometry(total_rect)
        self.show()
        
        # 激活防录屏（确保截屏选区窗口在共享屏幕中同样隐形）
        set_window_display_affinity(int(self.winId()), True)
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.globalPosition().toPoint()
            self._current_pos = self._start_pos
            self._is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._is_selecting = False
            self.hide()
            self.signal_cancelled.emit()

    def mouseMoveEvent(self, event):
        if self._is_selecting:
            self._current_pos = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._current_pos = event.globalPosition().toPoint()
            self.hide()

            x1 = min(self._start_pos.x(), self._current_pos.x())
            y1 = min(self._start_pos.y(), self._current_pos.y())
            x2 = max(self._start_pos.x(), self._current_pos.x())
            y2 = max(self._start_pos.y(), self._current_pos.y())
            w = x2 - x1
            h = y2 - y1

            if w > 10 and h > 10:
                self.signal_selected.emit(QRect(x1, y1, w, h))
            else:
                self.signal_cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._is_selecting = False
            self.hide()
            self.signal_cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        # 极淡的半透明背景辅助感知（用户可见，录屏隐形）
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        if self._is_selecting:
            x1 = min(self._start_pos.x(), self._current_pos.x()) - self.x()
            y1 = min(self._start_pos.y(), self._current_pos.y()) - self.y()
            w = abs(self._current_pos.x() - self._start_pos.x())
            h = abs(self._current_pos.y() - self._start_pos.y())
            sel_rect = QRect(x1, y1, w, h)

            # 选区高亮清空
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(sel_rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 边框
            pen = QPen(QColor(0, 200, 255, 230), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(sel_rect)

            # 尺寸提示
            info_text = f" {w} x {h} px "
            painter.setPen(Qt.GlobalColor.white)
            painter.fillRect(QRect(x1 + 4, y1 + 4, 80, 20), QColor(0, 0, 0, 180))
            painter.drawText(x1 + 8, y1 + 18, info_text)
