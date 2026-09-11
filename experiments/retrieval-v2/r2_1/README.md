# ProvenLattice V1.0-R2.1

R2.1 freezes two independent progression tracks at brpc commit
`ae09e960c7291605dda52356cc0c2d45567fb53e` with model
`claude-sonnet-4-5-20250929`.

## Track A — CodeGraph Progression

`CodeGraph-R2` is a **POSITIVE CANDIDATE** after T05. The frozen tasks are T01
(Document to Code), T03 (Code to Document), and T05 (Module Understanding). Their prompts are
byte-for-byte equal to the prior frozen task definitions. The evaluator-only R2 Evidence IDs do
not appear in Agent prompts.

The matrix is three repetitions of Native and CodeGraph for each task: 18 cells. Arm order is
counterbalanced by repetition. The Core-only database physically prevents Knowledge access.

The pre-run CodeGraph progression gate requires 18/18 valid cells; for every task, CodeGraph
success rate and median recall must be no lower than Native; CodeGraph must introduce no unsupported
citation and no higher wrong-path count; and at least two of the three task types must reduce median
tool turns or median unique files. Evidence precision and turns-to-first-relevant-evidence remain
reported comparison metrics but are not silently optimized after seeing results.

## Track B — Knowledge Evidence Audit and Requalification

The frozen T05 Knowledge-R2 run is classified as **A. Query Bundle Gap**. The correct Cross-Layer
Link was returned and used, but its directly supporting DocumentSection Evidence was neither
returned nor exposed. The lifecycle audit is in `t05-knowledge-lifecycle-audit.md` and `.json`.

The only implementation change is EvidenceBundle composition in `explain_symbol`: directly linked
DocumentSection Evidence accompanies the Cross-Layer Link in primary evidence. No Resolver,
Knowledge Coverage, graph contract, node, edge, or evaluator rule changes.

Knowledge R2.1 consists only of `T05 × Knowledge × 3`. Its gate is:

- 3/3 Task Success;
- median required Evidence recall 1.0;
- zero unsupported citations;
- no wrong Evidence regression.

Raw cells under `results/T*/` remain local; reviewed aggregate results are versioned.

If an infrastructure failure interrupts the matrix, `--resume` audits and preserves every complete
cell and resumes only missing cells. An empty directory left before artifact creation may be removed;
a non-empty invalid cell is never overwritten.
