param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Gold Set Freeze builder — P0 Graph Fidelity Qualification V1
# C/C++ structural relation gold (CALLS + IMPORTS, scope CXX_PRIMARY).
#
# Freeze discipline:
#   - Reads only sealed annotation records, sealed adjudication artifacts,
#     sealed audits/gates/addenda, frozen blind views, and the frozen
#     sampling frame. It never opens results/pilot-candidates.json or any
#     other system prediction / resolver / fidelity artifact.
#   - Performs no new adjudication: every final verdict comes either from
#     sealed A/B agreement or from a sealed adjudication artifact.
#   - Deterministic target synthesis; target-level A/B divergence is frozen
#     as an acceptable-target set, never resolved by this builder.
# ---------------------------------------------------------------------------

$results = Join-Path $ExperimentRoot 'results'
$blindRoot = Join-Path $ExperimentRoot 'blind_packages'
$goldDir = Join-Path $ExperimentRoot 'gold'

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

function New-Target($SymbolId, $Path, $StartLine, $QualifiedName) {
  [ordered]@{
    symbol_id = $SymbolId
    path = $Path
    start_line = $StartLine
    qualified_name = $QualifiedName
  }
}
# Shared deterministic target synthesis for verdict-agreed ONE_VALID_TARGET cases.
# entries: @{symbol_id; path; start_line; source('A'|'B')}
# candidates: frozen annotation candidate_symbol_ids for the case
# Identity: equal symbol_id => same; equal path => same (path-level target; used
#   when symbol ids are absent or non-comparable); two distinct ids both present
#   in the frozen candidate set => distinct. Otherwise non-comparable.
# Resolvable: path anchored, or symbol_id present in the frozen candidate set.
# Unresolvable entries (self-derived opaque ids without path anchor) are excluded
#   from acceptable_targets and documented; they never create divergence.
function Build-AgreedTarget($entries, $candidates, $sampleId) {
  foreach ($e in $entries) {
    if ($e.path) { $e.resolvable = $true }
    elseif ($e.symbol_id -and ($candidates -contains $e.symbol_id)) { $e.resolvable = $true }
    else { $e.resolvable = $false }
  }
  $groups = @()
  $notes = @()
  foreach ($e in $entries) {
    $matched = $false
    for ($i = 0; $i -lt $groups.Count; $i++) {
      $g = $groups[$i][0]
      $same = $null
      if ($g.symbol_id -and $e.symbol_id) {
        if ($g.symbol_id -eq $e.symbol_id) { $same = $true }
        elseif (($candidates -contains $g.symbol_id) -and ($candidates -contains $e.symbol_id)) { $same = $false }
        elseif ($g.path -and $e.path) { $same = ($g.path -eq $e.path) }
        else { $same = 'NONCOMPARABLE' }
      } elseif ($g.path -and $e.path) {
        $same = ($g.path -eq $e.path)
      } else {
        $same = 'NONCOMPARABLE'
      }
      if ($same -eq $true) { $groups[$i] += @($e); $matched = $true; break }
      if ($same -eq $false) { continue }
    }
    if (-not $matched) { $groups += ,@($e) }
  }
  $acceptable = @()
  $unresolvable = @()
  foreach ($grp in $groups) {
    if (@($grp | Where-Object { $_.resolvable }).Count -eq 0) {
      foreach ($e in $grp) {
        $unresolvable += [ordered]@{
          source_annotator = $e.source
          recorded_symbol_id = $e.symbol_id
          recorded_path = $e.path
          reason = 'annotator-recorded identifier absent from the frozen candidate set with no path anchor; not cross-comparable and not resolvable to a frozen repository entity'
        }
      }
      continue
    }
    $ranked = @($grp | Sort-Object -Property @{Expression = { if ($_.resolvable) { 0 } else { 1 } } }, @{Expression = { if ($_.source -eq 'B') { 0 } else { 1 } } })
    $t = New-Target $null $null $null $null
    foreach ($e in $ranked) {
      if (-not $t.symbol_id -and $e.symbol_id) { $t.symbol_id = $e.symbol_id }
      if (-not $t.path -and $e.path) { $t.path = $e.path }
      if ($null -eq $t.start_line -and $null -ne $e.start_line) { $t.start_line = $e.start_line }
    }
    $acceptable += @($t)
    $lines = @($grp | Where-Object { $null -ne $_.start_line } | ForEach-Object { $_.start_line } | Sort-Object -Unique)
    if ($grp.Count -gt 1 -and $lines.Count -gt 1 -and -not ($grp[0].symbol_id -and $grp[1].symbol_id -and $grp[0].symbol_id -eq $grp[1].symbol_id)) {
      $notes += ('line anchors differed within the same path ({0}); frozen as one path-level target under same-file declaration/definition equivalence' -f ($lines -join ' vs '))
    }
  }
  $status = $null
  if ($acceptable.Count -eq 1) { $status = 'UNIQUE' }
  elseif ($acceptable.Count -gt 1) { $status = 'DIVERGENT' }
  else { throw "No resolvable recorded target for verdict-agreed ONE case: $sampleId" }
  [ordered]@{
    status = $status
    final_target = $(if ($status -eq 'UNIQUE') { $acceptable[0] } else { $null })
    acceptable_targets = $acceptable
    canonical_target = $(if ($status -eq 'UNIQUE') { $acceptable[0] } else { $null })
    unresolvable_selections = $unresolvable
    notes = $notes
  }
}
$sevRank = @{ 'LOW' = 0; 'MEDIUM' = 1; 'HIGH' = 2 }
function Min-Sev([string]$a, [string]$b) {
  $vals = @()
  foreach ($v in @($a, $b)) { if ($v) { $vals += $sevRank[$v.ToUpperInvariant()] } }
  if ($vals.Count -eq 0) { return $null }
  $m = ($vals | Measure-Object -Minimum).Minimum
  foreach ($k in $sevRank.Keys) { if ($sevRank[$k] -eq $m) { return $k.ToUpperInvariant() } }
  return $null
}
function Norm-EvLoc($e) {
  if ($e -is [string]) { return $e }
  if ($e.path) {
    if ($null -ne $e.start_line -and $null -ne $e.end_line -and $e.start_line -ne $e.end_line) { return ('{0}:{1}-{2}' -f $e.path, $e.start_line, $e.end_line) }
    return ('{0}:{1}' -f $e.path, $e.start_line)
  }
  return ($e | ConvertTo-Json -Compress -Depth 5)
}

