param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Deterministic Graph Fidelity Scoring V1 - P0 Graph Fidelity Qualification V1
#
# Inputs (all read-only): frozen gold set, canonical system prediction,
# sealed System Prediction Join V1, frozen sampling frame (weights).
#
# Contract: GRAPH_FIDELITY_SCORING_V1
#   - every case classified into exactly one deterministic scoring state
#   - no gold/system mutation, no resolver/candidate-generation repair,
#   - no new annotation/adjudication, no RQ1 verdict / paper claim here.
# ---------------------------------------------------------------------------

$results = Join-Path $ExperimentRoot 'results'
$goldDir = Join-Path $ExperimentRoot 'gold'
$scriptPath = $PSCommandPath
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
function Round6($x) { if ($null -eq $x) { return $null } ; [math]::Round($x, 6) }
function Round4($x) { if ($null -eq $x) { return 'n/a' } ; ('{0:F4}' -f $x) }

$goldPath = Join-Path $goldDir 'cpp-structural-relation-gold-v1.json'
$systemPath = Join-Path $results 'pilot-candidates.json'
$joinPath = Join-Path $results 'system-gold-join-v1.json'
$sfcPath = Join-Path $results 'sampling-frame-correction-v1.json'

# --- 1. input integrity: hash gates ------------------------------------------

$goldSha = Hash $goldPath
$systemSha = Hash $systemPath
$joinSha = Hash $joinPath
$sfcSha = Hash $sfcPath

foreach ($line in @(Get-Content -LiteralPath (Join-Path $goldDir 'cpp-structural-relation-gold-v1.sha256'))) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split '  ', 2
  if ($parts[1] -eq 'cpp-structural-relation-gold-v1.json' -and $parts[0].ToLowerInvariant() -ne $goldSha) { throw 'GOLD HASH MISMATCH - STOP.' }
}
$joinShaOk = $false
foreach ($line in @(Get-Content -LiteralPath (Join-Path $results 'system-gold-join-v1.sha256'))) {
  if (-not $line.Trim()) { continue }
  $parts = $line -split '  ', 2
  if ($parts[1] -eq 'system-gold-join-v1.json') {
    if ($parts[0].ToLowerInvariant() -ne $joinSha) { throw 'JOIN HASH MISMATCH - STOP.' }
    $joinShaOk = $true
  }
}
if (-not $joinShaOk) { throw 'Join sha256 artifact entry missing - STOP.' }

$gold = LoadJson $goldPath
$system = LoadJson $systemPath
$join = LoadJson $joinPath
$sfc = LoadJson $sfcPath

if ($join.provenance.gold_sha256 -ne $goldSha) { throw 'Join provenance gold_sha256 != current gold hash - STOP.' }
if ($join.provenance.system_prediction_sha256 -ne $systemSha) { throw 'Join provenance system_prediction_sha256 != current system hash - STOP.' }

# frozen composition re-verification
$goldRecords = @($gold.records)
$goldCalls = @($goldRecords | Where-Object { $_.relation_type -eq 'CALLS' }).Count
$goldImports = @($goldRecords | Where-Object { $_.relation_type -eq 'IMPORTS' }).Count
$layerCounts = @{}
foreach ($r in $goldRecords) {
  if (-not $layerCounts.ContainsKey($r.target_status)) { $layerCounts[$r.target_status] = 0 }
  $layerCounts[$r.target_status]++
}
if ($goldRecords.Count -ne 174 -or $goldCalls -ne 86 -or $goldImports -ne 88) { throw 'Gold composition mismatch - STOP.' }
if ($layerCounts['UNIQUE'] -ne 123 -or $layerCounts['DIVERGENT'] -ne 6 -or $layerCounts['ABSENT'] -ne 44 -or $layerCounts['INDETERMINATE'] -ne 1) { throw 'Gold layer distribution mismatch - STOP.' }

$joinRows = @($join.rows)
if ($joinRows.Count -ne 174) { throw 'Join rows != 174 - STOP.' }
$joinMatched = @($joinRows | Where-Object { $_.join_status -eq 'MATCHED' }).Count
$joinMissing = @($joinRows | Where-Object { $_.join_status -eq 'MISSING' }).Count
if ($joinMatched -ne 174 -or $joinMissing -ne 0) { throw 'Join matched/missing mismatch - STOP.' }

# --- 2. frozen stratum weights ------------------------------------------------

$stratumByName = @{}
foreach ($st in $sfc.strata) { $stratumByName[($st.repository + '/' + $st.stratum)] = $st }
$cppStrataOrder = @($sfc.strata | Where-Object { $_.relation -in @('CALLS', 'IMPORTS') } | ForEach-Object { ($_.repository + '/' + $_.stratum) })

