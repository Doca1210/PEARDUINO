"""PearTree aggregator.

Polls a configured list of trees, caches their latest TreeState, and
serves the merged ranger dashboard. Chat is *not* proxied through this
server — visitors scan a tree's QR and chat directly with that tree's
on-device LLM. The aggregator only does aggregation + UI.

This is the pre-P2P architecture. Once Person C wires up Hyperswarm /
Hypercore, the cache below gets replaced by replication from peers,
and the role this server plays becomes "any peer's dashboard view".

Run:
    KNOWN_TREES="http://10.5.246.172:7000,http://10.5.246.180:7000" \\
    python3 server.py

Then open http://<your-laptop-ip>:8080/ on any device on the same wifi.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, send_from_directory

# Comma-separated list of tree base URLs. Override via env var.
DEFAULT_TREES = ["http://localhost:7000"]
KNOWN_TREES = (
    [t.strip() for t in os.environ.get("KNOWN_TREES", "").split(",") if t.strip()]
    or DEFAULT_TREES
)

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 2.0

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# Latest known state per tree_id. Updated by the polling thread.
_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url.replace("http://", "").replace("https://", "")


def _poll_one(url: str) -> None:
    host = _host_from_url(url)
    try:
        r = requests.get(f"{url.rstrip('/')}/state", timeout=POLL_TIMEOUT_S)
        r.raise_for_status()
        state = r.json()
        state["host"] = host
        state["online"] = True
        state["last_seen"] = time.time()
        with _lock:
            _cache[state.get("tree_id", host)] = state
    except requests.RequestException:
        with _lock:
            existing_id = next(
                (tid for tid, v in _cache.items() if v.get("host") == host),
                None,
            )
            if existing_id is not None:
                _cache[existing_id] = {**_cache[existing_id], "online": False}
            else:
                # First-ever poll failed; show a placeholder so the dashboard
                # makes the unreachable tree visible instead of silently
                # excluding it.
                _cache[host] = {
                    "tree_id": host,
                    "host": host,
                    "online": False,
                    "location": "(unreachable)",
                    "stress_index": 0,
                    "sensors": {"temp_c": 0.0, "humidity": 0.0, "movement": 0.0},
                    "vision": {"label": "offline", "confidence": 0.0},
                    "alert": "Tree unreachable",
                    "ts": "",
                }


def _poll_loop() -> None:
    while True:
        for url in KNOWN_TREES:
            try:
                _poll_one(url)
            except Exception as e:
                print(f"[aggregator] error polling {url}: {e}")
        time.sleep(POLL_INTERVAL_S)


@app.get("/")
def page_dashboard():
    return send_from_directory(STATIC_DIR, "dashboard.html")


@app.get("/qr")
def page_qr():
    return send_from_directory(STATIC_DIR, "qr.html")


@app.get("/trees")
def trees():
    with _lock:
        return jsonify(list(_cache.values()))


@app.get("/healthz")
def healthz():
    with _lock:
        online = sum(1 for v in _cache.values() if v.get("online"))
    return jsonify(
        {
            "ok": True,
            "trees_known": len(KNOWN_TREES),
            "trees_online": online,
            "tree_urls": KNOWN_TREES,
        }
    )


# Start the polling thread on import (works under both `python server.py`
# and `flask run`).
threading.Thread(target=_poll_loop, daemon=True).start()


if __name__ == "__main__":
    print(f"[aggregator] polling: {KNOWN_TREES}")
    app.run(host="0.0.0.0", port=8080)
