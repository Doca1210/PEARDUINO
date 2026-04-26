# SPDX-License-Identifier: MPL-2.0

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI

import numpy as np
import time
import json
from collections import deque

# -----------------------------
# INIT
# -----------------------------
logger = Logger("escorca")
web_ui = WebUI()

TREE_ID = "tree_001"
LOCATION = "Plaça Reial #3"

BUFFER_SIZE = 128
STEP = 32                 # sliding window step
BASELINE_SAMPLES = 80

buffer = deque(maxlen=BUFFER_SIZE)
baseline = []
history = deque(maxlen=300)

baseline_ready = False
mu = None
cov_inv = None

latest_temp = None
latest_humidity = None
temp_min = None

sample_count = 0

# -----------------------------
# FEATURE EXTRACTION
# -----------------------------
def extract_features(signal):
    signal = np.array(signal)

    # remove DC (gravity / bias)
    signal = signal - np.mean(signal)

    rms = np.sqrt(np.mean(signal**2))

    fft_vals = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), d=1/62.5)

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

        # stabilize covariance
        cov += np.eye(cov.shape[0]) * 1e-6
        cov_inv = np.linalg.pinv(cov)

        baseline_ready = True
        logger.info("✅ Baseline established")


# -----------------------------
# STRESS INDEX (FIXED)
# -----------------------------
def compute_stress(vib_score, temp, humidity):
    global temp_min

    if temp is None or humidity is None:
        return 0

    if temp_min is None:
        temp_min = temp

    temp_min = min(temp_min, temp)
    delta = temp - temp_min

    vib_part = min(vib_score * 15, 50)
    temp_part = min(delta * 6, 30)
    hum_part = max(0, (50 - humidity) * 0.5)

    return int(min(vib_part + temp_part + hum_part, 100))


# -----------------------------
# TREE STATE
# -----------------------------
def build_tree_state(vib_score):
    ts = int(time.time() * 1000)

    stress = compute_stress(vib_score, latest_temp, latest_humidity)

    alert = None
    if stress > 80:
        alert = "HIGH RISK: Possible structural failure"
    elif vib_score > 6:
        alert = "Resonance anomaly detected"
    elif stress > 50:
        alert = "Environmental stress"

    return {
        "tree_id": TREE_ID,
        "location": LOCATION,
        "ts": ts,
        "sensors": {
            "temp_c": latest_temp,
            "humidity": latest_humidity,
            "movement": round(vib_score, 4)
        },
        "vision": {
            "class": "none",
            "confidence": 0.0
        },
        "stress_index": stress,
        "alert": alert
    }


# -----------------------------
# PROCESS WINDOW (CONTINUOUS)
# -----------------------------
def process_window():
    if len(buffer) < BUFFER_SIZE:
        return

    signal = list(buffer)
    features = extract_features(signal)

    if not baseline_ready:
        update_baseline(features)
        return

    vib_score = anomaly(features)
    state = build_tree_state(vib_score)

    history.append(state)

    # send to UI
    try:
        web_ui.send_message("tree_state", state)
    except Exception:
        logger.debug("WebSocket send failed")

    logger.info(json.dumps(state))


# -----------------------------
# BRIDGE CALLBACKS
# -----------------------------
def vibration_sample(x, y, z):
    global sample_count

    # magnitude of acceleration
    mag = np.sqrt(x*x + y*y + z*z)

    buffer.append(mag)
    sample_count += 1

    # sliding window processing
    if len(buffer) == BUFFER_SIZE and sample_count % STEP == 0:
        process_window()


def thermo_sample(temp, humidity):
    global latest_temp, latest_humidity

    latest_temp = temp
    latest_humidity = humidity

    try:
        web_ui.send_message("thermo", {
            "temp": temp,
            "humidity": humidity,
            "ts": int(time.time() * 1000)
        })
    except Exception:
        logger.debug("Thermo WS send failed")

    logger.info(f"Thermo → temp={temp}°C humidity={humidity}%")


# -----------------------------
# API (FIXED HISTORY)
# -----------------------------
def get_history():
    return list(history)

web_ui.expose_api("GET", "/history", get_history)


# -----------------------------
# REGISTER BRIDGE
# -----------------------------
try:
    Bridge.provide("vibration_sample", vibration_sample)
    Bridge.provide("thermo_sample", thermo_sample)
    logger.info("✅ Bridge connected")
except RuntimeError:
    logger.warning("Bridge already registered")


# -----------------------------
# START
# -----------------------------
logger.info("🌳 Escorça running (continuous mode)")
App.run()