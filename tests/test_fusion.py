from app.fusion import fuse
from app.schemas import Signal


def signal(family, strength):
    return Signal(name=family, family=family, strength=strength, reason="test")


def test_fusion_rules():
    assert fuse([signal("compression", "strong"), signal("noise", "strong")]) == ("STRONG_SIGNALS", "R1")
    assert fuse([signal("compression", "strong")]) == ("WEAK_SIGNALS", "R2")
    assert fuse([signal("compression", "none")]) == ("INCONCLUSIVE", "R3")
    assert fuse([signal("compression", "none"), signal("noise", "none")]) == ("NO_SIGNALS", "R4")


def test_two_strong_same_family_is_not_strong_rule():
    assert fuse([signal("compression", "strong"), signal("compression", "strong")]) == ("WEAK_SIGNALS", "R2")

