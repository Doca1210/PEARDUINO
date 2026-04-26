# SPDX-License-Identifier: MPL-2.0
"""TreeState dataclasses shared between the sensor loop, the LLM brain,
and the HTTP API. Designed for the App Lab brick context: state is built
from sensor callbacks in main.py and passed to the brain by value, so
no file-based fallback is needed here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class SensorReadings:
    temp_c: float
    humidity: float
    movement: float    # vibration anomaly score (Mahalanobis distance)


@dataclass
class VisionResult:
    label: str
    confidence: float


@dataclass
class TreeState:
    tree_id: str
    location: str
    sensors: SensorReadings
    vision: VisionResult
    stress_index: int
    alert: str | None = None
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)
