param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Failure Attribution V1 - P0 Graph Fidelity Qualification V1
#
# Attributes the 28 scoring_error_cases[] of the sealed Graph Fidelity Scoring
# V1 artifact to failure mechanisms. Read-only over frozen inputs; every
# scoring state is preserved verbatim; no repair and no RQ1 claim.
#
# Evidence bases used per case:
#   candidate_set_empty        - sealed candidate set is empty (n=0)
#   sealed_adjudication_flag   - sealed adjudication artifact records
#                                correct_target_in_candidate_set explicitly
#   symbol_id_membership       - gold target symbol_id present/absent from the
#                                sealed candidate set (mechanical recompute)
#   db_verified_membership     - frozen V0.2 graph database (read-only) resolves
#                                a candidate node at the gold target path/line
# ---------------------------------------------------------------------------

$results = Join-Path $ExperimentRoot 'results'
$goldDir = Join-Path $ExperimentRoot 'gold'
$scriptPath = $PSCommandPath

function LoadJson([string]$Path) {
  [IO.File]::ReadAllText($Path, [Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
}
function Hash([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Write-Utf8Text([string]$Path, [string]$Text) {
  [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}
function Write-Utf8Json([string]$Path, $Value) {
  Write-Utf8Text $Path (($Value | ConvertTo-Json -Depth 40) + "`n")
}
function Rel([string]$Path) { $Path.Substring($ExperimentRoot.Length + 1).Replace('\', '/') }

$goldPath = Join-Path $goldDir 'cpp-structural-relation-gold-v1.json'
$systemPath = Join-Path $results 'pilot-candidates.json'
$joinPath = Join-Path $results 'system-gold-join-v1.json'
$scoringPath = Join-Path $results 'graph-fidelity-scoring-v1.json'

$goldSha = Hash $goldPath
$systemSha = Hash $systemPath
$joinSha = Hash $joinPath
$scoringSha = Hash $scoringPath

foreach ($line in @(Get-Content -LiteralPath (Join-Path $results 'graph-fidelity-scoring-v1.sha256'))) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split '  ', 2
  if ($parts[1] -eq 'graph-fidelity-scoring-v1.json' -and $parts[0].ToLowerInvariant() -ne $scoringSha) { throw 'SCORING HASH MISMATCH - STOP.' }
}

$gold = LoadJson $goldPath
$system = LoadJson $systemPath
$scoring = LoadJson $scoringPath

if ($scoring.provenance.gold_sha256 -ne $goldSha) { throw 'Scoring provenance gold hash mismatch - STOP.' }
if ($scoring.provenance.system_prediction_sha256 -ne $systemSha) { throw 'Scoring provenance system hash mismatch - STOP.' }

$errorCases = @($scoring.scoring_error_cases)
if ($errorCases.Count -ne 28) { throw "scoring_error_cases count $($errorCases.Count) != 28 - STOP." }
$goldById = @{}
foreach ($r in @($gold.records)) { $goldById[$r.sample_id] = $r }

# --- frozen per-case attribution table (evidence-derived; see file header) ----

$A = [ordered]@{}

# MISSED_RESOLUTION_OPPORTUNITY - candidate generation miss (empty sealed candidate sets)
$A['FQV1-aria2-713b641e93cc620c'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty'; rationale = 'system status=unresolved with an empty sealed candidate set (n=0); gold target (ValueBase::append, src/ValueBase.cc:123) exists in-repository and is determinable under Evidence Scope V1 but was never generated as a candidate.' }
$A['FQV1-aria2-52bdba205b5ce686'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty+sealed_adjudication_flag'; rationale = 'empty sealed candidate set (n=0); sealed Batch-02 adjudication records EMPTY_CANDIDATE_SET_TARGET_RECOVERABLE_BY_ALLOWED_NAVIGATION for the gold target HttpHeader::setStatusCode.' }
$A['FQV1-aria2-c900f72d67f383ae'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty+sealed_adjudication_flag'; rationale = 'empty sealed candidate set (n=0); sealed Batch-02 adjudication records EMPTY_CANDIDATE_SET_TARGET_RECOVERABLE_BY_ALLOWED_NAVIGATION for the gold target ServerStat::getHostname.' }
$A['FQV1-brpc-8c9d0887e1f9d4fe'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty'; rationale = 'empty sealed candidate set (n=0); gold target (src/brpc/couchbase.cpp:26) exists in-repository per sealed agreement.' }
$A['FQV1-rocksdb-657008a8ca392740'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty'; rationale = 'empty sealed candidate set (n=0); gold target (test_util/testharness.h:88) exists in-repository per sealed agreement.' }
$A['FQV1-rocksdb-ec017de0157014f4'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @('DECL_DEF_CANONICALIZATION'); basis = 'candidate_set_empty+sealed_adjudication_flag'; rationale = 'empty sealed candidate set (n=0); sealed final adjudication records correct_target_in_candidate_set=NO for RUN_ALL_TESTS (vendored gtest header) with declaration/definition canonicalization noted.' }
$A['FQV1-aria2-d92c0476f269fe9c'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty'; rationale = 'empty sealed candidate set (n=0); gold target (src/DHTMessageTrackerEntry.cc:58) exists in-repository per sealed agreement.' }
$A['FQV1-rocksdb-3b90b89381b8d13d'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'candidate_set_empty'; rationale = 'empty sealed candidate set (n=0); both gold-acceptable targets (db->DefaultColumnFamily decl/def anchors) exist in-repository per sealed agreement.' }
# MISSED - candidate generation miss with non-empty set (sealed flag)
$A['FQV1-brpc-bc38ae52a3ef3090'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @(); basis = 'sealed_adjudication_flag'; rationale = 'sealed final adjudication records correct_target_in_candidate_set=NO over 97 ambiguous candidates; gold target (butil::BasicStringPiece::data, src/butil/strings/string_piece.h:214) was not generated.' }
# MISSED - resolver abstention with the correct target present in the candidate set
$A['FQV1-brpc-68baef18ae4bd3ee'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol is present in the sealed candidate set (2 candidates), but the resolver stayed ambiguous and abstained.' }
$A['FQV1-brpc-b210f3349b031961'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol is present in the sealed candidate set (3 candidates); resolver abstained as ambiguous.' }
$A['FQV1-brpc-d12b7bdc3ecd5bbc'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'DIVERGENT case: both gold-acceptable targets are exactly the two sealed candidates; the resolver abstained instead of selecting either gold-acceptable target.' }
$A['FQV1-aria2-c6525c9d8d155f3f'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'one gold-acceptable target symbol is present in the sealed candidate set (3 candidates); resolver abstained as ambiguous.' }
$A['FQV1-rocksdb-85a27eca37b8f8c1'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol (util/comparator.cc:322) is present in the sealed candidate set (2 candidates); resolver abstained.' }
$A['FQV1-brpc-51d58c46a6424852'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol is present in the sealed candidate set (2 candidates); resolver abstained (overload-resolution ambiguity).' }
$A['FQV1-rocksdb-e23ab7dea713cf57'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol (Slice::NotSupported, include/rocksdb/advanced_cache.h:390) is present in the sealed candidate set (6 candidates); resolver abstained.' }
$A['FQV1-brpc-c854e345d2d4b8a8'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol is present in the sealed candidate set (4 candidates); resolver abstained as ambiguous.' }
$A['FQV1-aria2-0102241c89b94614'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'symbol_id_membership'; rationale = 'gold target symbol is present in the sealed candidate set (12 candidates); resolver abstained as ambiguous.' }
$A['FQV1-aria2-3fa9480748303413'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'db_verified_membership'; rationale = 'frozen V0.2 graph database resolves sealed candidate symbol:f93c721c... to BitfieldMan::getSparseMissingUnusedIndex at the gold target location (src/BitfieldMan.cc:303); the resolver abstained among 3 same-name overloads.' }
$A['FQV1-rocksdb-8b4ca63de7918ec9'] = @{ primary = 'RESOLVER_ABSTENTION'; contributing = @(); basis = 'db_verified_membership'; rationale = 'frozen V0.2 graph database resolves sealed candidate symbol:d1257f90... to Random::RandomString at the gold target location (util/random.cc:45); the resolver abstained among 3 same-name overloads.' }
# WRONG_TARGET_RESOLUTION
$A['FQV1-rocksdb-ecb7a6891b617490'] = @{ primary = 'CANDIDATE_GENERATION_MISS'; contributing = @('RESOLVER_WRONG_SELECTION', 'RECEIVER_OR_OWNER_MISMATCH'); basis = 'sealed_adjudication_flag'; rationale = 'sealed final adjudication records correct_target_in_candidate_set=NO: the unique gold target (Slice::size, include/rocksdb/slice.h:61) was never generated, so no correct selection was possible; the resolver then selected a same-name same-file method of a different owner (MultiGetJNIKeys::size) instead of abstaining.' }
# FALSE_RESOLUTION_ON_ABSENT - all over-resolutions on external receivers
$A['FQV1-rocksdb-8e526ba5ac0d956a'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'sealed_adjudication_flag'; rationale = 'receiver open_ttl_files_ is std::set<...>; the resolver resolved the erase call to the same-name in-repository WritePreparedTxnDB::PreparedHeap::erase (sealed Batch-02 adjudication: SAME_NAME_WRONG_RECEIVER_OWNER).' }
$A['FQV1-aria2-0f84707a755b6d84'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'sealed_adjudication_flag'; rationale = 'receiver is std::string; the resolver resolved data.size() to the same-name CookieStorage::size (src/CookieStorage.cc:426) via same-file resolution (sealed: SAME_NAME_WRONG_RECEIVER_OWNER).' }
$A['FQV1-aria2-4f7155139b696d14'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'receiver_type_evidence'; rationale = 'receiver tempQueue is std::vector<std::unique_ptr<BtMessage>> (external); the resolver over-resolved push_back to the same-name in-repository IndexedList::push_back from a 1-candidate set.' }
$A['FQV1-aria2-4656d1df0792fedd'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'receiver_type_evidence'; rationale = 'the call is std::move (external standard library); the resolver over-resolved it to the same-name in-repository IndexedList::move from a 1-candidate set.' }
$A['FQV1-rocksdb-aa505d4616aede0b'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'receiver_type_evidence'; rationale = 'receiver bufs_ is std::deque<BufferInfo*> (external); the resolver over-resolved emplace_back to the same-name in-repository autovector::emplace_back.' }
$A['FQV1-aria2-5c9b99ecc0454a4a'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'receiver_type_evidence'; rationale = 'receiver handlers is std::vector<OptionHandler*> (external, preprocessor-conditional context); the resolver over-resolved push_back to the same-name in-repository IndexedList::push_back.' }
$A['FQV1-aria2-c10fd7262a136c88'] = @{ primary = 'RESOLVER_OVER_RESOLUTION'; contributing = @('RECEIVER_OR_OWNER_MISMATCH'); basis = 'receiver_type_evidence'; rationale = 'the call is std::move (external standard library); the resolver over-resolved it to the same-name in-repository IndexedList::move from a 1-candidate set.' }

# --- mechanical validation of the table against frozen evidence ----------------

$attr = @()
$seen = @{}
foreach ($e in $errorCases) {
  $id = $e.sample_id
  if (-not $A.Contains($id)) { throw "No attribution for $id - STOP." }
  if ($seen.ContainsKey($id)) { throw "Duplicate attribution for $id - STOP." }
  $seen[$id] = $true
  $mech = $A[$id]
  $g = $goldById[$id]

  # scoring state must be preserved verbatim
  if ($e.scoring_state -notin @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT', 'MISSED_RESOLUTION_OPPORTUNITY')) { throw "Unexpected scoring state for $id" }

  # mechanical membership cross-check for the symbol_id_membership basis
  $cands = @($e.system_candidate_set)
  $member = $false
  foreach ($t in @($e.gold_acceptable_targets)) { if ($t.symbol_id -and ($cands -contains $t.symbol_id)) { $member = $true } }
  if ($mech.basis -eq 'symbol_id_membership' -and -not $member) { throw "Membership basis claimed but gold symbol absent from candidate set: $id" }
  if ($e.scoring_state -eq 'MISSED_RESOLUTION_OPPORTUNITY' -and $cands.Count -eq 0 -and $mech.primary -ne 'CANDIDATE_GENERATION_MISS') { throw "Empty candidate set must attribute CANDIDATE_GENERATION_MISS: $id" }

  $correctExists = $e.scoring_state -eq 'MISSED_RESOLUTION_OPPORTUNITY'
  $inCand = $null
  if ($e.scoring_state -eq 'MISSED_RESOLUTION_OPPORTUNITY') {
    if ($cands.Count -eq 0) { $inCand = $false }
    elseif ($member) { $inCand = $true }
    elseif ($mech.basis -match 'sealed_adjudication_flag' -and $g.correct_target_present_in_candidate_set -eq 'NO') { $inCand = $false }
    elseif ($mech.basis -eq 'db_verified_membership') { $inCand = $true }
  }

  $attr += [ordered]@{
    sample_id = $id
    repository = $e.repository
    relation = $e.relation
    stratum = $e.stratum
    scoring_state = $e.scoring_state
    gold_target_layer = $e.gold_target_layer
    gold_final_target = $e.gold_final_target
    gold_acceptable_targets = @($e.gold_acceptable_targets)
    system_status = $e.system_status
    resolver_strategy = $e.resolver_strategy
    resolver_confidence = $e.resolver_confidence
    predicted_target = $e.predicted_target
    system_candidate_count = $cands.Count
    system_candidate_set = $cands
    correct_target_exists_in_repository = $correctExists
    correct_target_in_candidate_set = $inCand
    primary_failure = $mech.primary
    contributing_failures = @($mech.contributing)
    evidence_basis = $mech.basis
    rationale = $mech.rationale
  }
}
if ($attr.Count -ne 28) { throw "Attributed $($attr.Count) != 28 - STOP." }
foreach ($id in $A.Keys) { if (-not $seen.ContainsKey($id)) { throw "Attribution table entry not among error cases: $id" } }

# --- stats ---------------------------------------------------------------------

function Count-By($key) {
  $h = [ordered]@{}
  foreach ($r in $attr) {
    $k = $r.$key
    if (-not $h.Contains($k)) { $h[$k] = 0 }
    $h[$k]++
  }
  return $h
}
$byState = Count-By 'scoring_state'
$byRepo = Count-By 'repository'
$byRel = Count-By 'relation'
$byStrategy = Count-By 'resolver_strategy'
$byPrimary = [ordered]@{}
foreach ($r in $attr) {
  $k = $r.primary_failure
  if (-not $byPrimary.Contains($k)) { $byPrimary[$k] = 0 }
  $byPrimary[$k]++
}
$contrib = [ordered]@{}
foreach ($r in $attr) { foreach ($c in @($r.contributing_failures)) { if (-not $contrib.Contains($c)) { $contrib[$c] = 0 }; $contrib[$c]++ } }

# --- emit -----------------------------------------------------------------------

$createdAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$out = [ordered]@{
  artifact = 'graph-fidelity-failure-attribution-v1'
  status = 'ATTRIBUTION_COMPLETE_NO_REPAIR'
  created_at = $createdAt
  claims = [ordered]@{ rq1_verdict = 'NOT WRITTEN IN THIS ARTIFACT'; note = 'mechanism attribution of the 28 sealed scoring error cases only; no repair, no re-scoring, no new results' }
  provenance = [ordered]@{
    gold_file = (Rel $goldPath)
    gold_sha256 = $goldSha
    system_prediction_file = (Rel $systemPath)
    system_prediction_sha256 = $systemSha
    join_file = (Rel $joinPath)
    join_sha256 = $joinSha
    scoring_file = (Rel $scoringPath)
    scoring_sha256 = $scoringSha
    attribution_script = (Rel $scriptPath)
    attribution_script_sha256 = (Hash $scriptPath)
  }
  method = [ordered]@{
    scope = 'scoring_error_cases[] of graph-fidelity-scoring-v1 (28 cases); scoring states preserved verbatim'
    mechanism_vocabulary = @('CANDIDATE_GENERATION_MISS', 'RESOLVER_WRONG_SELECTION', 'RESOLVER_OVER_RESOLUTION', 'RESOLVER_ABSTENTION', 'RECEIVER_OR_OWNER_MISMATCH', 'SHADOWING_OR_SCOPE', 'DECL_DEF_CANONICALIZATION', 'BUILD_CONTEXT_LIMIT', 'GRAPH_REPRESENTATION_LIMIT', 'OTHER')
    decision_rules = [ordered]@{
      MISSED_RESOLUTION_OPPORTUNITY = 'correct_target_in_candidate_set=false (incl. empty candidate sets and sealed adjudication flags) -> CANDIDATE_GENERATION_MISS; true (symbol_id membership or frozen-database verification) -> RESOLVER_ABSTENTION'
      WRONG_TARGET_RESOLUTION = 'correct target absent from candidate set -> CANDIDATE_GENERATION_MISS primary with RESOLVER_WRONG_SELECTION contributing; no conflation of the two'
      FALSE_RESOLUTION_ON_ABSENT = 'primary RESOLVER_OVER_RESOLUTION with the concrete contributing mechanism recorded per case'
    }
    db_verification = 'the two path-only agreed gold targets among missed opportunities were verified against the frozen V0.2 graph databases (read-only): candidate nodes resolve to the gold target path/line'
  }
  counts = [ordered]@{
    total = 28
    by_scoring_state = $byState
    by_repository = $byRepo
    by_relation = $byRel
    by_resolver_strategy = $byStrategy
    by_primary_failure = $byPrimary
    contributing_failures = $contrib
  }
  attributed_cases = $attr
  discipline = [ordered]@{
    gold_mutation = 0
    system_prediction_mutation = 0
    scoring_mutation = 0
    resolver_or_candidate_generation_repair = 0
    reproducibility = 'attribution table + mechanical validation recomputed by tools/attribute-failures-v1.ps1'
  }
}
$outPath = Join-Path $results 'graph-fidelity-failure-attribution-v1.json'
Write-Utf8Json $outPath $out

# markdown report
$md = New-Object Text.StringBuilder
[void]$md.AppendLine('# Graph Fidelity Failure Attribution V1')
[void]$md.AppendLine('')
[void]$md.AppendLine('```text')
[void]$md.AppendLine('status: ATTRIBUTION_COMPLETE_NO_REPAIR')
[void]$md.AppendLine('scope:  28 scoring_error_cases[] of graph-fidelity-scoring-v1; scoring states unchanged')
[void]$md.AppendLine('claims: no RQ1 verdict, no repair, no post-repair results in this artifact')
[void]$md.AppendLine('```')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Provenance')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Artifact | SHA256 |')
[void]$md.AppendLine('| --- | --- |')
[void]$md.AppendLine(('| Gold (cpp-structural-relation-gold-v1.json) | ' + $goldSha + ' |'))
[void]$md.AppendLine(('| System prediction (pilot-candidates.json) | ' + $systemSha + ' |'))
[void]$md.AppendLine(('| Join (system-gold-join-v1.json) | ' + $joinSha + ' |'))
[void]$md.AppendLine(('| Scoring (graph-fidelity-scoring-v1.json) | ' + $scoringSha + ' |'))
[void]$md.AppendLine(('| Attribution script | ' + (Hash $scriptPath) + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Attribution totals (28/28)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Primary failure mechanism | n |')
[void]$md.AppendLine('| --- | ---: |')
foreach ($k in $byPrimary.Keys) { [void]$md.AppendLine(('| ' + $k + ' | ' + $byPrimary[$k] + ' |')) }
[void]$md.AppendLine('')
[void]$md.AppendLine('Key mechanism counts: CANDIDATE_GENERATION_MISS ' + $(if ($byPrimary.Contains('CANDIDATE_GENERATION_MISS')) { $byPrimary['CANDIDATE_GENERATION_MISS'] } else { 0 }) + ', RESOLVER_ABSTENTION ' + $(if ($byPrimary.Contains('RESOLVER_ABSTENTION')) { $byPrimary['RESOLVER_ABSTENTION'] } else { 0 }) + ', RESOLVER_WRONG_SELECTION ' + $(if ($byPrimary.Contains('RESOLVER_WRONG_SELECTION')) { $byPrimary['RESOLVER_WRONG_SELECTION'] } else { 0 }) + ' (primary; +1 contributing), RESOLVER_OVER_RESOLUTION ' + $(if ($byPrimary.Contains('RESOLVER_OVER_RESOLUTION')) { $byPrimary['RESOLVER_OVER_RESOLUTION'] } else { 0 }) + '.')
[void]$md.AppendLine('')
[void]$md.AppendLine('Contributing failures: ' + (($contrib.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '))
[void]$md.AppendLine('')
[void]$md.AppendLine('## By scoring state')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Scoring state | n | mechanisms |')
[void]$md.AppendLine('| --- | ---: | --- |')
foreach ($k in @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT', 'MISSED_RESOLUTION_OPPORTUNITY')) {
  $mechs = ($attr | Where-Object { $_.scoring_state -eq $k } | Group-Object primary_failure | Sort-Object Count -Descending | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join ', '
  [void]$md.AppendLine(('| ' + $k + ' | ' + $byState[$k] + ' | ' + $mechs + ' |'))
}
[void]$md.AppendLine('')
[void]$md.AppendLine('## By repository / relation / resolver strategy')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Dimension | Distribution |')
[void]$md.AppendLine('| --- | --- |')
[void]$md.AppendLine(('| repository | ' + (($byRepo.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ') + ' |'))
[void]$md.AppendLine(('| relation | ' + (($byRel.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ') + ' |'))
[void]$md.AppendLine(('| resolver strategy | ' + (($byStrategy.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ') + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Per-case attributions')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Sample | State | Repo | Relation | Strategy | Cand n | Correct target in cand set | Primary | Contributing |')
[void]$md.AppendLine('| --- | --- | --- | --- | --- | ---: | --- | --- | --- |')
foreach ($r in $attr) {
  $inC = if ($null -eq $r.correct_target_in_candidate_set) { 'n/a' } else { ($r.correct_target_in_candidate_set.ToString()).ToLower() }
  [void]$md.AppendLine(('| ' + $r.sample_id + ' | ' + $r.scoring_state + ' | ' + $r.repository + ' | ' + $r.relation + ' | ' + $r.resolver_strategy + ' | ' + $r.system_candidate_count + ' | ' + $inC + ' | ' + $r.primary_failure + ' | ' + ((@($r.contributing_failures) -join ', ')) + ' |'))
}
[void]$md.AppendLine('')
[void]$md.AppendLine('## MISSED_RESOLUTION split (20 cases)')
[void]$md.AppendLine('')
[void]$md.AppendLine(('- correct target NOT in candidate set (incl. 8 empty candidate sets and 1 sealed flag over 97 ambiguous candidates) -> CANDIDATE_GENERATION_MISS: ' + $byPrimary['CANDIDATE_GENERATION_MISS'] + ' of the 20 missed opportunities'))
[void]$md.AppendLine(('- correct target IS in candidate set but the resolver abstained -> RESOLVER_ABSTENTION: ' + $byPrimary['RESOLVER_ABSTENTION'] + ' of 20'))
[void]$md.AppendLine('- correct_target_exists_in_repository = true for all 20 (gold target-present cases); no BUILD_CONTEXT_LIMIT case occurs in the error set')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Discipline')
[void]$md.AppendLine('')
[void]$md.AppendLine('- Gold, system prediction, join and scoring artifacts read-only; mutation = 0; scoring states echoed unchanged.')
[void]$md.AppendLine('- No resolver/candidate-generation repair, no re-annotation/adjudication, no post-repair results, no RQ1 claim.')
Write-Utf8Text (Join-Path $results 'graph-fidelity-failure-attribution-v1.md') ($md.ToString() + "`n")

$sums = @(
  ('{0}  graph-fidelity-failure-attribution-v1.json' -f (Hash $outPath)),
  ('{0}  graph-fidelity-failure-attribution-v1.md' -f (Hash (Join-Path $results 'graph-fidelity-failure-attribution-v1.md')))
)
Write-Utf8Text (Join-Path $results 'graph-fidelity-failure-attribution-v1.sha256') (($sums -join "`n") + "`n")

Write-Output 'GRAPH_FIDELITY_FAILURE_ATTRIBUTION_V1 built.'
Write-Output ('primary: ' + (($byPrimary.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '))
Write-Output ('by state: ' + (($byState.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '))
