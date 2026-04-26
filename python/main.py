# SPDX-License-Identifier: MPL-2.0

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

import os
import numpy as np
import time
import json
from collections import deque
from datetime import datetime, timezone

from brain import TreeBrain
from state import SensorReadings, TreeState, VisionResult

# -----------------------------
# INIT
# -----------------------------
logger = Logger("escorca")
web_ui = WebUI()
brain = TreeBrain()

# Per-deployment identity. Override TREE_ID and TREE_LOCATION in the App
# Lab deployment env so the same brick image can run on multiple UNO Qs
# without code changes.
TREE_ID = os.environ.get("TREE_ID", "tree_001")
LOCATION = os.environ.get("TREE_LOCATION", "Plaça Reial #3")

# Sampling: 62.5 Hz
FS = 62.5

BUFFER_SIZE = 128      # ~2 seconds
STEP = 32              # ~0.5 sec updates
BASELINE_SAMPLES = 80

buffer = deque(maxlen=BUFFER_SIZE)
baseline = []
history = deque(maxlen=300)

baseline_ready = False
mu = None
cov_inv = None

latest_temp = None
latest_humidity = None
temp_buffer = deque(maxlen=30)  # ~30 sec (assuming ~1Hz thermo updates)

sample_count = 0

# Most recent TreeState produced by process_window. Read by all HTTP API
# endpoints. None until the baseline is established and the first window
# has been processed.
latest_state: TreeState | None = None


# -----------------------------
# FEATURE EXTRACTION
# -----------------------------
def extract_features(signal):
    signal = np.array(signal)

    # remove gravity / DC
    signal = signal - np.mean(signal)

    rms = np.sqrt(np.mean(signal**2))

    fft_vals = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), d=1/FS)

    dom_freq = freqs[np.argmax(fft_vals)]

    if np.sum(fft_vals) > 0:
        centroid = np.sum(freqs * fft_vals) / np.sum(fft_vals)
    else:
        centroid = 0

    decay = np.mean(np.abs(np.diff(signal)))

    return np.array([rms, dom_freq, centroid, decay])


# -----------------------------
# ANOMALY (Mahalanobis)
# -----------------------------
def anomaly(x):
    global mu, cov_inv

    if mu is None:
        return 0.0

    d = x - mu
    return float(np.sqrt(d.T @ cov_inv @ d))


# -----------------------------
# BASELINE LEARNING
# -----------------------------
def update_baseline(x):
    global baseline_ready, mu, cov_inv

    if baseline_ready:
        return

    baseline.append(x)
    logger.info(f"Baseline: {len(baseline)}/{BASELINE_SAMPLES}")

    if len(baseline) >= BASELINE_SAMPLES:
        data = np.array(baseline)

        mu = np.mean(data, axis=0)
        cov = np.cov(data, rowvar=False)

        cov += np.eye(cov.shape[0]) * 1e-6
        cov_inv = np.linalg.pinv(cov)

        baseline_ready = True
        logger.info("Baseline established")


# -----------------------------
# TEMPERATURE RATE
# -----------------------------
def temp_rate():
    if len(temp_buffer) < 2:
        return 0.0

    (t1, ts1) = temp_buffer[0]
    (t2, ts2) = temp_buffer[-1]

    dt = ts2 - ts1
    if dt <= 0:
        return 0.0

    return (t2 - t1) / dt


# -----------------------------
# STRESS INDEX (PHYSICAL MODEL)
# -----------------------------
def compute_stress(vib_score, temp, humidity):
    if temp is None or humidity is None:
        return 0

    # --- vibration normalization ---
    vib_norm = min(vib_score / 10.0, 1.0)

    # --- temperature rate ---
    rate = temp_rate()
    temp_norm = min(max(rate - 0.01, 0) / 0.1, 1.0)

    # --- humidity deviation ---
    if humidity < 40:
        hum_dev = (40 - humidity) / 40
    elif humidity > 70:
        hum_dev = (humidity - 70) / 30
    else:
        hum_dev = 0

    hum_dev = min(hum_dev, 1.0)

    # --- combined stress ---
    stress = int(100 * (
        0.5 * vib_norm +
        0.3 * temp_norm +
        0.2 * hum_dev
    ))

    return stress