$frozenCommits = [ordered]@{
  aria2 = '9e7273583f83e881e3ec067b523ba88724088d2f'
  brpc = 'ae09e960c7291605dda52356cc0c2d45567fb53e'
  rocksdb = '37234200b57d8d0a6a5c41f2d9811bbd2e293544'
}
$coreProtocols = @('CALLS_V1', 'EVIDENCE_SCOPE_V1', 'DECL_DEF_EQUIVALENCE_V1')

# --- sealed input integrity anchors ------------------------------------------

$inputProvenance = @()
function Add-Prov([string]$path, [string]$role, [string]$level, [string]$anchor) {
  $script:inputProvenance += [ordered]@{
    path = (Rel $path); role = $role; sha256 = (Hash $path); verification = $level; anchor = $anchor
  }
}
function Assert-ShaFile([string]$shaFilePath, [string]$baseDir) {
  foreach ($line in @(Get-Content -LiteralPath $shaFilePath)) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split '  ', 2
    $target = Join-Path $baseDir $parts[1]
    if (-not (Test-Path -LiteralPath $target)) { throw "Anchored file missing: $($parts[1])" }
    if ((Hash $target) -ne $parts[0].ToLowerInvariant()) { throw "Sealed input hash mismatch: $($parts[1])" }
  }
}

# batch-02 + final adjudication artifacts (self-anchored)
Assert-ShaFile (Join-Path $results 'batch-02-cpp-calls-adjudication.sha256') $results
Assert-ShaFile (Join-Path $ExperimentRoot 'final-cpp-adjudication.sha256') $ExperimentRoot
Add-Prov (Join-Path $results 'batch-02-cpp-calls-adjudication.json') 'sealed Batch 02 adjudication (4 cases)' 'sha256-anchored' 'results/batch-02-cpp-calls-adjudication.sha256'
Add-Prov (Join-Path $ExperimentRoot 'final-cpp-adjudication.json') 'sealed final C/C++ adjudication (13 cases)' 'sha256-anchored' 'final-cpp-adjudication.sha256'

# calibration gate input anchors
$gate = LoadJson (Join-Path $results 'calibration-gate-01.json')
foreach ($k in $gate.inputs_sha256.PSObject.Properties.Name) {
  $p = Join-Path $results $k
  if ((Hash $p) -ne $gate.inputs_sha256.$k) { throw "Calibration input hash mismatch: $k" }
}
Add-Prov (Join-Path $results 'annotator-a-calibration-01-normalized.json') 'sealed Annotator A calibration record (normalized)' 'sha256-anchored' 'calibration-gate-01.inputs_sha256'
Add-Prov (Join-Path $results 'annotator-b-calibration-01.json') 'sealed Annotator B calibration record + frozen calibration case metadata' 'sha256-anchored' 'calibration-gate-01.inputs_sha256'
Add-Prov (Join-Path $results 'calibration-gate-01.json') 'sealed calibration gate (python out-of-scope list; D1/D2/D3)' 'observed-at-freeze' 'audit record'
Add-Prov (Join-Path $results 'protocol-addendum-calls-v1-macro-semantics.md') 'FROZEN addendum (macro semantics; resolves calibration case FQV1-rocksdb-1273fbd969565cef)' 'frozen-protocol' 'protocol commit 12f405c677582a2982d035433bf6837126772716'
Add-Prov (Join-Path $results 'protocol-addendum-evidence-scope-v1.md') 'FROZEN owner-ratified addendum (supersedes OPEN-1; resolves calibration case FQV1-aria2-713b641e93cc620c)' 'frozen-protocol' 'protocol commit 12f405c677582a2982d035433bf6837126772716'

# blind-package anchors
$shaSums = @{}
foreach ($rel in @(
  'batch-03\annotator-a', 'batch-03\annotator-b',
  'batch-04\annotator-a', 'batch-04\annotator-b',
  'batch-05\annotator-a', 'batch-05\annotator-b')) {
  $dir = Join-Path $blindRoot $rel
  foreach ($line in @(Get-Content -LiteralPath (Join-Path $dir 'SHA256SUMS'))) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split '  ', 2
    $shaSums[(Join-Path $dir $parts[1])] = $parts[0].ToLowerInvariant()
  }
}
function Assert-PkgHash([string]$path, [string]$label) {
  if (-not $shaSums.ContainsKey($path)) { throw "No SHA256SUMS anchor for $label" }
  if ((Hash $path) -ne $shaSums[$path]) { throw "Blind package payload hash mismatch: $label" }
}
$batchSpec = @(
  [ordered]@{ cohort = 'batch_03'; a = Join-Path $blindRoot 'batch-03\annotator-a\output\annotation-record-template.json'; b = Join-Path $blindRoot 'batch-03\annotator-b\output\annotation-record-template.json'; view = Join-Path $blindRoot 'batch-03\annotator-a\input\annotator-a-blind-view.json'; manifest = Join-Path $blindRoot 'batch-03\annotator-a\input\batch-03-manifest.json' },
  [ordered]@{ cohort = 'batch_04'; a = Join-Path $blindRoot 'batch-04\annotator-a\output\annotator-a-batch-04-annotations.json'; b = Join-Path $blindRoot 'batch-04\annotator-b\output\annotation-record-template.json'; view = Join-Path $blindRoot 'batch-04\annotator-a\input\annotator-a-blind-view.json'; manifest = Join-Path $blindRoot 'batch-04\annotator-a\input\batch-04-manifest.json' },
  [ordered]@{ cohort = 'batch_05'; a = Join-Path $blindRoot 'batch-05\annotator-a\output\annotator-a-batch-05-annotations.json'; b = Join-Path $blindRoot 'batch-05\annotator-b\output\annotator-b-batch-05-annotation-records.json'; view = Join-Path $blindRoot 'batch-05\annotator-a\input\annotator-a-blind-view.json'; manifest = Join-Path $blindRoot 'batch-05\annotator-a\input\batch-05-manifest.json' }
)
foreach ($s in $batchSpec) {
  Assert-PkgHash $s.view "blind view $($s.cohort)"
  Add-Prov $s.view "frozen blind view $($s.cohort) (case metadata + annotation candidate scope)" 'sha256-anchored' 'blind package SHA256SUMS'
  Add-Prov $s.manifest "frozen batch manifest $($s.cohort) (case order)" 'sha256-anchored' 'blind package SHA256SUMS'
}
# sealed record outputs: anchored where a seal artifact records their hash.
# SHA256SUMS freezes the pre-annotation package state; completed sealed outputs
# differ from the blank-template entries by design (audit-03 preflight:
# completed_output_files_differ_from_blank_template_hash = true), so completed
# outputs without a seal-artifact hash are recorded as observed-at-freeze.
Add-Prov $batchSpec[0].a 'sealed Annotator A batch-03 records' 'observed-at-freeze' 'blind-agreement-audit-03 preflight PASS (completed output differs from frozen blank-template SHA256SUMS entry by design)'
Add-Prov $batchSpec[0].b 'sealed Annotator B batch-03 records' 'observed-at-freeze' 'blind-agreement-audit-03 preflight PASS (completed output differs from frozen blank-template SHA256SUMS entry by design)'
Add-Prov $batchSpec[1].a 'sealed Annotator A batch-04 records' 'observed-at-freeze' 'audit-04 preflight PASS (completed output not in SHA256SUMS; seal-verification cites blank-template hash)'
if ((Hash $batchSpec[1].b) -ne 'daeb0a4427d2fb90cd40e1270bd2f2ca72e9a93649101b6d35eb2815dae1601f') { throw 'B04 sealed output hash does not match batch-04 seal verification.' }
Add-Prov $batchSpec[1].b 'sealed Annotator B batch-04 records' 'sha256-anchored' 'results/batch-04-annotation-seal-verification.json (b.output_sha256)'
if ((Hash $batchSpec[2].a) -ne '08915528c97394f9ee52453190ed7241a125a739e8c3995c222754b951dee622') { throw 'A05 sealed output hash does not match audit-05 seal evidence.' }
Add-Prov $batchSpec[2].a 'sealed Annotator A batch-05 records' 'sha256-anchored' 'blind-agreement-audit-05 preflight (a_seal_evidence)'
if ((Hash $batchSpec[2].b) -ne '560d08cc940bdfa6eb4416fd0298a98a441845d184bdcce5e93f5e212f2c220c') { throw 'B05 sealed output hash does not match B05 seal JSON.' }
Add-Prov $batchSpec[2].b 'sealed Annotator B batch-05 records' 'sha256-anchored' 'annotator-b-batch-05-seal.json (annotation_sha256)'