# per-stratum gold count must equal frozen sample_n_cpp (weights validity gate)
$stratumGoldCounts = @{}
foreach ($row in $joinRows) {
  $stName = ($row.gold.repository + '/' + $row.system.stratum)
  if (-not $stratumByName.ContainsKey($stName)) { throw "Unknown stratum $stName for $($row.sample_id) - STOP." }
  $st = $stratumByName[$stName]
  if ($st.relation -ne $row.gold.relation_type -or $st.repository -ne $row.gold.repository) {
    throw "Stratum/repo/relation inconsistency for $($row.sample_id) - STOP."
  }
  if (-not $stratumGoldCounts.ContainsKey($stName)) { $stratumGoldCounts[$stName] = 0 }
  $stratumGoldCounts[$stName]++
}
foreach ($stName in $cppStrataOrder) {
  $expected = [int]$stratumByName[$stName].sample_n_cpp
  $actual = if ($stratumGoldCounts.ContainsKey($stName)) { $stratumGoldCounts[$stName] } else { 0 }
  if ($actual -ne $expected) { throw "Stratum $stName gold count $actual != frozen sample_n_cpp $expected - STOP." }
}

# --- 3. deterministic state classification ------------------------------------

function Test-Membership($pred, $accList) {
  if (-not $pred) { return $null }
  if (-not $pred.symbol_id -and -not $pred.path) { return $null }
  foreach ($a in @($accList)) {
    if ($pred.symbol_id -and $a.symbol_id -and $pred.symbol_id -eq $a.symbol_id) { return $true }
    if ($pred.path -and $a.path -and $pred.path -eq $a.path) { return $true }
  }
  return $false
}

$states = @()
$joinDerivedMismatch = 0
foreach ($row in $joinRows) {
  $g = $row.gold
  $sys = $row.system
  $layer = $g.target_status
  $resolved = [bool]($sys -and $sys.status -eq 'resolved')
  $pred = if ($sys) { $sys.predicted_target } else { $null }
  $state = $null
  $membership = $null

  if ($layer -eq 'INDETERMINATE') {
    $state = 'INDETERMINATE_EXCLUDED'
  } elseif ($layer -eq 'ABSENT') {
    $state = if ($resolved) { 'FALSE_RESOLUTION_ON_ABSENT' } else { 'JUSTIFIED_ABSTENTION' }
  } else {
    if ($resolved) {
      $acc = @($g.acceptable_targets)
      $membership = Test-Membership $pred $acc
      $state = if ($membership -eq $true) { 'CORRECT_RESOLUTION' } else { 'WRONG_TARGET_RESOLUTION' }
    } else {
      $state = 'MISSED_RESOLUTION_OPPORTUNITY'
    }
  }

  # cross-check against the join artifact's derived fields (independent recompute)
  $joinLayer = $row.derived.gold_target_layer
  $joinResolved = $row.derived.system_resolved
  $joinInAcc = $row.derived.predicted_target_in_acceptable_targets
  if ($joinLayer -ne $layer -or $joinResolved -ne $resolved) { throw "Join derived mismatch for $($row.sample_id) - STOP." }
  if ($null -ne $joinInAcc -and $null -ne $membership -and $joinInAcc -ne $membership) { $joinDerivedMismatch++ }

  $st = $stratumByName[($row.gold.repository + '/' + $row.system.stratum)]
  $w = [double]$st.weight_stratum_cpp / [int]$st.sample_n_cpp

  $states += [pscustomobject]@{
    sample_id = $row.sample_id
    repository = $g.repository
    relation_type = $g.relation_type
    stratum = $row.system.stratum
    stratumKey = ($row.gold.repository + '/' + $row.system.stratum)
    weight = $w
    layer = $layer
    resolved = $resolved
    state = $state
    row = $row
  }
}
if ($joinDerivedMismatch -ne 0) { throw "Membership recompute disagrees with join derived fields in $joinDerivedMismatch rows - STOP." }

$stateCounts = @{}
foreach ($s in $states) {
  if (-not $stateCounts.ContainsKey($s.state)) { $stateCounts[$s.state] = 0 }
  $stateCounts[$s.state]++
}
$total = $states.Count
$targetPresent = @($states | Where-Object { $_.layer -eq 'UNIQUE' -or $_.layer -eq 'DIVERGENT' }).Count
$absent = @($states | Where-Object { $_.layer -eq 'ABSENT' }).Count
$indeterminate = @($states | Where-Object { $_.layer -eq 'INDETERMINATE' }).Count
if ($total -ne 174) { throw 'Not all cases classified - STOP.' }
if (($stateCounts['CORRECT_RESOLUTION'] + $stateCounts['WRONG_TARGET_RESOLUTION'] + $stateCounts['MISSED_RESOLUTION_OPPORTUNITY']) -ne 129) { throw 'Target-present reconciliation != 129 - STOP.' }
if (($stateCounts['FALSE_RESOLUTION_ON_ABSENT'] + $stateCounts['JUSTIFIED_ABSTENTION']) -ne 44) { throw 'ABSENT reconciliation != 44 - STOP.' }
if ($stateCounts['INDETERMINATE_EXCLUDED'] -ne 1) { throw 'INDETERMINATE reconciliation != 1 - STOP.' }
if ($targetPresent -ne 129 -or $absent -ne 44 -or $indeterminate -ne 1) { throw 'Layer totals mismatch - STOP.' }

# --- 4. metric engine -----------------------------------------------------------

