# Methodology

The fusion rules are deterministic:

- R1 `STRONG_SIGNALS`: at least two different families are strong.
- R2 `WEAK_SIGNALS`: no R1, with at least one weak or strong family.
- R3 `INCONCLUSIVE`: fewer than two determined families or a failed quality gate.
- R4 `NO_SIGNALS`: at least two determined families and all are none.

The current image modules are ELA, noise residual, ORB copy-move, and an explicit not-determined learned-detector placeholder. Scores are bounded between zero and one. No score alone is a verdict.

