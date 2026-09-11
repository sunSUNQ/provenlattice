# Evaluator V2 fixtures

`tests/test_evaluator_v2.py` is the deterministic E1–E10 fixture suite:

| Fixture | Contract |
|---|---|
| E1 | exact required evidence |
| E2 | valid ANY_OF alternative |
| E3 | supporting evidence cannot satisfy required concept |
| E4 | distractor/invalid evidence |
| E5 | unknown Evidence ID |
| E6 | document fragment canonicalization |
| E7 | Windows/POSIX path equivalence |
| E8 | multiple valid evidence paths |
| E9 | partial ALL_OF concept coverage |
| E10 | malformed citation rejected |
