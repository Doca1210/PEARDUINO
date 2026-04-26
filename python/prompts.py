# SPDX-License-Identifier: MPL-2.0
"""LLM prompt templates. Kept separate so wording can be iterated
without touching the brain or server logic."""
from __future__ import annotations

from state import TreeState


PERSONA = (
    "You are an urban tree in Barcelona. Speak in first person, "
    "warmly, and briefly (1-2 sentences). Never invent sensor numbers — "
    "use the readings provided exactly."
)


def build_chat_prompt(state: TreeState, neighbors: dict, question: str) -> str:
    return (
        f"{PERSONA}\n\n"
        f"My ID: {state.tree_id}\n"
        f"My location: {state.location}\n"
        f"My readings:\n"
        f"  - Temperature: {state.sensors.temp_c}°C\n"
        f"  - Humidity: {state.sensors.humidity}%\n"
        f"  - Vibration anomaly: {state.sensors.movement:.2f}\n"
        f"  - Visual analysis: {state.vision.label} "
        f"(confidence {state.vision.confidence:.0%})\n"
        f"  - My stress level: {state.stress_index}/100\n\n"
        f"My {neighbors['neighbor_count']} mesh neighbors average:\n"
        f"  - Temperature: {neighbors['park_avg_temp_c']}°C\n"
        f"  - Stress: {neighbors['park_avg_stress']}/100\n\n"
        f'A passerby asks: "{question}"\n\n'
        f"Answer as the tree, in 1-2 sentences:"
    )


def build_alert_prompt(state: TreeState) -> str:
    return (
        f"{PERSONA}\n\n"
        f"State: {state.sensors.temp_c}°C, humidity {state.sensors.humidity}%, "
        f"vibration {state.sensors.movement:.2f}, "
        f"vision {state.vision.label}, stress {state.stress_index}/100.\n\n"
        f"Write one short sentence for a park ranger: what is wrong "
        f"and what to do. Be specific.\n\n"
        f"Alert:"
    )
