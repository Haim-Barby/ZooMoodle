"""Zone-level attention aggregates.

The live camera path is not part of this demo. Callers may store samples only
when they label the source `sample-not-camera`. No frames are accepted.
"""

from __future__ import annotations

from app.domain import SEAT_ZONES

DISCLAIMER = (
    "Attention map stub. No camera is running, no frames are stored, and "
    "there is no face recognition. Figures below are zone aggregates only, "
    "and only if sample data labeled sample-not-camera was entered. "
    "This is an indicator, not a grade."
)


class AttentionAggregator:
    def __init__(self):
        self.samples: list[dict] = []

    def add_sample(self, t_seconds: float, zone: str, level: float, source: str) -> None:
        if source != "sample-not-camera":
            raise ValueError("only sample-not-camera data is accepted in this demo")
        if zone not in SEAT_ZONES:
            raise ValueError("unknown seat zone")
        level_value = float(level)
        if not 0.0 <= level_value <= 1.0:
            raise ValueError("level must be between 0 and 1")
        self.samples.append(
            {
                "t_seconds": float(t_seconds),
                "zone": zone,
                "level": level_value,
                "source": source,
            }
        )

    def by_zone(self, start: float | None = None, end: float | None = None) -> dict:
        chosen = []
        for sample in self.samples:
            if start is not None and sample["t_seconds"] < start:
                continue
            if end is not None and sample["t_seconds"] > end:
                continue
            chosen.append(sample)
        buckets: dict[str, list[float]] = {}
        for sample in chosen:
            buckets.setdefault(sample["zone"], []).append(sample["level"])
        zones = {
            zone: {
                "mean_level": round(sum(values) / len(values), 3),
                "samples": len(values),
            }
            for zone, values in sorted(buckets.items())
        }
        return {
            "disclaimer": DISCLAIMER,
            "empty": not chosen,
            "source": "sample-not-camera" if chosen else "none",
            "zones": zones,
            "count": len(chosen),
        }
