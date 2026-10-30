from collections.abc import Iterable
from .schemas import Signal, Tier


def fuse(signals: Iterable[Signal]) -> tuple[Tier, str]:
    determined = [s for s in signals if s.strength != "not_determined"]
    families = {s.family for s in determined}
    strong_families = {s.family for s in determined if s.strength == "strong"}
    if len(strong_families) >= 2:
        return "STRONG_SIGNALS", "R1"
    if any(s.strength in ("weak", "strong") for s in determined):
        return "WEAK_SIGNALS", "R2"
    if len(families) < 2:
        return "INCONCLUSIVE", "R3"
    return "NO_SIGNALS", "R4"

