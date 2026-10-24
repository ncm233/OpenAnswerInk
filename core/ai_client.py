import json
import httpx
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal

class AIStreamWorker(QThread):
    """异步大模型流式推理与思维链工作线程"""
    signal_reasoning = pyqtSignal(str)   # 思考过程 chunk
    signal_content = pyqtSignal(str)     # 正式回答 chunk
    signal_finished = pyqtSignal()       # 推理结束
    signal_error = pyqtSignal(str)       # 错误信息

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_text: str,
        images_b64: Optional[List[str]] = None,
        temperature: float = 0.3,
        enable_thinking: bool = False,
        enable_web_search: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.user_text = user_text
        self.images_b64 = images_b64 or []
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.enable_web_search = enable_web_search
        self._is_cancelled = False
        self._active_response = None
        self._client = None

    def cancel(self):
        self._is_cancelled = True
        if self._active_response is not None:
            try:
                self._active_response.close()
            except Exception:
                pass
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    def run(self):
        system_content = self.system_prompt or ""
        if self.enable_web_search:
            web_note = (
                "\n\n【联网检索模式已开启】\n"
                "可结合实时互联网最新知识补充推导事实，但依然必须严格遵守字数与单屏行数限制！"
            )
            system_content = (system_content + web_note) if system_content else web_note.strip()

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})

        user_content: List[Dict[str, Any]] = []
        if self.user_text:
            user_content.append({"type": "text", "text": self.user_text})

        for img in self.images_b64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": img
                }
            })

        if not self.images_b64:
            messages.append({"role": "user", "content": self.user_text})
        else:
            messages.append({"role": "user", "content": user_content})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 严格限制生成长度：客观笔试题 140 tokens，1 秒内直接秒杀，物理级杜绝超屏滚轮
        if "interview" in system_content or "面试" in system_content:
            max_tokens_val = 450
        elif "code" in system_content or "代码" in system_content:
            max_tokens_val = 600
        else:
            max_tokens_val = 140

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": self.temperature,
            "enable_thinking": self.enable_thinking,
            "max_tokens": max_tokens_val
        }
        if self.enable_web_search:
            payload["enable_search"] = True

        def _process_stream(client_inst, target_payload):
            try:
                with client_inst.stream("POST", url, headers=headers, json=target_payload) as response:
                    self._active_response = response
                    if response.status_code == 400:
                        err_text = response.read().decode("utf-8", errors="replace")
                        if ("enable_thinking" in err_text or "enable_search" in err_text or "extra" in err_text.lower()) and ("enable_thinking" in target_payload or "enable_search" in target_payload):
                            fallback_payload = target_payload.copy()
                            fallback_payload.pop("enable_thinking", None)
                            fallback_payload.pop("enable_search", None)
                            return _process_stream(client_inst, fallback_payload)
                        self.signal_error.emit(f"HTTP {response.status_code}: {err_text}")
                        return False
                    elif response.status_code != 200:
                        err_text = response.read().decode("utf-8", errors="replace")
                        self.signal_error.emit(f"HTTP {response.status_code}: {err_text}")
                        return False

                    for line in response.iter_lines():
                        if self._is_cancelled:
                            try:
                                response.close()
                            except Exception:
                                pass
                            break
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                try:
                                    response.close()
                                except Exception:
                                    pass
                                break
                            try:
                                chunk = json.loads(raw_data)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})

                                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                                if reasoning and self.enable_thinking:
                                    self.signal_reasoning.emit(reasoning)

                                content = delta.get("content")
                                if content:
                                    self.signal_content.emit(content)

                                finish_reason = choices[0].get("finish_reason")
                                if finish_reason in ("stop", "length"):
                                    try:
                                        response.close()
                                    except Exception:
                                        pass
                                    break

                            except json.JSONDecodeError:
                                continue
                    return True
            except httpx.RequestError as re:
                if self._is_cancelled:
                    return False
                raise re

        try:
            with httpx.Client(timeout=45.0) as client:
                self._client = client
                ok = _process_stream(client, payload)

            if not self._is_cancelled and ok:
                self.signal_finished.emit()

        except Exception as e:
            if not self._is_cancelled:
                self.signal_error.emit(f"网络请求异常: {str(e)}")


