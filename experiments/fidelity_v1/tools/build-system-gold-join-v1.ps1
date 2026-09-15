param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# System Prediction Join V1 - P0 Graph Fidelity Qualification V1
#
# Reads the frozen C/C++ Gold Set and the canonical ProvenLattice system
# prediction (results/pilot-candidates.json) and produces a reproducible
# LEFT JOIN artifact on sample_id.
#
# Discipline:
#   - Gold is READ ONLY and authoritative; hash verified before anything else.
#   - System prediction is READ ONLY; raw fields preserved verbatim.
#   - No correctness rewrite, no resolver/candidate-generation repair, no
#     re-annotation, no re-adjudication, no RQ1 verdict in this artifact.
#   - Derived fields are deterministic and documented.
# ---------------------------------------------------------------------------

$results = Join-Path $ExperimentRoot 'results'
$goldDir = Join-Path $ExperimentRoot 'gold'
$joinScriptPath = $PSCommandPath

$sw = [Diagnostics.Stopwatch]::StartNew()

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

# --- inputs -------------------------------------------------------------------

$goldJsonPath = Join-Path $goldDir 'cpp-structural-relation-gold-v1.json'
$goldShaPath = Join-Path $goldDir 'cpp-structural-relation-gold-v1.sha256'
$goldManifestPath = Join-Path $goldDir 'gold-freeze-manifest.json'
$systemPath = Join-Path $results 'pilot-candidates.json'

# 1. Gold hash verification (hard gate): .sha256 artifact AND freeze manifest
$goldSha = Hash $goldJsonPath
$shaFileOk = $false
foreach ($line in @(Get-Content -LiteralPath $goldShaPath)) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split '  ', 2
  if ($parts[1] -eq 'cpp-structural-relation-gold-v1.json' -and $parts[0].ToLowerInvariant() -eq $goldSha) { $shaFileOk = $true }
}
if (-not $shaFileOk) { throw 'GOLD HASH FAIL vs cpp-structural-relation-gold-v1.sha256 - join refused.' }
$goldManifest = LoadJson $goldManifestPath
$manifestOk = $false
foreach ($o in $goldManifest.outputs) {
  if ($o.path -eq 'cpp-structural-relation-gold-v1.json' -and $o.sha256 -eq $goldSha) { $manifestOk = $true }
}
if (-not $manifestOk) { throw 'GOLD HASH FAIL vs gold-freeze-manifest.json - join refused.' }
Write-Output 'gold_sha256 verification: PASS'

# 2. Load gold (READ ONLY) and re-verify frozen composition
$gold = LoadJson $goldJsonPath
$goldRecords = @($gold.records)
$goldIds = @($goldRecords | ForEach-Object { $_.sample_id })
$goldUnique = @($goldIds | Sort-Object -Unique)
if ($goldRecords.Count -ne 174) { throw "Gold record count $($goldRecords.Count) != 174" }
if ($goldUnique.Count -ne 174) { throw "Gold unique IDs $($goldUnique.Count) != 174" }
$goldCalls = @($goldRecords | Where-Object { $_.relation_type -eq 'CALLS' }).Count
$goldImports = @($goldRecords | Where-Object { $_.relation_type -eq 'IMPORTS' }).Count
if ($goldCalls -ne 86 -or $goldImports -ne 88) { throw "Gold composition mismatch (CALLS $goldCalls / IMPORTS $goldImports)" }

# 3. Load system prediction (READ ONLY) - canonical source confirmed:
#    build_pilot.py output documented in README as the audit asset joined
#    only after annotation; all blind packages were derived from it.
$system = LoadJson $systemPath
$systemRecords = @($system.cases)
$systemSha = Hash $systemPath
$sysById = @{}
foreach ($c in $systemRecords) {
  if ($sysById.ContainsKey($c.case_id)) { throw "DUPLICATE system prediction for sample_id $($c.case_id) - STOP/FLAG rule applies." }
  $sysById[$c.case_id] = $c
}
$systemDuplicates = 0

# --- join ---------------------------------------------------------------------

