#!/usr/bin/env python3
"""
ArchiBox Agent — Windows PC control via ESP32 USB HID
Polls archimade:8766 and executes TYPE/KEY/MOUSE commands via pynput.
"""
import sys
import os
import time
import json
import socket
import threading
import urllib.request
import urllib.error
import base64

# ── Config from key (passed as CLI args or read from USB key) ─────────────────
ARCHIMADE_HOST = "192.168.0.119"
ARCHIMADE_PORT = 8766
DEVICE_ID = "win-pc-01"
DEVICE_TOKEN = ""
ARCHIMADE_SERVER = f"http://{ARCHIMADE_HOST}:{ARCHIMADE_PORT}"
POLL_INTERVAL = 2.0
HEALTH_PORT = 8767
VERSION = "0.2.0"

running = True
verbose = os.environ.get("ARCHIBOX_VERBOSE", "0") == "1"


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


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def api_headers():
    return {
        "User-Agent": f"ArchiBox-Agent/{VERSION}",
        "X-Archibox-Token": DEVICE_TOKEN,
        "X-Archibox-Device": DEVICE_ID,
        "Content-Type": "application/json",
    }


def http_get(path, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    req = urllib.request.Request(url, headers=api_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code}: {path}")
        return None
    except Exception as e:
        log(f"GET {path}: {e}")
        return None


def http_post(path, data=None, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, headers=api_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"POST {path}: {e}")
        return None


# ── Keyboard / Mouse via pynput ────────────────────────────────────────────────

def init_pynput():
    try:
        from pynput.keyboard import Controller as KbCtrl
        from pynput.mouse import Controller as MouseCtrl
        return True
    except ImportError:
        log("ERROR: pynput not installed. Run: pip install pynput")
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
        log(f"type_text error: {e}")
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
        log(f"press_key error: {e}")
        return False


def mouse_move(x, y):
    if not _pynput_ready:
        return False
    try:
        from pynput.mouse import Controller
        Controller().move(x, y)
        return True
    except Exception as e:
        log(f"mouse_move error: {e}")
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
        log(f"mouse_click error: {e}")
        return False


def mouse_scroll(dx, dy):
    if not _pynput_ready:
        return False
    try:
        from pynput.mouse import Controller
        Controller().scroll(dx, dy)
        return True
    except Exception as e:
        log(f"mouse_scroll error: {e}")
        return False


# ── Screenshot ─────────────────────────────────────────────────────────────────

def take_screenshot():
    try:
        import mss
        with mss.mss() as s:
            img = s.grab(s.monitors[1])
            png = mss.tools.to_png(img.rgb, img.size)
            return base64.b64encode(png).decode()
    except ImportError:
        log("mss not installed — run: pip install mss")
        return None
    except Exception as e:
        log(f"screenshot error: {e}")
        return None


# ── Command dispatch ────────────────────────────────────────────────────────────

def execute(cmd):
    global _pynput_ready

    log(f"EXEC: {cmd}")
    cmd = cmd.strip()

    if not cmd or cmd == "PING":
        return True

    # DELAY n  — attend n millisecondes (permet de calibrer les sequences)
    if cmd.startswith("DELAY "):
        try:
            ms = int(cmd[6:].strip())
            time.sleep(ms / 1000.0)
            log(f"DELAY done: {ms}ms")
            return True
        except ValueError:
            log(f"DELAY: invalid value: {cmd[6:]}")
            return False

    if cmd.startswith("TYPE "):
    log(f"EXEC: {cmd}")
    cmd = cmd.strip()

    if not cmd or cmd == "PING":
        return True

    if cmd.startswith("TYPE "):
        text = cmd[5:]
        log(f"TYPE: {text[:50]}{'...' if len(text)>50 else ''}")
        return type_text(text)

    if cmd.startswith("KEY "):
        log(f"KEY: {cmd[4:]}")
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
            dx = int(parts[-2])
            dy = int(parts[-1])
            return mouse_scroll(dx, dy)
        except (ValueError, IndexError):
            pass

    if cmd == "SCREENSHOT":
        log("SCREENSHOT: capturing...")
        data = take_screenshot()
        if data:
            log(f"SCREENSHOT: {len(data)} bytes sent")
            http_post(f"/screenshot/{DEVICE_ID}", {"data": data})
        else:
            log("SCREENSHOT: failed", "ERROR")
        return True

    if cmd == "STOP":
        global running
        running = False
        log("STOP received")
        return True

    log(f"Unknown command: {cmd}")
    return False


# ── Registration + poll loop ────────────────────────────────────────────────────

def register():
    hostname = socket.gethostname()
    r = http_get(f"/register?device_id={DEVICE_ID}&type=windows-agent&hostname={hostname}")
    if r:
        log(f"Registered: {r}")
    return r is not None


def poll_loop():
    global running
    register()

    while running:
        try:
            data = http_get(f"/poll/{DEVICE_ID}")
            if data:
                cmd = data.get("cmd")
                if cmd:
                    log(f"CMD: {cmd}")
                    execute(cmd)
        except Exception as e:
            log(f"Poll error: {e}")

        for _ in range(int(POLL_INTERVAL * 10)):
            if not running:
                break
            time.sleep(0.1)


# ── Health HTTP server ─────────────────────────────────────────────────────────

def health_server(port=HEALTH_PORT):
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
                        "hostname": socket.gethostname(),
                        "archimade": ARCHIMADE_SERVER,
                        "running": running,
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        srv = HTTPServer(("0.0.0.0", port), H)
        srv.serve_forever()
    except Exception as e:
        log(f"Health server error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global ARCHIMADE_HOST, ARCHIMADE_PORT, DEVICE_ID, DEVICE_TOKEN, ARCHIMADE_SERVER

    print(f"ArchiBox Agent v{VERSION}")
    print("=" * 40)

    # Parse CLI args: agent.py <token> <device_id> <archimade_host> [archimade_port]
    if len(sys.argv) >= 2:
        DEVICE_TOKEN = sys.argv[1]
    if len(sys.argv) >= 3:
        DEVICE_ID = sys.argv[2]
    if len(sys.argv) >= 4:
        ARCHIMADE_HOST = sys.argv[3]
    if len(sys.argv) >= 5:
        ARCHIMADE_PORT = int(sys.argv[4])

    ARCHIMADE_SERVER = f"http://{ARCHIMADE_HOST}:{ARCHIMADE_PORT}"

    if not DEVICE_TOKEN:
        log("ERROR: No token provided. Usage: archibox-agent.exe <token> [device_id] [archimade_host] [port]")
        sys.exit(1)

    log(f"Token: {DEVICE_TOKEN[:8]}...")
    log(f"Device: {DEVICE_ID}")
    log(f"Archimade: {ARCHIMADE_SERVER}")
    log(f"Hostname: {socket.gethostname()}")
    log(f"pynput ready: {_pynput_ready}")

    # Start health server in background thread
    t = threading.Thread(target=health_server, daemon=True)
    t.start()
    log(f"Health server: http://localhost:{HEALTH_PORT}/health")

    poll_loop()
    log("Agent stopped.")


if __name__ == "__main__":
    main()
