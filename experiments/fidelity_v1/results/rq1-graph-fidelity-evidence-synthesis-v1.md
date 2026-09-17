# RQ1 — Graph Fidelity Final Evidence Synthesis V1

## 1. RQ1 Verdict

Under the frozen C/C++ Structural Relation Fidelity V1 benchmark, the current ProvenLattice V0.2 Graph Fabric is usually semantically correct when it resolves an evaluable relation, but its fidelity is substantially constrained by coverage—especially for CALLS in high-population nonresolved strata.

This conclusion must not be compressed into a single accuracy number:

- Semantic precision when resolving is high but not perfect: resolved precision is 93.10% in the unweighted 174-case sample view and 89.92% after population weighting.
- Coverage is the principal limitation: sample target-opportunity coverage is 84.50%, whereas population-weighted target-opportunity coverage is 24.36%; the weighted missed-resolution-opportunity rate is 75.64%.
- CALLS and IMPORTS behave differently. In the evaluated sample, IMPORTS has 100% resolved precision, 100% target-opportunity coverage, and 100% abstention quality. CALLS has 85.71% resolved precision, 71.01% target-opportunity coverage, and 31.03% abstention quality.
- C/C++ REFERENCES is not represented by the evaluated extractor. Its population is zero, so REFERENCES fidelity cannot be estimated in V1. This is a `GRAPH_REPRESENTATION_GAP`, not a low measured REFERENCES accuracy.

Accordingly, the evidence supports the bounded statement: when ProvenLattice resolves an evaluable C/C++ CALLS or IMPORTS relation in this frozen benchmark, its semantic target is usually correct. It also supports the statement that fidelity is primarily limited by relation-resolution coverage rather than pervasive wrong-target selection: there is one wrong-target resolution versus 20 missed resolution opportunities, and weighted target-opportunity coverage is only 24.36%.

## 2. Evidence Level

**RQ1 Evidence Level: QUALIFIED**

Scope: current ProvenLattice V0.2 Graph Fabric; C/C++ CALLS and IMPORTS; aria2, brpc, and RocksDB; frozen V1 sampling frame.

The evidence exceeds `PARTIAL`: it includes three repositories, 174 frozen Gold cases, independent/blinded annotation across multiple batches, adjudication, deterministic join and scoring, failure attribution for all 28 scored errors, frozen population weights, and per-stratum reporting. It is not `REPLICATED` or `GENERALIZED`: there is no external-system baseline, no post-repair replication, no evidence for C/C++ REFERENCES, only three repositories, and no million/10M-scale fidelity validation.

## 3. Core Findings

The 174-case Gold set contains 86 CALLS and 88 IMPORTS: 123 UNIQUE, 6 DIVERGENT, 44 ABSENT, and 1 INDETERMINATE. Deterministic scoring classified every case exactly once:

| Scoring state | Count |
|---|---:|
| CORRECT_RESOLUTION | 108 |
| WRONG_TARGET_RESOLUTION | 1 |
| MISSED_RESOLUTION_OPPORTUNITY | 20 |
| FALSE_RESOLUTION_ON_ABSENT | 7 |
| JUSTIFIED_ABSTENTION | 37 |
| INDETERMINATE_EXCLUDED | 1 |

The semantic precision claim is supported but must include both estimates: sample resolved precision is 93.10%, while population-weighted resolved precision is 89.92%. The corresponding selective risks are 6.90% and 10.08%.

The coverage limitation is stronger than the wrong-target-selection signal. Only one target-present resolved case selected the wrong semantic target, while 20 target-present cases were left unresolved. This does not make over-resolution negligible: seven ABSENT cases were nevertheless resolved, and all seven involved receiver/owner mismatch.

## 4. Population-Weighted Findings

| Metric | Sample descriptive | Population-weighted |
|---|---:|---:|
| Resolved Precision | 0.9310 | 0.8992 |
| Selective Risk | 0.0690 | 0.1008 |
| Resolution Coverage | 0.6705 | 0.1866 |
| Target Opportunity Coverage | 0.8450 | 0.2436 |
| False Resolution on Absent Rate | 0.1591 | 0.0468 |
| Abstention Rate | 0.3295 | 0.8134 |
| Abstention Quality | 0.6491 | 0.3393 |
| Missed Resolution Opportunity Rate | 0.1550 | 0.7564 |

The sample resolution coverage of 67.05% and weighted resolution coverage of 18.66% are both correct because they answer different questions. The sample is stratified and intentionally allocates cases across repositories, relations, and resolved/nonresolved strata; it is not distributed in proportion to the extraction population. Population weighting restores each stratum's frozen population share.

The largest stratum, RocksDB `CALLS_NONRESOLVED`, contains 226,886 C/C++ relations and carries weight 0.5503. Its nine-case sample contains six target-present cases, all six scored as missed resolutions, and three ABSENT cases, all three scored as justified abstentions. Reweighting therefore gives this low-coverage stratum dominant influence. The weighted result is an expected consequence of the sampling design, not an anomaly, and the unweighted sample must not be described as the deployment population.

## 5. Relation-Specific Findings

### CALLS

CALLS is the dominant measured fidelity limitation. Its sample resolved precision is 85.71%, target-opportunity coverage is 71.01%, and abstention quality is 31.03%. All 28 attributed scoring errors are CALLS. The population-weighted results are further dominated by nonresolved CALLS, especially the RocksDB stratum described above.

### IMPORTS

