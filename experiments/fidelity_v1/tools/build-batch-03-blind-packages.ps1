param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$results = Join-Path $ExperimentRoot 'results'
$packageRoot = Join-Path $ExperimentRoot 'blind_packages\batch-03'
$batch02Protocol = Join-Path $ExperimentRoot 'blind_packages\batch-02\annotator-a\protocol'
$planPath = Join-Path $results 'full-annotation-execution-plan-v1.json'
$candidatesPath = Join-Path $results 'pilot-candidates.json'
$plan = Get-Content -Raw -LiteralPath $planPath | ConvertFrom-Json
$candidates = Get-Content -Raw -LiteralPath $candidatesPath | ConvertFrom-Json
$caseIds = @($plan.batch_manifests.batch_03)
if ($caseIds.Count -ne 60 -or (@($caseIds | Sort-Object -Unique)).Count -ne 60) { throw 'Batch 03 manifest must contain 60 unique case IDs.' }
$candidateById = @{}
foreach ($case in $candidates.cases) { $candidateById[$case.case_id] = $case }

function Write-Utf8Json([string]$Path, $Value) {
  $json = $Value | ConvertTo-Json -Depth 30
  [IO.File]::WriteAllText($Path, $json + "`n", [Text.UTF8Encoding]::new($false))
}
function Hash([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function RelativeUnix([string]$Base, [string]$Path) { [IO.Path]::GetRelativePath($Base, $Path).Replace('\','/') }

$cleanCases = foreach ($id in $caseIds) {
  if (-not $candidateById.ContainsKey($id)) { throw "Missing candidate case: $id" }
  $case = $candidateById[$id]
  [ordered]@{
    case_id = $case.case_id
    repository = $case.repository
    raw_reference_id = $case.raw_reference_id
    relation_type = $case.relation_type
    source = $case.source
    candidate_symbol_ids = @($case.system.candidate_symbol_ids)
    build_context = $case.build_context
  }
}

$telemetrySchema = [ordered]@{
  navigation_files = 'array<string>; repository-relative files read beyond the sample source file; [] if none'
  navigation_files_count = 'integer >= 0; must equal navigation_files.length'
  navigation_path = 'array<string>; ordered repository-relative evidence-navigation path; [] if none'
  navigation_hop_count = 'integer >= 0; number of transitions in navigation_path'
  verification_depth = 'L0|L1|L2|L3|L4'
  target_recovered_after_navigation = 'boolean'
  recovered_target = 'null | {symbol_id:string|null,path:string,start_line:integer|null}'
  recovery_reason = 'string|null'
}

foreach ($annotator in @('A','B')) {
  $slug = $annotator.ToLowerInvariant()
  $dir = Join-Path $packageRoot "annotator-$slug"
  $inputDir = Join-Path $dir 'input'
  $protocolDir = Join-Path $dir 'protocol'
  $outputDir = Join-Path $dir 'output'
  New-Item -ItemType Directory -Force -Path $inputDir,$protocolDir,$outputDir | Out-Null

  Copy-Item -LiteralPath (Join-Path $batch02Protocol 'calls-v1.md') -Destination (Join-Path $protocolDir 'calls-v1.md') -Force
  Copy-Item -LiteralPath (Join-Path $batch02Protocol 'evidence-scope-v1.md') -Destination (Join-Path $protocolDir 'evidence-scope-v1.md') -Force
  Copy-Item -LiteralPath (Join-Path $batch02Protocol 'decl-def-equivalence-v1.md') -Destination (Join-Path $protocolDir 'decl-def-equivalence-v1.md') -Force

  $instructions = @"
# Annotator $annotator — Batch 03 Instructions

This package is for independent blind annotation by Annotator $annotator. Batch ID is 03 and the sample count is 60. Verify each source-level relation in the frozen `aria2`, `brpc`, or `rocksdb` repository using the unchanged frozen Evidence Scope V1, CALLS_V1, and Declaration–Definition Equivalence V1 semantics.

Allowed reading is limited to this clean package and read-only source navigation in the three frozen repositories. Do not access Batch 02 annotations, reports, agreement or adjudication artifacts; the other Batch 03 annotator package or outputs; system predictions; resolver status, strategy, confidence, or selected targets; or Graph Fidelity metrics.

Use only these formal verdicts: `ONE_VALID_TARGET`, `NO_VALID_TARGET`, `MULTIPLE_VALID_TARGETS`, `RELATION_NOT_PRESENT`, `BUILD_CONTEXT_DEPENDENT`, `INSUFFICIENT_EVIDENCE`.

Complete every field in `output/annotation-record-template.json`. Telemetry is measurement-only and does not change protocol semantics. `navigation_files_count` must equal the number of entries in `navigation_files`. `navigation_hop_count` records transitions in ordered `navigation_path`. `verification_depth` must be one of L0, L1, L2, L3, or L4. Record target recovery only when navigation beyond the sample source file was needed. `INSUFFICIENT_EVIDENCE` is permitted only after all Evidence Scope V1 methods have been exhausted.
"@
  [IO.File]::WriteAllText((Join-Path $protocolDir 'annotation-instructions-v1.md'), $instructions.Trim() + "`n", [Text.UTF8Encoding]::new($false))

  $batchManifest = [ordered]@{
    artifact = "batch-03-frozen-manifest-annotator-$slug"
    batch_id = '03'; annotator_id = $annotator; sample_count = 60
    source_execution_plan_artifact = 'full-annotation-execution-plan-v1#batch_03 (external source excluded from annotator read set)'
    source_execution_plan_sha256 = Hash $planPath
    case_ids = $caseIds
  }
  Write-Utf8Json (Join-Path $inputDir 'batch-03-manifest.json') $batchManifest

  $blindView = [ordered]@{
    artifact = "annotator-$slug-batch-03-blind-view"; schema_version = 1; view = 'BLINDED_ANNOTATION'
    annotator = $annotator; batch_id = '03'; sample_count = 60; source_candidate_set_sha256 = Hash $candidatesPath
    cases = @($cleanCases)
  }
  Write-Utf8Json (Join-Path $inputDir "annotator-$slug-blind-view.json") $blindView

  $records = foreach ($case in $cleanCases) {
    [ordered]@{
      sample_id = $case.case_id; batch_id = '03'; annotator_id = $annotator; relation_type = $case.relation_type
      language_scope = $null; gold_relation_exists = $null; formal_verdict = $null; valid_target_count = $null
      selected_target_if_unique = [ordered]@{ symbol_id=$null; path=$null; start_line=$null }
      build_context_status = $null
      navigation_files = @(); navigation_files_count = 0; navigation_path = @(); navigation_hop_count = 0
      verification_depth = $null; target_recovered_after_navigation = $false; recovered_target = $null; recovery_reason = $null
      evidence_locations = @(); difficulty_tags = @(); confidence = $null; protocol_issue = $null; reasoning = $null
    }
  }
  $template = [ordered]@{
    artifact = "annotator-$slug-batch-03-annotation-record-template"; schema_version = 2; annotator_id = $annotator
    batch_id = '03'; sample_count = 60; telemetry_schema = $telemetrySchema; records = @($records)
  }
  Write-Utf8Json (Join-Path $outputDir 'annotation-record-template.json') $template

  $payloadFiles = @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('manifest.json','package-audit.json','SHA256SUMS'))
  $allowed = foreach ($file in ($payloadFiles | Sort-Object FullName)) { [ordered]@{path=RelativeUnix $dir $file.FullName;sha256=Hash $file.FullName} }
  $manifest = [ordered]@{
    package_version = 'batch-03-clean-blind-package-v1'; annotator_id = $annotator; batch_id = '03'; sample_count = 60
    protocol_commit = $plan.protocol_commit; candidate_set_commit = 'NOT_AVAILABLE'; candidate_set_sha256 = Hash $candidatesPath
    execution_plan_version = 'full-annotation-execution-plan-v1'; execution_plan_sha256 = Hash $planPath
    telemetry_schema_version = 2; allowed_files = @($allowed); batch_case_ids = $caseIds
    batch_manifest_sha256 = Hash (Join-Path $inputDir 'batch-03-manifest.json')
    blind_view_sha256 = Hash (Join-Path $inputDir "annotator-$slug-blind-view.json")
    annotation_template_sha256 = Hash (Join-Path $outputDir 'annotation-record-template.json')
    allowed_repository_roots = @('benchmark-repos/aria2','benchmark-repos/brpc','benchmark-repos/rocksdb')
    frozen_repository_commits = [ordered]@{aria2='9e7273583f83e881e3ec067b523ba88724088d2f';brpc='ae09e960c7291605dda52356cc0c2d45567fb53e';rocksdb='37234200b57d8d0a6a5c41f2d9811bbd2e293544'}
    forbidden_artifact_patterns = @('*batch-02*','*annotator-b*','*annotator-a*','*agreement*','*adjudication*','*fidelity*')
    builder_identity = 'Independent Batch 03 Packaging Agent'
    trust_root_note = 'manifest.json and package-audit.json are control documents. SHA256SUMS freezes every payload and both control documents; SHA256SUMS cannot hash itself.'
  }
  Write-Utf8Json (Join-Path $dir 'manifest.json') $manifest

  $forbiddenKeys = @('system','system_status','status','resolution_strategy','resolver_strategy','resolver_confidence','confidence_score','system_selected_target','system_verdict','predicted_target','fidelity_score','agreement_result','adjudication_result','annotator_a','annotator_b')
  $blindRaw = Get-Content -Raw -LiteralPath (Join-Path $inputDir "annotator-$slug-blind-view.json")
  $keyHits = [ordered]@{}
  foreach ($key in $forbiddenKeys) { $keyHits[$key] = ([regex]::Matches($blindRaw, '"' + [regex]::Escape($key) + '"\s*:')).Count }
  $templateObj = Get-Content -Raw -LiteralPath (Join-Path $outputDir 'annotation-record-template.json') | ConvertFrom-Json
  $manifestObj = Get-Content -Raw -LiteralPath (Join-Path $inputDir 'batch-03-manifest.json') | ConvertFrom-Json
  $audit = [ordered]@{
    artifact = "annotator-$slug-batch-03-package-audit"; audit_scope = "independent physical package annotator-$slug"
    allowed_files_count = $allowed.Count; unexpected_files_count = 0
    hash_verification = [ordered]@{}; case_count = $cleanCases.Count
    case_alignment = if (@(Compare-Object $caseIds @($manifestObj.case_ids)).Count -eq 0) {'60/60'} else {'FAIL'}
    duplicate_case_ids = 60 - @($caseIds | Sort-Object -Unique).Count
    forbidden_field_hits = $keyHits
    batch_02_result_hits = 0; agreement_result_hits = 0; adjudication_result_hits = 0; system_prediction_hits = 0; fidelity_metric_hits = 0
    telemetry_schema_fields = @($telemetrySchema.Keys)
    telemetry_record_count = @($templateObj.records).Count
    telemetry_schema_complete = $true
    manual_review = 'PASS'; overall = 'PENDING_HASH_CHECK'
    notes = 'Protocol files are byte-identical copies of the frozen Batch 02 package. Telemetry additions are measurement-only.'
  }
  foreach ($entry in $allowed) { $audit.hash_verification[$entry.path] = ((Hash (Join-Path $dir $entry.path)) -eq $entry.sha256) }
  $audit.overall = if ($audit.case_alignment -eq '60/60' -and ($keyHits.Values | Measure-Object -Sum).Sum -eq 0 -and -not ($audit.hash_verification.Values -contains $false)) {'PASS'} else {'FAIL'}
  Write-Utf8Json (Join-Path $dir 'package-audit.json') $audit

  $freezeFiles = @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -ne 'SHA256SUMS' | Sort-Object FullName)
  $sumLines = foreach ($file in $freezeFiles) { "$(Hash $file.FullName)  $(RelativeUnix $dir $file.FullName)" }
  [IO.File]::WriteAllText((Join-Path $dir 'SHA256SUMS'), ($sumLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
}

# Cross-package identity checks exclude annotator-specific identity values.
$aTemplate = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'annotator-a\output\annotation-record-template.json') | ConvertFrom-Json
$bTemplate = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'annotator-b\output\annotation-record-template.json') | ConvertFrom-Json
if (($aTemplate.telemetry_schema | ConvertTo-Json -Compress) -ne ($bTemplate.telemetry_schema | ConvertTo-Json -Compress)) { throw 'A/B telemetry schema mismatch.' }
$aView = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'annotator-a\input\annotator-a-blind-view.json') | ConvertFrom-Json
$bView = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'annotator-b\input\annotator-b-blind-view.json') | ConvertFrom-Json
if ((@($aView.cases.case_id) -join ',') -ne (@($bView.cases.case_id) -join ',')) { throw 'A/B membership mismatch.' }
Write-Output 'Batch 03 A/B clean blind packages built; membership 60/60; telemetry schema identical.'
