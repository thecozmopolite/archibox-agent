#!/usr/bin/env python3
"""
ArchiBox Agent — macOS sidecar
Polls archimade and executes TYPE/KEY/MOUSE commands via CGEvent (PyObjC).
Usage: python3 archibox_agent_mac.py <token> [device_id] [archimade_host] [port]
"""
import sys, os, time, json, socket, threading, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request, urllib.error

VERSION = "0.1.0"
ARCHIMADE_SERVER = "http://192.168.0.119:8766"
DEVICE_ID = "mac-book-01"
DEVICE_TOKEN = ""
POLL_INTERVAL = 2.0
HEALTH_PORT = 8767
running = True

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def api_headers():
    return {
        "User-Agent": f"ArchiBox-Agent-Mac/{VERSION}",
        "X-Archibox-Token": DEVICE_TOKEN,
        "X-Archibox-Device": DEVICE_ID,
        "Content-Type": "application/json",
    }

def http_get(path, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    req = urllib.request.Request(url, headers=api_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"GET {path}: {e}")
        return None

def http_post(path, data=None, timeout=5):
    url = f"{ARCHIMADE_SERVER}{path}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, headers=api_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"POST {path}: {e}")
        return None

# ── Keyboard / Mouse via PyObjC ───────────────────────────────────────────────
try:
    import Cocoa, Quartz
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False
    log("WARNING: PyObjC not installed. Run: pip install pyobjc-framework-Quartz")

def type_text(text):
    if not HAS_PYOBJC: return False
    try:
        for ch in text:
            try:
                c = ord(ch.upper())
                if 65 <= c <= 90:  # A-Z
                    k = Cocoa.CGEventKeyboardKeyCreate(c - 65 + 0x04)
                elif 48 <= c <= 57:  # 0-9
                    k = Cocoa.CGEventKeyboardKeyCreate(c - 48 + 0x1D)
                elif ch == ' ':
                    k = Cocoa.CGEventKeyboardKeyCreate(0x31)
                else:
                    continue
                d = Cocoa.CGEventCreateKeyboardEvent(None, k, True)
                Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, d)
                ru = Cocoa.CGEventCreateKeyboardEvent(None, k, False)
                Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, ru)
            except Exception:
                pass
        return True
    except Exception as e:
        log(f"type_text error: {e}")
        return False

def press_key(code):
    if not HAS_PYOBJC: return False
    try:
        k = Cocoa.CGEventKeyboardKeyCreate(code)
        d = Cocoa.CGEventCreateKeyboardEvent(None, k, True)
        Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, d)
        ru = Cocoa.CGEventCreateKeyboardEvent(None, k, False)
        Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, ru)
        return True
    except Exception as e:
        log(f"press_key error: {e}")
        return False

KEY_CODES = {
    "RETURN": 0x24, "ENTER": 0x24,
    "TAB": 0x30, "ESCAPE": 0x35, "ESC": 0x35,
    "BACKSPACE": 0x33, "DELETE": 0x75,
    "UP": 0x7E, "DOWN": 0x7D, "LEFT": 0x7B, "RIGHT": 0x7C,
    "HOME": 0x73, "END": 0x77,
    "PAGEUP": 0x74, "PAGEDOWN": 0x79,
    "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76,
    "F5": 0x60, "F6": 0x61, "F7": 0x62, "F8": 0x64,
    "F9": 0x65, "F10": 0x6D, "F11": 0x67, "F12": 0x6F,
    "SPACE": 0x31,
}

def press_combo(combo):
    if not HAS_PYOBJC: return False
    parts = combo.upper().replace("+", " ").split()
    key_code = None
    flags = 0
    for p in parts:
        p = p.strip()
        if p in ("CMD", "COMMAND"): flags |= Quartz.CGEventFlags.maskCommand
        elif p in ("SHIFT"): flags |= Quartz.CGEventFlags.maskShift
        elif p in ("CTRL", "CONTROL"): flags |= Quartz.CGEventFlags.maskControl
        elif p in ("ALT", "OPTION"): flags |= Quartz.CGEventFlags.maskAlternate
        elif p in KEY_CODES: key_code = KEY_CODES[p]
    if key_code is None: return False
    try:
        k = Cocoa.CGEventKeyboardKeyCreate(key_code)
        d = Cocoa.CGEventCreateKeyboardEvent(None, k, True)
        if flags: Cocoa.CGEventSetFlags(d, flags)
        Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, d)
        ru = Cocoa.CGEventCreateKeyboardEvent(None, k, False)
        Cocoa.CGEventPost(Cocoa.kCGHIDEventTap, ru)
        return True
    except Exception as e:
        log(f"press_combo error: {e}")
        return False

def mouse_move(x, y):
    if not HAS_PYOBJC: return False
    try:
        cur = Quartz.CGEventGetCurrentEvent()
        loc = Quartz.CGEventGetLocation(cur)
        p = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (loc.x + x, loc.y - y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, p)
        return True
    except Exception as e:
        log(f"mouse_move error: {e}")
        return False