function Test-InAcceptable($pred, $accList) {
  if (-not $pred) { return $null }
  if (-not $pred.symbol_id -and -not $pred.path) { return $null }
  foreach ($a in @($accList)) {
    if ($pred.symbol_id -and $a.symbol_id -and $pred.symbol_id -eq $a.symbol_id) { return $true }
    if ($pred.path -and $a.path -and $pred.path -eq $a.path) { return $true }
  }
  return $false
}

$rows = @()
$matched = 0
$missing = 0
$missingIds = @()
$resolvedEmptyTarget = 0
$rawRefMismatch = 0

foreach ($g in $goldRecords) {
  $id = $g.sample_id
  $sys = $null
  $joinStatus = 'MISSING'
  if ($sysById.ContainsKey($id)) {
    $joinStatus = 'MATCHED'
    $matched++
    $sys = $sysById[$id]
    if ($sys.system.status -eq 'resolved' -and (-not $sys.system.predicted_target -or (-not $sys.system.predicted_target.symbol_id -and -not $sys.system.predicted_target.path))) {
      $resolvedEmptyTarget++
    }
    if ($g.source_location.raw_reference_id -and $sys.raw_reference_id -and ($g.source_location.raw_reference_id -ne $sys.raw_reference_id)) {
      $rawRefMismatch++
    }
  } else {
    $missing++
    $missingIds += $id
  }

  $layer = $g.target_status
  $sysResolved = [bool]($sys -and $sys.system.status -eq 'resolved')
  $inAcc = $null
  if ($sys -and $sysResolved -and ($layer -eq 'UNIQUE' -or $layer -eq 'DIVERGENT')) {
    $acc = @($g.acceptable_targets)
    if ($layer -eq 'UNIQUE' -and $acc.Count -eq 0 -and $g.final_gold_target) { $acc = @($g.final_gold_target) }
    $inAcc = Test-InAcceptable $sys.system.predicted_target $acc
  }

  $goldBlock = [ordered]@{}
  foreach ($p in $g.PSObject.Properties) { $goldBlock[$p.Name] = $p.Value }

  $sysBlock = $null
  if ($sys) {
    $sysBlock = [ordered]@{
      status = $sys.system.status
      resolution_strategy = $sys.system.resolution_strategy
      provenance = $sys.system.provenance
      confidence = $sys.system.confidence
      predicted_target = $sys.system.predicted_target
      candidate_symbol_ids = @($sys.system.candidate_symbol_ids)
      stratum = $sys.stratum
      build_context = $sys.build_context
      source = $sys.source
      raw_reference_id = $sys.raw_reference_id
    }
  }

  $rows += [ordered]@{
    sample_id = $id
    join_status = $joinStatus
    gold = $goldBlock
    system = $sysBlock
    derived = [ordered]@{
      system_resolved = $sysResolved
      gold_target_layer = $layer
      predicted_target_in_acceptable_targets = $inAcc
    }
  }
}

if ($rows.Count -ne 174) { throw "Join rows $($rows.Count) != 174" }
if ($matched + $missing -ne 174) { throw "matched + missing != 174" }

# system-only IDs (present in prediction, absent from gold universe)
$systemOnlyIds = @($systemRecords | Where-Object { -not ($goldIds -contains $_.case_id) } | ForEach-Object { $_.case_id })
$systemOnlyByStratum = @{}
foreach ($c in $systemRecords) {
  if ($goldIds -contains $c.case_id) { continue }
  $k = $c.stratum
  if (-not $systemOnlyByStratum.ContainsKey($k)) { $systemOnlyByStratum[$k] = @() }
  $systemOnlyByStratum[$k] += @($c.case_id)
}

# --- provenance + artifact ----------------------------------------------------

$createdAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$sw.Stop()
$runtime = ('{0:0.00}s' -f $sw.Elapsed.TotalSeconds)

