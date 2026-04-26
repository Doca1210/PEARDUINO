# PearTree — UNO Q brick

The Arduino App Lab brick for **PearTree**, the EdgeAI sentinel network for
Barcelona's urban trees. Built for HackUPC 2026, Qualcomm *"EdgeAI for a
Resilient and Greener Barcelona"* track.

This repository is the device-side deployable. Deploy it as an App Lab
brick to one Arduino UNO Q per tree. For the laptop-side aggregator that
merges all trees into a fleet view, see `~/aggregator/`. For the full
from-scratch runbook covering both halves, see `~/setup.md`.

## What this brick does

- Reads from Modulino **Movement** (vibration / acceleration) and Modulino
  **Thermo** (temperature + humidity) over QWIIC, in `sketch.ino`.
- Pushes samples to the Linux side via `Bridge.notify`.
- On the Linux side, computes a vibration **anomaly score** using
  Mahalanobis distance against an online-learned baseline (no Edge Impulse
  classifier required for this part).
- Computes a **stress index** (0–100) from temperature drift, humidity, and
  vibration anomaly.
- Generates **first-person alerts and chat replies** via an on-device LLM
  (Ollama + Qwen2.5-0.5B-Instruct), with a deterministic templated fallback
  if Ollama isn't available.
- Exposes an HTTP API and a self-contained web UI (dashboard, chat, QR
  generator) via the `arduino:web_ui` brick, on port 7000.

## Hardware

- Arduino UNO Q
- Modulino Movement (accelerometer)
- Modulino Thermo (temperature + humidity)
- USB-C cable + included PSU
- QWIIC cable

## Brick layout

```
PEARDUINO/
├── app.yaml               brick manifest (name, dependencies)
├── sketch/
│   ├── sketch.ino         STM32 side: Modulino reads, Bridge.notify
│   └── sketch.yaml        Arduino library deps
├── python/
│   ├── main.py            Linux side: bridge callbacks, anomaly, API
│   ├── brain.py           Ollama LLM + templated fallback
│   ├── prompts.py         LLM prompt templates
│   ├── state.py           TreeState dataclass
│   └── requirements.txt   Python deps (numpy, requests)
└── assets/                served as static files at root by web_ui brick
    ├── index.html         ranger dashboard
    ├── talk.html          talk-to-a-tree mobile chat
    ├── qr.html            offline QR generator
    └── qrcode.js          vendored QR library (MIT)
```

## Deploy

Bundle as a zip and import into Arduino App Lab:

```bash
cd /Users/adrian.patricio
rm -f PearTree.zip
zip -rq PearTree.zip PEARDUINO -x "*/__pycache__/*" "*/.git/*" "*/.DS_Store"
```

Import `PearTree.zip` in App Lab, set per-device env vars, click deploy.

### Per-device env vars

| Variable | Purpose | Example |
|---|---|---|
| `TREE_ID` | Unique identifier for this tree node | `tree_001` |
| `TREE_LOCATION` | Human-readable label shown on the dashboard | `Plaça Reial #3` |
| `OLLAMA_URL` | Override Ollama endpoint (optional) | `http://localhost:11434` |
| `TREE_MODEL` | Override LLM model name (optional) | `qwen2.5:0.5b` |

If App Lab's UI doesn't expose env vars, edit the defaults at the top of
`python/main.py` per device before zipping.

### One-time setup on the UNO Q (for the LLM)

App Lab installs Python deps but not Ollama (it's a Linux service, not a
Python package). Open a shell on the UNO Q and run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
```

The brick auto-detects Ollama at boot. Without it, the `/healthz` endpoint
reports `"llm": false` and chat falls back to deterministic templates —
the demo still works end-to-end.

## HTTP API

All endpoints on port 7000.

| Method | Path | Returns |
|---|---|---|
| GET | `/healthz` | `{"ok": true, "llm": bool, "baseline_ready": bool}` |
| GET | `/state` | Current `TreeState` for this node |
| GET | `/trees` | This tree plus simulated neighbors (replaced when mesh lands) |
| GET | `/alert` | `{"alert": str, "state": TreeState}` |
| POST | `/chat` | Body `{"question": str}` → `{"answer": str, "state": TreeState}` |
| GET | `/history` | Last ~300 TreeStates (debug) |
| GET | `/` | Ranger dashboard HTML |
| GET | `/talk.html` | Mobile chat UI (accepts `?tree_id=X` query) |
| GET | `/qr.html` | Printable QR generator |

`TreeState` JSON shape:

```json
{
  "tree_id": "tree_001",
  "location": "Plaça Reial #3",
  "sensors": {"temp_c": 34.2, "humidity": 38.0, "movement": 5.4},
  "vision": {"label": "no_camera", "confidence": 0.0},
  "stress_index": 72,
  "alert": "URGENT — Tree tree_001 at Plaça Reial #3: ...",
  "ts": "2026-04-25T12:00:00+00:00"
}
```

`movement` is a vibration anomaly score (Mahalanobis distance against the
learned baseline), not a binary detection. `vision` is a placeholder until
an Edge Impulse model is deployed.

## Status

| Component | Status |
|---|---|
| Modulino sensor reads (movement + thermo) | Working |
| Vibration anomaly via Mahalanobis distance | Working |
| Stress index | Working |
| On-device LLM (Ollama + Qwen2.5-0.5B) | Working when installed; templated fallback otherwise |
| Ranger dashboard, chat, QR generator | Working |
| Vision (Edge Impulse `.eim`) | Planned — placeholder `"no_camera"` for now |
| Hyperswarm / Hypercore peer-to-peer mesh | Planned — replaces the simulated neighbours in `/trees` |

## License

Mozilla Public License 2.0. See `LICENSE.txt`.

The vendored QR library (`assets/qrcode.js`) is © Kazuhiko Arase, used
under the MIT license.

## Acknowledgements

Built at HackUPC 2026 with **Arduino**, **Qualcomm**, and the
**Universitat Politècnica de Catalunya (UPC)**.
