# SPDX-License-Identifier: MPL-2.0
"""On-device LLM with templated fallback.

Uses Ollama as the runtime — easy to install on the UNO Q's Linux side
without compiling. If Ollama isn't reachable or the model isn't pulled,
we fall back to deterministic templates so the rest of the system keeps
working end-to-end.

Setup on the UNO Q (one-time):
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen2.5:0.5b

Smoke-test:
    python brain.py "how are you?"
"""
from __future__ import annotations

import os
import sys

import requests

from prompts import build_alert_prompt, build_chat_prompt
from state import SensorReadings, TreeState, VisionResult

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("TREE_MODEL", "qwen2.5:0.5b")

GEN_TIMEOUT_S = 15


class TreeBrain:
    def __init__(self):
        self._llm_available = self._probe()

    @property
    def using_llm(self) -> bool:
        return self._llm_available

    def chat(self, state: TreeState, neighbors: dict, question: str) -> str:
        if not self._llm_available:
            return _template_chat(state, neighbors, question)
        prompt = build_chat_prompt(state, neighbors, question)
        return self._generate(prompt, max_tokens=80) or _template_chat(
            state, neighbors, question
        )

    def alert(self, state: TreeState) -> str:
        if not self._llm_available:
            return _template_alert(state)
        prompt = build_alert_prompt(state)
        return self._generate(prompt, max_tokens=60) or _template_alert(state)

    def _probe(self) -> bool:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            r.raise_for_status()
            tags = [m["name"] for m in r.json().get("models", [])]
            if any(t == MODEL or t.startswith(f"{MODEL}:") for t in tags):
                print(f"[brain] using Ollama model {MODEL}")
                return True
            print(
                f"[brain] Ollama is up but {MODEL} isn't pulled — "
                f"run: ollama pull {MODEL}"
            )
            return False
        except requests.RequestException as e:
            print(
                f"[brain] Ollama not reachable at {OLLAMA_URL} ({e}); "
                f"using templates"
            )
            return False

    def _generate(self, prompt: str, max_tokens: int) -> str | None:
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.6,
                        "stop": [
                            "\n\n",
                            "Question:",
                            "Alert:",
                            "A passerby",
                        ],
                    },
                },
                timeout=GEN_TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json()["response"].strip()
        except requests.RequestException as e:
            print(f"[brain] generation failed ({e}); falling back to template")
            return None


# --- Templated fallbacks --------------------------------------------------
# Cheap, deterministic responses used when the LLM is unavailable. Good
# enough to develop and demo the full pipeline.

def _template_chat(state: TreeState, neighbors: dict, question: str) -> str:
    q = question.lower()
    base = f"I'm {state.tree_id} in {state.location}."
    if any(k in q for k in ("how are you", "feeling", "okay", "ok")):
        if state.stress_index > 60:
            return (
                f"{base} Honestly, struggling — it's {state.sensors.temp_c}°C "
                f"with {state.sensors.humidity}% humidity, and my stress is "
                f"{state.stress_index}/100. I could use some water."
            )
        return (
            f"{base} Doing alright — {state.sensors.temp_c}°C and "
            f"humidity around {state.sensors.humidity}%."
        )
    if any(k in q for k in ("hot", "temp", "warm", "cold")):
        delta = state.sensors.temp_c - neighbors["park_avg_temp_c"]
        return (
            f"{base} It's {state.sensors.temp_c}°C here — "
            f"{delta:+.1f}°C versus the park average."
        )
    if any(k in q for k in ("humid", "wet", "dry")):
        return (
            f"{base} Humidity is {state.sensors.humidity}% — "
            f"{'pretty dry' if state.sensors.humidity < 40 else 'comfortable'} for me."
        )
    if any(k in q for k in ("shake", "wind", "vibration", "movement")):
        return (
            f"{base} My vibration anomaly score is "
            f"{state.sensors.movement:.2f}; "
            f"{'something is shaking me' if state.sensors.movement > 4 else 'all calm'}."
        )
    if any(k in q for k in ("neighbor", "park", "others", "around")):
        return (
            f"{base} My {neighbors['neighbor_count']} neighbors average "
            f"{neighbors['park_avg_stress']}/100 stress; I'm at "
            f"{state.stress_index}."
        )
    return (
        f"{base} Stress {state.stress_index}/100, "
        f"last reading {state.sensors.temp_c}°C."
    )


def _template_alert(state: TreeState) -> str:
    label = state.vision.label.replace("_", " ")
    if state.stress_index > 70:
        return (
            f"URGENT — Tree {state.tree_id} at {state.location}: "
            f"stress {state.stress_index}/100, {state.sensors.temp_c}°C, "
            f"humidity {state.sensors.humidity}%. Inspect now."
        )
    if state.stress_index > 40:
        return (
            f"Watch — Tree {state.tree_id} at {state.location}: moderate "
            f"stress ({state.stress_index}/100), {label}."
        )
    return f"OK — Tree {state.tree_id} at {state.location}: {state.stress_index}/100."


if __name__ == "__main__":
    # Standalone smoke-test with a fake state
    fake = TreeState(
        tree_id="tree_001",
        location="Plaça Reial #3",
        sensors=SensorReadings(temp_c=34.2, humidity=38.0, movement=5.4),
        vision=VisionResult(label="leaf_drought_stress", confidence=0.78),
        stress_index=72,
    )
    fake_neighbors = {
        "neighbor_count": 6,
        "park_avg_temp_c": 30.1,
        "park_avg_stress": 45,
    }
    brain = TreeBrain()
    if len(sys.argv) > 1:
        print(brain.chat(fake, fake_neighbors, " ".join(sys.argv[1:])))
    else:
        print("ALERT:", brain.alert(fake))
        print("CHAT :", brain.chat(fake, fake_neighbors, "how are you?"))
