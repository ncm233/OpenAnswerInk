import os
import json
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    # AI 接口配置
    "api_base_url": "https://api.siliconflow.cn/v1",
    "api_key": os.environ.get("OPENAI_API_KEY", ""),  # 请在设置界面配置或通过环境变量传入
    "model_name": "deepseek-ai/DeepSeek-V4.1-Flash",
    "vision_model_name": "Qwen/Qwen3-VL-32B-Instruct",   # 极速视觉提干大模型 (秒级高精 OCR / 公式)
    "fine_vision_model_name": "Qwen/Qwen3-VL-32B-Instruct", # 行测图形推理专用 32B 深度视觉分析模型
    "use_two_stage_pipeline": True,  # 开启双模型黄金组合流水线 (视觉提干 + DeepSeek深度思考答题)
    "temperature": 0.3,
    "stream_mode": True,
    "enable_thinking": False,        # 默认关闭深度思考 (秒出最终结果，绝不啰嗦)
    "enable_web_search": False,      # 是否开启主模型联网思考检索
    
    # 窗口与显示
    "anti_capture_enabled": True,    # WDA_EXCLUDEFROMCAPTURE 防常规录屏与屏幕共享
    "transparent_mode": True,        # 默认透明背景+纯黑文字（防监考/隐形题词板模式）
    "window_opacity": 1.0,           # 窗口文字不透明度 (0.3 ~ 1.0)
    "stays_on_top": True,            # 窗口置顶
    
    # 模拟键入配置
    "auto_type_wpm": 85,             # 键入速率 (字/分)
    "auto_type_jitter_ms": 25,       # 键入随机抖动偏差 (ms)，防止机器节奏检测
    
    # 面试内录配置
    "interview_auto_trigger_sec": 2.2, # 语音静音停顿判定时间
    "interview_speaker_index": 0,    # 录音设备索引
    
    # 快捷键
    "hotkey_region_capture": "alt+a",
    "hotkey_full_capture": "alt+s",
    "hotkey_fine_capture": "alt+w",  # 行测精细图像全屏识别解题键
    "hotkey_multipage_capture": "alt+d",
    "hotkey_interview_toggle": "alt+m",
    "hotkey_auto_type": "alt+t",
    "hotkey_toggle_window": "alt+h",
    "hotkey_toggle_click_through": "alt+c",
    
    # 预设提示词 (严格遵循：答案最先置顶，单屏完全显示，绝不滑动滚轮)
    "prompts": {
        "exam_general": "你是一位顶级全能笔试与公考应试专家。请审视题目并直接给出最简练、精准的解答。\n【强制单屏完全显示规范（绝不滑动滚轮）】：\n1. 第一行必须直接置顶输出：【最终答案：选项/结论】（例如：【最终答案：C】）；\n2. 随后仅用 1~2 句话（60字以内）写出核心秒杀依据与关键排除点；\n3. 严禁生成代码，严禁客套废话与空行；全文严格控制在 3 行以内，确保在当前悬浮窗内一眼看全，绝不超屏！",
        "exam_choice": "你是一位秒杀客观题的选择题专家。\n【极简置顶规范】：\n1. 第一行直接置顶：【最终答案：选项】（例如：【最终答案：B】）；\n2. 随后用 1 句话（40字以内）写出秒杀理由或排除逻辑；\n3. 严禁任何废话，全文严格控制在 2~3 行以内，直接秒杀！",
        "exam_code": "你是一位顶级算法与软件架构专家。仅当需要编写代码时，直接给出最优时间与空间复杂度的完整代码与关键思路，避免多余寒暄。",
        "interview_copilot": "你是一位经验丰富的技术面试导师。当前是面试官的实时提问，请以应聘者第一人称口吻，用条理清晰、专业深刻且符合口语表达的提纲式要点组织回答。突出STAR原则与核心技术深度。",
        "code_explain": "请对选中的代码逻辑进行逐层拆解分析，指出算法复杂度、可能存在的潜在边界Bug及优化空间。"
    },
    "max_tokens": 140,
    "active_prompt_preset": "exam_general"
}

CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "OpenAnswerInk"
CONFIG_FILE = CONFIG_DIR / "config.json"

class ConfigManager:
    def __init__(self):
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 保留用户的 API 凭据与模式偏好，更新提示词预设与防滚轮上限
                    if "prompts" in data:
                        data["prompts"].update(DEFAULT_CONFIG["prompts"])
                    self.config.update(data)
                    if "max_tokens" not in self.config:
                        self.config["max_tokens"] = 140
            except Exception as e:
                print(f"[ConfigManager] 加载配置失败，使用默认配置: {e}")
        else:
            self.save()

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ConfigManager] 保存配置失败: {e}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save()

config_manager = ConfigManager()