# -----------------------------
# TREE STATE
# -----------------------------
def build_tree_state(vib_score: float) -> TreeState:
    stress = compute_stress(vib_score, latest_temp, latest_humidity)
    return TreeState(
        tree_id=TREE_ID,
        location=LOCATION,
        sensors=SensorReadings(
            temp_c=latest_temp if latest_temp is not None else 0.0,
            humidity=latest_humidity if latest_humidity is not None else 0.0,
            movement=round(vib_score, 4),
        ),
        # Vision is a placeholder until an Edge Impulse model is deployed.
        vision=VisionResult(label="no_camera", confidence=0.0),
        stress_index=stress,
    )


# -----------------------------
# PROCESS WINDOW
# -----------------------------
def process_window():
    global latest_state

    if len(buffer) < BUFFER_SIZE:
        return

    signal = list(buffer)
    features = extract_features(signal)

    if not baseline_ready:
        update_baseline(features)
        return

    vib_score = anomaly(features)
    state = build_tree_state(vib_score)

    # Generate the alert via the brain (LLM if available, templates otherwise).
    state.alert = brain.alert(state)

    latest_state = state
    history.append(state.to_dict())

    # send to UI (real-time push channel; dashboards that poll /trees
    # ignore this, but it's available for future websocket clients)
    try:
        web_ui.send_message("tree_state", state.to_dict())
    except Exception:
        logger.debug("WS send failed")

    logger.info(json.dumps(state.to_dict()))


# -----------------------------
# BRIDGE CALLBACKS
# -----------------------------
def vibration_sample(x, y, z):
    global sample_count

    # magnitude
    mag = np.sqrt(x*x + y*y + z*z)

    # remove gravity
    mag = mag - 1.0

    buffer.append(mag)
    sample_count += 1

    if len(buffer) == BUFFER_SIZE and sample_count % STEP == 0:
        process_window()


def thermo_sample(temp, humidity):
    global latest_temp, latest_humidity

    latest_temp = temp
    latest_humidity = humidity

    temp_buffer.append((temp, time.time()))

    try:
        web_ui.send_message("thermo", {
            "temp": temp,
            "humidity": humidity,
            "ts": int(time.time() * 1000)
        })
    except Exception:
        logger.debug("Thermo WS failed")

    logger.info(f"Thermo -> temp={temp}°C humidity={humidity}%")


# -----------------------------
# SIMULATED MESH NEIGHBORS
# -----------------------------
# Until Person C's PEARS / Hypercore mesh is wired, /trees returns the
# real local tree plus a couple of hand-picked neighbors at varied stress
# bands so the dashboard sort and color-coding have something to display.

def _simulated_neighbors() -> list[TreeState]:
    return [
        TreeState(
            tree_id="tree_017",
            location="Passeig de Gràcia #12",
            sensors=SensorReadings(temp_c=29.8, humidity=55.0, movement=0.6),
            vision=VisionResult(label="healthy_canopy", confidence=0.91),
            stress_index=24,
            alert="OK — tree_017: 24/100.",
        ),
        TreeState(
            tree_id="tree_103",
            location="Parc de la Ciutadella E-7",
            sensors=SensorReadings(temp_c=31.5, humidity=42.0, movement=2.1),
            vision=VisionResult(label="early_leaf_yellowing", confidence=0.64),
            stress_index=48,
            alert="Watch — tree_103: moderate stress (48/100), early leaf yellowing.",
        ),
    ]