# batch-02 sealed records (observed at freeze; audit-02 preflight anchor)
$a02Path = Join-Path $results 'annotator-a-batch-02.json'
$b02Path = Join-Path $results 'annotator-b-batch-02.json'
Add-Prov $a02Path 'sealed Annotator A batch-02 records' 'observed-at-freeze' 'blind-agreement-audit-02 amendment (preflight PASS)'
Add-Prov $b02Path 'sealed Annotator B batch-02 records + frozen batch-02 case metadata' 'observed-at-freeze' 'blind-agreement-audit-02 amendment (preflight PASS)'

# frozen sampling frame (universe reconciliation only)
$sfcPath = Join-Path $results 'sampling-frame-correction-v1.json'
Add-Prov $sfcPath 'frozen sampling frame (universe cpp_fidelity=174; CALLS 86 / IMPORTS 88)' 'frozen-frame' 'milestone-freeze-p0-fidelity-v1'

# --- sealed adjudication records ---------------------------------------------

$adjudicated = @{}
$b02Adj = LoadJson (Join-Path $results 'batch-02-cpp-calls-adjudication.json')
foreach ($r in $b02Adj.adjudications) {
  $finalT = New-Target $r.canonical_target_symbol_id $null $null $r.canonical_source_target
  $acc = @($finalT)
  if ($r.acceptable_declaration_twin) { $acc += @(New-Target $r.acceptable_declaration_twin $null $null $null) }
  $adjudicated[$r.case_id] = [ordered]@{
    final_gold_verdict = $r.final_gold_verdict
    final_gold_target = $finalT
    acceptable_targets = $acc
    canonical_target = $finalT
    target_status = $(if ($r.final_gold_verdict -in @('NO_VALID_TARGET', 'RELATION_NOT_PRESENT')) { 'ABSENT' } elseif ($r.final_gold_verdict -in @('BUILD_CONTEXT_DEPENDENT', 'INSUFFICIENT_EVIDENCE')) { 'INDETERMINATE' } else { 'UNIQUE' })
    gold_source = 'adjudicated'
    adjudication_source = 'results/batch-02-cpp-calls-adjudication.json (SEALED)'
    confidence = $null
    evidence_locations = @($r.evidence_locations)
    failure_mechanism = $r.failure_mechanism
    correct_target_present_in_candidate_set = $r.correct_target_present_in_candidate_set
    cross_file_navigation_required = $r.cross_file_recovery_necessary
  }
}
$finalAdj = LoadJson (Join-Path $ExperimentRoot 'final-cpp-adjudication.json')
if ($finalAdj.closure_summary.closed -ne 13 -or $finalAdj.closure_summary.status -ne 'COMPLETE') { throw 'Final adjudication artifact is not CLOSED/COMPLETE.' }
foreach ($r in $finalAdj.records) {
  if ($r.final_adjudication_status -ne 'CLOSED') { throw "Final adjudication record not CLOSED: $($r.sample_id)" }
  $ft = $null
  if ($r.final_target) { $ft = New-Target $null $r.final_target.path $r.final_target.start_line $r.final_target.symbol }
  $acc = @()
  foreach ($t in @($r.acceptable_targets)) { $acc += @(New-Target $null $t.path $t.start_line $null) }
  $ct = $null
  if ($r.canonical_target) { $ct = New-Target $null $r.canonical_target.path $r.canonical_target.start_line $null }
  $adjudicated[$r.sample_id] = [ordered]@{
    final_gold_verdict = $r.final_verdict
    final_gold_target = $ft
    acceptable_targets = $acc
    canonical_target = $ct
    target_status = $(if ($r.final_verdict -in @('NO_VALID_TARGET', 'RELATION_NOT_PRESENT')) { 'ABSENT' } elseif ($r.final_verdict -in @('BUILD_CONTEXT_DEPENDENT', 'INSUFFICIENT_EVIDENCE')) { 'INDETERMINATE' } elseif ($ft) { 'UNIQUE' } else { 'DIVERGENT' })
    gold_source = 'adjudicated'
    adjudication_source = 'final-cpp-adjudication.json (SEALED, source-only)'
    confidence = $r.confidence
    evidence_locations = @($r.evidence_locations)
    failure_mechanism = $r.primary_failure_mechanism
    correct_target_present_in_candidate_set = $r.correct_target_in_candidate_set
    cross_file_navigation_required = $r.cross_file_navigation_required
  }
}

