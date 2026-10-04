#!/usr/bin/env python3
"""
ArchiBox Agent — Windows sidecar
Listens to archimade commands and executes them via pynput (keyboard/mouse)
"""
import sys
import os
import time
import json
import requests
import threading
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ─── CONFIG ────────────────────────────────────────────────────────────────────
AGENT_VERSION = "0.1.0"
ARCHIMADE_HOST = "192.168.0.119"
ARCHIMADE_PORT = 8766
DEVICE_ID = "win-pc-01"           # will be auto-registered
HEARTBEAT_S = 30
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = f"http://{ARCHIMADE_HOST}:{ARCHIMADE_PORT}"

running = True
verbose = os.environ.get("ARCHIBOX_VERBOSE", "0") == "1"

def log(msg):
    if verbose:
        print(f"[archibox] {msg}", flush=True)

def blink_led(n=3):
    """Tell ESP32 to blink its LED (if connected)."""
    try:
        # LED command goes through archimade
        requests.post(f"{BASE_URL}/cmd/esp32s3-box-01",
                      json={"cmd": f"LED {n}"}, timeout=3)
    except Exception as e:
        log(f"LED feedback failed: {e}")

# ─── Keyboard / Mouse ─────────────────────────────────────────────────────────

def type_text(text):
    """Type a string using pynput keyboard."""
    try:
        from pynput.keyboard import Controller, Key
        kb = Controller()
        for ch in text:
            try:
                kb.press(ch)
                kb.release(ch)
            except ValueError:
                # special char
                pass
        blink_led(1)
        return True
    except ImportError:
        log("pynput not installed — install: pip install pynput")
        return False
    except Exception as e:
        log(f"type_text error: {e}")
        return False

def press_key(combo):
    """Press a key combo like 'WIN R', 'CTRL C', 'ALT F4', etc."""
    try:
        from pynput.keyboard import Controller, Key
        keys_map = {
            "WIN": Key.cmd, "CTRL": Key.ctrl, "SHIFT": Key.shift,
            "ALT": Key.alt, "ENTER": Key.enter, "ESC": Key.esc,
            "TAB": Key.tab, "BACKSPACE": Key.backspace, "DELETE": Key.delete,
            "UP": Key.up, "DOWN": Key.down, "LEFT": Key.left, "RIGHT": Key.right,
            "HOME": Key.home, "END": Key.end, "PAGEUP": Key.page_up, "PAGEDOWN": Key.page_down,
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
        blink_led(2)
        return True
    except ImportError:
        log("pynput not installed")
        return False
    except Exception as e:
        log(f"press_key error: {e}")
        return False

def mouse_move(x, y):
    """Move mouse relative by x,y pixels."""
    try:
        from pynput.mouse import Controller
        m = Controller()
        m.move(x, y)
        blink_led(1)
        return True
    except ImportError:
        log("pynput not installed")
        return False
    except Exception as e:
        log(f"mouse_move error: {e}")
        return False

def mouse_click(btn="left"):
    """Click left or right mouse button."""
    try:
        from pynput.mouse import Controller, Button
        m = Controller()
        b = Button.left if btn == "left" else Button.right
        m.press(b)
        m.release(b)
        blink_led(1)
        return True
    except ImportError:
        log("pynput not installed")
        return False
    except Exception as e:
        log(f"mouse_click error: {e}")
        return False

def mouse_scroll(dx, dy):
    """Scroll mouse."""
    try:
        from pynput.mouse import Controller
        m = Controller()
        m.scroll(dx, dy)
        blink_led(1)
        return True
    except Exception as e:
        log(f"mouse_scroll error: {e}")
        return False

# ─── Screenshot ────────────────────────────────────────────────────────────────

def take_screenshot():
    """Take a screenshot and return base64 data."""
    try:
        import mss
        import base64
        with mss.mss() as s:
            img = s.grab(s.monitors[1])
            png = mss.tools.to_png(img.rgb, img.size)
            return base64.b64encode(png).decode()
    except ImportError:
        log("mss not installed — install: pip install mss")
        return None
    except Exception as e:
        log(f"screenshot error: {e}")
        return None

# ─── Command dispatch ─────────────────────────────────────────────────────────

def execute(cmd):
    """Parse and execute a command string."""
    log(f"execute: {cmd}")
    cmd = cmd.strip()

    if cmd.startswith("TYPE "):
        text = cmd[5:]
        return type_text(text)

    elif cmd.startswith("KEY "):
        return press_key(cmd[4:])

    elif cmd.startswith("MOUSE "):
        parts = cmd[6:].split()
        if len(parts) >= 2:
            try:
                return mouse_move(int(parts[0]), int(parts[1]))
            except ValueError:
                pass

    elif cmd.startswith("CLICK "):
        btn = cmd[6:].strip().split()[0] if len(cmd) > 6 else "left"
        return mouse_click(btn)

    elif cmd.startswith("SCROLL ") or cmd.startswith("MOUSE SCROLL "):
        parts = cmd.split()
        if len(parts) >= 3:
            try:
                return mouse_scroll(int(parts[-2]), int(parts[-1]))
            except ValueError:
                pass

    elif cmd == "SCREENSHOT":
        data = take_screenshot()
        if data:
            try:
                requests.post(f"{BASE_URL}/screenshot/{DEVICE_ID}",
                              json={"data": data}, timeout=10)
                log("Screenshot sent")
                return True
            except Exception as e:
                log(f"screenshot send error: {e}")
        return False

    elif cmd == "STOP":
        global running
        running = False
        log("STOP received — agent going idle")
        return True

    elif cmd == "PING":
        return True  # just acknowledge, no action

    elif cmd.startswith("ECHO "):
        log(f"ECHO: {cmd[5:]}")  # log only
        return True

    else:
        log(f"Unknown command: {cmd}")
        return False

# ─── Register & Poll loop ──────────────────────────────────────────────────────

def register():
    try:
        r = requests.get(f"{BASE_URL}/register?device_id={DEVICE_ID}&type=windows-agent&hostname={socket.gethostname()}", timeout=5)
        log(f"Register: {r.status_code}")
    except Exception as e:
        log(f"Register failed: {e}")

def poll_loop():
    global running
    register()
    last_poll = 0

    while running:
        try:
            r = requests.get(f"{BASE_URL}/poll/{DEVICE_ID}", timeout=5)
            data = r.json()
            cmd = data.get("cmd")
            if cmd:
                log(f"Got cmd: {cmd}")
                execute(cmd)
            last_poll = time.time()
        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            log(f"Poll error: {e}")
        time.sleep(2)

# ─── Health check HTTP server ───────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "device_id": DEVICE_ID, "running": running}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def health_server(port=8767):
    srv = HTTPServer(("0.0.0.0", port), HealthHandler)
    srv.serve_forever()

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    global running
    print(f"ArchiBox Agent v{AGENT_VERSION}")
    print(f"Archimade: {ARCHIMADE_HOST}:{ARCHIMADE_PORT}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Hostname: {socket.gethostname()}")
    print("Commands: TYPE, KEY, MOUSE, CLICK, SCROLL, SCREENSHOT, STOP")
    print("-" * 40)

    # Start health server in background
    t = threading.Thread(target=health_server, daemon=True)
    t.start()
    log("Health server started on :8767")

    poll_loop()
    print("[archibox] Agent stopped.")


if __name__ == "__main__":
    main()
