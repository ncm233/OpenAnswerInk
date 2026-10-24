# OpenAnswerInk - 智能笔试与面试领航助手 (开源纯净重构版)

本项目是基于对 **AnswerInk 21.61** 逆向技术分析文档（[AnswerInk_21.61_完整技术栈与实现分析.md](file:///e:/rea/output/doc/AnswerInk_21.61_完整技术栈与实现分析.md)）的深度解构，为解决在线笔试做题、技术面试辅助场景而开发的**100% 纯净、安全、高性能原生 Python/PyQt6 桌面端应用**。

---

## 🎯 核心价值：去粗取精，剔除黑客木马

在原始 AnswerInk 21.61 逆向报告中，揭示了该软件包含严重的灰色 RAT（远程控制木马）隐患：
- ❌ **原版恶意行为**：私自向用户系统注入 `DeskSync.exe` 开机自启后门、静默长轮询回传桌面屏幕流、DPAPI 窃取 Chrome/Edge 密码与 Cookie、读取 Wi-Fi 密码、扫描 `.env` 凭据、甚至盗取微信聊天记录。
- ✅ **OpenAnswerInk 纯净原则**：**100% 剥离并彻底剔除所有后门、间谍与窃密模块**！
- ✅ **透明自主控制**：支持直连主流大模型（DeepSeek、OpenAI、阿里通义千问、硅基流动、本地 Ollama 等），API Key 与数据全本地存储，零中转、零泄露。

---

## 🚀 完整核心功能矩阵

| 功能模块 | 实现技术 | 说明 |
|---|---|---|
| **隐形置顶透明浮窗** | PyQt6 + Windows API | 无边框、半透明、自动顶层看门狗，`WS_EX_NOACTIVATE` 避免抢夺考场焦点 |
| **防常规录屏与投屏** | `SetWindowDisplayAffinity(0x11)` | Windows 10 (19041+) 原生机制，在屏幕共享（腾讯会议/Zoom/浏览器考场）中对考官与录屏**完全隐形**，仅本人可见 |
| **多形态智能截图** | PyQt6 QScreen + 多屏融合 | 支持全屏截屏、无遮罩拖拽选区截屏、长题多页累加暂存合并提交 |
| **视觉与推理大模型** | OpenAI 兼容流式 SSE | 完美支持 DeepSeek-R1 思考链（`reasoning_content`）流式折叠展示 + Markdown 答案极速渲染 |
| **面试系统扬声器内录** | Windows WASAPI Loopback + Whisper | 使用 `soundcard` 捕获考官提问声音（不录环境杂音），带 VAD 停顿判定与实时语音转写 |
| **拟人化自动键入** | Win32 `SendInput` (Unicode + 抖动) | 将答案以自然打字速度模拟输入到指定文本框，带正态随机时延抖动，规避系统作弊节奏检测 |
| **历史归档与报告导出** | `python-docx` 导出 Word | 自动留存历次截图、问题、思考链与答案，一键导出专业排版的 DOCX 报告 |
| **全局全局热键** | `keyboard` 模块 | `Alt+A` 选区截图、`Alt+S` 全屏截图、`Alt+D` 多页累加、`Alt+M` 面试内录、`Alt+T` 自动键入 |

---

## ⌨️ 默认全局快捷键

| 快捷键 | 功能动作 |
|---|---|
| <kbd>Alt + A</kbd> | **区域截图答题**：屏幕拉选框，松开立即提交 AI 解答 |
| <kbd>Alt + S</kbd> | **全屏截图答题**：全屏捕获多显示器题目并提交 AI |
| <kbd>Alt + D</kbd> | **多页题累加截图**：连续截取长试卷、多页代码，点击“立即发送”合并求解 |
| <kbd>Alt + M</kbd> | **面试内录监听切换**：启动/停止系统扬声器声音捕获与面试官提问转写 |
| <kbd>Alt + T</kbd> | **拟人化自动键入**：选中文本后触发，3秒内将光标对准输入框即开始模拟打字 |
| <kbd>Alt + H</kbd> | **老板键 (显示/隐藏浮窗)**：瞬间显示或隐藏整个领航助手窗口 |

---

## 🛠️ 快速启动指南

### 1. 运行依赖要求
- Windows 10 / Windows 11 (建议 19041 以上以获得完整的 `0x11` 防录屏能力)
- Python 3.10+ (已在 Python 3.11 环境完整验证测试通过)

### 2. 双击一键启动
在项目根目录下直接双击运行：
```text
run.bat
```
或通过命令行运行：
```powershell
cd e:\open_answer_ink
python -X utf8 main.py
```

### 3. 初次配置模型（点击右上角 ⚙️ 设置）
- **DeepSeek 官方**：Base URL: `https://api.deepseek.com/v1`，填入你的 API Key，主模型: `deepseek-chat` 或 `deepseek-reasoner`。
- **阿里千问 (DashScope)**：Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`，主模型: `qwen2.5-72b-instruct`，视觉模型: `qwen2.5-vl-72b-instruct`。
- **OpenAI 官方**：Base URL: `https://api.openai.com/v1`，主模型: `gpt-4o`。
- **硅基流动 (SiliconFlow)**：Base URL: `https://api.siliconflow.cn/v1`。

---

## 📁 模块架构一览

```text
e:\open_answer_ink\
  ├── main.py                  # 应用程序主入口、DPI适配与全局热键注册
  ├── config.py                # 集中化持久化配置管理器 (%APPDATA%/OpenAnswerInk/config.json)
  ├── requirements.txt         # 核心依赖清单
  ├── run.bat                  # 一键启动批处理脚本
  │
  ├── core/
  │   ├── screen_capture.py    # 跨屏与高DPI截图、选区裁剪、多页暂存队列
  │   ├── ai_client.py         # OpenAI兼容流式多模态客户端（支持DeepSeek-R1思考链）
  │   ├── audio_capture.py     # WASAPI扬声器回环录制、VAD断句与Faster-Whisper识别
  │   ├── keyboard_typer.py    # Win32 SendInput Unicode拟人化键入引擎
  │   ├── history_manager.py   # 本地记录持久化与 Word (.docx) 导出排版
  │   └── hotkey_manager.py    # 线程安全的全局热键管理器
  │
  ├── ui/
  │   ├── main_window.py       # PyQt6 暗黑毛玻璃半透明浮窗、流式回答展示、思考链折叠
  │   ├── selection_overlay.py # 防捕获的全屏无缝透明选区画布
  │   └── settings_dialog.py   # 多厂商预设、防录屏开关、透明度、WPM打字速度调节
  │
  └── utils/
      └── display_affinity.py  # SetWindowDisplayAffinity (0x11 / 0x01) 底层 Win32 封装
```
