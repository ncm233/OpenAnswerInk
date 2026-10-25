"""
局域网手机副屏桥接模块 (LAN Phone-Bridge Server - Zero Dependencies Standard Library Edition)
将 OpenAnswerInk 的搜图解题流程保留在 PC 运算，同时将题目与最终答案实时推送到手机端浏览器。
当 PC 被专考客户端霸屏独占时，PC 在后台静默抓屏推导，手机作为隐形物理副屏呈现文字答案。
"""
import os
import io
import time
import uuid
import json
import socket
import queue
import threading
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Set, Dict, List, Any, Optional

import qrcode
from PyQt6.QtCore import QObject, pyqtSignal

# --------------------------------------------------------------------------- #
# 本机网络 IP 获取与可用端口探查
# --------------------------------------------------------------------------- #
def find_available_port(start_port: int = 8000) -> int:
    """自动探查可用端口，若被占用则平滑探测备用端口"""
    for p in [start_port, 8899, 8080, 8008, 8888, 9000]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", p))
                return p
        except OSError:
            continue
    return start_port

def get_lan_ips() -> list[str]:
    """获取本机所有可用局域网 IPv4 地址"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        if not primary.startswith("127."):
            ips.append(primary)
        s.close()
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips or ["127.0.0.1"]

# --------------------------------------------------------------------------- #
# 移动端专用 Web 页面模板 (超低功耗纯黑 AMOLED、大字答案、防熄屏、触控遥控)
# --------------------------------------------------------------------------- #
MOBILE_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<title>OpenAnswerInk · 手机隐形副屏</title>
<style>
  :root {
    --bg: #090a0f;
    --card: #131620;
    --border: #232838;
    --txt: #f1f5f9;
    --dim: #94a3b8;
    --accent: #38bdf8;
    --ans-bg: #0b192c;
    --ans-border: #1d4ed8;
    --btn-fine: #7c3aed;
    --btn-fast: #0284c7;
  }
  body.stealth-mode {
    --bg: #000000;
    --card: #0a0a0a;
    --border: #1a1a1a;
    --txt: #71717a;
    --dim: #3f3f46;
    --accent: #94a3b8;
    --ans-bg: #0f0f0f;
    --ans-border: #27272a;
    --btn-fine: #27272a;
    --btn-fast: #18181b;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0; background: var(--bg); color: var(--txt);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
    padding-bottom: calc(88px + env(safe-area-inset-bottom));
    min-height: 100vh;
    transition: background 0.2s, color 0.2s;
  }
  header {
    position: sticky; top: 0; z-index: 20;
    background: rgba(9, 10, 15, 0.94); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 10px 14px calc(10px + env(safe-area-inset-top));
    display: flex; align-items: center; justify-content: space-between;
  }
  body.stealth-mode header {
    background: #000000;
  }
  .title-group { display: flex; align-items: center; gap: 8px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: #ef4444; }
  .dot.online { background: #10b981; box-shadow: 0 0 8px #10b981; }
  h1 { font-size: 15px; margin: 0; font-weight: 700; color: var(--txt); }
  .header-actions { display: flex; gap: 6px; align-items: center; }
  .btn-header {
    background: var(--card); border: 1px solid var(--border); color: var(--txt);
    font-size: 11px; padding: 4px 8px; border-radius: 6px; cursor: pointer;
  }
  .btn-header.active { background: #0284c7; color: #fff; border-color: #38bdf8; }

  #main { padding: 12px; display: flex; flex-direction: column; gap: 12px; }

  .tip-banner {
    background: rgba(2, 132, 199, 0.12); border: 1px solid rgba(2, 132, 199, 0.28);
    border-radius: 8px; padding: 8px 12px; font-size: 11.5px; color: var(--dim);
    display: flex; justify-content: space-between; align-items: center;
  }
  .empty-box {
    text-align: center; color: var(--dim); padding: 40px 16px; font-size: 13.5px; line-height: 1.8;
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  }
  .empty-box b { color: var(--accent); }

  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    animation: fadeIn 0.25s ease-out;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

  .card-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border);
    font-size: 11.5px; color: var(--dim);
  }
  .card-tag { font-weight: 700; color: var(--accent); }
  .card-img-wrap {
    max-height: 170px; overflow: hidden; background: #000; border-bottom: 1px solid var(--border);
    position: relative; cursor: pointer; display: none;
  }
  .card-img-wrap img { width: 100%; height: auto; display: block; object-fit: contain; }
  .img-tip { position: absolute; bottom: 4px; right: 8px; font-size: 10px; background: rgba(0,0,0,0.65); padding: 2px 6px; border-radius: 4px; color: #94a3b8; }

  .ans-box {
    padding: 12px 14px; background: var(--ans-bg);
    border-left: 4px solid var(--ans-border); margin: 10px; border-radius: 8px;
    font-size: 14.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  }
  .ans-box .ans-title {
    font-size: 21px; font-weight: 900; color: #38bdf8; margin-bottom: 6px; display: block;
    letter-spacing: 0.5px;
  }
  body.stealth-mode .ans-box .ans-title {
    color: #94a3b8;
  }
  .ans-box.pending { color: var(--dim); font-style: italic; }

  footer {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 30;
    background: rgba(15, 17, 23, 0.96); backdrop-filter: blur(16px);
    border-top: 1px solid var(--border);
    padding: 10px 14px calc(10px + env(safe-area-inset-bottom));
    display: flex; gap: 10px;
  }
  body.stealth-mode footer {
    background: #000000;
  }
  .btn-action {
    flex: 1; border: none; border-radius: 10px; padding: 13px 8px;
    font-size: 13.5px; font-weight: 700; color: #fff; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3); text-align: center;
    transition: transform 0.1s, opacity 0.1s;
  }
  .btn-action:active { transform: scale(0.97); }
  .btn-fine { background: linear-gradient(135deg, #7c3aed, #6d28d9); }
  .btn-fast { background: linear-gradient(135deg, #0284c7, #0369a1); }
  .btn-clear { flex: 0 0 54px; background: #262c3d; color: #cbd5e1; font-weight: 600; }
  body.stealth-mode .btn-action {
    background: #18181b; color: #71717a; border: 1px solid #27272a;
  }

  #toast {
    position: fixed; top: 60px; left: 50%; transform: translateX(-50%);
    background: rgba(30, 41, 59, 0.95); color: #fff; border: 1px solid #475569;
    padding: 8px 18px; border-radius: 20px; font-size: 12.5px; z-index: 100;
    opacity: 0; pointer-events: none; transition: opacity 0.2s; white-space: nowrap;
  }
  #toast.show { opacity: 1; }

  #fullView {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.92);
    z-index: 200; align-items: center; justify-content: center;
  }
  #fullView.show { display: flex; }
  #fullView img { max-width: 98%; max-height: 98%; object-fit: contain; }
</style>
</head>
<body>

<header>
  <div class="title-group">
    <span class="dot" id="netDot"></span>
    <h1 id="headerTitle">手机隐形副屏</h1>
  </div>
  <div class="header-actions">
    <button class="btn-header" id="btnStealth" onclick="toggleStealth()">🕶️ 防窥</button>
    <button class="btn-header" id="btnVibrate" onclick="toggleVibrate()">🔔 震动</button>
  </div>
</header>

<div id="main">
  <div class="tip-banner">
    <span>💡 屏幕常亮防锁屏已激活 | 考场霸屏副屏专用</span>
    <span id="connTag" style="font-size:11px;color:var(--dim);">连接中...</span>
  </div>

  <div class="empty-box" id="emptyBox">
    ⚡ <b>手机隐形副屏已就绪！</b><br /><br />
    电脑端 OpenAnswerInk 即使被霸屏独占压制，依然在后台全力截屏与大模型运算。<br /><br />
    👉 <b>操作方式</b>：<br />
    1. 点击下方按钮，电脑静默全屏捕获并极速解题；<br />
    2. 或在电脑上直接按热键 <b>Alt+S (全屏) / Alt+W (精细)</b>；<br />
    文字答案将在 1~2 秒内自动流式直达此屏幕！
  </div>
</div>

<footer>
  <button class="btn-action btn-clear" id="btnClear" onclick="clearCards()">清空</button>
  <button class="btn-action btn-fast" id="btnFast" onclick="remoteTrigger('fast')">🖥️ 全屏答题</button>
  <button class="btn-action btn-fine" id="btnFine" onclick="remoteTrigger('fine')">🧩 精细答题</button>
</footer>

<div id="toast"></div>
<div id="fullView" onclick="this.classList.remove('show')"><img id="fullImg" /></div>

<script>
(() => {
  let stealth = false;
  let vibrateEnabled = true;
  let wakeLock = null;
  let cards = {}; // id -> DOM
  let eventSource = null;

  const netDot = document.getElementById('netDot');
  const connTag = document.getElementById('connTag');
  const mainDiv = document.getElementById('main');
  const emptyBox = document.getElementById('emptyBox');
  const toast = document.getElementById('toast');
  const fullView = document.getElementById('fullView');
  const fullImg = document.getElementById('fullImg');

  // 防锁屏 WakeLock
  async function requestWakeLock() {
    try {
      if ('wakeLock' in navigator) {
        wakeLock = await navigator.wakeLock.request('screen');
      }
    } catch(e) {
      console.log('WakeLock error:', e);
    }
  }
  requestWakeLock();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') requestWakeLock();
  });

  window.toggleStealth = function() {
    stealth = !stealth;
    document.body.classList.toggle('stealth-mode', stealth);
    const btn = document.getElementById('btnStealth');
    btn.classList.toggle('active', stealth);
    btn.textContent = stealth ? '🕶️ 极暗' : '🕶️ 防窥';
    showToast(stealth ? '已切换至 AMOLED 极暗防窥模式' : '已恢复默认高对比模式');
  };

  window.toggleVibrate = function() {
    vibrateEnabled = !vibrateEnabled;
    const btn = document.getElementById('btnVibrate');
    btn.classList.toggle('active', vibrateEnabled);
    btn.textContent = vibrateEnabled ? '🔔 震动' : '🔕 静音';
    showToast(vibrateEnabled ? '答案到达震动提醒: 开' : '答案到达震动提醒: 关');
  };

  window.showToast = function(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
  };

  window.clearCards = function() {
    mainDiv.querySelectorAll('.card').forEach(c => c.remove());
    emptyBox.style.display = 'block';
    cards = {};
    showToast('已清空屏幕记录');
  };

  window.viewImage = function(src) {
    if (!src) return;
    fullImg.src = src;
    fullView.classList.add('show');
  };

  window.remoteTrigger = function(mode) {
    if (vibrateEnabled && navigator.vibrate) navigator.vibrate(40);
    const label = mode === 'fine' ? '精细答题' : '全屏速答';
    showToast('已通知电脑: ' + label);
    fetch('/api/trigger?mode=' + mode, { method: 'POST' })
      .then(res => res.json())
      .catch(err => {
        showToast('远程指令下发失败，请确认连接');
      });
  };

  function escapeHtml(str) {
    return (str || '').replace(/[&<>'"]/g, tag => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
  }

  function createOrUpdateCard(id, imgUrl, timeStr, mode) {
    emptyBox.style.display = 'none';
    let card = cards[id];
    if (!card) {
      card = document.createElement('div');
      card.className = 'card';
      card.id = 'card_' + id;
      const modeLabel = mode === 'fine' ? '🧩 行测精细 32B' : '🖥️ 全屏速答 8B';
      const timeVal = timeStr || new Date().toLocaleTimeString();

      let imgHtml = '';
      if (imgUrl) {
        imgHtml = `
          <div class="card-img-wrap" style="display:block;" onclick="viewImage('${imgUrl}')">
            <img src="${imgUrl}" alt="题目截图" />
            <span class="img-tip">点击看原图</span>
          </div>`;
      } else {
        imgHtml = `
          <div class="card-img-wrap" id="img_wrap_${id}" onclick="viewImage('')">
            <img id="img_${id}" alt="题目截图" />
            <span class="img-tip">点击看原图</span>
          </div>`;
      }

      card.innerHTML = `
        <div class="card-header">
          <span class="card-tag">${modeLabel}</span>
          <span>${timeVal}</span>
        </div>
        ${imgHtml}
        <div class="ans-box pending" id="ans_${id}">
          ⏳ PC 端大模型正在深度拆解推导...
        </div>
      `;
      mainDiv.insertBefore(card, mainDiv.firstChild);
      cards[id] = card;
    } else if (imgUrl) {
      const imgWrap = card.querySelector(`#img_wrap_${id}`);
      const imgEl = card.querySelector(`#img_${id}`);
      if (imgWrap && imgEl) {
        imgEl.src = imgUrl;
        imgWrap.style.display = 'block';
        imgWrap.onclick = () => viewImage(imgUrl);
      }
    }
  }

  function updateAnswer(id, text, status) {
    let card = cards[id];
    if (!card) {
      createOrUpdateCard(id, '', '', 'fast');
      card = cards[id];
    }
    const ansEl = card.querySelector(`#ans_${id}`);
    if (!ansEl) return;

    if (status === 'generating') {
      ansEl.classList.add('pending');
    } else {
      ansEl.classList.remove('pending');
    }

    // 格式化置顶突出显示【最终答案：X】
    let formattedHtml = '';
    const match = text.match(/(【最终答案[：:][^】]+】)/);
    if (match) {
      const topTitle = match[1];
      const restText = text.replace(topTitle, '').trim();
      formattedHtml = `<span class="ans-title">${topTitle}</span><div>${escapeHtml(restText)}</div>`;
    } else {
      formattedHtml = escapeHtml(text);
    }
    ansEl.innerHTML = formattedHtml;

    // 最终答案到达时震动
    if (status === 'ok' && vibrateEnabled && navigator.vibrate) {
      navigator.vibrate([60, 40, 60]);
    }
  }

  // 建立 Server-Sent Events (SSE) 直连通道
  function connectSSE() {
    if (eventSource) {
      eventSource.close();
    }
    eventSource = new EventSource('/api/events');

    eventSource.onopen = () => {
      netDot.classList.add('online');
      connTag.textContent = '🟢 已连接电脑';
      connTag.style.color = '#10b981';
    };

    eventSource.onerror = () => {
      netDot.classList.remove('online');
      connTag.textContent = '🔴 连接中断，自动重连中...';
      connTag.style.color = '#ef4444';
    };

    eventSource.addEventListener('shot', (e) => {
      try {
        const d = JSON.parse(e.data);
        createOrUpdateCard(d.id, d.url, d.time, d.mode);
      } catch(err) {
        console.error(err);
      }
    });

    eventSource.addEventListener('answer', (e) => {
      try {
        const d = JSON.parse(e.data);
        updateAnswer(d.id, d.text, d.status);
      } catch(err) {
        console.error(err);
      }
    });

    eventSource.addEventListener('toast', (e) => {
      try {
        const d = JSON.parse(e.data);
        showToast(d.text);
      } catch(err) {
        console.error(err);
      }
    });
  }

  connectSSE();
})();
</script>
</body>
</html>
"""