IMPORTS is strong within this benchmark: sample resolved precision, target-opportunity coverage, and abstention quality are each 100%. There are no attributed IMPORTS failures. This is evidence about the frozen C/C++ IMPORTS cases in aria2, brpc, and RocksDB; it is not evidence that IMPORTS resolution is universally perfect.

### REFERENCES

The evaluated extractor produced a C/C++ REFERENCES population of 0. REFERENCES is therefore not represented and is not evaluable in V1. No REFERENCES accuracy, precision, coverage, or fidelity estimate is supported. Classification: `GRAPH_REPRESENTATION_GAP`.

## 6. Failure-Mechanism Findings

All 28 scored errors have primary attribution: 10 `CANDIDATE_GENERATION_MISS`, 11 `RESOLVER_ABSTENTION`, and 7 `RESOLVER_OVER_RESOLUTION`.

- Candidate generation gap: nine of the 20 missed opportunities had the correct repository target absent from the candidate set. The single wrong-target case was also primarily a candidate-generation miss, bringing the total primary count to 10; it additionally involved wrong selection and receiver/owner mismatch. A missing correct candidate is not a case where the resolver ranked and selected the wrong candidate.
- Resolver abstention: in 11 of the 20 missed opportunities, the correct target was present in the candidate set but the resolver did not resolve it. These are not candidate-generation failures.
- Resolver over-resolution: seven Gold-ABSENT cases were resolved. These are false resolutions, not missed resolutions. Receiver/owner mismatch occurred in all seven; six used single-candidate `unique_symbol_resolution` on external-receiver calls.

These mechanisms require different future interventions, but repair design and repair experiments are outside this synthesis.

## 7. Claim Boundary

### Supported

- The frozen 174-case C/C++ evaluation produced 108 correct resolutions, 1 wrong-target resolution, 20 missed opportunities, 7 false resolutions on ABSENT cases, 37 justified abstentions, and 1 excluded INDETERMINATE case.
- Resolved semantic targets are usually correct in the evaluated sample and weighted population estimates: 93.10% sample resolved precision and 89.92% population-weighted resolved precision.
- Coverage is the principal measured limitation relative to wrong-target selection: 20 missed opportunities versus one wrong-target resolution, with 24.36% weighted target-opportunity coverage and a 75.64% weighted missed-opportunity rate.
- The 28 attributed failures separate into candidate generation, resolver abstention, and over-resolution mechanisms; they should not be collapsed into one category of resolver error.
- C/C++ REFERENCES population is zero and its fidelity cannot be estimated in V1.

### Supported with scope qualifier

- For the current V0.2 system on the frozen aria2, brpc, and RocksDB C/C++ benchmark, resolved CALLS/IMPORTS targets are usually semantically correct.
- IMPORTS is strong within the evaluated benchmark.
- CALLS is the dominant fidelity limitation within the evaluated relation population.
- Population-weighted performance is substantially more abstention- and coverage-limited than the balanced descriptive sample suggests.

Every such claim must retain the qualifiers: current V0.2, three repositories, C/C++, CALLS/IMPORTS, and frozen V1 benchmark.

### Not Supported

- ProvenLattice has high graph fidelity in general.
- ProvenLattice handles C/C++ REFERENCES reliably.
- ProvenLattice generalizes to arbitrary repositories, languages, or relation types.
- ProvenLattice outperforms Joern, SCIP, CodeGraphContext, or any other system.
- ProvenLattice has demonstrated fidelity at one-million- or 10M-LOC scale.
- The current Graph Fidelity problem is solved.
- IMPORTS resolution is universally perfect.
- The unweighted 174-case sample metrics directly describe the deployment population.

## 8. Threats and Limitations

- Language and relation scope is limited to C/C++ CALLS and IMPORTS.
- C/C++ REFERENCES is absent from the extraction population.
- Repository diversity is limited to aria2, brpc, and RocksDB.
- The benchmark has 174 Gold cases; rare failure modes may be imprecisely estimated.
- Population estimates depend on the frozen stratified sampling frame and its weights.
- RocksDB `CALLS_NONRESOLVED` contributes 55.03% of the weighted C/C++ population, making weighted conclusions sensitive to that stratum's observed behavior.
- One INDETERMINATE case is excluded from correctness denominators.
- No external-system baseline supports comparative claims.
- There is no independent replication, post-repair replication, or demonstrated million/10M-scale fidelity generalization.

## 9. Next Evidence Required

- Add and freeze a C/C++ REFERENCES population before estimating REFERENCES fidelity.
- Replicate the same frozen protocol on additional repositories and, where relevant, additional languages and relation types.
- Run an independently frozen post-repair evaluation before claiming improvement.
- Add external baselines before making comparative performance claims.
- Validate fidelity at substantially larger repository and graph scales before making million/10M-scale claims.

These are evidence requirements, not repair work performed in this task.

## 10. Final Milestone Recommendation

The current evidence is sufficient to freeze **P0 Graph Fidelity Qualification V1** as a completed research milestone with evidence level `QUALIFIED` and the scope boundaries above.

`research milestone closed` does not mean `Graph Fidelity problem solved`. The milestone establishes a reproducible bounded baseline, identifies strong in-scope IMPORTS behavior, quantifies CALLS coverage limitations, and records the C/C++ REFERENCES representation gap. It does not establish generalized fidelity or close the identified capability gaps.

Status: **RQ1 EVIDENCE SYNTHESIS COMPLETE**

Input artifacts and scoring results were not modified. No parser, candidate generator, resolver, or extractor repair was performed.
