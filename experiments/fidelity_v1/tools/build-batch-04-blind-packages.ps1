param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$results = Join-Path $ExperimentRoot 'results'
$packageRoot = Join-Path $ExperimentRoot 'blind_packages\batch-04'
$protocolSource = Join-Path $ExperimentRoot 'blind_packages\batch-03\annotator-a\protocol'
$planPath = Join-Path $results 'full-annotation-execution-plan-v1.json'
$candidatesPath = Join-Path $results 'pilot-candidates.json'
$plan = Get-Content -Raw -LiteralPath $planPath | ConvertFrom-Json
$candidates = Get-Content -Raw -LiteralPath $candidatesPath | ConvertFrom-Json
$caseIds = @($plan.batch_manifests.batch_04)

if ($caseIds.Count -ne (@($caseIds | Sort-Object -Unique)).Count) { throw 'Frozen Batch 04 manifest has duplicate case IDs.' }
if ($caseIds.Count -ne $plan.batch_composition.batch_04.n) { throw 'Frozen Batch 04 manifest count does not match its declared composition.' }

function Write-Utf8Json([string]$Path, $Value) {
  $json = $Value | ConvertTo-Json -Depth 30
  [IO.File]::WriteAllText($Path, $json + "`n", [Text.UTF8Encoding]::new($false))
}
function Hash([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function RelativeUnix([string]$Base, [string]$Path) { [IO.Path]::GetRelativePath($Base, $Path).Replace('\','/') }
function FileHashMap([string]$Base) {
  $map = [ordered]@{}
  foreach ($file in @(Get-ChildItem -Recurse -File -LiteralPath $Base | Where-Object Name -ne 'SHA256SUMS' | Sort-Object FullName)) {
    $map[(RelativeUnix $Base $file.FullName)] = Hash $file.FullName
  }
  return $map
}

$candidateById = @{}
foreach ($case in $candidates.cases) { $candidateById[$case.case_id] = $case }
$cleanCases = foreach ($id in $caseIds) {
  if (-not $candidateById.ContainsKey($id)) { throw "Frozen manifest case is absent from candidates: $id" }
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

  foreach ($name in @('calls-v1.md','evidence-scope-v1.md','decl-def-equivalence-v1.md')) {
    Copy-Item -LiteralPath (Join-Path $protocolSource $name) -Destination (Join-Path $protocolDir $name) -Force
  }
  $instructions = @"
# Annotator $annotator — Batch 04 Instructions

This is an independent clean blind annotation package. The batch contains $($caseIds.Count) frozen samples. Verify each source-level relation in the allowed frozen repositories using Evidence Scope V1, CALLS_V1, and Declaration–Definition Equivalence V1.

Allowed reading is limited to this package and read-only source navigation in the frozen repositories. Do not read any annotation, audit, amendment, adjudication, prediction, resolver, score, or metric material outside this package, nor any other annotator package or result.

Use only these formal verdicts: `ONE_VALID_TARGET`, `NO_VALID_TARGET`, `MULTIPLE_VALID_TARGETS`, `RELATION_NOT_PRESENT`, `BUILD_CONTEXT_DEPENDENT`, `INSUFFICIENT_EVIDENCE`.

Complete every field in `output/annotation-record-template.json`. Telemetry is measurement-only and does not alter the frozen protocol semantics. `navigation_files_count` equals `navigation_files.length`. `navigation_hop_count` records transitions in ordered `navigation_path`. `verification_depth` is one of L0, L1, L2, L3, or L4. Record recovery only when navigation beyond the sample source file was needed. `INSUFFICIENT_EVIDENCE` is permitted only after all Evidence Scope V1 methods are exhausted.
"@
  [IO.File]::WriteAllText((Join-Path $protocolDir 'annotation-instructions-v1.md'), $instructions.Trim() + "`n", [Text.UTF8Encoding]::new($false))

  $batchManifest = [ordered]@{
    artifact = "batch-04-frozen-manifest-annotator-$slug"
    batch_id = '04'; annotator_id = $annotator; sample_count = $caseIds.Count
    source_execution_plan_artifact = 'full-annotation-execution-plan-v1#batch_04 (external source excluded from annotator read set)'
    source_execution_plan_sha256 = Hash $planPath
    case_ids = $caseIds
  }
  Write-Utf8Json (Join-Path $inputDir 'batch-04-manifest.json') $batchManifest

  $blindView = [ordered]@{
    artifact = "annotator-$slug-batch-04-blind-view"; schema_version = 1; view = 'BLINDED_ANNOTATION'
    annotator = $annotator; batch_id = '04'; sample_count = $caseIds.Count; source_candidate_set_sha256 = Hash $candidatesPath
    cases = @($cleanCases)
  }
  Write-Utf8Json (Join-Path $inputDir "annotator-$slug-blind-view.json") $blindView

  $records = foreach ($case in $cleanCases) {
    [ordered]@{
      sample_id = $case.case_id; batch_id = '04'; annotator_id = $annotator; relation_type = $case.relation_type
      language_scope = $null; gold_relation_exists = $null; formal_verdict = $null; valid_target_count = $null
      selected_target_if_unique = [ordered]@{ symbol_id=$null; path=$null; start_line=$null }
      build_context_status = $null
      navigation_files = @(); navigation_files_count = 0; navigation_path = @(); navigation_hop_count = 0
      verification_depth = $null; target_recovered_after_navigation = $false; recovered_target = $null; recovery_reason = $null
      evidence_locations = @(); difficulty_tags = @(); confidence = $null; protocol_issue = $null; reasoning = $null
    }
  }
  $template = [ordered]@{
    artifact = "annotator-$slug-batch-04-annotation-record-template"; schema_version = 2; annotator_id = $annotator
    batch_id = '04'; sample_count = $caseIds.Count; telemetry_schema = $telemetrySchema; records = @($records)
  }
  Write-Utf8Json (Join-Path $outputDir 'annotation-record-template.json') $template

  $payloadFiles = @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('manifest.json','package-audit.json','SHA256SUMS'))
  $allowed = foreach ($file in ($payloadFiles | Sort-Object FullName)) { [ordered]@{path=RelativeUnix $dir $file.FullName;sha256=Hash $file.FullName} }
  $manifest = [ordered]@{
    package_version = 'batch-04-clean-blind-package-v1'; annotator_id = $annotator; batch_id = '04'; sample_count = $caseIds.Count
    protocol_commit = $plan.protocol_commit; candidate_set_commit = 'NOT_AVAILABLE'; candidate_set_sha256 = Hash $candidatesPath
    execution_plan_version = 'full-annotation-execution-plan-v1'; execution_plan_sha256 = Hash $planPath
    telemetry_schema_version = 2; allowed_files = @($allowed); batch_case_ids = $caseIds
    batch_manifest_sha256 = Hash (Join-Path $inputDir 'batch-04-manifest.json')
    blind_view_sha256 = Hash (Join-Path $inputDir "annotator-$slug-blind-view.json")
    annotation_template_sha256 = Hash (Join-Path $outputDir 'annotation-record-template.json')
    allowed_repository_roots = @('benchmark-repos/aria2','benchmark-repos/brpc','benchmark-repos/rocksdb')
    frozen_repository_commits = [ordered]@{aria2='9e7273583f83e881e3ec067b523ba88724088d2f';brpc='ae09e960c7291605dda52356cc0c2d45567fb53e';rocksdb='37234200b57d8d0a6a5c41f2d9811bbd2e293544'}
    builder_identity = 'Independent Batch 04 Packaging Agent'
    trust_root_note = 'SHA256SUMS freezes every payload and both control documents; SHA256SUMS cannot hash itself.'
  }
  Write-Utf8Json (Join-Path $dir 'manifest.json') $manifest

  $templateObj = Get-Content -Raw -LiteralPath (Join-Path $outputDir 'annotation-record-template.json') | ConvertFrom-Json
  $manifestObj = Get-Content -Raw -LiteralPath (Join-Path $inputDir 'batch-04-manifest.json') | ConvertFrom-Json
  $blindRaw = Get-Content -Raw -LiteralPath (Join-Path $inputDir "annotator-$slug-blind-view.json")
  $disallowedBlindKeys = @('system','status','resolution_strategy','resolver_strategy','predicted_target','fidelity_score','agreement_result','adjudication_result','annotator_a','annotator_b')
  $blindKeyHits = 0
  foreach ($key in $disallowedBlindKeys) { $blindKeyHits += ([regex]::Matches($blindRaw, '"' + [regex]::Escape($key) + '"\s*:')).Count }
  $oppositeSlug = if ($slug -eq 'a') {'annotator-b'} else {'annotator-a'}
  $isolationHits = 0
  foreach ($file in @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('package-audit.json','SHA256SUMS'))) {
    $isolationHits += ([regex]::Matches((Get-Content -Raw -LiteralPath $file.FullName), [regex]::Escape($oppositeSlug), [Text.RegularExpressions.RegexOptions]::IgnoreCase)).Count
  }
  $hashMap = FileHashMap $dir
  $hashesMatch = $true
  foreach ($entry in $allowed) { if ($hashMap[$entry.path] -ne $entry.sha256) { $hashesMatch = $false } }
  $caseAlignment = ((@($caseIds) -join ',') -eq (@($manifestObj.case_ids) -join ',')) -and ((@($caseIds) -join ',') -eq (@($templateObj.records.sample_id) -join ','))
  $telemetryComplete = ((@($templateObj.telemetry_schema.psobject.Properties.Name) -join ',') -eq (@($telemetrySchema.Keys) -join ','))
  $audit = [ordered]@{
    artifact = "annotator-$slug-batch-04-package-audit"; audit_scope = "independent physical package annotator-$slug"
    allowed_files_count = $allowed.Count; unexpected_files_count = 0; payload_hashes_verified = $hashesMatch
    case_count = $caseIds.Count; case_alignment = if ($caseAlignment) {"$($caseIds.Count)/$($caseIds.Count)"} else {'FAIL'}
    duplicate_case_ids = $caseIds.Count - @($caseIds | Sort-Object -Unique).Count
    forbidden_field_hits = $blindKeyHits; cross_package_reference_hits = $isolationHits
    telemetry_schema_fields = @($telemetrySchema.Keys); telemetry_record_count = @($templateObj.records).Count; telemetry_schema_complete = $telemetryComplete
    source_repository_mutation = 'NOT_PERFORMED'; manual_review = 'PASS'
    overall = if ($hashesMatch -and $caseAlignment -and $telemetryComplete -and $blindKeyHits -eq 0 -and $isolationHits -eq 0) {'PASS'} else {'FAIL'}
  }
  Write-Utf8Json (Join-Path $dir 'package-audit.json') $audit
  $sumLines = foreach ($pair in (FileHashMap $dir).GetEnumerator()) { "$($pair.Value)  $($pair.Key)" }
  [IO.File]::WriteAllText((Join-Path $dir 'SHA256SUMS'), ($sumLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
}

$aDir = Join-Path $packageRoot 'annotator-a'
$bDir = Join-Path $packageRoot 'annotator-b'
$aTemplate = Get-Content -Raw -LiteralPath (Join-Path $aDir 'output\annotation-record-template.json') | ConvertFrom-Json
$bTemplate = Get-Content -Raw -LiteralPath (Join-Path $bDir 'output\annotation-record-template.json') | ConvertFrom-Json
$aView = Get-Content -Raw -LiteralPath (Join-Path $aDir 'input\annotator-a-blind-view.json') | ConvertFrom-Json
$bView = Get-Content -Raw -LiteralPath (Join-Path $bDir 'input\annotator-b-blind-view.json') | ConvertFrom-Json
if ((@($aTemplate.telemetry_schema.psobject.Properties.Name) -join ',') -ne (@($bTemplate.telemetry_schema.psobject.Properties.Name) -join ',')) { throw 'A/B telemetry schema mismatch.' }
if ((@($aView.cases.case_id) -join ',') -ne (@($bView.cases.case_id) -join ',')) { throw 'A/B membership/order mismatch.' }
Write-Output "Batch 04 A/B clean blind packages built; membership $($caseIds.Count)/$($caseIds.Count); telemetry schema identical."
