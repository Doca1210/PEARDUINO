# PearTree — From-Scratch Setup

End-to-end runbook to bring the system up from cold metal: one UNO Q (or
two) running the EdgeAI brick, one laptop running the aggregator, any
phone or laptop on the same wifi as the ranger console.

---

## 1. The map: what runs where

| Component | Path | Runs on | What it does |
|---|---|---|---|
| **PEARDUINO** brick | `~/PEARDUINO/` (or `PearTree.zip`) | Arduino UNO Q (deployed via App Lab) | Sensor reads, vibration anomaly detection, on-device LLM chat, per-tree HTTP API on `:7000` |
| **Aggregator** | `~/aggregator/` | Your laptop | Polls every known tree, caches state, serves the ranger dashboard on `:8080` |
| **Browser / phone** | any device | Same wifi as the laptop | Opens the dashboard URL; scans QR codes to chat with individual trees |
| (legacy) `~/hackupc-tree/` | local-only sandbox | Your laptop | Original dev fixture, no longer the deploy unit. Can be ignored. |

**Mental model:**
- One UNO Q = one tree. Each one runs its own copy of PEARDUINO, generates its own LLM responses, exposes its own `:7000`.
- The aggregator is a thin laptop service that polls the trees and merges their state into a fleet view.
- Chat is *direct*: phone scans a tree's QR → talks to that tree's `:7000` → on-device LLM answers. The aggregator is **not** in the chat path.

---

## 2. Prerequisites (one-time)