# --------------------------------------------------------------------------- #
# ThreadedHTTPServer 与请求分发处理器
# --------------------------------------------------------------------------- #
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class LANBridgeServer(QObject):
    signal_remote_trigger = pyqtSignal(str) # 转发手机端触发指令 ("fine" | "fast")

    def __init__(self, port: int = 8000, parent=None):
        super().__init__(parent)
        self.port = find_available_port(port)
        self.lan_ips = get_lan_ips()
        self.primary_ip = self.lan_ips[0] if self.lan_ips else "127.0.0.1"

        self._server: Optional[ThreadedHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self.is_running = False

        # 客户端订阅队列与锁
        self._subscribers: List[queue.Queue] = []
        self._subscribers_lock = threading.Lock()

        # 题目截图缓存 (最多存 25 张) 与最新答案
        self.shots_cache: Dict[str, bytes] = {}
        self.last_shot_id: str = ""
        self.last_shot_mode: str = "fast"
        self.last_shot_time: str = ""
        self.last_answer_text: str = ""
        self.last_answer_status: str = "ok"

    def start_server(self):
        """启动后台 HTTP + SSE 服务"""
        if self.is_running and self._server is not None:
            return

        server_instance = self

        class LANBridgeHTTPHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # 静默处理，避免高频心跳刷屏日志
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                # 1. 移动端主界面
                if path in ("/", "/index.html", "/mobile"):
                    html_bytes = MOBILE_HTML_TEMPLATE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html_bytes)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(html_bytes)

                # 2. 截屏原图读取
                elif path.startswith("/shot/"):
                    shot_id = path.replace("/shot/", "").strip()
                    img_data = server_instance.shots_cache.get(shot_id)
                    if not img_data:
                        self.send_response(404)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(img_data)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.end_headers()
                    self.wfile.write(img_data)

                # 3. 二维码生成 API
                elif path == "/api/qr":
                    try:
                        qr = qrcode.QRCode(box_size=6, border=2)
                        target_url = server_instance.get_mobile_url()
                        qr.add_data(target_url)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        qr_bytes = buf.getvalue()

                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(len(qr_bytes)))
                        self.end_headers()
                        self.wfile.write(qr_bytes)
                    except Exception:
                        self.send_response(500)
                        self.end_headers()

                # 4. SSE 实时推流通讯
                elif path == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-transform")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    client_q = queue.Queue(maxsize=100)
                    with server_instance._subscribers_lock:
                        server_instance._subscribers.append(client_q)

                    # 如果当前已有最近一次答题，立即推送历史初值
                    if server_instance.last_shot_id:
                        shot_init = {
                            "id": server_instance.last_shot_id,
                            "url": f"/shot/{server_instance.last_shot_id}",
                            "time": server_instance.last_shot_time,
                            "mode": server_instance.last_shot_mode
                        }
                        self.wfile.write(f"event: shot\ndata: {json.dumps(shot_init, ensure_ascii=False)}\n\n".encode("utf-8"))
                    if server_instance.last_answer_text:
                        ans_init = {
                            "id": server_instance.last_shot_id,
                            "text": server_instance.last_answer_text,
                            "status": server_instance.last_answer_status
                        }
                        self.wfile.write(f"event: answer\ndata: {json.dumps(ans_init, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                    try:
                        while True:
                            try:
                                msg = client_q.get(timeout=15.0)
                                if msg is None:
                                    break
                                event_type, data_obj = msg
                                line = f"event: {event_type}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"
                                self.wfile.write(line.encode("utf-8"))
                                self.wfile.flush()
                            except queue.Empty:
                                # 保持连接心跳
                                self.wfile.write(b": keepalive\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        with server_instance._subscribers_lock:
                            if client_q in server_instance._subscribers:
                                server_instance._subscribers.remove(client_q)

                # 5. 状态查询
                elif path == "/api/status":
                    with server_instance._subscribers_lock:
                        sub_count = len(server_instance._subscribers)
                    data = {
                        "status": "online",
                        "ip": server_instance.primary_ip,
                        "port": server_instance.port,
                        "subscribers": sub_count,
                        "last_shot_id": server_instance.last_shot_id
                    }
                    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                parsed = urlparse(self.path)
                # 远程触发答题 (/api/trigger?mode=fine|fast)
                if parsed.path == "/api/trigger":
                    qs = parse_qs(parsed.query)
                    mode = qs.get("mode", ["fast"])[0]
                    if mode not in ("fine", "fast"):
                        action = qs.get("action", ["full"])[0]
                        mode = "fine" if action == "fine" else "fast"

                    # 触发 Qt 主线程信号进行静默截屏与破题
                    server_instance.signal_remote_trigger.emit(mode)

                    res = json.dumps({"status": "ok", "mode": mode}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(res)))
                    self.end_headers()
                    self.wfile.write(res)
                else:
                    self.send_response(404)
                    self.end_headers()

        try:
            self._server = ThreadedHTTPServer(("0.0.0.0", self.port), LANBridgeHTTPHandler)
            self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._server_thread.start()
            self.is_running = True
            print(f"[LANBridge] 手机副屏服务启动成功: http://{self.primary_ip}:{self.port}")
        except Exception as e:
            print(f"[LANBridge] 手机副屏服务启动失败: {e}")

    def stop_server(self):
        """停止后台 HTTP 服务"""
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        self.is_running = False

    def get_mobile_urls(self) -> List[str]:
        """获取所有可用局域网访问地址"""
        return [f"http://{ip}:{self.port}/" for ip in self.lan_ips]

    def get_mobile_url(self) -> str:
        """获取主局域网访问地址"""
        return f"http://{self.primary_ip}:{self.port}/"

    def get_subscriber_count(self) -> int:
        """获取当前在线手机连接数"""
        with self._subscribers_lock:
            return len(self._subscribers)

    def _broadcast(self, event_type: str, data: Dict[str, Any]):
        """向所有在线手机广播事件"""
        with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait((event_type, data))
            except queue.Full:
                pass

    def push_shot(self, shot_id: str, image_bytes: bytes, mode: str = "fast"):
        """将截屏缩略图广播至所有在线手机"""
        self.shots_cache[shot_id] = image_bytes
        # 维持最多 25 张截图缓存，防止内存膨胀
        if len(self.shots_cache) > 25:
            oldest_key = next(iter(self.shots_cache))
            del self.shots_cache[oldest_key]

        time_str = time.strftime("%H:%M:%S")
        self.last_shot_id = shot_id
        self.last_shot_mode = mode
        self.last_shot_time = time_str

        payload = {
            "type": "shot",
            "id": shot_id,
            "url": f"/shot/{shot_id}",
            "time": time_str,
            "mode": mode
        }
        self._broadcast("shot", payload)

    def push_answer(self, shot_id: str, text: str, status: str = "ok"):
        """将 AI 答案实时广播至所有在线手机"""
        self.last_shot_id = shot_id
        self.last_answer_text = text
        self.last_answer_status = status

        payload = {
            "type": "answer",
            "id": shot_id,
            "text": text,
            "status": status
        }
        self._broadcast("answer", payload)

    def push_toast(self, text: str):
        """向手机端推送轻提示"""
        self._broadcast("toast", {"type": "toast", "text": text})

lan_bridge_server = LANBridgeServer()
