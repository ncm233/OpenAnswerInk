from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QCheckBox, QTextEdit,
    QTabWidget, QWidget, QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt
from config import config_manager

class SettingsDialog(QDialog):
    """设置对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ OpenAnswerInk 参数与模型设置")
        self.resize(540, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QLabel {
                color: #cfd2dc;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #2b2b36;
                color: #ffffff;
                border: 1px solid #3d3d4e;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #00a6ed;
            }
            QPushButton {
                background-color: #2e3856;
                color: #ffffff;
                border: 1px solid #3f4d75;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b486e;
                border-color: #00a6ed;
            }
            QPushButton#saveBtn {
                background-color: #00875a;
                border-color: #00a86b;
            }
            QPushButton#saveBtn:hover {
                background-color: #00a86b;
            }
            QTabWidget::pane {
                border: 1px solid #3d3d4e;
                background-color: #23232c;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #1e1e24;
                color: #a0a0b0;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #23232c;
                color: #00d2ff;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(self)

        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        # Tab 1: AI 模型配置
        tab_ai = QWidget()
        form_ai = QFormLayout(tab_ai)
        form_ai.setSpacing(12)

        self.combo_preset = QComboBox()
        self.combo_preset.addItems(["自定义服务", "DeepSeek 官方", "OpenAI 官方", "阿里千问 (DashScope)", "硅基流动 (SiliconFlow)"])
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        form_ai.addRow("厂商快速预设:", self.combo_preset)

        self.edit_base_url = QLineEdit(config_manager.get("api_base_url", ""))
        form_ai.addRow("API Base URL:", self.edit_base_url)

        self.edit_api_key = QLineEdit(config_manager.get("api_key", ""))
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        btn_show_key = QPushButton("显示/隐藏")
        btn_show_key.setFixedWidth(80)
        btn_show_key.clicked.connect(self._toggle_key_echo)
        row_key = QHBoxLayout()
        row_key.addWidget(self.edit_api_key)
        row_key.addWidget(btn_show_key)
        form_ai.addRow("API Key:", row_key)

        self.edit_model = QLineEdit(config_manager.get("model_name", "deepseek-chat"))
        form_ai.addRow("主模型代号:", self.edit_model)

        self.edit_vision_model = QLineEdit(config_manager.get("vision_model_name", "gpt-4o"))
        form_ai.addRow("常规极速视觉模型 (8B):", self.edit_vision_model)

        self.edit_fine_vision_model = QLineEdit(config_manager.get("fine_vision_model_name", "Qwen/Qwen3-VL-32B-Instruct"))
        form_ai.addRow("行测精细识图模型 (32B):", self.edit_fine_vision_model)

        self.check_two_stage = QCheckBox("开启双模型流水线 (视觉大模型秒级提干 + 主模型深度思考答题)")
        self.check_two_stage.setChecked(config_manager.get("use_two_stage_pipeline", True))
        self.check_two_stage.setStyleSheet("color: #f59e0b; font-weight: bold;")
        form_ai.addRow("双模型流水线:", self.check_two_stage)

        self.check_thinking = QCheckBox("开启主模型深度思考 (输出思维链推导，适合复杂难题/代码/问答)")
        self.check_thinking.setChecked(config_manager.get("enable_thinking", False))
        self.check_thinking.setStyleSheet("color: #38bdf8; font-weight: bold;")
        form_ai.addRow("深度思考模式:", self.check_thinking)

        self.check_web_search = QCheckBox("开启主模型联网思考检索 (实时搜索最新知识与时事，动态分析)")
        self.check_web_search.setChecked(config_manager.get("enable_web_search", False))
        self.check_web_search.setStyleSheet("color: #4ade80; font-weight: bold;")
        form_ai.addRow("联网思考检索:", self.check_web_search)

        tabs.addTab(tab_ai, "🤖 AI 模型与鉴权")

        # Tab 2: 窗口防录屏与打字
        tab_sys = QWidget()
        form_sys = QFormLayout(tab_sys)
        form_sys.setSpacing(12)

        self.check_anti_capture = QCheckBox("开启防常规录屏与投屏 (WDA_EXCLUDEFROMCAPTURE)")
        self.check_anti_capture.setChecked(config_manager.get("anti_capture_enabled", True))
        self.check_anti_capture.setStyleSheet("color: #00e5ff; font-weight: bold;")
        form_sys.addRow("防抓取隐形:", self.check_anti_capture)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(30, 100)
        self.slider_opacity.setValue(int(config_manager.get("window_opacity", 0.94) * 100))
        self.label_opacity = QLabel(f"{self.slider_opacity.value()}%")
        self.slider_opacity.valueChanged.connect(lambda v: self.label_opacity.setText(f"{v}%"))
        row_op = QHBoxLayout()
        row_op.addWidget(self.slider_opacity)
        row_op.addWidget(self.label_opacity)
        form_sys.addRow("窗口不透明度:", row_op)

        self.slider_wpm = QSlider(Qt.Orientation.Horizontal)
        self.slider_wpm.setRange(30, 180)
        self.slider_wpm.setValue(config_manager.get("auto_type_wpm", 85))
        self.label_wpm = QLabel(f"{self.slider_wpm.value()} WPM")
        self.slider_wpm.valueChanged.connect(lambda v: self.label_wpm.setText(f"{v} WPM"))
        row_wpm = QHBoxLayout()
        row_wpm.addWidget(self.slider_wpm)
        row_wpm.addWidget(self.label_wpm)
        form_sys.addRow("自动模拟打字速率:", row_wpm)

        tabs.addTab(tab_sys, "🛡️ 防录屏与键入")

        # Tab 3: 提示词设定
        tab_prompts = QWidget()
        layout_prompts = QVBoxLayout(tab_prompts)

        self.combo_prompt_preset = QComboBox()
        self.combo_prompt_preset.addItems([
            "exam_general (全能应试秒杀 - 推荐)",
            "exam_choice (客观选择题)",
            "exam_code (笔试编程与算法)",
            "interview_copilot (面试领航)",
            "code_explain (代码分析)"
        ])
        active_preset = config_manager.get("active_prompt_preset", "exam_general")
        for i in range(self.combo_prompt_preset.count()):
            if self.combo_prompt_preset.itemText(i).startswith(active_preset):
                self.combo_prompt_preset.setCurrentIndex(i)
                break
        self.combo_prompt_preset.currentIndexChanged.connect(self._on_prompt_preset_switched)
        layout_prompts.addWidget(QLabel("选择当前生效的提示词预设:"))
        layout_prompts.addWidget(self.combo_prompt_preset)

        self.edit_prompt_content = QTextEdit()
        layout_prompts.addWidget(self.edit_prompt_content)
        self._load_prompt_content()

        tabs.addTab(tab_prompts, "📝 提示词定制")

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 保存配置")
        btn_save.setObjectName("saveBtn")
        btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _toggle_key_echo(self):
        if self.edit_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_preset_changed(self, idx: int):
        presets = {
            1: ("https://api.deepseek.com/v1", "deepseek-chat", "gpt-4o"),
            2: ("https://api.openai.com/v1", "gpt-4o", "gpt-4o"),
            3: ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen2.5-72b-instruct", "qwen2.5-vl-72b-instruct"),
            4: ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V4.1-Flash", "Qwen/Qwen3-VL-8B-Instruct")
        }
        if idx in presets:
            url, model, vision = presets[idx]
            self.edit_base_url.setText(url)
            self.edit_model.setText(model)
            self.edit_vision_model.setText(vision)

    def _load_prompt_content(self):
        prompts = config_manager.get("prompts", {})
        cur = self.combo_prompt_preset.currentText().split()[0]
        self.edit_prompt_content.setPlainText(prompts.get(cur, ""))

    def _on_prompt_preset_switched(self):
        self._load_prompt_content()

    def _save_settings(self):
        config_manager.set("api_base_url", self.edit_base_url.text().strip())
        config_manager.set("api_key", self.edit_api_key.text().strip())
        config_manager.set("model_name", self.edit_model.text().strip())
        config_manager.set("vision_model_name", self.edit_vision_model.text().strip())
        config_manager.set("fine_vision_model_name", self.edit_fine_vision_model.text().strip())
        config_manager.set("use_two_stage_pipeline", self.check_two_stage.isChecked())
        config_manager.set("enable_thinking", self.check_thinking.isChecked())
        config_manager.set("enable_web_search", self.check_web_search.isChecked())
        config_manager.set("anti_capture_enabled", self.check_anti_capture.isChecked())
        config_manager.set("window_opacity", self.slider_opacity.value() / 100.0)
        config_manager.set("auto_type_wpm", self.slider_wpm.value())

        # 保存当前提示词
        cur_preset = self.combo_prompt_preset.currentText().split()[0]
        prompts = config_manager.get("prompts", {})
        prompts[cur_preset] = self.edit_prompt_content.toPlainText().strip()
        config_manager.set("prompts", prompts)
        config_manager.set("active_prompt_preset", cur_preset)

        QMessageBox.information(self, "成功", "设置已保存！")
        self.accept()
