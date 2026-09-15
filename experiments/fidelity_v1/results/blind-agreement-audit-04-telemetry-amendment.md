# Audit 04 Telemetry-Label Reconciliation

**Result: MAPPING GAP RECORDED — no annotation or protocol change**

The frozen Batch 04 telemetry schema defines `verification_depth` only as the
enumeration `L0|L1|L2|L3|L4`. The permitted frozen protocol files do not define
which depth corresponds to same-file navigation, cross-file navigation,
cross-module navigation, or Build Context. Therefore the planned interpretation
`L0=blind`, `L1=same-file`, `L2=cross-file`, `L3=cross-module`, `L4=Build Context`
cannot be asserted for Batch 04.

Observed telemetry remains intact:

| Source | Depth labels | Navigation files |
| --- | --- | ---: |
| A | L0: 60 | 0 total |
| B | L0: 49; L1: 11 | 11 total |

The navigation-only classification is still computable from the frozen fields:
49 cases have zero navigation files for both annotators (`LOCAL_ONLY`), and 11
have at least one navigation file (`CROSS_FILE`). The original report's
`CROSS_FILE / L1` is retained only as an observed-label pairing, not as a
frozen semantic definition.

No `SCHEMA_INCOMPATIBILITY` is declared: all required fields and enum values
are present and valid. This is a measurement-meaning availability gap. It does
not change formal verdicts, target-cardinality results, Drift Gate, or sealed
A04/B04 records. C/C++ Drift Gate remains **PASS** and Batch 05 C/C++ remains
**UNBLOCKED**.
