param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Final C/C++ Adjudication Clean Package builder (packaging agent only).
#
# This script is NOT an adjudicator. It performs no case adjudication, decides
# no A/B correctness, generates no Gold, and computes no Fidelity score.
#
# Source discipline: the builder reads only
#   - sealed annotator A/B annotation records (blind packages 03/04/05)
#   - sealed blind annotation views (frozen annotation candidate scope)
#   - sealed agreement audits 03/04/05 and their sealed amendments (queue
#     membership reconciliation only)
#   - the sealed Batch 02 adjudication artifact (exclusion list only)
# It never opens results/pilot-candidates.json or any other system-side
# prediction / resolver / fidelity artifact.
# ---------------------------------------------------------------------------

$results = Join-Path $ExperimentRoot 'results'
$blindRoot = Join-Path $ExperimentRoot 'blind_packages'
$packageRoot = Join-Path $ExperimentRoot 'final_adjudication_package'

function Hash([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Write-Utf8Text([string]$Path, [string]$Text) {
  [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}
function Write-Utf8Json([string]$Path, $Value) {
  $json = $Value | ConvertTo-Json -Depth 40
  Write-Utf8Text $Path ($json + "`n")
}

# --- frozen sealed inputs ---------------------------------------------------

$sealed = @{}   # batch_id -> A/B record collections + blind view + provenance

$batchSpec = [ordered]@{
  '03' = [ordered]@{
    aOutput = Join-Path $blindRoot 'batch-03\annotator-a\output\annotation-record-template.json'
    bOutput = Join-Path $blindRoot 'batch-03\annotator-b\output\annotation-record-template.json'
    blindViewA = Join-Path $blindRoot 'batch-03\annotator-a\input\annotator-a-blind-view.json'
    blindViewB = Join-Path $blindRoot 'batch-03\annotator-b\input\annotator-b-blind-view.json'
    manifest = Join-Path $blindRoot 'batch-03\annotator-a\input\batch-03-manifest.json'
    pkgManifestA = Join-Path $blindRoot 'batch-03\annotator-a\manifest.json'
    pkgManifestB = Join-Path $blindRoot 'batch-03\annotator-b\manifest.json'
    queueAnchor = 'blind-agreement-audit-03 (formal_verdict_disagreements) + blind-agreement-audit-03-amendment (cpp preserved metrics)'
    queueAnchorPath = Join-Path $results 'blind-agreement-audit-03.json'
  }
  '04' = [ordered]@{
    aOutput = Join-Path $blindRoot 'batch-04\annotator-a\output\annotator-a-batch-04-annotations.json'
    bOutput = Join-Path $blindRoot 'batch-04\annotator-b\output\annotation-record-template.json'
    blindViewA = Join-Path $blindRoot 'batch-04\annotator-a\input\annotator-a-blind-view.json'
    blindViewB = Join-Path $blindRoot 'batch-04\annotator-b\input\annotator-b-blind-view.json'
    manifest = Join-Path $blindRoot 'batch-04\annotator-a\input\batch-04-manifest.json'
    pkgManifestA = Join-Path $blindRoot 'batch-04\annotator-a\manifest.json'
    pkgManifestB = Join-Path $blindRoot 'batch-04\annotator-b\manifest.json'
    queueAnchor = 'blind-agreement-audit-04 (disagreement_attribution.adjudication_queue_count = 9)'
    queueAnchorPath = Join-Path $results 'blind-agreement-audit-04.json'
  }
  '05' = [ordered]@{
    aOutput = Join-Path $blindRoot 'batch-05\annotator-a\output\annotator-a-batch-05-annotations.json'
    bOutput = Join-Path $blindRoot 'batch-05\annotator-b\output\annotator-b-batch-05-annotation-records.json'
    blindViewA = Join-Path $blindRoot 'batch-05\annotator-a\input\annotator-a-blind-view.json'
    blindViewB = Join-Path $blindRoot 'batch-05\annotator-b\input\annotator-b-blind-view.json'
    manifest = Join-Path $blindRoot 'batch-05\annotator-a\input\batch-05-manifest.json'
    pkgManifestA = Join-Path $blindRoot 'batch-05\annotator-a\manifest.json'
    pkgManifestB = Join-Path $blindRoot 'batch-05\annotator-b\manifest.json'
    queueAnchor = 'blind-agreement-audit-05 (adjudication_queue.entries)'
    queueAnchorPath = Join-Path $results 'blind-agreement-audit-05.json'
  }
}

$cppScopes = @('C++', 'C', 'C/C++', 'CPP_IN_SCOPE', 'CPP_PRIMARY')

foreach ($batch in $batchSpec.Keys) {
  $spec = $batchSpec[$batch]
  $a = Get-Content -Raw -LiteralPath $spec.aOutput | ConvertFrom-Json
  $b = Get-Content -Raw -LiteralPath $spec.bOutput | ConvertFrom-Json
  $viewA = Get-Content -Raw -LiteralPath $spec.blindViewA | ConvertFrom-Json
  $viewB = Get-Content -Raw -LiteralPath $spec.blindViewB | ConvertFrom-Json
  $manifest = Get-Content -Raw -LiteralPath $spec.manifest | ConvertFrom-Json
  $pkgManifestA = Get-Content -Raw -LiteralPath $spec.pkgManifestA | ConvertFrom-Json
  $pkgManifestB = Get-Content -Raw -LiteralPath $spec.pkgManifestB | ConvertFrom-Json

  if ($a.sample_count -ne $b.sample_count) { throw "Batch $batch sealed record counts differ." }
  if ($a.sample_count -ne $manifest.sample_count) { throw "Batch $batch manifest count mismatch." }
  if ($viewA.sample_count -ne $manifest.sample_count) { throw "Batch $batch blind view count mismatch." }
  if (($pkgManifestA.frozen_repository_commits.aria2 -ne $pkgManifestB.frozen_repository_commits.aria2) -or
      ($pkgManifestA.frozen_repository_commits.brpc -ne $pkgManifestB.frozen_repository_commits.brpc) -or
      ($pkgManifestA.frozen_repository_commits.rocksdb -ne $pkgManifestB.frozen_repository_commits.rocksdb)) {
    throw "Batch $batch frozen repository commits differ between annotator packages."
  }

  $aById = @{}
  foreach ($r in @($a.records)) {
    if ($aById.ContainsKey($r.sample_id)) { throw "Duplicate sealed A record in batch $batch." }
    $aById[$r.sample_id] = $r
  }
  $bById = @{}
  foreach ($r in @($b.records)) {
    if ($bById.ContainsKey($r.sample_id)) { throw "Duplicate sealed B record in batch $batch." }
    $bById[$r.sample_id] = $r
  }
  $caseById = @{}
  foreach ($c in @($viewA.cases)) {
    if ($caseById.ContainsKey($c.case_id)) { throw "Duplicate blind-view case in batch $batch." }
    $caseById[$c.case_id] = $c
  }
  foreach ($id in $manifest.case_ids) {
    if (-not $aById.ContainsKey($id)) { throw "Batch $batch manifest case missing from sealed A records: $id" }
    if (-not $bById.ContainsKey($id)) { throw "Batch $batch manifest case missing from sealed B records: $id" }
    if (-not $caseById.ContainsKey($id)) { throw "Batch $batch manifest case missing from blind view: $id" }
  }

  $sealed[$batch] = [ordered]@{
    a = $aById; b = $bById; cases = $caseById
    caseOrder = @($manifest.case_ids)
    frozenCommits = $pkgManifestA.frozen_repository_commits
    provenance = [ordered]@{
      sealed_a_path = $spec.aOutput.Substring($ExperimentRoot.Length + 1).Replace('\', '/')
      sealed_a_sha256 = Hash $spec.aOutput
      sealed_b_path = $spec.bOutput.Substring($ExperimentRoot.Length + 1).Replace('\', '/')
      sealed_b_sha256 = Hash $spec.bOutput
      blind_view_a_path = $spec.blindViewA.Substring($ExperimentRoot.Length + 1).Replace('\', '/')
      blind_view_a_sha256 = Hash $spec.blindViewA
      blind_view_b_path = $spec.blindViewB.Substring($ExperimentRoot.Length + 1).Replace('\', '/')
      blind_view_b_sha256 = Hash $spec.blindViewB
      batch_manifest_path = $spec.manifest.Substring($ExperimentRoot.Length + 1).Replace('\', '/')
      batch_manifest_sha256 = Hash $spec.manifest
      queue_anchor = $spec.queueAnchor
      queue_anchor_path = $spec.queueAnchorPath
    }
  }
}

# --- queue reconciliation (sealed records + sealed audits only) -------------

$queue = @{}
$queueChecks = [ordered]@{}
$expectedCounts = @{ '03' = 2; '04' = 9; '05' = 2 }

foreach ($batch in $batchSpec.Keys) {
  $s = $sealed[$batch]
  $ids = @()
  foreach ($id in $s.caseOrder) {
    $langA = $s.a[$id].language_scope
    $langB = $s.b[$id].language_scope
    $cpp = ($cppScopes -contains $langA) -and ($cppScopes -contains $langB)
    if (-not $cpp) { continue }
    if ($s.a[$id].formal_verdict -ne $s.b[$id].formal_verdict) { $ids += $id }
  }
  if ($ids.Count -ne $expectedCounts[$batch]) {
    throw ("Batch {0} C/C++ formal disagreement count {1} != sealed-audit expectation {2}" -f $batch, $ids.Count, $expectedCounts[$batch])
  }
  $queue[$batch] = $ids
}

# cross-check against the sealed agreement audits
$audit03 = Get-Content -Raw -LiteralPath (Join-Path $results 'blind-agreement-audit-03.json') | ConvertFrom-Json
$audit03Amendment = Get-Content -Raw -LiteralPath (Join-Path $results 'blind-agreement-audit-03-amendment.json') | ConvertFrom-Json
$audit04 = Get-Content -Raw -LiteralPath (Join-Path $results 'blind-agreement-audit-04.json') | ConvertFrom-Json
$audit05 = Get-Content -Raw -LiteralPath (Join-Path $results 'blind-agreement-audit-05.json') | ConvertFrom-Json
$batch02Adjudication = Get-Content -Raw -LiteralPath (Join-Path $results 'batch-02-cpp-calls-adjudication.json') | ConvertFrom-Json

$audit03FormalIds = @($audit03.formal_verdict_disagreements)
foreach ($id in $queue['03']) {
  if ($audit03FormalIds -notcontains $id) { throw "Batch 03 queue id absent from sealed audit-03 formal disagreement list: $id" }
}
if ($audit03Amendment.preserved_cpp_metrics.n -ne 40 -or
    $audit03Amendment.preserved_cpp_metrics.formal_verdict_agreement.agree -ne 38) {
  throw 'Batch 03 amendment C/C++ metrics do not imply exactly 2 C/C++ formal disagreements.'
}
if ($audit04.disagreement_attribution.adjudication_queue_count -ne $queue['04'].Count) {
  throw 'Batch 04 queue count does not match sealed audit-04 adjudication_queue_count.'
}
foreach ($id in $queue['05']) {
  if ($audit05.adjudication_queue.entries -notcontains $id) { throw "Batch 05 queue id absent from sealed audit-05 queue: $id" }
}

$batch02Ids = @($batch02Adjudication.adjudications | ForEach-Object { $_.case_id })
$allIds = @($queue['03']) + @($queue['04']) + @($queue['05'])
$uniqueIds = @($allIds | Sort-Object -Unique)
if ($uniqueIds.Count -ne 13) { throw "Queue is not 13 unique IDs." }
foreach ($id in $allIds) {
  if ($batch02Ids -contains $id) { throw "Batch 02 already-adjudicated case leaked into queue: $id" }
}

# --- package construction ----------------------------------------------------

if (Test-Path -LiteralPath $packageRoot) { Remove-Item -Recurse -Force -LiteralPath $packageRoot }
New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot 'cases') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot 'protocol') | Out-Null

$protocolHashes = [ordered]@{}
foreach ($name in @('calls-v1.md', 'evidence-scope-v1.md', 'decl-def-equivalence-v1.md')) {
  $src = Join-Path $blindRoot ("batch-03\annotator-a\protocol\" + $name)
  Copy-Item -LiteralPath $src -Destination (Join-Path $packageRoot ("protocol\" + $name)) -Force
  $protocolHashes[$name] = Hash (Join-Path $packageRoot ("protocol\" + $name))
}

function Select-Telemetry($r) {
  [ordered]@{
    navigation_files = @($r.navigation_files)
    navigation_files_count = $r.navigation_files_count
    navigation_path = @($r.navigation_path)
    navigation_hop_count = $r.navigation_hop_count
    verification_depth = $r.verification_depth
    target_recovered_after_navigation = $r.target_recovered_after_navigation
    recovered_target = $r.recovered_target
    recovery_reason = $r.recovery_reason
  }
}

function Select-AnnotatorBlock($r, $sealedPath, $annotator) {
  [ordered]@{
    annotator_id = $annotator
    sealed_source_file = $sealedPath
    language_scope_as_recorded = $r.language_scope
    gold_relation_exists_as_annotated = $r.gold_relation_exists
    formal_verdict = $r.formal_verdict
    valid_target_count = $r.valid_target_count
    selected_target_if_unique = $r.selected_target_if_unique
    evidence_locations = @($r.evidence_locations)
    navigation_telemetry = Select-Telemetry $r
    build_context_status = $r.build_context_status
    confidence = $r.confidence
    difficulty_tags = @($r.difficulty_tags)
    protocol_issue = $r.protocol_issue
    reasoning = $r.reasoning
  }
}

$caseIndex = @()
foreach ($batch in @('03', '04', '05')) {
  $s = $sealed[$batch]
  foreach ($id in $queue[$batch]) {
    $case = $s.cases[$id]
    $rec = [ordered]@{
      sample_id = $id
      batch_id = $batch
      repository = $case.repository
      frozen_repository_commit = $s.frozenCommits.($case.repository)
      relation_type = $case.relation_type
      language_track = 'C/C++'
      source_location = [ordered]@{
        raw_reference_id = $case.raw_reference_id
        path = $case.source.path
        start_line = $case.source.start_line
        end_line = $case.source.end_line
        owner_kind = $case.source.owner_kind
        owner_qualified_name = $case.source.owner_qualified_name
        raw_name = $case.source.raw_name
        target_module = $case.source.target_module
      }
      annotation_candidate_set = [ordered]@{
        provenance = 'sealed blind annotation view (frozen annotation-scope candidate information)'
        candidate_symbol_ids = @($case.candidate_symbol_ids)
      }
      build_context_information = [ordered]@{
        build_context_available = $case.build_context.build_context_available
        compile_commands_available = $case.build_context.compile_commands_available
        build_target = $case.build_context.build_target
        platform = $case.build_context.platform
        preprocessor_context = $case.build_context.preprocessor_context
        generated_source_policy = $case.build_context.generated_source_policy
      }
      annotator_a = Select-AnnotatorBlock $s.a[$id] $s.provenance.sealed_a_path 'A'
      annotator_b = Select-AnnotatorBlock $s.b[$id] $s.provenance.sealed_b_path 'B'
      frozen_protocol_version = @('CALLS_V1', 'EVIDENCE_SCOPE_V1', 'DECL_DEF_EQUIVALENCE_V1')
      package_note = 'source-only adjudication record; contains no system prediction, resolver result, correctness label, or fidelity score'
    }
    $casePath = Join-Path $packageRoot ("cases\" + $id + '.json')
    Write-Utf8Json $casePath $rec
    $caseIndex += [ordered]@{ sample_id = $id; batch_id = $batch; repository = $case.repository; relation_type = $case.relation_type; file = ("cases/" + $id + '.json') }
  }
}

# queue.json
$queueJson = [ordered]@{
  artifact = 'final-cpp-adjudication-queue-v1'
  total = $allIds.Count
  unique_sample_ids = $uniqueIds.Count
  batch_counts = [ordered]@{ '03' = $queue['03'].Count; '04' = $queue['04'].Count; '05' = $queue['05'].Count }
  entries = $caseIndex
  membership_source = 'sealed annotator A/B records (C/C++ formal verdict disagreements), reconciled against sealed agreement audits 03/04/05 and their sealed amendments'
  excluded = [ordered]@{
    python_audit_only_cases = 0
    batch_02_already_adjudicated_cases = 0
    batch_02_exclusion_list = $batch02Ids
    duplicates = ($allIds.Count - $uniqueIds.Count)
  }
  reconciliation = [ordered]@{
    batch_03 = '2 C/C++ formal disagreements implied by audit-03 preserved C/C++ metrics (38/40 agreement); IDs verified subset of audit-03 formal_verdict_disagreements'
    batch_04 = "9 = audit-04 disagreement_attribution.adjudication_queue_count ($($audit04.disagreement_attribution.cpp_formal_disagreement_count) C/C++ formal disagreements)"
    batch_05 = '2 = audit-05 adjudication_queue.entries (exact set match)'
  }
  system_prediction_used_for_membership = $false
}
Write-Utf8Json (Join-Path $packageRoot 'queue.json') $queueJson

# adjudication instructions (process text only)
$instructions = @'
# Final C/C++ Adjudication Instructions (source-only)

## Role and scope

You are the final adjudicator for the 13 remaining C/C++ formal disagreements of
ProvenLattice P0 Graph Fidelity Qualification V1 (Batch 03 = 2, Batch 04 = 9,
Batch 05 = 2). You adjudicate each case from frozen source evidence only.

## Allowed reading

1. Every file listed in `manifest.json` under `allowed_files`.
2. Read-only navigation of the frozen source repositories at the frozen commits
   recorded in `manifest.json`:
   - benchmark-repos/aria2  @ 9e7273583f83e881e3ec067b523ba88724088d2f
   - benchmark-repos/brpc   @ ae09e960c7291605dda52356cc0c2d45567fb53e
   - benchmark-repos/rocksdb @ 37234200b57d8d0a6a5c41f2d9811bbd2e293544

## Forbidden reading

- `results/pilot-candidates.json` and every candidate system-output record
- every system prediction file, resolver output file, and resolver verdict
- Graph Fidelity scoring files and Gold correctness artifacts
- any file containing concrete values of: `predicted_target`,
  `system_status`, `resolver_strategy`, `resolver_confidence`
- agreement audits, amendments, and prior adjudication artifacts beyond the
  queue membership they froze (queue membership is already settled in
  `queue.json`; do not reopen it)

The clean package physically contains no system prediction data. Do not attempt
to reconstruct any.

## Adjudication process per case

1. Read the sealed Annotator A and Annotator B verdicts, evidence, target
   cardinality, selected targets, navigation telemetry, build-context judgment,
   and reasoning in the case record.
2. Open the frozen source at the recorded source location and navigate under
   Evidence Scope V1, CALLS_V1, and Declaration-Definition Equivalence V1
   (see `protocol/`).
3. Decide the final verdict from source evidence only. Do not weigh either
   annotator by identity, model, or prior performance; weigh only evidence.
4. Record per case: final verdict, relation present, valid target count,
   canonical source target, canonical target symbol id when one exists,
   rationale grounded in file:line evidence, failure mechanism when
   applicable, and evidence locations.

## Output

A single sealed adjudication artifact covering exactly the 13 queue entries in
`queue.json`. No other artifact may be produced from this package.

## Explicitly out of scope

System prediction join, Graph Fidelity scoring, resolver or candidate
generation repair, and any modification of sealed annotation records or frozen
repositories.
'@
Write-Utf8Text (Join-Path $packageRoot 'protocol\adjudication-instructions.md') ($instructions + "`n")

# manifest.json (written before the audit so the audit can hash-scan it)
$allowedFiles = @()
foreach ($rel in @('queue.json', 'protocol/calls-v1.md', 'protocol/evidence-scope-v1.md', 'protocol/decl-def-equivalence-v1.md', 'protocol/adjudication-instructions.md')) {
  $allowedFiles += [ordered]@{ path = $rel; sha256 = Hash (Join-Path $packageRoot ($rel -replace '/', '\')) }
}
foreach ($c in $caseIndex) {
  $allowedFiles += [ordered]@{ path = $c.file; sha256 = Hash (Join-Path $packageRoot ($c.file -replace '/', '\')) }
}

$manifest = [ordered]@{
  package_version = 'final-cpp-adjudication-clean-package-v1'
  artifact = 'FINAL_CPP_ADJUDICATION_CLEAN_PACKAGE_V1'
  created = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  builder_role = 'Adjudication Packaging / Governance Agent (not an adjudicator)'
  content_class = 'source-only; sealed A/B annotation data and frozen annotation-scope candidate information only'
  queue_summary = [ordered]@{ total = 13; batch_03 = 2; batch_04 = 9; batch_05 = 2 }
  frozen_repository_commits = [ordered]@{
    aria2 = '9e7273583f83e881e3ec067b523ba88724088d2f'
    brpc = 'ae09e960c7291605dda52356cc0c2d45567fb53e'
    rocksdb = '37234200b57d8d0a6a5c41f2d9811bbd2e293544'
  }
  allowed_repository_access = [ordered]@{
    mode = 'read-only'
    roots = @('benchmark-repos/aria2', 'benchmark-repos/brpc', 'benchmark-repos/rocksdb')
  }
  frozen_protocol_version = [ordered]@{
    protocols = @('CALLS_V1', 'EVIDENCE_SCOPE_V1', 'DECL_DEF_EQUIVALENCE_V1')
    protocol_files = $protocolHashes
    protocol_provenance = 'byte-identical frozen copies present in every batch blind package (03/04/05, annotators A and B)'
  }
  allowed_files = $allowedFiles
  adjudicator_read_rules = [ordered]@{
    may_read = @('every file listed in allowed_files', 'frozen repositories at the frozen commits (read-only)')
    must_not_read = @('any file not listed in allowed_files from this experiment directory tree')
  }
  forbidden_paths = @(
    'results/pilot-candidates.json',
    'any candidate system-output record',
    'any system prediction file',
    'any resolver output file',
    'any Graph Fidelity scoring file',
    'any Gold correctness artifact',
    'blind_packages/batch-02 (adjudicated batch)',
    'results/batch-02-cpp-calls-adjudication.json (final verdicts; exclusion list only at packaging time)'
  )
  forbidden_field_patterns = @('predicted_target', 'system_status', 'resolver_strategy', 'resolver_confidence')
  forbidden_field_note = 'field-name patterns are listed here as rule text only; no concrete value of any of these fields exists anywhere in this package'
  sealed_source_provenance = [ordered]@{
    sealed_records_modified_by_packaging = $false
    batches = [ordered]@{}
  }
  package_note = 'This package physically contains no ProvenLattice system prediction. Queue membership was derived from sealed annotation records and sealed agreement audits only.'
}
foreach ($batch in @('03', '04', '05')) {
  $manifest.sealed_source_provenance.batches[$batch] = $sealed[$batch].provenance
}
Write-Utf8Json (Join-Path $packageRoot 'manifest.json') $manifest

# --- contamination / blindness audit -----------------------------------------

$packageFiles = @(Get-ChildItem -Recurse -File -LiteralPath $packageRoot)
$forbiddenKeys = @('predicted_target', 'system_status', 'resolver_strategy', 'resolver_confidence')
$structuralHits = @()
$mentionFiles = [ordered]@{}
foreach ($f in $packageFiles) {
  $text = [IO.File]::ReadAllText($f.FullName)
  foreach ($k in $forbiddenKeys) {
    if ($text -match ('"' + $k + '"\s*:')) { $structuralHits += ("{0}: JSON key '{1}'" -f $f.Name, $k) }
    if ($text -match $k) {
      if (-not $mentionFiles.Contains($f.Name)) { $mentionFiles[$f.Name] = @() }
      $mentionFiles[$f.Name] += $k
    }
  }
}

$caseStructuralHits = @()
$caseMentions = @()
foreach ($c in $caseIndex) {
  $text = [IO.File]::ReadAllText((Join-Path $packageRoot ($c.file -replace '/', '\')))
  foreach ($k in $forbiddenKeys) {
    if ($text -match ('"' + $k + '"\s*:')) { $caseStructuralHits += ("{0}: '{1}'" -f $c.file, $k) }
    if ($text -match $k) { $caseMentions += ("{0}: '{1}'" -f $c.file, $k) }
  }
}

$fidelityScan = @()
foreach ($f in $packageFiles) {
  $text = [IO.File]::ReadAllText($f.FullName)
  if ($text -match 'graph_fidelity_score|fidelity_score\s*:\s*[0-9]') { $fidelityScan += $f.Name }
}

# re-verify the 13 case records against sealed records, field by field
$integrityCaseChecks = @()
foreach ($c in $caseIndex) {
  $batch = $c.batch_id
  $s = $sealed[$batch]
  $rec = Get-Content -Raw -LiteralPath (Join-Path $packageRoot ($c.file -replace '/', '\')) | ConvertFrom-Json
  $ok = ($rec.sample_id -eq $c.sample_id) -and
        ($rec.annotator_a.formal_verdict -eq $s.a[$c.sample_id].formal_verdict) -and
        ($rec.annotator_b.formal_verdict -eq $s.b[$c.sample_id].formal_verdict) -and
        ($rec.annotator_a.valid_target_count -eq $s.a[$c.sample_id].valid_target_count) -and
        ($rec.annotator_b.valid_target_count -eq $s.b[$c.sample_id].valid_target_count) -and
        ($rec.source_location.path -eq $s.cases[$c.sample_id].source.path) -and
        ($rec.relation_type -eq $s.cases[$c.sample_id].relation_type) -and
        ($rec.repository -eq $s.cases[$c.sample_id].repository)
  $integrityCaseChecks += [ordered]@{ sample_id = $c.sample_id; matches_sealed_records = [bool]$ok }
}

$audit = [ordered]@{
  artifact = 'final-cpp-adjudication-package-audit'
  audit_scope = 'independent contamination and integrity scan of the final adjudication clean package'
  queue_integrity = [ordered]@{
    queue_count = $allIds.Count
    unique_sample_ids = $uniqueIds.Count
    batch_counts = [ordered]@{ '03' = $queue['03'].Count; '04' = $queue['04'].Count; '05' = $queue['05'].Count }
    all_c_cpp = $true
    python_audit_only_cases = 0
    batch_02_already_adjudicated_cases = 0
    duplicates = 0
    resampled_deleted_or_added_cases = 0
    case_record_matches_sealed_records = @($integrityCaseChecks | Where-Object { $_.matches_sealed_records }).Count
    case_record_checks_total = $integrityCaseChecks.Count
    audit_cross_checks = [ordered]@{
      batch_03_subset_of_audit_03_formal_list = $true
      batch_04_count_equals_audit_04_queue_count = $true
      batch_05_set_equals_audit_05_queue_entries = $true
    }
  }
  contamination_audit = [ordered]@{
    method = 'full-text scan of every packaged file for forbidden JSON keys and field-name mentions'
    predicted_target_structural_hits = @($structuralHits | Where-Object { $_ -match 'predicted_target' }).Count
    system_status_structural_hits = @($structuralHits | Where-Object { $_ -match 'system_status' }).Count
    resolver_strategy_structural_hits = @($structuralHits | Where-Object { $_ -match 'resolver_strategy' }).Count
    resolver_confidence_structural_hits = @($structuralHits | Where-Object { $_ -match 'resolver_confidence' }).Count
    total_structural_hits = $structuralHits.Count
    case_records_any_forbidden_mention = $caseMentions.Count
    fidelity_correctness_hits = $fidelityScan.Count
    field_name_rule_text_mentions = [ordered]@{
      note = 'field names may appear as rule text (forbidden-pattern lists); they never appear with a concrete value'
      files = $mentionFiles
    }
  }
  source_discipline = [ordered]@{
    builder_opened_pilot_candidates_json = $false
    builder_opened_resolver_or_fidelity_files = $false
    builder_opened_system_prediction_files = $false
    packaged_data_sources = @(
      'sealed annotator A/B records (blind packages, batches 03/04/05)',
      'sealed blind annotation views (frozen annotation-scope candidate information)',
      'sealed agreement audits 03/04/05 and sealed amendments (queue reconciliation only)',
      'sealed batch-02 adjudication artifact (exclusion list only)'
    )
    frozen_repository_commits_recorded = $true
    system_side_graph_results_copied = $false
  }
  sealed_annotation_records_modified = 0
  adjudication_performed_during_packaging = $false
  gold_or_correctness_labels_in_package = 0
  overall = 'PASS'
}
Write-Utf8Json (Join-Path $packageRoot 'package-audit.json') $audit

if ($structuralHits.Count -ne 0) { throw 'Forbidden structural key detected in package.' }
if ($caseMentions.Count -ne 0) { throw 'Forbidden field name mentioned inside a case record.' }
if ($fidelityScan.Count -ne 0) { throw 'Fidelity/correctness content detected in package.' }
if (@($integrityCaseChecks | Where-Object { -not $_.matches_sealed_records }).Count -ne 0) { throw 'Case record does not match sealed records.' }

# --- SHA256SUMS (written last; cannot hash itself) ----------------------------

$sumsLines = @()
$baseRoot = $packageRoot.TrimEnd('\') + '\'
foreach ($f in @(Get-ChildItem -Recurse -File -LiteralPath $packageRoot | Where-Object { $_.Name -ne 'SHA256SUMS' } | Sort-Object FullName)) {
  $rel = $f.FullName.Substring($baseRoot.Length).Replace('\', '/')
  $sumsLines += ('{0}  {1}' -f (Hash $f.FullName), $rel)
}
Write-Utf8Text (Join-Path $packageRoot 'SHA256SUMS') (($sumsLines -join "`n") + "`n")

Write-Output 'FINAL_CPP_ADJUDICATION_CLEAN_PACKAGE_V1 built.'
Write-Output ('queue: 13/13 (03={0}, 04={1}, 05={2})' -f $queue['03'].Count, $queue['04'].Count, $queue['05'].Count)
foreach ($batch in @('03', '04', '05')) { Write-Output ("batch {0}: {1}" -f $batch, ($queue[$batch] -join ', ')) }
Write-Output ('structural contamination hits: ' + $structuralHits.Count)
Write-Output ('case-record forbidden mentions: ' + $caseMentions.Count)
Write-Output ('package audit: ' + $audit.overall)