def mouse_click(btn="left"):
    if not HAS_PYOBJC: return False
    try:
        loc = Quartz.CGEventGetLocation(Quartz.CGEventCreateCurrentEvent())
        t = Quartz.kCGEventLeftMouseDown if btn == "left" else Quartz.kCGEventRightMouseDown
        r = Quartz.kCGEventLeftMouseUp if btn == "left" else Quartz.kCGEventRightMouseUp
        d = Quartz.CGEventCreateMouseEvent(None, t, loc, Quartz.kCGMouseButtonLeft if btn == "left" else Quartz.kCGMouseButtonRight)
        u = Quartz.CGEventCreateMouseEvent(None, r, loc, Quartz.kCGMouseButtonLeft if btn == "left" else Quartz.kCGMouseButtonRight)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, d)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, u)
        return True
    except Exception as e:
        log(f"mouse_click error: {e}")
        return False

def mouse_scroll(dx, dy):
    if not HAS_PYOBJC: return False
    try:
        loc = Quartz.CGEventGetLocation(Quartz.CGEventCreateCurrentEvent())
        scr = Quartz.CGEventCreateScrollWheelEvent2(None, Quartz.kCGScrollWheelEventId, Quartz.kCGScrollWheelEventDeltaAxis1, dy, dx)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, scr)
        return True
    except Exception as e:
        log(f"mouse_scroll error: {e}")
        return False

# ── Screenshot ─────────────────────────────────────────────────────────────────
def take_screenshot():
    try:
        import subprocess
        sc = subprocess.run(["screencapture", "-x", "/tmp/archibox_screenshot.png"], capture_output=True)
        with open("/tmp/archibox_screenshot.png", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        log(f"screenshot error: {e}")
        return None

# ── Command dispatch ────────────────────────────────────────────────────────────
def execute(cmd):
    log(f"EXEC: {cmd}")
    cmd = cmd.strip()
    if not cmd or cmd == "PING": return True
    if cmd.startswith("TYPE "): return type_text(cmd[5:])
    if cmd.startswith("KEY "): return press_combo(cmd[4:])
    if cmd.startswith("MOUSE ") and len(cmd) > 6:
        parts = cmd[6:].split()
        if len(parts) >= 2:
            try: return mouse_move(int(parts[0]), int(parts[1]))
            except: pass
    if cmd.startswith("CLICK "): return mouse_click(cmd[6:].strip().split()[0] if len(cmd) > 6 else "left")
    if "SCROLL" in cmd:
        parts = cmd.split()
        try: return mouse_scroll(int(parts[-2]), int(parts[-1]))
        except: pass
    if cmd == "SCREENSHOT":
        data = take_screenshot()
        if data: http_post(f"/screenshot/{DEVICE_ID}", {"data": data})
        return True
    if cmd == "STOP":
        global running
        running = False
        return True
    log(f"Unknown: {cmd}")
    return False

# ── Health server ──────────────────────────────────────────────────────────────
def health_server(port=HEALTH_PORT):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "ok", "version": VERSION,
                    "device_id": DEVICE_ID, "hostname": socket.gethostname(),
                    "archimade": ARCHIMADE_SERVER, "running": running,
                    "pyobjc": HAS_PYOBJC,
                }).encode())
            else:
                self.send_response(404); self.end_headers()
    try:
        HTTPServer(("0.0.0.0", port), H).serve_forever()
    except Exception as e:
        log(f"Health server error: {e}")

# ── Poll loop ─────────────────────────────────────────────────────────────────
def poll_loop():
    http_get(f"/register?device_id={DEVICE_ID}&type=macos-agent&hostname={socket.gethostname()}")
    while running:
        try:
            data = http_get(f"/poll/{DEVICE_ID}")
            if data:
                cmd = data.get("cmd")
                if cmd: execute(cmd)
        except Exception as e:
            log(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global ARCHIMADE_SERVER, DEVICE_ID, DEVICE_TOKEN
    print(f"ArchiBox Agent Mac v{VERSION}")
    print("=" * 40)
    if len(sys.argv) >= 2: DEVICE_TOKEN = sys.argv[1]
    if len(sys.argv) >= 3: DEVICE_ID = sys.argv[2]
    if len(sys.argv) >= 4: ARCHIMADE_SERVER = f"http://{sys.argv[3]}:{sys.argv[4] if len(sys.argv) >= 5 else 8766}"
    if not DEVICE_TOKEN:
        log("Usage: archibox_agent_mac.py <token> [device_id] [host] [port]")
        sys.exit(1)
    log(f"Token: {DEVICE_TOKEN[:8]}...")
    log(f"Device: {DEVICE_ID}")
    log(f"Archimade: {ARCHIMADE_SERVER}")
    log(f"PyObjC: {HAS_PYOBJC}")
    t = threading.Thread(target=health_server, daemon=True)
    t.start()
    log(f"Health: http://localhost:{HEALTH_PORT}/health")
    poll_loop()
    log("Agent stopped.")

if __name__ == "__main__":
    main()
