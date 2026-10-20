"""Java RQ1 Formal Stable qualification decision rule (Issue Pilot #4).

PLAN_VERSION v1.2-amendment-r3 (owner decision PL-SOLO-V2-OWNER-DECISION-
20261020-R3 section 2, revision 1):

- QUALIFIED / NOT_QUALIFIED stay the ONLY qualification outcomes; the
  frozen binary rule (plan-frozen-v1.md section 5) is unchanged.
- INCONCLUSIVE is an honest disclosure tier for INVALID evidence, not a
  qualification middle tier. It fires only when the design-weighted
  estimator or its bootstrap CI cannot be computed validly:

  G1  total sample size is 0
  G2  a stratum with population N_h > 0 received n_h = 0 sampled cases
      (coverage hole: W_h = N_h / N assigns that share weight while no
      data represents it - the weighted estimate would be biased)
  G3  a metric is undefined (None / NaN: its denominator is empty)
  G4  annotation is incomplete (sampled cases without a final adjudication)

  Wide-but-valid confidence intervals are NOT INCONCLUSIVE: a valid
  estimate that fails the bounds is a legitimate NOT_QUALIFIED.
"""
from __future__ import annotations

import math

RP_MIN, RP_LO_MIN = 0.90, 0.85
FRA_MAX, FRA_HI_MAX = 0.10, 0.15


def _defined(value) -> bool:
    return value is not None and isinstance(value, (int, float)) \
        and not isinstance(value, bool) and math.isfinite(value)


def stable_verdict(rp, rp_lo, fra, fra_hi, calibration_passed: bool,
                   stratum_samples: dict[str, int],
                   stratum_populations: dict[str, int],
                   annotation_complete: bool = True) -> dict:
    """Return {"verdict": ..., "reasons": [...]}.

    verdict is one of QUALIFIED / NOT_QUALIFIED / INCONCLUSIVE. All input
    numbers are reported verbatim by the caller regardless of verdict.
    """
    reasons: list[str] = []
    n_total = sum(stratum_samples.values())
    if n_total == 0:
        reasons.append("G1_total_sample_zero")
    for stratum, population in stratum_populations.items():
        if population > 0 and stratum_samples.get(stratum, 0) == 0:
            reasons.append(f"G2_unrepresented_stratum:{stratum}")
    for name, value in (("rp", rp), ("rp_lo", rp_lo),
                        ("fra", fra), ("fra_hi", fra_hi)):
        if not _defined(value):
            reasons.append(f"G3_metric_undefined:{name}")
    if not annotation_complete:
        reasons.append("G4_annotation_incomplete")
    if reasons:
        return {"verdict": "INCONCLUSIVE", "reasons": reasons}

    qualified = (rp >= RP_MIN and rp_lo >= RP_LO_MIN
                 and fra <= FRA_MAX and fra_hi <= FRA_HI_MAX
                 and calibration_passed)
    return {"verdict": "QUALIFIED" if qualified else "NOT_QUALIFIED",
            "reasons": []}
