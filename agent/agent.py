#!/usr/bin/env python3
"""
ArchiBox Agent v0.3.0 — Windows PC control via ESP32 USB Serial
- Reçoit le token de l'ESP via USB Serial
- Poll archimade avec ce token
- Exécute les commandes HID via pynput
"""
import sys
import os
import time
import json
import socket
import threading
import serial
import serial.tools.list_ports
import urllib.request
import urllib.error
import base64
import io

VERSION = "0.4.0"
running = True
_serial_lock = threading.Lock()  # Serial port access guard

# ── Config auto-detectée ────────────────────────────────────────────────────
ARCHIMADE_HOST = "192.168.0.119"
ARCHIMADE_PORT = 8766
ARCHIMADE_SERVER = f"http://{ARCHIMADE_HOST}:{ARCHIMADE_PORT}"
DEVICE_ID = "win-pc-01"
DEVICE_TOKEN = None          # reçu de l'ESP
POLL_INTERVAL = 2.0
esp_token = None            # token broadcasté par l'ESP
ser = None


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "/tmp"), "ArchiBox", "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "agent.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── ESP Serial ───────────────────────────────────────────────────────────────

def find_esp_port():
    """Trouve le port COM de l'ESP32-S3-Box."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        # ESP32-S3-Box apparaît comme "USB Serial" ou "Silicon Labs CP210x"
        desc = p.description or ""
        if any(k in desc.lower() for k in ["usb serial", "cp210", "ch340", "ch343", "esp", "arduino"]):
            log(f"ESP found: {p.device} — {desc}")
            return p.device
    # Fallback: premier port dispo
    if ports:
        log(f"No ESP identified — using {ports[0].device} as fallback")
        return ports[0].device
    return None


def serial_read_line(timeout=5.0):
    """Lit une ligne depuis l'ESP (bloquante, timeout)."""
    if not ser:
        return None
    with _serial_lock:
        old = ser.timeout
        ser.timeout = timeout
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            return line if line else None
        except Exception as e:
            log(f"Serial read error: {e}", "ERROR")
            return None
        finally:
            ser.timeout = old


def serial_write(msg):
    """Envoie un message à l'ESP."""
    if not ser:
        return
    with _serial_lock:
        try:
            ser.write((msg + "\n").encode())
            ser.flush()
        except Exception as e:
            log(f"Serial write error: {e}", "ERROR")


def wait_for_token():
    """Attend le TOKEN:<uuid> de l'ESP."""
    log("Waiting for TOKEN from ESP...")
    while running:
        line = serial_read_line(timeout=10.0)
        if line and line.startswith("TOKEN:"):
            token = line[6:].strip()
            log(f"TOKEN received from ESP: {token[:8]}...")
            return token
        elif line:
            log(f"ESP [unexpected]: {line[:60]}")
    return None


# ── HTTP helpers ────────────────────────────────────────────────────────────

def api_headers(token):
    return {
        "User-Agent": f"ArchiBox-Agent/{VERSION}",
        "X-Archibox-Token": token,
        "X-Archibox-Device": DEVICE_ID,
        "Content-Type": "application/json",
    }