# --- cohort record iteration --------------------------------------------------

$records = @()
$cppScopes = @('C++', 'C', 'C/C++', 'CPP_IN_SCOPE', 'CPP_PRIMARY')
$cohortStats = [ordered]@{}

function Add-Record($rec) {
  $script:records += $rec
  $c = $rec.batch_cohort; $rel = $rec.relation_type
  $k1 = "$c/$rel"
  if (-not $script:cohortStats.Contains($k1)) { $script:cohortStats[$k1] = 0 }
  $script:cohortStats[$k1]++
}

# calibration cohort
$pythonOutOfScope = @($gate.scope_adjudication.python_out_of_scope_cases)
$normById = @{}; foreach ($c in (LoadJson (Join-Path $results 'annotator-a-calibration-01-normalized.json')).cases) { $normById[$c.case_id] = $c }
$bcal = LoadJson (Join-Path $results 'annotator-b-calibration-01.json')
$calibAddendum = [ordered]@{
  'FQV1-rocksdb-1273fbd969565cef' = [ordered]@{
    verdict = 'NO_VALID_TARGET'
    source = 'results/calibration-gate-01 (D1) + results/protocol-addendum-calls-v1-macro-semantics.md (FROZEN)'
    confidence = 'HIGH'
    target = $null
  }
  'FQV1-aria2-713b641e93cc620c' = [ordered]@{
    verdict = 'ONE_VALID_TARGET'
    source = 'results/calibration-gate-01 OPEN-1 superseded by results/protocol-addendum-evidence-scope-v1.md (FROZEN, owner-ratified); B cross-file type propagation is the protocol-conformant strategy'
    confidence = 'MEDIUM'
    target = $null
  }
}
foreach ($c in $bcal.cases) {
  if ($pythonOutOfScope -contains $c.case_id) { continue }
  if ($c.relation_type -notin @('CALLS', 'IMPORTS')) { continue }
  $a = $normById[$c.case_id]
  $bAnn = $c.annotation
  $bTarget = $null
  if ($bAnn.gold_target_symbol_id -or $bAnn.gold_target_path) {
    $bTarget = New-Target $bAnn.gold_target_symbol_id $bAnn.gold_target_path $bAnn.gold_target_start_line $null
  }
  $srcLoc = $c.source
  $evLoc = @('{0}:{1}' -f $srcLoc.path, $srcLoc.start_line)
  if ($srcLoc.end_line -ne $srcLoc.start_line) { $evLoc[0] = '{0}:{1}-{2}' -f $srcLoc.path, $srcLoc.start_line, $srcLoc.end_line }
  $protocols = @($coreProtocols)
  if ($calibAddendum.Contains($c.case_id)) {
    $ca = $calibAddendum[$c.case_id]
    $caTarget = $ca.target
    $accTargets = @()
    if ($ca.verdict -eq 'ONE_VALID_TARGET') {
      if (-not $bTarget) { throw "Addendum-resolved ONE case without structured B target: $($c.case_id)" }
      $caTarget = $bTarget
      $accTargets = @($bTarget)
    }
    $rec = [ordered]@{
      sample_id = $c.case_id; batch_cohort = 'calibration_01'; repository = $c.repository
      relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
      source_location = [ordered]@{ raw_reference_id = $c.raw_reference_id; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
      scope = 'CXX_PRIMARY'
      final_gold_verdict = $ca.verdict
      final_gold_target = $caTarget
      acceptable_targets = $accTargets
      canonical_target = $caTarget
      target_status = $(if ($ca.verdict -eq 'ONE_VALID_TARGET') { 'UNIQUE' } else { 'ABSENT' })
      gold_source = 'adjudicated'
      adjudication_source = $ca.source
      confidence = $ca.confidence
      evidence_locations = $evLoc
      sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.mapped_formal_verdict; annotator_b = $bAnn.relation_verdict }
      uncrosscomparable_selections = @()
      target_note = $null
      protocol_version = $protocols
    }
    Add-Record $rec
    continue
  }
  if ($a.mapped_formal_verdict -ne $bAnn.relation_verdict) { throw "Unresolved calibration disagreement: $($c.case_id)" }
  $verdict = $bAnn.relation_verdict
  $tStatus = 'ABSENT'; $fTarget = $null; $acc = @(); $canon = $null; $unres = @(); $tNotes = @()
  if ($verdict -eq 'ONE_VALID_TARGET') {
    if (-not $bTarget) { throw "Calibration ONE case without structured B target: $($c.case_id)" }
    $syn = Build-AgreedTarget @(@{ symbol_id = $bAnn.gold_target_symbol_id; path = $bAnn.gold_target_path; start_line = $bAnn.gold_target_start_line; source = 'B' }) @($c.candidate_symbol_ids) $c.case_id
    $tStatus = $syn.status; $fTarget = $syn.final_target; $acc = $syn.acceptable_targets; $canon = $syn.canonical_target
    $unres = $syn.unresolvable_selections; $tNotes = $syn.notes
  } elseif ($verdict -in @('BUILD_CONTEXT_DEPENDENT', 'INSUFFICIENT_EVIDENCE')) { $tStatus = 'INDETERMINATE' }
  $rec = [ordered]@{
    sample_id = $c.case_id; batch_cohort = 'calibration_01'; repository = $c.repository
    relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
    source_location = [ordered]@{ raw_reference_id = $c.raw_reference_id; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
    scope = 'CXX_PRIMARY'
    final_gold_verdict = $verdict
    final_gold_target = $fTarget
    acceptable_targets = $acc
    canonical_target = $canon
    target_status = $tStatus
    gold_source = 'agreed_annotation'
    adjudication_source = $null
    confidence = $a.mapping_confidence
    evidence_locations = $evLoc
    sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.mapped_formal_verdict; annotator_b = $bAnn.relation_verdict }
    target_provenance = 'annotator_b structured target; Annotator A verdict agreement per frozen MR-1 mapping (prose target evidence, no structured target in sealed calibration records)'
    uncrosscomparable_selections = $unres
    target_note = $(if ($tNotes) { $tNotes -join '; ' } else { $null })
    protocol_version = $protocols
  }
  Add-Record $rec
}