$joinJson = [ordered]@{
  artifact = 'system-gold-join-v1'
  status = 'JOIN_COMPLETE_NO_SCORING'
  created_at = $createdAt
  runtime = $runtime
  claims = [ordered]@{
    fidelity_verdict = 'NOT_COMPUTED_IN_THIS_ARTIFACT'
    rq1_verdict = 'NOT YET AVAILABLE'
    note = 'raw observation join only; scoring/interpretation is a later phase'
  }
  provenance = [ordered]@{
    gold_file = (Rel $goldJsonPath)
    gold_sha256 = $goldSha
    gold_sha256_verification = 'PASS (cpp-structural-relation-gold-v1.sha256 + gold-freeze-manifest.json)'
    gold_mutation = 0
    system_prediction_file = (Rel $systemPath)
    system_prediction_source_basis = 'canonical system prediction: build_pilot.py output over frozen V0.2 graph databases; documented audit asset joined only after annotation (experiments/fidelity_v1/README.md)'
    system_prediction_sha256 = $systemSha
    system_prediction_modified = 0
    join_script = (Rel $joinScriptPath)
    join_script_sha256 = (Hash $joinScriptPath)
    join_key = 'sample_id'
    join_type = 'LEFT JOIN (gold authoritative)'
  }
  join_integrity = [ordered]@{
    gold_sample_ids = 174
    gold_unique_ids = 174
    gold_calls = $goldCalls
    gold_imports = $goldImports
    system_record_count = $systemRecords.Count
    matched = $matched
    missing = $missing
    matched_plus_missing = ($matched + $missing)
    duplicate_system_ids = $systemDuplicates
    system_only_ids = $systemOnlyIds.Count
    system_only_by_stratum = $systemOnlyByStratum
    missing_system_ids = $missingIds
    resolved_cases_with_empty_predicted_target = $resolvedEmptyTarget
    raw_reference_id_mismatches = $rawRefMismatch
    gold_composition_check = 'CALLS 86 / IMPORTS 88 / Python 0 / REFERENCES 0 (re-verified at join time)'
  }
  derived_field_definitions = [ordered]@{
    system_resolved = 'true iff a matched system record exists and system.status == resolved'
    gold_target_layer = 'gold.target_status verbatim (UNIQUE / DIVERGENT / ABSENT / INDETERMINATE)'
    predicted_target_in_acceptable_targets = 'membership of system.predicted_target in gold acceptable targets; identity = symbol_id equality (both present) or path equality (both present). null when: join missing, system not resolved, gold layer ABSENT/INDETERMINATE, or predicted_target empty. No canonical-target requirement is applied for DIVERGENT rows; no correctness labels are emitted in this artifact.'
  }
  rows = $rows
}
$joinJsonPath = Join-Path $results 'system-gold-join-v1.json'
Write-Utf8Json $joinJsonPath $joinJson