def http_get(path, token, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    req = urllib.request.Request(url, headers=api_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            log("Unauthorized — token may be revoked", "ERROR")
        return None
    except Exception as e:
        log(f"GET {path}: {e}")
        return None


def http_post(path, token, data=None, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, headers=api_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"POST {path}: {e}")
        return None


# ── HID via pynput ──────────────────────────────────────────────────────────

def init_pynput():
    try:
        from pynput.keyboard import Controller as KbCtrl
        from pynput.mouse import Controller as MouseCtrl
        return True
    except ImportError:
        log("pynput not installed — run: pip install pynput", "ERROR")
        return False


_pynput_ready = init_pynput()


def type_text(text):
    if not _pynput_ready:
        return False
    try:
        from pynput.keyboard import Controller
        kb = Controller()
        for ch in text:
            try:
                kb.press(ch)
                kb.release(ch)
            except ValueError:
                pass
        return True
    except Exception as e:
        log(f"type_text error: {e}", "ERROR")
        return False


def press_key(combo):
    if not _pynput_ready:
        return False
    try:
        from pynput.keyboard import Controller, Key
        keys_map = {
            "WIN": Key.cmd, "CTRL": Key.ctrl, "SHIFT": Key.shift,
            "ALT": Key.alt, "ENTER": Key.enter, "ESC": Key.esc,
            "TAB": Key.tab, "BACKSPACE": Key.backspace, "DELETE": Key.delete,
            "UP": Key.up, "DOWN": Key.down, "LEFT": Key.left, "RIGHT": Key.right,
            "HOME": Key.home, "END": Key.end,
            "PAGEUP": Key.page_up, "PAGEDOWN": Key.page_down,
            "F1": Key.f1, "F2": Key.f2, "F3": Key.f3, "F4": Key.f4,
            "F5": Key.f5, "F6": Key.f6, "F7": Key.f7, "F8": Key.f8,
            "F9": Key.f9, "F10": Key.f10, "F11": Key.f11, "F12": Key.f12,
        }
        kb = Controller()
        parts = combo.upper().replace("+", " ").split()
        normal_keys = []
        for p in parts:
            p = p.strip()
            if p in keys_map:
                normal_keys.append(keys_map[p])
            elif len(p) == 1:
                normal_keys.append(p.lower())
        for k in normal_keys[:-1]:
            kb.press(k)
        for k in normal_keys:
            kb.release(k)
        return True
    except Exception as e:
        log(f"press_key error: {e}", "ERROR")
        return False


def mouse_move(x, y):
    if not _pynput_ready:
        return False
    try:
        from pynput.mouse import Controller
        Controller().move(x, y)
        return True
    except Exception as e:
        log(f"mouse_move error: {e}", "ERROR")
        return False


def mouse_click(btn="left"):
    if not _pynput_ready:
        return False
    try:
        from pynput.mouse import Controller, Button
        m = Controller()
        b = Button.left if btn == "left" else Button.right
        m.press(b)
        m.release(b)
        return True
    except Exception as e:
        log(f"mouse_click error: {e}", "ERROR")
        return False


def mouse_scroll(dx, dy):
    if not _pynput_ready:
        return False
    try:
        from pynput.mouse import Controller
        Controller().scroll(dx, dy)
        return True
    except Exception as e:
        log(f"mouse_scroll error: {e}", "ERROR")
        return False


# ── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot():
    try:
        import mss
        with mss.mss() as s:
            img = s.grab(s.monitors[1])
            png = mss.tools.to_png(img.rgb, img.size)
            return base64.b64encode(png).decode()
    except ImportError:
        log("mss not installed — run: pip install mss", "ERROR")
        return None
    except Exception as e:
        log(f"screenshot error: {e}", "ERROR")
        return None


# ── Audio chunk reader ─────────────────────────────────────────────────────────
# Protocol: ESP sends  SIZE:NNNNN\n  then N bytes of PCM  then  ###END###\n

import wave
import tempfile
import re as _re


def _parse_size_from_buf(buf):
    """Extract audio size from buffer containing SIZE:N\\n line."""
    text = buf.decode('utf-8', errors='ignore')
    for line in text.split('\n'):
        m = _re.match(r'SIZE:(\d+)', line.strip())
        if m:
            return int(m.group(1)), buf.find(line.encode())
    return None, -1


def read_audio_chunk(serial_conn, timeout=30):
    """Read one audio chunk from ESP. Returns PCM bytes or None."""
    t0 = time.time()
    raw = b''
    audio_data = b''

    # Per-read locking: lock only during each read() call
    # This allows esp_reader to interleave line reads during chunk transfer

    # Wait for first byte > 127 (start of PCM data after SIZE line)
    while time.time() - t0 < timeout:
        if serial_conn.in_waiting:
            with _serial_lock:
                chunk = serial_conn.read(serial_conn.in_waiting)
            raw += chunk

            # Find SIZE: line in what we've read
            for line in raw.decode('utf-8', errors='ignore').split('\n'):
                m = _re.match(r'SIZE:(\d+)', line.strip())
                if m:
                    target_size = int(m.group(1))
                    nl_pos = raw.find((line + '\n').encode())
                    audio_start = nl_pos + len(line) + 1
                    audio_data = raw[audio_start:]
                    break

            if audio_data and audio_data[0] > 127:
                break
        time.sleep(0.02)

    if not audio_data:
        return None

    # Read remaining bytes to reach target_size
    target_size = len(audio_data) + 1  # rough estimate
    # Re-parse properly
    m = _re.search(rb'SIZE:(\d+)', raw)
    if not m:
        return None
    target_size = int(m.group(1))
    nl_pos = m.start() + m.end()
    audio_start = nl_pos + 1
    audio_data = raw[audio_start:]

    # Read exact byte count
    while len(audio_data) < target_size and time.time() - t0 < timeout:
        if serial_conn.in_waiting:
            with _serial_lock:
                got = serial_conn.read(min(serial_conn.in_waiting, target_size - len(audio_data)))
            audio_data += got
        else:
            time.sleep(0.02)

    # Drain until ###END###
    deadline = time.time() + 3
    while time.time() < deadline:
        if serial_conn.in_waiting:
            with _serial_lock:
                serial_conn.read(serial_conn.in_waiting)
            break
        time.sleep(0.05)

    if len(audio_data) >= target_size * 0.9:
        return audio_data[:target_size]
    return None


def write_wav(path, pcm_bytes, sample_rate=16000):
    n = len(pcm_bytes) // 2
    with wave.open(path, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm_bytes)


# ── Whisper transcription ────────────────────────────────────────────────────

_whisper_model = None


def whisper_load():
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
        model_name = os.environ.get('WHISPER_MODEL', 'small')
        log(f"Loading Whisper '{model_name}' (int8 CPU)...")
        t0 = time.time()
        _whisper_model = WhisperModel(model_name, device='cpu', compute_type='int8')
        log(f"Whisper ready in {time.time()-t0:.1f}s")
        return True
    except ImportError:
        log("faster-whisper not installed — audio transcription disabled", "WARNING")
        return False
    except Exception as e:
        log(f"Whisper load error: {e}", "ERROR")
        return False


def whisper_transcribe(pcm_bytes):
    global _whisper_model
    if not _whisper_model:
        return None
    tmp = tempfile.mktemp(suffix='.wav')
    try:
        write_wav(tmp, pcm_bytes)
        segments, info = _whisper_model.transcribe(tmp, language='fr')
        text = ''.join(s.text for s in segments).strip()
        if text:
            log(f"Whisper: {text}")
        return text or None
    except Exception as e:
        log(f"Whisper error: {e}", "ERROR")
        return None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# ── Audio thread ─────────────────────────────────────────────────────────────

_audio_thread_running = False


def audio_loop(serial_conn, token):
    """Background thread: reads audio chunks, transcribes, sends to archimade."""
    global _audio_thread_running, esp_token
    _audio_thread_running = True

    # Load whisper lazily on first use
    whisper_loaded = whisper_load()

    while _audio_thread_running and running:
        chunk = read_audio_chunk(serial_conn, timeout=35)
        if not chunk:
            time.sleep(1)
            continue

        log(f"Audio: {len(chunk)} bytes ({len(chunk)/32000:.1f}s)")

        if whisper_loaded and esp_token:
            text = whisper_transcribe(chunk)
            if text:
                # Send transcription to archimade
                r = http_post(f"/transcribe/{DEVICE_ID}", esp_token, {
                    'text': text,
                    'device_id': DEVICE_ID,
                })
                if r:
                    log(f"Transcription sent to archimade")


# ── Mute/unmute ESP32 ────────────────────────────────────────────────────────

def esp_mute():
    serial_write('MUTE')
    log("Sent MUTE to ESP32")


def esp_unmute():
    serial_write('UNMUTE')
    log("Sent UNMUTE to ESP32")


# ── Command execution ────────────────────────────────────────────────────────

def execute(cmd):
    log(f"EXEC: {cmd}")
    cmd = cmd.strip()

    if not cmd or cmd == "PING":
        return True

    if cmd.startswith("DELAY "):
        try:
            ms = int(cmd[6:].strip())
            time.sleep(ms / 1000.0)
            return True
        except ValueError:
            return False

    if cmd.startswith("TYPE "):
        return type_text(cmd[5:])

    if cmd.startswith("KEY "):
        return press_key(cmd[4:])

    if cmd.startswith("MOUSE ") and len(cmd) > 6:
        parts = cmd[6:].split()
        if len(parts) >= 2:
            try:
                return mouse_move(int(parts[0]), int(parts[1]))
            except ValueError:
                pass

    if cmd.startswith("CLICK "):
        btn = cmd[6:].strip().split()[0] if len(cmd) > 6 else "left"
        return mouse_click(btn)

    if "SCROLL" in cmd:
        parts = cmd.split()
        try:
            return mouse_scroll(int(parts[-2]), int(parts[-1]))
        except (ValueError, IndexError):
            pass

    if cmd == "SCREENSHOT":
        data = take_screenshot()
        if data and esp_token:
            http_post(f"/screenshot/{DEVICE_ID}", esp_token, {"data": data})
        return True

    if cmd == "TRANSCRIBE" and esp_token:
        # Request audio chunk transcription
        serial_write('UNMUTE')
        time.sleep(5)  # Let ESP record
        serial_write('MUTE')
        return True

    if cmd == "MUTE":
        esp_mute()
        return True

    if cmd == "UNMUTE":
        esp_unmute()
        return True

    if cmd == "STOP":
        global running
        running = False
        return True

    log(f"Unknown command: {cmd}")
    return False


# ── ESP serial reader thread ────────────────────────────────────────────────

def esp_reader():
    """Thread qui lit les commandes de l'ESP et les exécute."""
    global running
    while running:
        line = serial_read_line(timeout=5.0)
        if not line:
            continue

        if line.startswith("CMD:"):
            cmd = line[4:].strip()
            log(f"CMD from ESP: {cmd[:60]}")
            ok = execute(cmd)
            serial_write("OK" if ok else "ERR")

        elif line.startswith("PING"):
            serial_write("PONG")

        elif line.startswith("TOKEN:"):
            global esp_token
            esp_token = line[6:].strip()
            log(f"TOKEN update from ESP: {esp_token[:8]}...")
            # Start audio thread once token is known
            audio_t = threading.Thread(target=audio_loop, args=(ser, esp_token), daemon=True)
            audio_t.start()
            log("Audio thread started")
            # Mic starts muted — unmute after handshake
            time.sleep(0.5)
            esp_unmute()

        elif line == "STOP":
            running = False
            log("STOP from ESP")
            serial_write("OK")

        elif line:
            log(f"ESP: {line[:60]}")


# ── Poll archimade ───────────────────────────────────────────────────────────

def register(token):
    hostname = socket.gethostname()
    r = http_get(f"/register?device_id={DEVICE_ID}&type=windows-agent&hostname={hostname}", token)
    if r:
        log(f"Registered: {r}")
    return r is not None


def poll_archimade():
    """Boucle de polling — utilise le token de l'ESP."""
    global esp_token, running

    # 1. Attendre le token de l'ESP
    esp_token = wait_for_token()
    if not esp_token:
        log("No token from ESP — exiting", "ERROR")
        return

    register(esp_token)

    while running:
        try:
            data = http_get(f"/poll/{DEVICE_ID}", esp_token)
            if data:
                cmd = data.get("cmd")
                if cmd:
                    log(f"CMD from archimade: {cmd[:60]}")
                    execute(cmd)
        except Exception as e:
            log(f"Poll error: {e}", "ERROR")

        for _ in range(int(POLL_INTERVAL * 10)):
            if not running:
                break
            time.sleep(0.1)


# ── Health HTTP server ────────────────────────────────────────────────────────

def health_server(port=8767):
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "ok",
                        "version": VERSION,
                        "device_id": DEVICE_ID,
                        "esp_connected": ser is not None,
                        "token_received": esp_token is not None,
                        "archimade": ARCHIMADE_SERVER,
                        "running": running,
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        srv = HTTPServer(("0.0.0.0", port), H)
        srv.serve_forever()
    except Exception as e:
        log(f"Health server error: {e}", "ERROR")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global ser, DEVICE_ID

    print(f"ArchiBox Agent v{VERSION}")
    print("=" * 40)

    # Auto-detect ESP COM port
    esp_port = find_esp_port()
    if not esp_port:
        input("Aucun ESP détecté. Branche l'ESP et appuie sur Entrée...")

    # Parse device_id optionnel
    if len(sys.argv) >= 2:
        DEVICE_ID = sys.argv[1]

    log(f"Connecting to ESP on {esp_port or 'auto'}...")
    try:
        ser = serial.Serial(
            port=esp_port,
            baudrate=115200,
            timeout=5.0,
            write_timeout=5.0,
        )
        # Attendre que l'ESP soit prêt
        time.sleep(1.5)
        ser.reset_input_buffer()
        log("ESP serial connected")
    except Exception as e:
        log(f"Cannot open {esp_port}: {e}", "ERROR")
        sys.exit(1)

    # Démarrer le reader série ESP
    reader_t = threading.Thread(target=esp_reader, daemon=True)
    reader_t.start()

    # Health server
    health_t = threading.Thread(target=health_server, daemon=True)
    health_t.start()
    log(f"Health server: http://localhost:8767/health")

    # Poll archimade avec le token ESP
    poll_archimade()

    # Cleanup
    if ser:
        ser.close()
    log("Agent stopped.")


if __name__ == "__main__":
    main()
