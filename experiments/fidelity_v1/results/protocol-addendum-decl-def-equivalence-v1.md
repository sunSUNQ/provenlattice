# Protocol Addendum — Declaration–Definition Equivalence V1 (FROZEN)

```text
status: FROZEN
date: 2026-09-14
ratified_by: experiment owner (batch-02 audit directive)
parent_protocol_commit: 12f405c677582a2982d035433bf6837126772716
companion_artifact: sampling-frame-correction-v1.json
trigger: OBS-DECL-DEFN-TWIN (batch-02) - graph models one function as declaration +
         definition nodes; naive "gold = definition" scoring would count modeling
         duplication as resolver failure.
```

## Rule

For a declaration / definition pair that can be proven to denote the **same semantic entity**
(same qualified name; declaration role vs definition role by source location; NOT overloads,
which are distinct entities even when same-named):

```text
acceptable_targets = [
    declaration_symbol_id,
    definition_symbol_id
]

canonical_target = definition_symbol_id
```

`canonical_target` is the single representative used for unified display, query returns, and the
Gold Set's primary target. Fidelity scoring is two-layered:

```text
Semantic Target Correctness
  -> declaration twin OR definition twin counts as CORRECT

Canonical Node Correctness
  -> whether the canonical representative was hit
```

Example:

```text
CALL foo()  resolved to  foo declaration
=> semantic_relation = CORRECT
   canonical_node    = NON_CANONICAL_TWIN
NOT WRONG_TARGET
```

## Gold schema additions

```text
target_equivalence_group   { canonical_target, acceptable_targets[], members[], equivalence_reason }
canonical_target
acceptable_targets[]
equivalence_reason         = DECLARATION_DEFINITION_TWIN
```

## Verification method and current groups

Group membership is established by same-qualified-name queries over the frozen graph databases
(role assignment: declaration = header/source-range node; definition = body node). Detected in
Annotator B batch-02 (5 groups; all golds are definitions, hence canonical_target == gold id):

| case | entity | gold/canonical (definition) | declaration twin |
| --- | --- | --- | --- |
| FQV1-aria2-42189fc8a97eb196 | aria2.DHTPingTask.addMessage | src/DHTPingTask.cc:59 | src/DHTPingTask.h:57 |
| FQV1-brpc-d12b7bdc3ecd5bbc | bthread_start_urgent | src/bthread/bthread.cpp:335 | src/bthread/bthread.h:51 |
| FQV1-brpc-925bccaa1f6af572 | brpc.policy.ReadThriftStruct | src/brpc/policy/thrift_protocol.cpp:126 | src/brpc/thrift_message.h:120 |
| FQV1-aria2-52bdba205b5ce686 | aria2.HttpHeader.setStatusCode | src/HttpHeader.cc:180 | src/HttpHeader.h:116 |
| FQV1-brpc-5a19585afcd8a6d6 | butil.BigEndianWriter.Write | src/butil/big_endian.cc:77 | src/butil/big_endian.h:91 |

Annotator B batch-02 records were enriched additively with the four schema fields (no verdict or
evidence text changed).

## Effective scope

```text
Effective from:      immediately (batch-02 join and all later batches)
Applies to:          all CALLS/REFERENCES gold targets with provable decl/def twins
Does not rewrite:    sealed Calibration A/B records - calibration twins
                     (aria2.List.append, CouchbaseResponse.MergeFrom) are interpreted
                     under this rule at scoring time
Scoring effect:      prevents Fidelity Precision from being artificially depressed by
                     graph node duplication
Guards:              applies only to provable same-entity twins; overloads, distinct
                     same-named entities, and shadowing cases are NOT equivalent groups
```
