# Batch 02 C/C++ CALLS Source-Only Adjudication

## Status

`SEALED` — four cases only. The sealed A/B annotation records were not modified.

The adjudicator used A/B verdicts and evidence, the frozen repositories, and
CALLS_V1, Evidence Scope V1, and Declaration–Definition Equivalence V1. No
system prediction, resolver status/strategy/confidence, system-selected target,
Fidelity metric, or later-batch outcome was read.

## Results

| Case | Final gold verdict | Failure mechanism | Correct target in candidate set | Cross-file recovery necessary |
| --- | --- | --- | --- | --- |
| `FQV1-rocksdb-8e526ba5ac0d956a` | `NO_VALID_TARGET` | Same name, wrong receiver/owner | No | Yes |
| `FQV1-aria2-52bdba205b5ce686` | `ONE_VALID_TARGET` | Empty candidate set; target recoverable by allowed navigation | No | Yes |
| `FQV1-aria2-0f84707a755b6d84` | `NO_VALID_TARGET` | Same name, wrong receiver/owner | No | No |
| `FQV1-aria2-c900f72d67f383ae` | `ONE_VALID_TARGET` | Empty candidate set; target recoverable by allowed navigation | No | Yes |

### `FQV1-rocksdb-8e526ba5ac0d956a`

The call at `utilities/blob_db/blob_db_impl.cc:1631` has receiver
`open_ttl_files_`. Its declaration at `utilities/blob_db/blob_db_impl.h:427`
establishes `std::set<std::shared_ptr<BlobFile>, BlobFileComparatorTTL>`, so the
callee is `std::set::erase`. The sole candidate belongs to another owner and is
not valid.

### `FQV1-aria2-52bdba205b5ce686`

The expression at `test/HttpResponseTest.cc:252` resolves uniquely to
`HttpHeader::setStatusCode(int)`. Its declaration is at `src/HttpHeader.h:116`
and canonical definition at `src/HttpHeader.cc:180`. The candidate set is
empty, but Evidence Scope V1 permits recovery; the definition is canonical
under Declaration–Definition Equivalence V1.

### `FQV1-aria2-0f84707a755b6d84`

`data` is locally declared as `std::string` at `src/CookieStorage.cc:157`, so
the line 159 calls resolve to `std::string::size()`. The supplied same-name
candidate is the unrelated `CookieStorage::size()` at line 426. Cross-file
navigation is unnecessary.

### `FQV1-aria2-c900f72d67f383ae`

`r` is `std::shared_ptr<ServerStat>` at `test/ServerStatManTest.cc:51`; the
line 53 call therefore resolves uniquely to the inline
`ServerStat::getHostname() const` at `src/ServerStat.h:59`. Its placement inside
`CPPUNIT_ASSERT_EQUAL` does not remove the source-level CALLS relation under
CALLS_V1. The candidate set is empty, and cross-file recovery is necessary.

## Validation

- Case scope: exactly the four queued Batch 02 C/C++ CALLS disagreements.
- Schema violations: 0.
- Case-scope violations: 0.
- Blindness violations: 0.
- Sealed A/B record modifications: 0.
- Frozen source repository mutations: 0.
