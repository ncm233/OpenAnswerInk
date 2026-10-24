import time
import sys
import numpy as np
import soundcard as sc
from faster_whisper import WhisperModel

def run_meeting_transcriber(
    sample_rate: int = 16000,
    silence_threshold_sec: float = 2.0,
    energy_threshold: float = 0.015,
    whisper_model_size: str = "tiny"
):
    """
    专门捕获腾讯会议/飞书会议中面试官声音并实时转录为文字的独立脚本。
    核心机制：通过 Windows WASAPI Loopback（扬声器回环内录）物理级隔离自身麦克风声音。
    """
    print("=" * 60)
    print("🚀 正在初始化面试官语音监听与转录系统...")
    print("=" * 60)

    # 1. 查找系统默认扬声器的 Loopback（回环内录）麦克风
    try:
        default_speaker = sc.default_speaker()
        # include_loopback=True 表示抓取从该扬声器流出的声音
        loopback_mic = sc.get_microphone(default_speaker.name, include_loopback=True)
        print(f"✅ 已锁定回环录音通道: [{default_speaker.name}]")
        print("💡 隔离原理: 该通道只记录耳机/喇叭里播放的声音（面试官），绝对不包含你自己的麦克风声音！")
    except Exception as e:
        print(f"❌ 获取回环音频设备失败: {e}")
        return

    # 2. 加载轻量级快速语音转写引擎 (Faster-Whisper)
    print(f"⏳ 正在加载本地离线 ASR 模型 ({whisper_model_size})...")
    model = WhisperModel(whisper_model_size, device="cpu", compute_type="int8")
    print("✅ 语音识别模型就绪！")
    print("-" * 60)
    print("🎙️ 正在实时监听面试官发言中... (请在腾讯会议/飞书会议中佩戴耳机)")
    print("-" * 60)

    chunk_duration = 0.2  # 每次读取 200ms 音频帧
    num_frames = int(sample_rate * chunk_duration)

    audio_buffer = []
    is_speaking = False
    silence_start_time = None

    try:
        with loopback_mic.recorder(samplerate=sample_rate, channels=1) as recorder:
            while True:
                # 读取 200ms 采样数据
                data = recorder.record(numframes=num_frames)
                data_1d = data[:, 0] if data.ndim > 1 else data

                # 计算音频实时振幅/能量 (RMS)
                rms = float(np.sqrt(np.mean(data_1d ** 2)))

                # 判定是否有声音
                if rms > energy_threshold:
                    if not is_speaking:
                        is_speaking = True
                        print("\n[🎙️ 正在倾听面试官提问...]", end="", flush=True)
                    audio_buffer.append(data_1d)
                    silence_start_time = None
                else:
                    if is_speaking:
                        audio_buffer.append(data_1d)
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time >= silence_threshold_sec:
                            # 判定面试官一句话提问结束
                            print(" -> [✨ 提问完毕，开始快速转写...]")
                            full_audio = np.concatenate(audio_buffer).astype(np.float32)
                            audio_buffer.clear()
                            is_speaking = False
                            silence_start_time = None

                            # 过滤小于 0.8 秒的突发杂音
                            if len(full_audio) >= sample_rate * 0.8:
                                t_start = time.time()
                                segments, _ = model.transcribe(
                                    full_audio,
                                    language="zh",
                                    beam_size=3,
                                    condition_on_previous_text=False
                                )
                                text = "".join([s.text for s in segments]).strip()
                                cost = round(time.time() - t_start, 2)
                                if text:
                                    print(f"👉 【面试官提问】: {text} （耗时: {cost}s）\n")
                                else:
                                    print("（未识别到清晰文字）\n")

    except KeyboardInterrupt:
        print("\n🛑 已停止监听。")

if __name__ == "__main__":
    run_meeting_transcriber()
