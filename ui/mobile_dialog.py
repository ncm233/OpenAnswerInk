import io
import qrcode
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QApplication
)
from PyQt6.QtGui import QPixmap, QImage, QFont
from PyQt6.QtCore import Qt, QTimer
from core.lan_bridge import lan_bridge_server

class MobileSyncDialog(QDialog):
    """手机端实时同步扫码与连接指引窗口"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 手机端实时同步连接 (考场霸屏被压专用)")
        self.setFixedSize(450, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #f4f4f5;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #f4f4f5;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border-color: #0284c7;
            }
            QPushButton#btnCopy {
                background-color: #0284c7;
                border-color: #0369a1;
                color: white;
            }
            QPushButton#btnCopy:hover {
                background-color: #0369a1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 标题
        title_lbl = QLabel("📱 手机端实时答题同步")
        title_lbl.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        sub_title = QLabel("解决考场客户端“全屏独占/霸屏/防切屏”压制浮窗的终极方案")
        sub_title.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        sub_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_title)

        # 二维码展示区
        qr_frame = QFrame()
        qr_frame.setStyleSheet("background: white; border-radius: 12px; padding: 10px;")
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_qr_pixmap()
        qr_layout.addWidget(self.lbl_qr)

        layout.addWidget(qr_frame, 0, Qt.AlignmentFlag.AlignCenter)

        # 网址展示
        self.url_str = lan_bridge_server.get_mobile_url()
        self.lbl_url = QLabel(f"手机浏览器访问：<b style='color:#38bdf8;'>{self.url_str}</b>")
        self.lbl_url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_url.setStyleSheet("font-size: 13px; margin-top: 4px;")
        layout.addWidget(self.lbl_url)

        # 实时在线状态
        self.lbl_status = QLabel("⚪ 等待手机连接...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #eab308; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 复制链接")
        btn_copy.setObjectName("btnCopy")
        btn_copy.clicked.connect(self._copy_link)
        btn_layout.addWidget(btn_copy)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        # 说明卡片
        tips_box = QFrame()
        tips_box.setStyleSheet("background: rgba(39, 39, 42, 0.6); border-radius: 8px; padding: 10px 12px;")
        t_layout = QVBoxLayout(tips_box)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(4)

        t1 = QLabel("<b>• 局域网直连</b>：确保手机与电脑连同一个 Wi-Fi（或手机开热点给电脑）")
        t1.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        t_layout.addWidget(t1)

        t2 = QLabel("<b>• 霸屏应对</b>：当电脑被考试软件全屏遮挡时，按 <b>Alt+S</b> 或手机点按钮，答案瞬间同步到手机")
        t2.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        t_layout.addWidget(t2)

        t3 = QLabel("<b>• 屏幕防熄屏</b>：手机端已内置自动 WakeLock 锁屏防止，并支持震动提醒")
        t3.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        t_layout.addWidget(t3)

        layout.addWidget(tips_box)

        # 定时刷新连接状态
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_status)
        self._timer.start(1000)
        self._update_status()

    def _load_qr_pixmap(self):
        try:
            qr = qrcode.QRCode(box_size=5, border=1)
            qr.add_data(lan_bridge_server.get_mobile_url())
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qimg = QImage()
            qimg.loadFromData(buf.getvalue())
            self.lbl_qr.setPixmap(QPixmap.fromImage(qimg))
        except Exception as e:
            self.lbl_qr.setText(f"二维码生成失败: {e}")

    def _update_status(self):
        count = lan_bridge_server.get_subscriber_count()
        if count > 0:
            self.lbl_status.setText(f"🟢 手机已成功连接 (在线设备: {count} 台) | 实时就绪")
            self.lbl_status.setStyleSheet("color: #22c55e; font-size: 12px; font-weight: bold;")
        else:
            self.lbl_status.setText("⚪ 等待手机连接 (请用手机浏览器扫码打开)...")
            self.lbl_status.setStyleSheet("color: #eab308; font-size: 12px; font-weight: bold;")

    def _copy_link(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.url_str)
        QMessageBox.information(self, "提示", f"已复制手机端访问地址至剪贴板：\n{self.url_str}")