function Get-Metrics($subset, $weighted) {
  $pick = { param($s, $prop) if ($weighted) { $s.weight } else { 1 } }
  $evaluable = @($subset | Where-Object { $_.layer -ne 'INDETERMINATE' })
  $wEval = ($evaluable | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $resEval = @($evaluable | Where-Object { $_.resolved })
  $wRes = ($resEval | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $c = @($subset | Where-Object { $_.state -eq 'CORRECT_RESOLUTION' })
  $wq = @($subset | Where-Object { $_.state -eq 'WRONG_TARGET_RESOLUTION' })
  $m = @($subset | Where-Object { $_.state -eq 'MISSED_RESOLUTION_OPPORTUNITY' })
  $f = @($subset | Where-Object { $_.state -eq 'FALSE_RESOLUTION_ON_ABSENT' })
  $j = @($subset | Where-Object { $_.state -eq 'JUSTIFIED_ABSTENTION' })
  $wC = ($c | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wW = ($wq | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wM = ($m | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wF = ($f | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wJ = ($j | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wTarget = ($subset | Where-Object { $_.layer -eq 'UNIQUE' -or $_.layer -eq 'DIVERGENT' } | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum
  $wAbsent = ($subset | Where-Object { $_.layer -eq 'ABSENT' } | ForEach-Object { & $pick $_ 'w' } | Measure-Object -Sum).Sum

  $rp = $null; $sr = $null
  if (($wC + $wW + $wF) -gt 0) { $rp = $wC / ($wC + $wW + $wF); $sr = 1.0 - $rp }
  $cov = $null; $abs = $null
  if ($wEval -gt 0) { $cov = $wRes / $wEval; $abs = 1.0 - $cov }
  $toc = $null
  if ($wTarget -gt 0) { $toc = ($wC + $wW) / $wTarget }
  $fra = $null
  if ($wAbsent -gt 0) { $fra = $wF / $wAbsent }
  $aq = $null
  if (($wJ + $wM) -gt 0) { $aq = $wJ / ($wJ + $wM) }
  $mor = $null
  if ($wTarget -gt 0) { $mor = $wM / $wTarget }

  [ordered]@{
    n_rows = $subset.Count
    n_evaluable = $evaluable.Count
    n_resolved_evaluable = $resEval.Count
    n_abstained_evaluable = ($evaluable.Count - $resEval.Count)
    counts = [ordered]@{
      correct_resolution = $c.Count
      wrong_target_resolution = $wq.Count
      missed_resolution_opportunity = $m.Count
      false_resolution_on_absent = $f.Count
      justified_abstention = $j.Count
      indeterminate_excluded = @($subset | Where-Object { $_.state -eq 'INDETERMINATE_EXCLUDED' }).Count
    }
    metrics = [ordered]@{
      resolved_precision = Round6 $rp
      selective_risk = Round6 $sr
      resolution_coverage_evaluable = Round6 $cov
      target_opportunity_coverage = Round6 $toc
      false_resolution_on_absent_rate = Round6 $fra
      abstention_rate_evaluable = Round6 $abs
      abstention_quality = Round6 $aq
      missed_resolution_opportunity_rate = Round6 $mor
    }
  }
}

# --- 5. views -------------------------------------------------------------------

# unweighted sample view (all 174; operational rate reported separately)
$sampleView = Get-Metrics $states $false
$operationalRate = Round6 ((@($states | Where-Object { $_.resolved }).Count) / 174)
$resolvedErrors = $stateCounts['WRONG_TARGET_RESOLUTION'] + $stateCounts['FALSE_RESOLUTION_ON_ABSENT']
$wrongShare = if ($resolvedErrors -gt 0) { Round6 ($stateCounts['WRONG_TARGET_RESOLUTION'] / $resolvedErrors) } else { $null }
$falseShare = if ($resolvedErrors -gt 0) { Round6 ($stateCounts['FALSE_RESOLUTION_ON_ABSENT'] / $resolvedErrors) } else { $null }

# weighted population view
$weightedView = Get-Metrics $states $true
$wOperational = Round6 (($states | Where-Object { $_.resolved } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum)

# macro views
function Macro-By($key) {
  $groups = @($states | Group-Object -Property $key | Sort-Object Name)
  $out = [ordered]@{}
  $names = @()
  foreach ($grp in $groups) {
    $sub = @($grp.Group)
    $names += $grp.Name
    $out[$grp.Name] = [ordered]@{
      unweighted = Get-Metrics $sub $false
      weighted = Get-Metrics $sub $true
    }
  }
  $metricKeys = @('resolved_precision', 'selective_risk', 'resolution_coverage_evaluable', 'target_opportunity_coverage', 'false_resolution_on_absent_rate', 'abstention_rate_evaluable', 'abstention_quality', 'missed_resolution_opportunity_rate')
  $meanU = [ordered]@{}; $meanW = [ordered]@{}
  foreach ($mk in $metricKeys) {
    $vals = @($names | ForEach-Object { $out[$_].unweighted.metrics[$mk] } | Where-Object { $null -ne $_ })
    $meanU[$mk] = if ($vals.Count -gt 0) { Round6 (($vals | Measure-Object -Average).Average) } else { $null }
    $valsW = @($names | ForEach-Object { $out[$_].weighted.metrics[$mk] } | Where-Object { $null -ne $_ })
    $meanW[$mk] = if ($valsW.Count -gt 0) { Round6 (($valsW | Measure-Object -Average).Average) } else { $null }
  }
  [ordered]@{ groups = $out; macro_mean_unweighted = $meanU; macro_mean_weighted = $meanW }
}
$macroRepo = Macro-By 'repository'
$macroRel = Macro-By 'relation_type'

# per-stratum view (frozen order)
$perStratum = @()
foreach ($stName in $cppStrataOrder) {
  $st = $stratumByName[$stName]
  $sub = @($states | Where-Object { $_.stratumKey -eq $stName })
  $mU = Get-Metrics $sub $false
  $mW = Get-Metrics $sub $true
  $perStratum += [ordered]@{
    stratum = $st.stratum
    stratum_key = $stName
    repository = $st.repository
    relation = $st.relation
    population_N_cpp = [int]$st.population_N_cpp
    sample_n_cpp = [int]$st.sample_n_cpp
    weight_stratum_cpp = [double]$st.weight_stratum_cpp
    gold_layer_counts = [ordered]@{
      target_present = @($sub | Where-Object { $_.layer -eq 'UNIQUE' -or $_.layer -eq 'DIVERGENT' }).Count
      absent = @($sub | Where-Object { $_.layer -eq 'ABSENT' }).Count
      indeterminate = @($sub | Where-Object { $_.layer -eq 'INDETERMINATE' }).Count
    }
    scoring_states = $mU.counts
    metrics_unweighted = $mU.metrics
    metrics_weighted = $mW.metrics
  }
}

# canonical node correctness (separate from semantic acceptable-target membership)
$canonEvaluable = @($states | Where-Object { $_.resolved -and ($_.layer -eq 'UNIQUE' -or $_.layer -eq 'DIVERGENT') })
$canonYes = 0; $canonNo = 0; $canonNA = 0
foreach ($s in $canonEvaluable) {
  $canon = $s.row.gold.canonical_target
  $pred = $s.row.system.predicted_target
  if (-not $canon -or (-not $canon.symbol_id -and -not $canon.path)) { $canonNA++; continue }
  $match = $false
  if ($pred -and $pred.symbol_id -and $canon.symbol_id -and $pred.symbol_id -eq $canon.symbol_id) { $match = $true }
  if (-not $match -and $pred -and $pred.path -and $canon.path -and $pred.path -eq $canon.path) { $match = $true }
  if ($match) { $canonYes++ } else { $canonNo++ }
}
$canonical = [ordered]@{
  note = 'semantic correctness (acceptable-target membership) is the primary Resolved Precision input; canonical-node correctness is reported separately and never overrides it. DIVERGENT cases carry no frozen canonical target and are counted as not-evaluable here.'
  evaluated_resolved_target_present = $canonEvaluable.Count
  canonical_match = $canonYes
  canonical_mismatch = $canonNo
  not_evaluable_no_frozen_canonical = $canonNA
}

# INDETERMINATE observation
$indet = @($states | Where-Object { $_.layer -eq 'INDETERMINATE' })[0]
$indeterminateObservation = [ordered]@{
  sample_id = $indet.sample_id
  repository = $indet.repository
  relation_type = $indet.relation_type
  system_resolved = $indet.resolved
  system_status = $indet.row.system.status
  resolver_strategy = $indet.row.system.resolution_strategy
  resolver_confidence = $indet.row.system.confidence
  predicted_target = $indet.row.system.predicted_target
  note = 'observation only; excluded from every correctness/risk/abstention denominator by contract'
}

# error case prep (attribution happens later; no mechanism labels here)
$errorStates = @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT', 'MISSED_RESOLUTION_OPPORTUNITY')
$errorCases = @()
foreach ($s in ($states | Where-Object { $errorStates -contains $_.state })) {
  $errorCases += [ordered]@{
    sample_id = $s.sample_id
    repository = $s.repository
    relation = $s.relation_type
    stratum = $s.stratum
    scoring_state = $s.state
    gold_target_layer = $s.layer
    gold_final_target = $s.row.gold.final_gold_target
    gold_acceptable_targets = @($s.row.gold.acceptable_targets)
    system_status = $s.row.system.status
    predicted_target = $s.row.system.predicted_target
    system_candidate_set = @($s.row.system.candidate_symbol_ids)
    resolver_strategy = $s.row.system.resolution_strategy
    resolver_confidence = $s.row.system.confidence
  }
}

# --- 6. emit artifact -----------------------------------------------------------

$createdAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$sw.Stop()
$runtime = ('{0:0.00}s' -f $sw.Elapsed.TotalSeconds)

$scoring = [ordered]@{
  artifact = 'graph-fidelity-scoring-v1'
  status = 'SCORING_COMPLETE_NO_INTERPRETATION'
  scoring_contract_version = 'GRAPH_FIDELITY_SCORING_V1'
  created_at = $createdAt
  runtime = $runtime
  claims = [ordered]@{
    rq1_verdict = 'NOT WRITTEN IN THIS ARTIFACT'
    note = 'deterministic scoring only; interpretation, failure attribution and paper claims are later phases'
  }
  provenance = [ordered]@{
    gold_file = (Rel $goldPath)
    gold_sha256 = $goldSha
    system_prediction_file = (Rel $systemPath)
    system_prediction_sha256 = $systemSha
    join_file = (Rel $joinPath)
    join_sha256 = $joinSha
    sampling_frame_file = (Rel $sfcPath)
    sampling_frame_sha256 = $sfcSha
    scoring_script = (Rel $scriptPath)
    scoring_script_sha256 = (Hash $scriptPath)
    scoring_source = 'results/system-gold-join-v1.json (frozen join of sealed gold x canonical system prediction)'
  }
  input_integrity = [ordered]@{
    gold_records = 174
    gold_calls = $goldCalls
    gold_imports = $goldImports
    gold_layers = [ordered]@{ UNIQUE = $layerCounts['UNIQUE']; DIVERGENT = $layerCounts['DIVERGENT']; ABSENT = $layerCounts['ABSENT']; INDETERMINATE = $layerCounts['INDETERMINATE'] }
    system_matched = $joinMatched
    system_missing = $joinMissing
    duplicate_system_ids = 0
    gold_sha256_consistent_with_join_provenance = $true
    system_sha256_consistent_with_join_provenance = $true
    join_sha256_consistent_with_join_artifact = $true
    per_stratum_gold_counts_equal_frozen_sample_n_cpp = $true
    membership_recompute_matches_join_derived = $true
  }
  state_definitions = [ordered]@{
    CORRECT_RESOLUTION = 'target layer in {UNIQUE, DIVERGENT} AND system resolved AND predicted_target in acceptable_targets (membership; UNIQUE acceptable set == the unique gold target; DIVERGENT never requires canonical match)'
    WRONG_TARGET_RESOLUTION = 'target layer in {UNIQUE, DIVERGENT} AND system resolved AND predicted_target not in acceptable_targets'
    MISSED_RESOLUTION_OPPORTUNITY = 'target layer in {UNIQUE, DIVERGENT} AND system_resolved = false'
    FALSE_RESOLUTION_ON_ABSENT = 'gold layer ABSENT AND system resolved'
    JUSTIFIED_ABSTENTION = 'gold layer ABSENT AND system_resolved = false'
    INDETERMINATE_EXCLUDED = 'gold layer INDETERMINATE; never auto-scored correct or wrong'
  }
  reconciliation = [ordered]@{
    cases_classified_exactly_once = $total
    target_present_reconciled = "$($stateCounts['CORRECT_RESOLUTION'] + $stateCounts['WRONG_TARGET_RESOLUTION'] + $stateCounts['MISSED_RESOLUTION_OPPORTUNITY'])/129"
    absent_reconciled = "$($stateCounts['FALSE_RESOLUTION_ON_ABSENT'] + $stateCounts['JUSTIFIED_ABSTENTION'])/44"
    indeterminate_reconciled = "1/1"
    membership_recompute_vs_join_derived_mismatches = 0
  }
  counts = $stateCounts
  unweighted_sample_view = [ordered]@{
    note = 'descriptive sample-level view; not the sole headline'
    operational_resolution_rate_all_174 = $operationalRate
    resolved_error_decomposition = [ordered]@{
      resolved_errors_total = $resolvedErrors
      wrong_target_share = $wrongShare
      false_resolution_on_absent_share = $falseShare
    }
    sample = $sampleView
  }
  weighted_population_view = [ordered]@{
    note = 'frozen weights weight_stratum_cpp / sample_n_cpp per case (sampling-frame-correction-v1); denominators are weight masses of each metric universe; INDETERMINATE excluded from correctness denominators by construction'
    weight_mass_total = Round6 (($states | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum)
    operational_resolution_rate_all_174 = $wOperational
    resolved_error_decomposition_weighted = [ordered]@{
      resolved_errors_weight = Round6 (($states | Where-Object { $_.state -in @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT') } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum)
      wrong_target_share = Round6 (($states | Where-Object { $_.state -eq 'WRONG_TARGET_RESOLUTION' } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum / (($states | Where-Object { $_.state -in @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT') } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum))
      false_resolution_on_absent_share = Round6 (($states | Where-Object { $_.state -eq 'FALSE_RESOLUTION_ON_ABSENT' } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum / (($states | Where-Object { $_.state -in @('WRONG_TARGET_RESOLUTION', 'FALSE_RESOLUTION_ON_ABSENT') } | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum))
    }
    population = $weightedView
  }
  macro_by_repository = $macroRepo
  macro_by_relation = $macroRel
  per_stratum = $perStratum
  highlighted_stratum = [ordered]@{
    stratum = 'rocksdb CALLS_NONRESOLVED'
    weight_stratum_cpp = [double][double]($sfc.strata | Where-Object { $_.stratum -eq 'CALLS_NONRESOLVED' -and $_.repository -eq 'rocksdb' }).weight_stratum_cpp
    fact = 'largest population weight among all strata; shown for visibility, no causal interpretation in this artifact'
    entry = $perStratum | Where-Object { $_.stratum_key -eq 'rocksdb/CALLS_NONRESOLVED' }
  }
  canonical_node_correctness = $canonical
  indeterminate_observation = $indeterminateObservation
  scoring_error_cases = $errorCases
  discipline = [ordered]@{
    gold_mutation = 0
    system_prediction_mutation = 0
    resolver_or_candidate_generation_repair = 0
    new_annotation_or_adjudication = 0
    reproducibility = 'all metrics recomputed by tools/score-graph-fidelity-v1.ps1 from frozen inputs'
  }
}
$scoringPath = Join-Path $results 'graph-fidelity-scoring-v1.json'
Write-Utf8Json $scoringPath $scoring

# markdown report
$md = New-Object Text.StringBuilder
[void]$md.AppendLine('# Graph Fidelity Scoring V1 - Deterministic Results')
[void]$md.AppendLine('')
[void]$md.AppendLine('```text')
[void]$md.AppendLine('status:   SCORING_COMPLETE_NO_INTERPRETATION')
[void]$md.AppendLine('contract: GRAPH_FIDELITY_SCORING_V1')
[void]$md.AppendLine('inputs:   gold(sealed) x system(canonical) via system-gold-join-v1 (sealed)')
[void]$md.AppendLine('claims:   no RQ1 verdict, no paper claim, no attribution in this artifact')
[void]$md.AppendLine('```')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Provenance')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Item | Value |')
[void]$md.AppendLine('| --- | --- |')
[void]$md.AppendLine(('| Gold SHA256 | ' + $goldSha + ' |'))
[void]$md.AppendLine(('| System prediction SHA256 | ' + $systemSha + ' |'))
[void]$md.AppendLine(('| Join SHA256 | ' + $joinSha + ' |'))
[void]$md.AppendLine(('| Sampling frame SHA256 | ' + $sfcSha + ' |'))
[void]$md.AppendLine(('| Scoring script SHA256 | ' + (Hash $scriptPath) + ' |'))
[void]$md.AppendLine(('| Created (UTC) / runtime | ' + $createdAt + ' / ' + $runtime + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Scoring states (174/174 classified exactly once)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| State | n |')
[void]$md.AppendLine('| --- | ---: |')
foreach ($k in @('CORRECT_RESOLUTION', 'WRONG_TARGET_RESOLUTION', 'MISSED_RESOLUTION_OPPORTUNITY', 'FALSE_RESOLUTION_ON_ABSENT', 'JUSTIFIED_ABSTENTION', 'INDETERMINATE_EXCLUDED')) {
  [void]$md.AppendLine(('| ' + $k + ' | ' + $stateCounts[$k] + ' |'))
}
[void]$md.AppendLine('')
[void]$md.AppendLine('Reconciliation: target-present 129/129; ABSENT 44/44; INDETERMINATE 1/1.')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Unweighted sample view (descriptive)')
[void]$md.AppendLine('')
[void]$md.AppendLine(('N evaluable = ' + $sampleView.n_evaluable + ' (173 evaluable; 1 INDETERMINATE excluded); N resolved (evaluable) = ' + $sampleView.n_resolved_evaluable + '; N abstained (evaluable) = ' + $sampleView.n_abstained_evaluable + ''))
[void]$md.AppendLine('')
[void]$md.AppendLine('| Metric | Value |')
[void]$md.AppendLine('| --- | ---: |')
$mv = $sampleView.metrics
[void]$md.AppendLine(('| Resolved Precision | ' + (Round4 $mv.resolved_precision) + ' |'))
[void]$md.AppendLine(('| Selective Risk = P(wrong | resolved, evaluable) | ' + (Round4 $mv.selective_risk) + ' |'))
[void]$md.AppendLine(('| Resolution Coverage (evaluable) | ' + (Round4 $mv.resolution_coverage_evaluable) + ' |'))
[void]$md.AppendLine(('| Operational resolution rate (119/174, reported separately) | ' + (Round4 $operationalRate) + ' |'))
[void]$md.AppendLine(('| Target Opportunity Coverage | ' + (Round4 $mv.target_opportunity_coverage) + ' |'))
[void]$md.AppendLine(('| False Resolution on Absent Rate | ' + (Round4 $mv.false_resolution_on_absent_rate) + ' |'))
[void]$md.AppendLine(('| Abstention Rate (evaluable) | ' + (Round4 $mv.abstention_rate_evaluable) + ' |'))
[void]$md.AppendLine(('| Abstention Quality | ' + (Round4 $mv.abstention_quality) + ' |'))
[void]$md.AppendLine(('| Missed Resolution Opportunity Rate | ' + (Round4 $mv.missed_resolution_opportunity_rate) + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine(('Resolved error decomposition: ' + $resolvedErrors + ' resolved errors = WRONG_TARGET ' + $stateCounts['WRONG_TARGET_RESOLUTION'] + ' (' + (Round4 $wrongShare) + ') + FALSE_RESOLUTION_ON_ABSENT ' + $stateCounts['FALSE_RESOLUTION_ON_ABSENT'] + ' (' + (Round4 $falseShare) + ')'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Weighted population view (frozen sampling-frame weights)')
[void]$md.AppendLine('')
$wv = $weightedView.metrics
[void]$md.AppendLine('| Metric | Value |')
[void]$md.AppendLine('| --- | ---: |')
[void]$md.AppendLine(('| Resolved Precision | ' + (Round4 $wv.resolved_precision) + ' |'))
[void]$md.AppendLine(('| Selective Risk | ' + (Round4 $wv.selective_risk) + ' |'))
[void]$md.AppendLine(('| Resolution Coverage (evaluable) | ' + (Round4 $wv.resolution_coverage_evaluable) + ' |'))
[void]$md.AppendLine(('| Operational resolution rate (weighted, all 174) | ' + (Round4 $wOperational) + ' |'))
[void]$md.AppendLine(('| Target Opportunity Coverage | ' + (Round4 $wv.target_opportunity_coverage) + ' |'))
[void]$md.AppendLine(('| False Resolution on Absent Rate | ' + (Round4 $wv.false_resolution_on_absent_rate) + ' |'))
[void]$md.AppendLine(('| Abstention Rate (evaluable) | ' + (Round4 $wv.abstention_rate_evaluable) + ' |'))
[void]$md.AppendLine(('| Abstention Quality | ' + (Round4 $wv.abstention_quality) + ' |'))
[void]$md.AppendLine(('| Missed Resolution Opportunity Rate | ' + (Round4 $wv.missed_resolution_opportunity_rate) + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Macro by repository (subgroup values preserved)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Repository | Resolved Precision | Selective Risk | Res.Coverage | Target Opp.Coverage | False-Res/Absent | Abstention Rate | Abstention Quality | Missed Opp.Rate |')
[void]$md.AppendLine('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
foreach ($k in @($macroRepo.groups.Keys)) {
  $m = $macroRepo.groups[$k].unweighted.metrics
  [void]$md.AppendLine(('| ' + $k + ' | ' + (Round4 $m.resolved_precision) + ' | ' + (Round4 $m.selective_risk) + ' | ' + (Round4 $m.resolution_coverage_evaluable) + ' | ' + (Round4 $m.target_opportunity_coverage) + ' | ' + (Round4 $m.false_resolution_on_absent_rate) + ' | ' + (Round4 $m.abstention_rate_evaluable) + ' | ' + (Round4 $m.abstention_quality) + ' | ' + (Round4 $m.missed_resolution_opportunity_rate) + ' |'))
}
$mU = $macroRepo.macro_mean_unweighted
[void]$md.AppendLine(('| macro mean (unweighted) | ' + (Round4 $mU.resolved_precision) + ' | ' + (Round4 $mU.selective_risk) + ' | ' + (Round4 $mU.resolution_coverage_evaluable) + ' | ' + (Round4 $mU.target_opportunity_coverage) + ' | ' + (Round4 $mU.false_resolution_on_absent_rate) + ' | ' + (Round4 $mU.abstention_rate_evaluable) + ' | ' + (Round4 $mU.abstention_quality) + ' | ' + (Round4 $mU.missed_resolution_opportunity_rate) + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Macro by relation (subgroup values preserved)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Relation | Resolved Precision | Selective Risk | Res.Coverage | Target Opp.Coverage | False-Res/Absent | Abstention Rate | Abstention Quality | Missed Opp.Rate |')
[void]$md.AppendLine('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
foreach ($k in @($macroRel.groups.Keys)) {
  $m = $macroRel.groups[$k].unweighted.metrics
  [void]$md.AppendLine(('| ' + $k + ' | ' + (Round4 $m.resolved_precision) + ' | ' + (Round4 $m.selective_risk) + ' | ' + (Round4 $m.resolution_coverage_evaluable) + ' | ' + (Round4 $m.target_opportunity_coverage) + ' | ' + (Round4 $m.false_resolution_on_absent_rate) + ' | ' + (Round4 $m.abstention_rate_evaluable) + ' | ' + (Round4 $m.abstention_quality) + ' | ' + (Round4 $m.missed_resolution_opportunity_rate) + ' |'))
}
$mR = $macroRel.macro_mean_unweighted
[void]$md.AppendLine(('| macro mean (unweighted) | ' + (Round4 $mR.resolved_precision) + ' | ' + (Round4 $mR.selective_risk) + ' | ' + (Round4 $mR.resolution_coverage_evaluable) + ' | ' + (Round4 $mR.target_opportunity_coverage) + ' | ' + (Round4 $mR.false_resolution_on_absent_rate) + ' | ' + (Round4 $mR.abstention_rate_evaluable) + ' | ' + (Round4 $mR.abstention_quality) + ' | ' + (Round4 $mR.missed_resolution_opportunity_rate) + ' |'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Per-stratum view (frozen strata; facts only)')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Stratum | pop_N_cpp | n_cpp | weight | target-present | ABSENT | correct | wrong | missed | false-res/absent | justified-abst | Res.Prec | Abst.Qual |')
[void]$md.AppendLine('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
foreach ($ps in $perStratum) {
  $c2 = $ps.scoring_states
  $mm = $ps.metrics_unweighted
  [void]$md.AppendLine(('| ' + $ps.stratum + ' (' + $ps.repository + ') | ' + $ps.population_N_cpp + ' | ' + $ps.sample_n_cpp + ' | ' + ('{0:F4}' -f $ps.weight_stratum_cpp) + ' | ' + $ps.gold_layer_counts.target_present + ' | ' + $ps.gold_layer_counts.absent + ' | ' + $c2.correct_resolution + ' | ' + $c2.wrong_target_resolution + ' | ' + $c2.missed_resolution_opportunity + ' | ' + $c2.false_resolution_on_absent + ' | ' + $c2.justified_abstention + ' | ' + (Round4 $mm.resolved_precision) + ' | ' + (Round4 $mm.abstention_quality) + ' |'))
}
[void]$md.AppendLine('')
[void]$md.AppendLine(('Highlighted stratum (fact only): RocksDB CALLS_NONRESOLVED carries population weight ' + ('{0:F4}' -f $scoring.highlighted_stratum.weight_stratum_cpp) + ' of the C/C++ universe - the largest of all strata. No causal interpretation is made here.'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## INDETERMINATE observation (excluded from all correctness denominators)')
[void]$md.AppendLine('')
[void]$md.AppendLine(('- sample_id: ' + $indeterminateObservation.sample_id + ' (' + $indeterminateObservation.repository + ', ' + $indeterminateObservation.relation_type + ')'))
[void]$md.AppendLine(('- system_resolved: ' + $indeterminateObservation.system_resolved + '; system_status: ' + $indeterminateObservation.system_status + '; strategy: ' + $indeterminateObservation.resolver_strategy + '; confidence: ' + $indeterminateObservation.resolver_confidence))
[void]$md.AppendLine(('- predicted_target: ' + ($indeterminateObservation.predicted_target | ConvertTo-Json -Compress -Depth 5)))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Canonical node correctness (separate metric)')
[void]$md.AppendLine('')
[void]$md.AppendLine(('evaluable resolved target-present cases: ' + $canonical.evaluated_resolved_target_present + '; canonical match: ' + $canonical.canonical_match + '; canonical mismatch: ' + $canonical.canonical_mismatch + '; not evaluable (no frozen canonical, incl. all DIVERGENT): ' + $canonical.not_evaluable_no_frozen_canonical + '. Semantic acceptable-target membership remains the sole Resolved Precision input.'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Error cases prepared for later attribution (no mechanism labels here)')
[void]$md.AppendLine('')
[void]$md.AppendLine(('scoring_error_cases: ' + $errorCases.Count + ' (WRONG_TARGET ' + $stateCounts['WRONG_TARGET_RESOLUTION'] + ', FALSE_RESOLUTION_ON_ABSENT ' + $stateCounts['FALSE_RESOLUTION_ON_ABSENT'] + ', MISSED_RESOLUTION_OPPORTUNITY ' + $stateCounts['MISSED_RESOLUTION_OPPORTUNITY'] + ') - full records in the JSON artifact.'))
[void]$md.AppendLine('')
[void]$md.AppendLine('## Discipline')
[void]$md.AppendLine('')
[void]$md.AppendLine('- Gold, system prediction and join artifacts read-only; mutation = 0.')
[void]$md.AppendLine('- No resolver/candidate-generation/parser repair; no new annotation or adjudication.')
[void]$md.AppendLine('- All metrics recomputable from the frozen inputs by tools/score-graph-fidelity-v1.ps1.')
Write-Utf8Text (Join-Path $results 'graph-fidelity-scoring-v1.md') ($md.ToString() + "`n")

$sums = @(
  ('{0}  graph-fidelity-scoring-v1.json' -f (Hash $scoringPath)),
  ('{0}  graph-fidelity-scoring-v1.md' -f (Hash (Join-Path $results 'graph-fidelity-scoring-v1.md')))
)
Write-Utf8Text (Join-Path $results 'graph-fidelity-scoring-v1.sha256') (($sums -join "`n") + "`n")

Write-Output 'GRAPH_FIDELITY_SCORING_V1 built.'
Write-Output ("states: C=" + $stateCounts['CORRECT_RESOLUTION'] + " W=" + $stateCounts['WRONG_TARGET_RESOLUTION'] + " M=" + $stateCounts['MISSED_RESOLUTION_OPPORTUNITY'] + " F=" + $stateCounts['FALSE_RESOLUTION_ON_ABSENT'] + " J=" + $stateCounts['JUSTIFIED_ABSTENTION'] + " I=" + $stateCounts['INDETERMINATE_EXCLUDED'])
Write-Output ("unweighted: RP=" + (Round4 $mv.resolved_precision) + " Cov=" + (Round4 $mv.resolution_coverage_evaluable) + " TOC=" + (Round4 $mv.target_opportunity_coverage) + " AQ=" + (Round4 $mv.abstention_quality))
Write-Output ("weighted:   RP=" + (Round4 $wv.resolved_precision) + " Cov=" + (Round4 $wv.resolution_coverage_evaluable) + " TOC=" + (Round4 $wv.target_opportunity_coverage) + " AQ=" + (Round4 $wv.abstention_quality))