class VisionExtractorWorker(QThread):
    """视觉大模型提干工作线程"""
    signal_extracted = pyqtSignal(str)   # 提取成功
    signal_error = pyqtSignal(str)       # 提取失败
    signal_status = pyqtSignal(str)      # 状态提示

    def __init__(
        self,
        base_url: str,
        api_key: str,
        vision_model: str,
        images_b64: List[str],
        mode: str = "ocr",
        custom_prompt: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.vision_model = vision_model
        self.images_b64 = images_b64
        self.mode = mode
        self.custom_prompt = custom_prompt
        self._is_cancelled = False
        self._active_response = None
        self._client = None

    def cancel(self):
        self._is_cancelled = True
        if self._active_response is not None:
            try:
                self._active_response.close()
            except Exception:
                pass
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    def run(self):
        if not self.images_b64:
            self.signal_error.emit("未提供需要识别的图片")
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        if self.custom_prompt:
            prompt_text = self.custom_prompt
        elif self.mode == "fine_visual":
            prompt_text = (
                "你是一个专业公考行测图形推理的视觉特征提取器。不要开启 Thinking，不要输出任何长篇解题过程。\n"
                "请严格审视图片，仅提取图形的客观微观特征并输出标准结构化 JSON（严格不要输出 markdown 代码块外的任何文字）：\n"
                "{\n"
                '  "layout": {\n'
                '    "type": "3x3_matrix",\n'
                '    "missing": "r3c3"\n'
                '  },\n'
                '  "panels": [\n'
                '    {\n'
                '      "id": "r1c1",\n'
                '      "shape_count": 3,\n'
                '      "black_count": 1,\n'
                '      "directions": [0, 90, 180],\n'
                '      "closed_regions": 2,\n'
                '      "intersection_count": 1,\n'
                '      "symmetry": "vertical",\n'
                '      "relative_positions": ["circle_inside_square"]\n'
                '    }\n'
                '  ],\n'
                '  "options": [\n'
                '    {"id": "A", "shape_count": 0, "black_count": 0, "symmetry": "none", "features": "..."},\n'
                '    {"id": "B", "shape_count": 0, "black_count": 0, "symmetry": "none", "features": "..."},\n'
                '    {"id": "C", "shape_count": 0, "black_count": 0, "symmetry": "none", "features": "..."},\n'
                '    {"id": "D", "shape_count": 0, "black_count": 0, "symmetry": "none", "features": "..."}\n'
                '  ],\n'
                '  "candidate_rules": [\n'
                '    "第三格为前两格异或叠加"\n'
                '  ],\n'
                '  "uncertain_fields": [],\n'
                '  "visual_confidence": 0.95\n'
                "}\n"
                "【关键核心必须包含字段】：\n"
                "- 图形数量 (shape_count)\n"
                "- 黑白/填充 (black_count)\n"
                "- 方向与角度 (directions)\n"
                "- 相对位置 (relative_positions)\n"
                "- 封闭区域 (closed_regions)\n"
                "- 交点 (intersection_count)\n"
                "- 对称轴 (symmetry)\n"
                "- 叠加、相减、异或的候选规律 (candidate_rules)\n"
                "- 无法辨认的字段 (uncertain_fields)\n"
                "【严格限制最终输出在 400~800 tokens 以内，仅输出纯净结构化数据】"
            )
        else:
            prompt_text = (
                "请精准提取图片中的题目文本、数学公式与选项内容：\n"
                "1. 包含题干完整题设与全部选项；\n"
                "2. 数学公式采用标准 LaTeX 格式（行内 $...$，行间 $$...$$）；\n"
                "3. 保持原题排版顺序；\n"
                "4. 直接输出纯题目文本，绝不要进行解答，严禁任何废话！"
            )

        user_content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": prompt_text
            }
        ]

        for img in self.images_b64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": img}
            })

        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": user_content}],
            "stream": True,
            "temperature": 0.1,
            "enable_thinking": False,
            "max_tokens": 700
        }

        url = f"{self.base_url}/chat/completions"

        try:
            with httpx.Client(timeout=45.0) as client:
                self._client = client
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    self._active_response = resp
                    if self._is_cancelled:
                        return

                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="replace")
                        self.signal_error.emit(f"视觉识别服务返回 HTTP {resp.status_code}: {err_text}")
                        return

                    extracted_chunks = []
                    for line in resp.iter_lines():
                        if self._is_cancelled:
                            try:
                                resp.close()
                            except Exception:
                                pass
                            break
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                try:
                                    resp.close()
                                except Exception:
                                    pass
                                break
                            try:
                                chunk = json.loads(raw_data)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})
                                c = delta.get("content", "")
                                if c:
                                    extracted_chunks.append(c)

                                finish_reason = choices[0].get("finish_reason")
                                if finish_reason in ("stop", "length"):
                                    try:
                                        resp.close()
                                    except Exception:
                                        pass
                                    break
                            except json.JSONDecodeError:
                                continue

                    full_extracted = "".join(extracted_chunks).strip()
                    if not full_extracted and not self._is_cancelled:
                        self.signal_error.emit("未能从截图中提取到有效视觉文本")
                        return

                    if not self._is_cancelled:
                        self.signal_extracted.emit(full_extracted)

        except Exception as e:
            if not self._is_cancelled:
                self.signal_error.emit(f"视觉识别异常: {str(e)}")