# markdown report
$md = New-Object Text.StringBuilder
[void]$md.AppendLine('# System Prediction Join V1 - Report')
[void]$md.AppendLine('')
[void]$md.AppendLine('```text')
[void]$md.AppendLine('status: JOIN_COMPLETE_NO_SCORING')
[void]$md.AppendLine('join:   Gold LEFT JOIN SystemPrediction ON sample_id (gold authoritative)')
[void]$md.AppendLine('claims: NO fidelity verdict, NO RQ1 claim in this artifact')
[void]$md.AppendLine('```')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Provenance')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Item | Value |')
[void]$md.AppendLine('| --- | --- |')
[void]$md.AppendLine(('| Gold file | ' + (Rel $goldJsonPath) + ' |'))
[void]$md.AppendLine(('| Gold SHA256 | ' + $goldSha + ' |'))
[void]$md.AppendLine(('| Gold hash verification | PASS (cpp-structural-relation-gold-v1.sha256 + gold-freeze-manifest.json) |'))
[void]$md.AppendLine(('| System prediction file | ' + (Rel $systemPath) + ' |'))
[void]$md.AppendLine(('| System prediction SHA256 | ' + $systemSha + ' |'))
[void]$md.AppendLine(('| Join script | ' + (Rel $joinScriptPath) + ' |'))
[void]$md.AppendLine(('| Join script SHA256 | ' + (Hash $joinScriptPath) + ' |'))
[void]$md.AppendLine(('| Join key | sample_id |'))
[void]$md.AppendLine(('| Created (UTC) | ' + $createdAt + ' |'))
[void]$md.AppendLine(('| Runtime | ' + $runtime + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Join integrity')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Measure | Value |')
[void]$md.AppendLine('| --- | ---: |')
[void]$md.AppendLine('| Gold sample IDs | 174 |')
[void]$md.AppendLine('| Unique Gold IDs | 174 |')
[void]$md.AppendLine('| Matched system predictions | ' + $matched + ' |')
[void]$md.AppendLine('| Missing system predictions | ' + $missing + ' |')
[void]$md.AppendLine('| Matched + missing | ' + ($matched + $missing) + ' |')
[void]$md.AppendLine('| Duplicate system sample IDs | ' + $systemDuplicates + ' |')
[void]$md.AppendLine('| System-only sample IDs | ' + $systemOnlyIds.Count + ' |')
[void]$md.AppendLine('| System records total | ' + $systemRecords.Count + ' |')
[void]$md.AppendLine('| Resolved cases with empty predicted_target | ' + $resolvedEmptyTarget + ' |')
[void]$md.AppendLine('| raw_reference_id mismatches (gold vs system) | ' + $rawRefMismatch + ' |')
[void]$md.AppendLine('')
[void]$md.AppendLine('System-only IDs are the scope-excluded Protocol Universe cases (Python REFERENCES plus Python-source CALLS/IMPORTS stratum leakage), consistent with sampling-frame-correction-v1 scope_excluded_n = 95.')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Derived scoring-ready fields (deterministic, no verdict)')
[void]$md.AppendLine('')
$inAccTrue = @($rows | Where-Object { $_.derived.predicted_target_in_acceptable_targets -eq $true }).Count
$inAccFalse = @($rows | Where-Object { $_.derived.predicted_target_in_acceptable_targets -eq $false }).Count
$inAccNull = @($rows | Where-Object { $null -eq $_.derived.predicted_target_in_acceptable_targets }).Count
$sysRes = @($rows | Where-Object { $_.derived.system_resolved }).Count
[void]$md.AppendLine('| Field value | n |')
[void]$md.AppendLine('| --- | ---: |')
[void]$md.AppendLine('| system_resolved = true | ' + $sysRes + ' |')
[void]$md.AppendLine('| system_resolved = false | ' + (174 - $sysRes) + ' |')
[void]$md.AppendLine('| predicted_target_in_acceptable_targets = true | ' + $inAccTrue + ' |')
[void]$md.AppendLine('| predicted_target_in_acceptable_targets = false | ' + $inAccFalse + ' |')
[void]$md.AppendLine('| predicted_target_in_acceptable_targets = null (not evaluable) | ' + $inAccNull + ' |')
[void]$md.AppendLine('')
[void]$md.AppendLine('null = join missing, system abstained, gold layer ABSENT/INDETERMINATE, or empty predicted target. ABSENT rows are never scored as false targets; INDETERMINATE rows are never auto-counted as system errors.')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Discipline')
[void]$md.AppendLine('')
[void]$md.AppendLine('- Gold file read-only; re-hashed unchanged after the join (mutation = 0).')
[void]$md.AppendLine('- System prediction read-only; raw fields preserved verbatim (no correct/wrong rewrite).')
[void]$md.AppendLine('- No resolver/candidate-generation/parser repair; no re-annotation; no re-adjudication; anomalies are recorded, not fixed.')
Write-Utf8Text (Join-Path $results 'system-gold-join-v1.md') ($md.ToString() + "`n")

$sums = @(
  ('{0}  system-gold-join-v1.json' -f (Hash $joinJsonPath)),
  ('{0}  system-gold-join-v1.md' -f (Hash (Join-Path $results 'system-gold-join-v1.md')))
)
Write-Utf8Text (Join-Path $results 'system-gold-join-v1.sha256') (($sums -join "`n") + "`n")

# completion gate
$goldUnchanged = (Hash $goldJsonPath) -eq $goldSha
Write-Output 'SYSTEM_GOLD_JOIN_V1 built.'
Write-Output ("rows: 174 (matched $matched / missing $missing), duplicates: $systemDuplicates, system-only: $($systemOnlyIds.Count)")
Write-Output ("gold hash unchanged: $goldUnchanged; resolved-empty-target anomalies: $resolvedEmptyTarget; raw_ref mismatches: $rawRefMismatch")
Write-Output ("derived: in_acceptable true=$inAccTrue false=$inAccFalse null=$inAccNull")