# batch-02 cohort
$a02 = LoadJson $a02Path
$b02 = LoadJson $b02Path
$a02ById = @{}; foreach ($r in $a02.annotations) { $a02ById[$r.case_id] = $r }
foreach ($c in $b02.cases) {
  if ($c.language_scope -ne 'CPP_IN_SCOPE') { continue }
  if ($c.relation_type -notin @('CALLS', 'IMPORTS')) { continue }
  $a = $a02ById[$c.sample_id]
  $srcLoc = $c.source
  $bTarget = $null
  $sel = $c.selected_target_if_unique
  if ($sel -and ($sel.symbol_id -or $sel.path)) { $bTarget = New-Target $sel.symbol_id $sel.path $sel.start_line $null }
  if ($adjudicated.ContainsKey($c.sample_id)) {
    $adj = $adjudicated[$c.sample_id]
    $rec = [ordered]@{
      sample_id = $c.sample_id; batch_cohort = 'batch_02'; repository = $c.repository
      relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
      source_location = [ordered]@{ raw_reference_id = $null; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
      scope = 'CXX_PRIMARY'
      final_gold_verdict = $adj.final_gold_verdict
      final_gold_target = $adj.final_gold_target
      acceptable_targets = $adj.acceptable_targets
      canonical_target = $adj.canonical_target
      target_status = $adj.target_status
      gold_source = 'adjudicated'
      adjudication_source = $adj.adjudication_source
      confidence = $adj.confidence
      evidence_locations = $adj.evidence_locations
      sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.verdict; annotator_b = $c.formal_verdict }
      failure_mechanism = $adj.failure_mechanism
      uncrosscomparable_selections = @()
      target_note = $null
      protocol_version = @($coreProtocols)
    }
    Add-Record $rec
    continue
  }
  if ($a.verdict -ne $c.formal_verdict) { throw "Unresolved batch-02 disagreement: $($c.sample_id)" }
  $verdict = $c.formal_verdict
  $tStatus = 'ABSENT'; $fTarget = $null; $acc = @(); $canon = $null; $prov = $null; $unres = @(); $tNotes = @()
  if ($verdict -eq 'ONE_VALID_TARGET') {
    $entries = @()
    foreach ($sid in @($a.valid_target_candidate_ids)) { $entries += @{ symbol_id = $sid; path = $null; start_line = $null; source = 'A' } }
    if ($bTarget) { $entries += @{ symbol_id = $sel.symbol_id; path = $sel.path; start_line = $sel.start_line; source = 'B' } }
    $syn = Build-AgreedTarget $entries @($c.candidate_symbol_ids) $c.sample_id
    $tStatus = $syn.status; $fTarget = $syn.final_target; $acc = $syn.acceptable_targets; $canon = $syn.canonical_target
    $unres = $syn.unresolvable_selections; $tNotes = $syn.notes
    $srcs = @($entries | ForEach-Object { $_.source } | Sort-Object -Unique)
    $prov = $srcs -join '+'
  } elseif ($verdict -in @('BUILD_CONTEXT_DEPENDENT', 'INSUFFICIENT_EVIDENCE')) { $tStatus = 'INDETERMINATE' }
  $ev = @()
  foreach ($e in @($a.source_evidence)) { if ($e) { $ev += @(Norm-EvLoc $e) } }
  foreach ($e in @($c.evidence_locations)) { if ($e) { $ev += @(Norm-EvLoc $e) } }
  $rec = [ordered]@{
    sample_id = $c.sample_id; batch_cohort = 'batch_02'; repository = $c.repository
    relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
    source_location = [ordered]@{ raw_reference_id = $null; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
    scope = 'CXX_PRIMARY'
    final_gold_verdict = $verdict
    final_gold_target = $fTarget
    acceptable_targets = $acc
    canonical_target = $canon
    target_status = $tStatus
    gold_source = 'agreed_annotation'
    adjudication_source = $null
    confidence = (Min-Sev $a.confidence $c.confidence)
    evidence_locations = @($ev | Select-Object -Unique)
    sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.verdict; annotator_b = $c.formal_verdict }
    target_provenance = $prov
    uncrosscomparable_selections = $unres
    target_note = $(if ($tNotes) { $tNotes -join '; ' } else { $null })
    protocol_version = @($coreProtocols)
  }
  Add-Record $rec
}

