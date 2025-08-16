import os
import time
import socket
import math
import requests
import threading
import signal
import sys
from flask import Flask, jsonify

# ================== CONFIG (defaults from your script) ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")            # REQUIRED: set on Render
CHAT_ID   = os.getenv("CHAT_ID")              # REQUIRED: set on Render

SERVER_IP   = os.getenv("SERVER_IP", "teamcross.aternos.me")
SERVER_PORT = int(os.getenv("SERVER_PORT", 30414))

INTERVAL_SEC         = int(os.getenv("INTERVAL_SEC", 10))
ATTEMPTS_PER_CYCLE   = int(os.getenv("ATTEMPTS_PER_CYCLE", 5))
GAP_BETWEEN_ATTEMPTS = float(os.getenv("GAP_BETWEEN_ATTEMPTS", 1.5))
MAJORITY_THRESHOLD   = float(os.getenv("MAJORITY_THRESHOLD", 0.6))

MIN_ANNOUNCE_GAP_SEC = int(os.getenv("MIN_ANNOUNCE_GAP_SEC", 30))
SOCKET_TIMEOUT_SEC   = float(os.getenv("SOCKET_TIMEOUT_SEC", 3.0))
# =======================================================================

app = Flask(__name__)

# Shared state
state_lock = threading.Lock()
last_status = None         # True = online, False = offline
last_announce_ts = 0
last_sample_successes = 0

def ensure_env_or_die():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not CHAT_ID:
        missing.append("CHAT_ID")
    if missing:
        print(f"[BOOT] Missing required env vars: {', '.join(missing)}")
        print("[BOOT] Set them on Render dashboard (Environment) and redeploy.")
        sys.exit(1)

def probe_socket(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def get_stable_status() -> tuple[bool, int]:
    successes = 0
    for i in range(ATTEMPTS_PER_CYCLE):
        if probe_socket(SERVER_IP, SERVER_PORT, SOCKET_TIMEOUT_SEC):
            successes += 1
        if i < ATTEMPTS_PER_CYCLE - 1:
            time.sleep(GAP_BETWEEN_ATTEMPTS)
    needed = math.ceil(ATTEMPTS_PER_CYCLE * MAJORITY_THRESHOLD)
    online = successes >= needed
    return online, successes

def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": f"BOT_Info: {text}"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"[TG] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TG ERROR] {e}")

def now_hhmmss() -> str:
    return time.strftime("%H:%M:%S")

def monitor_loop():
    global last_status, last_announce_ts, last_sample_successes
    ensure_env_or_die()

    print("== Aternos watcher (Flask background) started ==")
    print(f"Server: {SERVER_IP}:{SERVER_PORT} | Chat: {CHAT_ID}")
    print(
        f"Checks: {ATTEMPTS_PER_CYCLE}x every ~{GAP_BETWEEN_ATTEMPTS}s (threshold {int(MAJORITY_THRESHOLD*100)}%), loop sleep {INTERVAL_SEC}s"
    )

    # initial stable status (silent)
    s, succ = get_stable_status()
    with state_lock:
        last_status = s
        last_sample_successes = succ
    print(f"[{now_hhmmss()}] Initial status: {'ONLINE' if s else 'OFFLINE'} ({succ}/{ATTEMPTS_PER_CYCLE} ok)")

    while True:
        try:
            s, succ = get_stable_status()
            with state_lock:
                prev = last_status
                last_sample_successes = succ

            print(f"[{now_hhmmss()}] Sample: {'ONLINE' if s else 'OFFLINE'} ({succ}/{ATTEMPTS_PER_CYCLE} ok)")

            if prev is None:
                with state_lock:
                    last_status = s
            elif s != prev:
                now_ts = time.time()
                with state_lock:
                    if now_ts - last_announce_ts >= MIN_ANNOUNCE_GAP_SEC:
                        last_status = s
                        last_announce_ts = now_ts
                        # send correct message according to new status
                        if s:
                            send_message("❌ Server is offline!")
                        else:
                            send_message("✅ Server is online!")
                    else:
                        print(f"[{now_hhmmss()}] Change suppressed (cooldown {MIN_ANNOUNCE_GAP_SEC}s)")
            # outer loop sleep
            time.sleep(INTERVAL_SEC)
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
            time.sleep(5)

# start background monitor thread once
monitor_thread = None
def start_monitor_thread():
    global monitor_thread
    if monitor_thread is None:
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

# Flask endpoints
@app.route("/")
def home():
    return "OK", 200

@app.route("/health")
def health():
    with state_lock:
        st = {"last_status": None if last_status is None else ("ONLINE" if last_status else "OFFLINE"),
              "last_successes": last_sample_successes,
              "last_announce_ts": last_announce_ts}
    return jsonify(st), 200

@app.route("/start_monitor")
def start_endpoint():
    # handy for manual start via browser if needed
    start_monitor_thread()
    return "monitor started", 200

def handle_shutdown(sig, frame):
    print(f"[{now_hhmmss()}] Received signal {sig}, exiting")
    sys.exit(0)

# ensure graceful shutdown
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

# start monitor thread at import time (Render will create the process)
start_monitor_thread()

if __name__ == "__main__":
    # for local dev: use PORT env var (Render provides $PORT)
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