- macOS laptop (this guide assumes it)
- Arduino App Lab IDE installed
- USB-C cable + the PSU shipped with the UNO Q (laptop USB power alone isn't enough)
- Modulino **Movement** + Modulino **Thermo** with QWIIC cables
- A wifi network where both the UNO Q and your laptop can talk to each other (venue wifi if it doesn't isolate clients, otherwise a phone hotspot)
- Python 3 on your laptop (`python3 --version` should show 3.10+)

If you have a corporate VPN like AppGate, **quit it entirely** for the
duration of this — even disconnected it can hijack local LAN routing.

---

## 3. Deploy PEARDUINO to your UNO Q

This is the device side. Repeat for each UNO Q if you have more than one.

### 3.1 Build the brick zip

App Lab takes either a folder or a zip. The zip path is more reliable
on current builds.

```bash
cd /Users/adrian.patricio
rm -f PearTree.zip
zip -rq PearTree.zip PEARDUINO -x "*/__pycache__/*" "*/.git/*" "*/.DS_Store"
ls -lh PearTree.zip
```

(After any code change, re-run this — that's the redeploy loop.)

### 3.2 Deploy via App Lab

1. Plug the UNO Q into your Mac with USB-C **and the included PSU**.
2. Connect the Modulino Movement and Modulino Thermo to the UNO Q's QWIIC port.
3. Open Arduino App Lab.
4. Import `PearTree.zip`.
5. **Set per-device env vars** (in App Lab's run config / environment panel):
   - First device: `TREE_ID=tree_001`, `TREE_LOCATION=Plaça Reial #3`
   - Second device: `TREE_ID=tree_002`, `TREE_LOCATION=Passeig de Gràcia #12`
   - If App Lab doesn't expose env vars on your build, edit the two lines at the top of `python/main.py` per device before zipping.
6. Hit **Deploy** / **Run**. App Lab compiles `sketch.ino` for the STM32, pushes the Python brick to the Linux side, installs `requirements.txt` (`numpy`, `requests`), and starts everything.

### 3.3 Find the device's wifi IP

App Lab usually exposes a terminal into the UNO Q's Linux side.
Otherwise SSH in (`arduino@<some-ip>` if you can reach it).

```bash
hostname -I
# Find the address on wlan0 — typically 10.x.x.x or 192.168.x.x.
# Ignore Docker bridges (172.17.x.x, 172.18.x.x).
```

Note this IP. The aggregator needs it.

### 3.4 Smoke-test on the device

In the same UNO Q shell:

```bash
curl http://localhost:7000/healthz
# Expect: {"ok":true,"llm":<true|false>,"baseline_ready":<true|false>}

curl http://localhost:7000/state | head -200
# Expect a TreeState JSON with the tree_id you set, real temp_c/humidity
```

If `/healthz` returns 200, the brick is alive. The vibration baseline
takes ~1.5s to learn — `baseline_ready` flips to `true` after that.

---

## 4. Install Ollama on the UNO Q (one-time, optional)

App Lab installs Python deps but **not** Ollama (it's a Linux service,
not a Python package). Without Ollama, chat falls back to deterministic
templated responses — the demo still works, but you lose the
natural-language tree.

In the UNO Q shell:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b
```

The model is ~400 MB, so do this on good wifi. Verify:

```bash
curl http://localhost:7000/healthz
# "llm" should now be true
```

The brick auto-detects Ollama at boot — no restart of PEARDUINO needed
after install (just check `/healthz`).

---

## 5. Run the aggregator on your laptop

This is the laptop side — runs on Mac with no Arduino dependencies.

### 5.1 Install Python deps (one-time)

```bash
cd ~/aggregator
pip3 install -r requirements.txt
```

### 5.2 Start it, pointed at your tree(s)

Single tree:

```bash
KNOWN_TREES="http://10.5.246.172:7000" python3 server.py
```

Two trees:

```bash
KNOWN_TREES="http://10.5.246.172:7000,http://10.5.246.180:7000" python3 server.py
```

Replace the IPs with whatever `hostname -I` showed on each UNO Q. You
should see:

```
[aggregator] polling: ['http://10.5.246.172:7000', ...]
 * Running on http://0.0.0.0:8080
```

Leave that terminal open. Ctrl-C kills the aggregator.

### 5.3 Verify the aggregator sees your tree(s)

In another terminal:

```bash
curl http://localhost:8080/healthz
# Expect: {"ok":true,"trees_known":1,"trees_online":1,...}

curl http://localhost:8080/trees | head -200
# Expect: a JSON list with one entry per tree, each with online: true
```

If `trees_online` is 0 but `trees_known` is 1, the laptop can't reach
the UNO Q — see Troubleshooting (§9).

---

## 6. Open the dashboard

Find your laptop's wifi IP:

```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Use the address on your wifi adapter (NOT a `192.168.x.x → 192.168.x.x`
VPN tunnel address — that's AppGate or similar; quit the VPN if you see
it).

Then on **any device** on the same wifi:

| Page | URL |
|---|---|
| Ranger dashboard | `http://<laptop-IP>:8080/` |
| QR generator | `http://<laptop-IP>:8080/qr` |
| Fleet API | `http://<laptop-IP>:8080/trees` |

---

## 7. Print the QR codes (one per tree)

For each tree, open the QR generator and fill in **the tree's host, not
the laptop's**:

- Host: `<tree-IP>:7000`   (e.g. `10.5.246.172:7000`)
- Tree ID: `tree_001`       (matching the env var you set on that UNO Q)
- Path: `/talk.html`        (default — leave it)
- Click "Print", or screenshot the QR

The QR encodes a URL like `http://10.5.246.172:7000/talk.html?tree_id=tree_001`.
A visitor scanning it lands on **that specific tree's** chat page,
where the on-device LLM answers as that tree.

Stick the QR on the physical demo plant. Repeat for each tree.

---

## 8. Demo-day checklist

Run through this 30 minutes before the demo, in order:

- [ ] AppGate / corp VPN quit on every laptop
- [ ] Both UNO Qs on the same wifi as the aggregator laptop
- [ ] Each UNO Q's IP confirmed via `hostname -I`
- [ ] `curl http://<unoq-ip>:7000/healthz` from the laptop returns 200
- [ ] Aggregator running, `curl http://localhost:8080/trees` shows all expected trees as `"online":true`
- [ ] Dashboard loads from your phone (proves cross-device wifi works)
- [ ] QR scan from your phone opens a tree's chat page and gets a reply
- [ ] You can produce a stress spike on stage (cover camera / shake board) and see the dashboard re-color within 2 seconds
- [ ] Killing one UNO Q gracefully (unplug or stop brick) shows the dashboard mark it offline within 2 seconds; the other tree keeps reporting

If the demo includes "kill the wifi" → confirm before going on stage
that the aggregator and at least one tree stay reachable to the
dashboard via local network even with no internet.

---

## 9. Troubleshooting

### "scp connection timed out"
Different networks. The Mac is on `10.31.x.x` (corp); UNO Q is on
`10.5.x.x` (venue). Switch the Mac's wifi to whatever the UNO Q is on,
or put both on a phone hotspot.

### "scp connection refused"
SSH daemon isn't running on the UNO Q. Use App Lab deploy instead — it
pushes via USB, no SSH needed.

### Dashboard shows all trees `(unreachable)`
Aggregator can't reach them. From the aggregator laptop:
```bash
curl http://<unoq-ip>:7000/healthz
```
If that times out, fix the network first (same wifi, no AppGate, no AP
isolation). If it returns 200, the aggregator config has the wrong IP
or port — restart with the right `KNOWN_TREES`.

### `/healthz` shows `"llm": false`
Ollama isn't installed on that UNO Q, or the model isn't pulled, or the
Ollama service died. SSH into the UNO Q and:
```bash
systemctl status ollama
ollama list   # should show qwen2.5:0.5b
```
If Ollama runs but the model is missing: `ollama pull qwen2.5:0.5b`.

### Dashboard renders but cards stuck on stress=0 forever
Vibration baseline isn't accumulating. Modulino Movement may be
disconnected or dead. In the App Lab logs, look for "Baseline: X/80"
counting up; if no such lines appear, the bridge between sketch and
Python isn't carrying samples — check the QWIIC cable.

### `pip3 install` fails on the UNO Q with "externally-managed-environment"
Use:
```bash
pip3 install --user --break-system-packages flask requests
```

### Laptop's `ifconfig` shows a `192.168.160.x` "tunnel" IP
That's AppGate's VPN — fully quit the AppGate app. Disconnecting alone
isn't enough.

### Venue wifi blocks port 22 (SSH) but you need a shell
Use App Lab's embedded terminal (talks over USB, not network).
Alternatively, install Tailscale on the UNO Q for a stable overlay
that works regardless of venue wifi:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

---

## 10. Common code-change loop

Edit something in `~/PEARDUINO/python/` or `~/PEARDUINO/assets/`:

```bash
cd /Users/adrian.patricio
rm -f PearTree.zip
zip -rq PearTree.zip PEARDUINO -x "*/__pycache__/*" "*/.git/*" "*/.DS_Store"
# → re-import PearTree.zip in App Lab and click deploy
```

Edit something in `~/aggregator/`:

```bash
# Ctrl-C the running aggregator, then:
cd ~/aggregator
KNOWN_TREES="..." python3 server.py
```

The aggregator changes are instant; the UNO Q changes take a redeploy.