# batches 03-05 cohorts
foreach ($s in $batchSpec) {
  $A = LoadJson $s.a
  $B = LoadJson $s.b
  $view = LoadJson $s.view
  $manifest = LoadJson $s.manifest
  $caseById = @{}; foreach ($c in $view.cases) { $caseById[$c.case_id] = $c }
  $aById = @{}; foreach ($r in $A.records) { $aById[$r.sample_id] = $r }
  $bById = @{}; foreach ($r in $B.records) { $bById[$r.sample_id] = $r }
  foreach ($id in $manifest.case_ids) {
    $c = $caseById[$id]
    if ($cppScopes -notcontains $bById[$id].language_scope) { continue }
    if ($c.relation_type -notin @('CALLS', 'IMPORTS')) { continue }
    $a = $aById[$id]; $b = $bById[$id]
    $srcLoc = $c.source
    function Sel-Target($t) {
      if ($t -and $t.symbol_id -eq 'symbol:placeholder') { return $null }
      if ($t -and ($t.symbol_id -or $t.path)) { return New-Target $t.symbol_id $t.path $t.start_line $null }
      return $null
    }
    if ($adjudicated.ContainsKey($id)) {
      $adj = $adjudicated[$id]
      $rec = [ordered]@{
        sample_id = $id; batch_cohort = $s.cohort; repository = $c.repository
        relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
        source_location = [ordered]@{ raw_reference_id = $c.raw_reference_id; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
        scope = 'CXX_PRIMARY'
        final_gold_verdict = $adj.final_gold_verdict
        final_gold_target = $adj.final_gold_target
        acceptable_targets = $adj.acceptable_targets
        canonical_target = $adj.canonical_target
        target_status = $adj.target_status
        gold_source = 'adjudicated'
        adjudication_source = $adj.adjudication_source
        confidence = $adj.confidence
        evidence_locations = $adj.evidence_locations
        sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.formal_verdict; annotator_b = $b.formal_verdict }
        failure_mechanism = $adj.failure_mechanism
        correct_target_present_in_candidate_set = $adj.correct_target_present_in_candidate_set
        cross_file_navigation_required = $adj.cross_file_navigation_required
        uncrosscomparable_selections = @()
        target_note = $null
        protocol_version = @($coreProtocols)
      }
      Add-Record $rec
      continue
    }
    if ($a.formal_verdict -ne $b.formal_verdict) { throw "Unresolved disagreement in $($s.cohort): $id" }
    $verdict = $b.formal_verdict
    $tStatus = 'ABSENT'; $fTarget = $null; $acc = @(); $canon = $null; $prov = $null; $unres = @(); $tNotes = @()
    if ($verdict -eq 'ONE_VALID_TARGET') {
      $entries = @()
      $aT = Sel-Target $a.selected_target_if_unique
      $bT = Sel-Target $b.selected_target_if_unique
      if ($aT) { $entries += @{ symbol_id = $a.selected_target_if_unique.symbol_id; path = $a.selected_target_if_unique.path; start_line = $a.selected_target_if_unique.start_line; source = 'A' } }
      if ($bT) { $entries += @{ symbol_id = $b.selected_target_if_unique.symbol_id; path = $b.selected_target_if_unique.path; start_line = $b.selected_target_if_unique.start_line; source = 'B' } }
      if ($entries.Count -eq 0) { throw "ONE case without any recorded target: $id" }
      $syn = Build-AgreedTarget $entries @($c.candidate_symbol_ids) $id
      $tStatus = $syn.status; $fTarget = $syn.final_target; $acc = $syn.acceptable_targets; $canon = $syn.canonical_target
      $unres = $syn.unresolvable_selections; $tNotes = $syn.notes
      $srcs = @($entries | ForEach-Object { $_.source } | Sort-Object -Unique)
      $prov = $srcs -join '+'
    } elseif ($verdict -in @('BUILD_CONTEXT_DEPENDENT', 'INSUFFICIENT_EVIDENCE')) { $tStatus = 'INDETERMINATE' }
    $ev = @()
    foreach ($e in @($a.evidence_locations)) { if ($e) { $ev += @(Norm-EvLoc $e) } }
    foreach ($e in @($b.evidence_locations)) { if ($e) { $ev += @(Norm-EvLoc $e) } }
    $rec = [ordered]@{
      sample_id = $id; batch_cohort = $s.cohort; repository = $c.repository
      relation_type = $c.relation_type; frozen_repository_commit = $frozenCommits[$c.repository]
      source_location = [ordered]@{ raw_reference_id = $c.raw_reference_id; path = $srcLoc.path; start_line = $srcLoc.start_line; end_line = $srcLoc.end_line; owner_kind = $srcLoc.owner_kind; owner_qualified_name = $srcLoc.owner_qualified_name; raw_name = $srcLoc.raw_name; target_module = $srcLoc.target_module }
      scope = 'CXX_PRIMARY'
      final_gold_verdict = $verdict
      final_gold_target = $fTarget
      acceptable_targets = $acc
      canonical_target = $canon
      target_status = $tStatus
      gold_source = 'agreed_annotation'
      adjudication_source = $null
      confidence = (Min-Sev $a.confidence $b.confidence)
      evidence_locations = @($ev | Select-Object -Unique)
      sealed_annotator_verdicts = [ordered]@{ annotator_a = $a.formal_verdict; annotator_b = $b.formal_verdict }
      target_provenance = $prov
      uncrosscomparable_selections = $unres
      target_note = $(if ($tNotes) { $tNotes -join '; ' } else { $null })
      protocol_version = @($coreProtocols)
    }
    Add-Record $rec
  }
}

# --- reconciliation gates ------------------------------------------------------

$total = $records.Count
$uniqueIds = @($records | ForEach-Object { $_.sample_id } | Sort-Object -Unique)
$calls = @($records | Where-Object { $_.relation_type -eq 'CALLS' })
$imports = @($records | Where-Object { $_.relation_type -eq 'IMPORTS' })
$adjudicatedRecords = @($records | Where-Object { $_.gold_source -eq 'adjudicated' })
$divergent = @($records | Where-Object { $_.target_status -eq 'DIVERGENT' })
$noVerdict = @($records | Where-Object { -not $_.final_gold_verdict })

if ($total -ne 174) { throw "Gold total $total != 174" }
if ($uniqueIds.Count -ne 174) { throw "Unique gold sample_ids $($uniqueIds.Count) != 174" }
if ($calls.Count -ne 86) { throw "CALLS gold $($calls.Count) != 86" }
if ($imports.Count -ne 88) { throw "IMPORTS gold $($imports.Count) != 88" }
if ($adjudicatedRecords.Count -ne 19) { throw "Adjudicated gold records $($adjudicatedRecords.Count) != 19" }
if ($noVerdict.Count -ne 0) { throw "Gold records without final verdict: $($noVerdict.Count)" }
foreach ($r in $records) {
  if ($r.scope -ne 'CXX_PRIMARY') { throw "Scope violation: $($r.sample_id)" }
  if ($r.relation_type -eq 'REFERENCES') { throw "REFERENCES leaked into gold: $($r.sample_id)" }
}
$sfc = LoadJson $sfcPath
if ($sfc.universe.cpp_fidelity -ne 174) { throw 'Sampling frame universe mismatch.' }
$sfcCalls = 0; $sfcImports = 0
foreach ($st in $sfc.strata) {
  if ($st.relation -eq 'CALLS') { $sfcCalls += $st.sample_n_cpp }
  if ($st.relation -eq 'IMPORTS') { $sfcImports += $st.sample_n_cpp }
}
if ($sfcCalls -ne 86 -or $sfcImports -ne 88) { throw 'Sampling frame stratum C/C++ CALLS/IMPORTS sums do not equal 86/88.' }

$cohortRecon = [ordered]@{}
foreach ($cohort in @('calibration_01', 'batch_02', 'batch_03', 'batch_04', 'batch_05')) {
  $rs = @($records | Where-Object { $_.batch_cohort -eq $cohort })
  $cohortRecon[$cohort] = [ordered]@{
    total = $rs.Count
    calls = @($rs | Where-Object { $_.relation_type -eq 'CALLS' }).Count
    imports = @($rs | Where-Object { $_.relation_type -eq 'IMPORTS' }).Count
    agreed = @($rs | Where-Object { $_.gold_source -eq 'agreed_annotation' }).Count
    adjudicated = @($rs | Where-Object { $_.gold_source -eq 'adjudicated' }).Count
  }
}
$verdictDist = @{}
foreach ($r in $records) {
  $k = $r.final_gold_verdict
  if (-not $verdictDist.ContainsKey($k)) { $verdictDist[$k] = 0 }
  $verdictDist[$k]++
}
$statusDist = @{}
foreach ($r in $records) {
  $k = $r.target_status
  if (-not $statusDist.ContainsKey($k)) { $statusDist[$k] = 0 }
  $statusDist[$k]++
}