def _neighbor_summary() -> dict:
    neighbors = _simulated_neighbors()
    if not neighbors:
        return {"neighbor_count": 0, "park_avg_temp_c": 0.0, "park_avg_stress": 0}
    avg_temp = sum(n.sensors.temp_c for n in neighbors) / len(neighbors)
    avg_stress = int(sum(n.stress_index for n in neighbors) / len(neighbors))
    return {
        "neighbor_count": len(neighbors),
        "park_avg_temp_c": round(avg_temp, 1),
        "park_avg_stress": avg_stress,
    }


def _empty_state() -> TreeState:
    """Returned by /state and /alert before the baseline has been
    learned. Lets the UI render a 'warming up' card instead of erroring."""
    return TreeState(
        tree_id=TREE_ID,
        location=LOCATION,
        sensors=SensorReadings(
            temp_c=latest_temp if latest_temp is not None else 0.0,
            humidity=latest_humidity if latest_humidity is not None else 0.0,
            movement=0.0,
        ),
        vision=VisionResult(label="warming_up", confidence=0.0),
        stress_index=0,
        alert="Calibrating vibration baseline…",
    )


# -----------------------------
# HTTP API
# -----------------------------
def get_history():
    return list(history)


def get_state():
    state = latest_state or _empty_state()
    return state.to_dict()


def get_trees():
    fleet = [latest_state or _empty_state()] + _simulated_neighbors()
    return [t.to_dict() for t in fleet]


def get_alert():
    state = latest_state or _empty_state()
    return {"alert": brain.alert(state), "state": state.to_dict()}


# Defensive POST handler: App Lab's web_ui.expose_api POST signature
# isn't documented, so we accept anything and try every plausible shape
# to extract the JSON body. Logs whatever it received so future bugs
# can be diagnosed from a single redeploy.
def post_chat(*args, **kwargs):
    logger.info(f"post_chat: args={args!r} kwargs={kwargs!r}")

    body = None

    # Try common shapes one at a time
    for candidate in list(args) + list(kwargs.values()):
        if isinstance(candidate, dict):
            body = candidate
            break
        if isinstance(candidate, (str, bytes)):
            try:
                body = json.loads(candidate)
                break
            except (ValueError, TypeError):
                continue
        # request-like objects from a typical web framework
        for attr in ("json", "get_json", "data"):
            v = getattr(candidate, attr, None)
            if callable(v):
                try:
                    v = v()
                except Exception:
                    v = None
            if isinstance(v, dict):
                body = v
                break
            if isinstance(v, (str, bytes)):
                try:
                    body = json.loads(v)
                    break
                except (ValueError, TypeError):
                    continue
        if body is not None:
            break

    body = body or {}
    question = (body.get("question") if isinstance(body, dict) else "") or ""
    question = question.strip()
    logger.info(f"post_chat: parsed question={question!r}")

    if not question:
        return {
            "error": "missing 'question'",
            "_debug": {"args_types": [type(a).__name__ for a in args],
                       "kwargs_keys": list(kwargs.keys())},
        }

    state = latest_state or _empty_state()
    answer = brain.chat(state, _neighbor_summary(), question)
    logger.info(f"post_chat: answer={answer!r}")
    return {
        "answer": answer,
        "state": state.to_dict(),
    }


def get_healthz():
    return {"ok": True, "llm": brain.using_llm, "baseline_ready": baseline_ready}


web_ui.expose_api("GET", "/history", get_history)
web_ui.expose_api("GET", "/state", get_state)
web_ui.expose_api("GET", "/trees", get_trees)
web_ui.expose_api("GET", "/alert", get_alert)
web_ui.expose_api("POST", "/chat", post_chat)
web_ui.expose_api("GET", "/healthz", get_healthz)


# -----------------------------
# REGISTER BRIDGE
# -----------------------------
try:
    Bridge.provide("vibration_sample", vibration_sample)
    Bridge.provide("thermo_sample", thermo_sample)
    logger.info("Bridge connected")
except RuntimeError:
    logger.warning("Bridge already registered")


# -----------------------------
# START
# -----------------------------
logger.info("Escorça running (continuous + physical model + LLM + dashboard)")
App.run()
