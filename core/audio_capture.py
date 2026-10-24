import time
import io
import wave
import numpy as np
import soundcard as sc
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal

class InterviewAudioListener(QThread):
    """
    通过 Windows WASAPI 扬声器回环录制系统正在播放的声音（如面试官通过 Zoom/腾讯会议/Teams 提问）。
    具备语音活动检测 (VAD) 与停顿断句判定。
    """
    signal_status = pyqtSignal(str)              # 状态信息（如：正在监听系统声音、检测到说话等）
    signal_audio_ready = pyqtSignal(np.ndarray)  # 产出已分段的语音波形
    signal_transcript = pyqtSignal(str)          # 转写出的文本提问
    signal_rms = pyqtSignal(float)               # 实时音量用于电平表展示

    def __init__(self, sample_rate: int = 16000, silence_threshold_sec: float = 1.2, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.silence_threshold_sec = silence_threshold_sec
        self.max_speaking_sec = 8.0     # 连续说话超过 8 秒自动切片转录，避免无限等待
        self._running = False
        self._energy_threshold = 0.002  # 降低阈值至 0.002，灵敏捕获日常对话及小音量外放
        self._whisper_model = None

    def stop(self):
        self._running = False

    def _init_whisper(self):
        """延迟加载 Whisper 模型，避免启动时耗时卡顿"""
        if self._whisper_model is None:
            self.signal_status.emit("正在加载本地极速语音识别引擎 (tiny)...")
            try:
                from faster_whisper import WhisperModel
                # 使用 tiny 模型，CPU 毫秒级离线出字
                self._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
                self.signal_status.emit("✅ 离线语音引擎就绪，正在监听系统声音...")
            except Exception as e:
                self.signal_status.emit(f"Whisper 初始化提示: {e}")

    def run(self):
        self._running = True
        self._init_whisper()

        try:
            default_sp = sc.default_speaker()
            loopback_mic = sc.get_microphone(default_sp.name, include_loopback=True)
            self.signal_status.emit(f"已锁定系统扬声器内录: {default_sp.name}")
        except Exception as e:
            self.signal_status.emit(f"获取系统回环音频失败: {e}")
            return

        chunk_duration = 0.15  # 每次读取 150ms 采样步长，响应更敏捷
        num_frames = int(self.sample_rate * chunk_duration)

        buffer = []
        is_speaking = False
        speaking_start_time = None
        silence_start_time = None

        with loopback_mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            while self._running:
                data = recorder.record(numframes=num_frames)
                data_1d = data[:, 0] if data.ndim > 1 else data
                rms = float(np.sqrt(np.mean(data_1d ** 2)))
                self.signal_rms.emit(rms)

                if rms > self._energy_threshold:
                    if not is_speaking:
                        is_speaking = True
                        speaking_start_time = time.time()
                    buffer.append(data_1d)
                    silence_start_time = None

                    # 如果对方连续说话超过 8 秒且无停顿，自动切分出一段先转写
                    if speaking_start_time and (time.time() - speaking_start_time >= self.max_speaking_sec):
                        self.signal_status.emit("⚡ 正在转录长句片段...")
                        full_audio = np.concatenate(buffer)
                        buffer.clear()
                        speaking_start_time = time.time()
                        self._transcribe_and_emit(full_audio)
                else:
                    if is_speaking:
                        buffer.append(data_1d)
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time >= self.silence_threshold_sec:
                            # 判定面试官提问完毕（停顿超过 1.2 秒）
                            self.signal_status.emit("✨ 提问完毕，开始极速转写...")
                            full_audio = np.concatenate(buffer)
                            buffer.clear()
                            is_speaking = False
                            silence_start_time = None
                            speaking_start_time = None
                            
                            self._transcribe_and_emit(full_audio)

    def _transcribe_and_emit(self, audio_data: np.ndarray):
        """将音频送入转写引擎"""
        if self._whisper_model is None:
            self._init_whisper()

        if self._whisper_model is not None:
            try:
                # 过滤太短的声音（< 0.8秒）
                if len(audio_data) < self.sample_rate * 0.8:
                    return

                # faster-whisper 接受 float32 numpy 数组
                segments, info = self._whisper_model.transcribe(
                    audio_data.astype(np.float32),
                    beam_size=3,
                    language="zh",
                    condition_on_previous_text=False
                )
                text = "".join([s.text for s in segments]).strip()
                if text:
                    self.signal_transcript.emit(text)
            except Exception as e:
                self.signal_status.emit(f"语音转写失败: {e}")