# --- emit gold artifacts --------------------------------------------------------

if (Test-Path -LiteralPath $goldDir) { Remove-Item -Recurse -Force -LiteralPath $goldDir }
New-Item -ItemType Directory -Force -Path $goldDir | Out-Null

$goldJson = [ordered]@{
  artifact = 'cpp-structural-relation-gold-v1'
  status = 'SEALED_FROZEN'
  created = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  scope = 'CXX_PRIMARY (C/C++ CALLS + IMPORTS only)'
  relation_scope_policy = [ordered]@{
    CALLS = 'INCLUDED'
    IMPORTS = 'INCLUDED'
    REFERENCES = 'NOT EVALUABLE FOR C/C++ (CXX_REFERENCE_RELATION_NOT_MODELED; sampling-frame-correction-v1 SFC-1); excluded from this gold set'
    python_any_relation = 'EXCLUDED (python_out_of_scope, 95 cases)'
  }
  universe_reconciliation = [ordered]@{
    cpp_fidelity_universe = 174
    gold_records_total = $total
    calls_gold = $calls.Count
    imports_gold = $imports.Count
    arithmetic = '86 + 88 = 174'
    unique_sample_ids = $uniqueIds.Count
    sampling_frame_cross_check = 'sampling-frame-correction-v1: cpp_fidelity=174; stratum C/C++ sums CALLS=86, IMPORTS=88'
    unresolved_adjudications = 0
    python_records = 0
    references_records = 0
  }
  synthesis_rules = [ordered]@{
    gold_source = 'adjudicated when a sealed adjudication artifact covers the case; otherwise agreed_annotation (sealed A verdict == sealed B verdict after frozen calibration mapping where applicable)'
    agreed_target_layer = 'verdict-agreed ONE_VALID_TARGET cases freeze the set of annotator-recorded targets. Identity: equal symbol_id => same target; equal path => same path-level target (same-file declaration/definition anchors); two distinct symbol ids both present in the frozen candidate set => distinct targets. Resolvable = path-anchored or symbol_id present in the frozen candidate set. Singleton resolvable set -> UNIQUE; multiple distinct resolvable targets -> DIVERGENT with acceptable_targets and final_gold_target=null; unresolvable selections (self-derived opaque ids without path anchor, as disclosed by annotator protocol_issue fields) are excluded from acceptable_targets and preserved in uncrosscomparable_selections. No new adjudication is performed at freeze.'
    absent_or_indeterminate = 'NO_VALID_TARGET/RELATION_NOT_PRESENT -> ABSENT; BUILD_CONTEXT_DEPENDENT/INSUFFICIENT_EVIDENCE -> INDETERMINATE; final_gold_target=null'
    confidence = 'min severity of the two sealed annotator confidences for agreed records; sealed adjudication confidence for adjudicated records (null where the sealed artifact records none)'
    evidence_locations = 'normalized union of sealed annotator evidence for agreed records; sealed adjudication evidence for adjudicated records'
    calibration_resolved = 'the two calibration disagreements are resolved by frozen protocol addenda (CALLS_V1 macro semantics; Evidence Scope V1 owner ratification) and classified gold_source=adjudicated'
    no_system_prediction = 'this gold set was synthesized without reading results/pilot-candidates.json or any system prediction, resolver, or fidelity artifact'
  }
  counts = [ordered]@{
    by_gold_source = [ordered]@{ agreed_annotation = @($records | Where-Object { $_.gold_source -eq 'agreed_annotation' }).Count; adjudicated = $adjudicatedRecords.Count }
    by_final_gold_verdict = [ordered]@{}
    by_target_status = [ordered]@{}
    target_divergent_cases = @($divergent | ForEach-Object { $_.sample_id })
  }
  frozen_protocol_version = [ordered]@{
    protocols = @($coreProtocols)
    addenda = @('protocol-addendum-calls-v1-macro-semantics.md (FROZEN)', 'protocol-addendum-evidence-scope-v1.md (FROZEN)', 'protocol-addendum-decl-def-equivalence-v1.md (FROZEN)')
    protocol_commit = '12f405c677582a2982d035433bf6837126772716'
  }
  frozen_repository_commits = $frozenCommits
  sealed_input_provenance = $inputProvenance
  records = $records
}
foreach ($k in $verdictDist.Keys) { $goldJson.counts.by_final_gold_verdict[$k] = $verdictDist[$k] }
foreach ($k in $statusDist.Keys) { $goldJson.counts.by_target_status[$k] = $statusDist[$k] }

$goldJsonPath = Join-Path $goldDir 'cpp-structural-relation-gold-v1.json'
Write-Utf8Json $goldJsonPath $goldJson

