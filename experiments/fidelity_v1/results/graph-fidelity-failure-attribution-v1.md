# Graph Fidelity Failure Attribution V1

```text
status: ATTRIBUTION_COMPLETE_NO_REPAIR
scope:  28 scoring_error_cases[] of graph-fidelity-scoring-v1; scoring states unchanged
claims: no RQ1 verdict, no repair, no post-repair results in this artifact
```

## Provenance

| Artifact | SHA256 |
| --- | --- |
| Gold (cpp-structural-relation-gold-v1.json) | 794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93 |
| System prediction (pilot-candidates.json) | 558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484 |
| Join (system-gold-join-v1.json) | a9fdd0a5b531e175703c64777c91bd6ba2578cf6db925e392ed1f39752099f6b |
| Scoring (graph-fidelity-scoring-v1.json) | 336794b4af7f5d9cbd518f21f2f788789413e2499fce0d668439b459e6d0382a |
| Attribution script | f80dceea78ddd6c7136e6495552e674f1e05da8250016311878dec34c87cc0fd |

## Attribution totals (28/28)

| Primary failure mechanism | n |
| --- | ---: |
| CANDIDATE_GENERATION_MISS | 10 |
| RESOLVER_ABSTENTION | 11 |
| RESOLVER_OVER_RESOLUTION | 7 |

Key mechanism counts: CANDIDATE_GENERATION_MISS 10, RESOLVER_ABSTENTION 11, RESOLVER_WRONG_SELECTION 0 (primary; +1 contributing), RESOLVER_OVER_RESOLUTION 7.

Contributing failures: DECL_DEF_CANONICALIZATION=1, RECEIVER_OR_OWNER_MISMATCH=8, RESOLVER_WRONG_SELECTION=1

## By scoring state

| Scoring state | n | mechanisms |
| --- | ---: | --- |
| WRONG_TARGET_RESOLUTION | 1 |  x1 |
| FALSE_RESOLUTION_ON_ABSENT | 7 |  x7 |
| MISSED_RESOLUTION_OPPORTUNITY | 20 |  x20 |

## By repository / relation / resolver strategy

| Dimension | Distribution |
| --- | --- |
| repository | aria2=12, brpc=7, rocksdb=9 |
| relation | CALLS=28 |
| resolver strategy | ambiguous=10, qualified_name_resolution=1, same_file_resolution=3, unique_symbol_resolution=6, unresolved=8 |

## Per-case attributions

| Sample | State | Repo | Relation | Strategy | Cand n | Correct target in cand set | Primary | Contributing |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| FQV1-aria2-713b641e93cc620c | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-brpc-68baef18ae4bd3ee | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | same_file_resolution | 2 | true | RESOLVER_ABSTENTION |  |
| FQV1-brpc-b210f3349b031961 | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | ambiguous | 3 | true | RESOLVER_ABSTENTION |  |
| FQV1-rocksdb-8e526ba5ac0d956a | FALSE_RESOLUTION_ON_ABSENT | rocksdb | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-brpc-d12b7bdc3ecd5bbc | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | qualified_name_resolution | 2 | true | RESOLVER_ABSTENTION |  |
| FQV1-aria2-52bdba205b5ce686 | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-aria2-0f84707a755b6d84 | FALSE_RESOLUTION_ON_ABSENT | aria2 | CALLS | same_file_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-aria2-c900f72d67f383ae | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-brpc-8c9d0887e1f9d4fe | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-rocksdb-657008a8ca392740 | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-aria2-c6525c9d8d155f3f | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | ambiguous | 3 | true | RESOLVER_ABSTENTION |  |
| FQV1-rocksdb-85a27eca37b8f8c1 | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | ambiguous | 2 | true | RESOLVER_ABSTENTION |  |
| FQV1-rocksdb-ec017de0157014f4 | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS | DECL_DEF_CANONICALIZATION |
| FQV1-aria2-4f7155139b696d14 | FALSE_RESOLUTION_ON_ABSENT | aria2 | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-brpc-51d58c46a6424852 | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | ambiguous | 2 | true | RESOLVER_ABSTENTION |  |
| FQV1-rocksdb-e23ab7dea713cf57 | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | ambiguous | 6 | true | RESOLVER_ABSTENTION |  |
| FQV1-aria2-4656d1df0792fedd | FALSE_RESOLUTION_ON_ABSENT | aria2 | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-rocksdb-ecb7a6891b617490 | WRONG_TARGET_RESOLUTION | rocksdb | CALLS | same_file_resolution | 1 | n/a | CANDIDATE_GENERATION_MISS | RESOLVER_WRONG_SELECTION, RECEIVER_OR_OWNER_MISMATCH |
| FQV1-rocksdb-aa505d4616aede0b | FALSE_RESOLUTION_ON_ABSENT | rocksdb | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-aria2-5c9b99ecc0454a4a | FALSE_RESOLUTION_ON_ABSENT | aria2 | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-brpc-c854e345d2d4b8a8 | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | ambiguous | 4 | true | RESOLVER_ABSTENTION |  |
| FQV1-aria2-0102241c89b94614 | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | ambiguous | 12 | true | RESOLVER_ABSTENTION |  |
| FQV1-aria2-d92c0476f269fe9c | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-brpc-bc38ae52a3ef3090 | MISSED_RESOLUTION_OPPORTUNITY | brpc | CALLS | ambiguous | 97 | false | CANDIDATE_GENERATION_MISS |  |
| FQV1-aria2-3fa9480748303413 | MISSED_RESOLUTION_OPPORTUNITY | aria2 | CALLS | ambiguous | 3 | true | RESOLVER_ABSTENTION |  |
| FQV1-rocksdb-8b4ca63de7918ec9 | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | ambiguous | 3 | true | RESOLVER_ABSTENTION |  |
| FQV1-aria2-c10fd7262a136c88 | FALSE_RESOLUTION_ON_ABSENT | aria2 | CALLS | unique_symbol_resolution | 1 | n/a | RESOLVER_OVER_RESOLUTION | RECEIVER_OR_OWNER_MISMATCH |
| FQV1-rocksdb-3b90b89381b8d13d | MISSED_RESOLUTION_OPPORTUNITY | rocksdb | CALLS | unresolved | 0 | false | CANDIDATE_GENERATION_MISS |  |

## MISSED_RESOLUTION split (20 cases)

- correct target NOT in candidate set (incl. 8 empty candidate sets and 1 sealed flag over 97 ambiguous candidates) -> CANDIDATE_GENERATION_MISS: 10 of the 20 missed opportunities
- correct target IS in candidate set but the resolver abstained -> RESOLVER_ABSTENTION: 11 of 20
- correct_target_exists_in_repository = true for all 20 (gold target-present cases); no BUILD_CONTEXT_LIMIT case occurs in the error set

## Discipline

- Gold, system prediction, join and scoring artifacts read-only; mutation = 0; scoring states echoed unchanged.
- No resolver/candidate-generation repair, no re-annotation/adjudication, no post-repair results, no RQ1 claim.