# markdown report
$md = New-Object Text.StringBuilder
[void]$md.AppendLine('# C/C++ Structural Relation Gold Set V1 - Freeze Report')
[void]$md.AppendLine('')
[void]$md.AppendLine('```text')
[void]$md.AppendLine('status: SEALED_FROZEN')
[void]$md.AppendLine('scope:  CXX_PRIMARY (C/C++ CALLS + IMPORTS)')
[void]$md.AppendLine('```')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Universe reconciliation')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Quantity | Value |')
[void]$md.AppendLine('| --- | ---: |')
[void]$md.AppendLine('| C/C++ Fidelity Universe (frozen sampling frame) | 174 |')
[void]$md.AppendLine('| Gold records total | ' + $total + ' |')
[void]$md.AppendLine('| CALLS Gold | ' + $calls.Count + ' |')
[void]$md.AppendLine('| IMPORTS Gold | ' + $imports.Count + ' |')
[void]$md.AppendLine('| Unique sample_ids | ' + $uniqueIds.Count + ' |')
[void]$md.AppendLine('| Unresolved adjudications | 0 |')
[void]$md.AppendLine('| Python records | 0 |')
[void]$md.AppendLine('| REFERENCES records | 0 |')
[void]$md.AppendLine('')
[void]$md.AppendLine('CALLS (86) + IMPORTS (88) = 174. Matches sampling-frame-correction-v1 (cpp_fidelity=174; stratum C/C++ sums CALLS=86, IMPORTS=88).')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Cohort reconciliation')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Cohort | Total | CALLS | IMPORTS | Agreed | Adjudicated |')
[void]$md.AppendLine('| --- | ---: | ---: | ---: | ---: | ---: |')
foreach ($cohort in @('calibration_01', 'batch_02', 'batch_03', 'batch_04', 'batch_05')) {
  $cr = $cohortRecon[$cohort]
  [void]$md.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} |' -f $cohort, $cr.total, $cr.calls, $cr.imports, $cr.agreed, $cr.adjudicated))
}
[void]$md.AppendLine('')
[void]$md.AppendLine('## Verdict distribution')
[void]$md.AppendLine('')
[void]$md.AppendLine('| final_gold_verdict | n |')
[void]$md.AppendLine('| --- | ---: |')
foreach ($k in ($verdictDist.Keys | Sort-Object)) { [void]$md.AppendLine(('| {0} | {1} |' -f $k, $verdictDist[$k])) }
[void]$md.AppendLine('')
[void]$md.AppendLine('## Target-layer status')
[void]$md.AppendLine('')
[void]$md.AppendLine('| target_status | n |')
[void]$md.AppendLine('| --- | ---: |')
foreach ($k in ($statusDist.Keys | Sort-Object)) { [void]$md.AppendLine(('| {0} | {1} |' -f $k, $statusDist[$k])) }
[void]$md.AppendLine('')
[void]$md.AppendLine(('Target-divergent verdict-agreed cases (acceptable_targets frozen as a set; final_gold_target intentionally null; no adjudication performed at freeze): ' + $divergent.Count))
[void]$md.AppendLine('')
foreach ($d in $divergent) { [void]$md.AppendLine(('- ' + $d.sample_id + ' (' + $d.batch_cohort + ', ' + $d.relation_type + ', acceptable: ' + ((@($d.acceptable_targets) | ForEach-Object { if ($_.path) { $_.path } else { $_.symbol_id } }) -join ' | ') + ')')) }
[void]$md.AppendLine('')
[void]$md.AppendLine('## Relation scope policy')
[void]$md.AppendLine('')
[void]$md.AppendLine('```text')
[void]$md.AppendLine('CALLS      INCLUDED')
[void]$md.AppendLine('IMPORTS    INCLUDED')
[void]$md.AppendLine('REFERENCES NOT EVALUABLE FOR C/C++ (CXX_REFERENCE_RELATION_NOT_MODELED, SFC-1)')
[void]$md.AppendLine('Python     EXCLUDED (95 python_out_of_scope cases)')
[void]$md.AppendLine('```')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Synthesis sources (all sealed)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Input | Role | Verification |')
[void]$md.AppendLine('| --- | --- | --- |')
foreach ($p in $inputProvenance) { [void]$md.AppendLine(('| ' + $p.path + ' | ' + $p.role + ' | ' + $p.verification + ' |')) }
[void]$md.AppendLine('')
[void]$md.AppendLine('## Freeze discipline')
[void]$md.AppendLine('')
[void]$md.AppendLine('- No system prediction, resolver output, or Graph Fidelity artifact was read; `results/pilot-candidates.json` was not opened.')
[void]$md.AppendLine('- No sealed annotation record was modified; no new adjudication was performed; every final verdict originates from sealed A/B agreement or a sealed adjudication artifact.')
[void]$md.AppendLine('- This gold set is read-only from this point. The next phase (system-gold join) must join system predictions ON sample_id without modifying any gold record.')
Write-Utf8Text (Join-Path $goldDir 'cpp-structural-relation-gold-v1.md') ($md.ToString() + "`n")

# freeze manifest
$manifest = [ordered]@{
  artifact = 'gold-freeze-manifest-v1'
  gold_artifact = 'cpp-structural-relation-gold-v1'
  status = 'SEALED_FROZEN'
  created = $goldJson.created
  outputs = @(
    [ordered]@{ path = 'cpp-structural-relation-gold-v1.json'; sha256 = (Hash $goldJsonPath) },
    [ordered]@{ path = 'cpp-structural-relation-gold-v1.md'; sha256 = (Hash (Join-Path $goldDir 'cpp-structural-relation-gold-v1.md')) }
  )
  reconciliation = [ordered]@{
    total = $total; unique_sample_ids = $uniqueIds.Count
    calls = $calls.Count; imports = $imports.Count
    arithmetic = '86 + 88 = 174'
    unresolved_adjudications = 0
    python_records = 0; references_records = 0
    cohort_reconciliation = $cohortRecon
    sampling_frame = 'sampling-frame-correction-v1 (cpp_fidelity=174; CALLS 86 / IMPORTS 88 per SFC-1)'
  }
  synthesis_rules = $goldJson.synthesis_rules
  frozen_protocol_version = $goldJson.frozen_protocol_version
  frozen_repository_commits = $frozenCommits
  sealed_input_provenance = $inputProvenance
  counts = $goldJson.counts
  join_phase_prerequisites = [ordered]@{
    gold_modification_forbidden = $true
    join_rule = 'LEFT JOIN system prediction ON sample_id; gold records are read-only'
    system_prediction_access = 'NOW PERMITTED only for the join phase after this seal (gold_sha256 recorded above must be re-verified at join time)'
  }
  builder_role = 'Gold Freeze agent (GLM-5.3-Flash); deterministic synthesis only, no adjudication, no system prediction read'
}
$manifestPath = Join-Path $goldDir 'gold-freeze-manifest.json'
Write-Utf8Json $manifestPath $manifest

$sums = @(
  ('{0}  cpp-structural-relation-gold-v1.json' -f (Hash $goldJsonPath)),
  ('{0}  cpp-structural-relation-gold-v1.md' -f (Hash (Join-Path $goldDir 'cpp-structural-relation-gold-v1.md'))),
  ('{0}  gold-freeze-manifest.json' -f (Hash $manifestPath))
)
Write-Utf8Text (Join-Path $goldDir 'cpp-structural-relation-gold-v1.sha256') (($sums -join "`n") + "`n")

Write-Output 'GOLD SET FROZEN: cpp-structural-relation-gold-v1'
Write-Output ("records: $total (CALLS " + $calls.Count + ' / IMPORTS ' + $imports.Count + '), unique: ' + $uniqueIds.Count)
Write-Output ("agreed: " + @($records | Where-Object { $_.gold_source -eq 'agreed_annotation' }).Count + "  adjudicated: " + $adjudicatedRecords.Count)
Write-Output ("target_status: " + (($statusDist.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', '))
Write-Output ("divergent: " + $divergent.Count + "  unresolved: 0  python: 0  references: 0")
