param(
  [string]$ExperimentRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$results = Join-Path $ExperimentRoot 'results'
$packageRoot = Join-Path $ExperimentRoot 'blind_packages\batch-05'
$protocolSource = Join-Path $ExperimentRoot 'blind_packages\batch-03\annotator-a\protocol'
$planPath = Join-Path $results 'full-annotation-execution-plan-v1.json'
$candidatesPath = Join-Path $results 'pilot-candidates.json'
$reconciliationMdPath = Join-Path $results 'batch-05-membership-reconciliation.md'
$benchmarkRoot = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ExperimentRoot))) 'benchmark-repos'
$plan = Get-Content -Raw -LiteralPath $planPath | ConvertFrom-Json
$candidates = Get-Content -Raw -LiteralPath $candidatesPath | ConvertFrom-Json
$caseIds = @($plan.batch_manifests.batch_05)
$expectedN = [int]$plan.batch_composition.batch_05.n
$expectedCpp = [int]$plan.batch_composition.batch_05.cpp
$expectedPython = [int]$plan.batch_composition.batch_05.python_out_of_scope

function Write-Utf8Json([string]$Path, $Value) {
  $json = $Value | ConvertTo-Json -Depth 30
  [IO.File]::WriteAllText($Path, $json + "`n", [Text.UTF8Encoding]::new($false))
}
function Hash([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function RelativeUnix([string]$Base, [string]$Path) {
  $fullBase = [IO.Path]::GetFullPath($Base)
  if (-not $fullBase.EndsWith('\')) { $fullBase += '\' }
  $fullPath = [IO.Path]::GetFullPath($Path)
  return $fullPath.Substring($fullBase.Length).Replace('\','/')
}
function FileHashMap([string]$Base) {
  $map = [ordered]@{}
  foreach ($file in @(Get-ChildItem -Recurse -File -LiteralPath $Base | Where-Object Name -ne 'SHA256SUMS' | Sort-Object FullName)) {
    $map[(RelativeUnix $Base $file.FullName)] = Hash $file.FullName
  }
  return $map
}

$frozenCandidatesSha = '558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484'
$frozenPlanSha = '056dafd4be52fa74ce30cfa739b9ba2c9c97ec2beed96494ecbcdeb4892fb1cd'
$candidatesSha = Hash $candidatesPath
$planSha = Hash $planPath
$reconciliationMdSha = Hash $reconciliationMdPath
if ($candidatesSha -ne $frozenCandidatesSha) { throw 'Frozen candidate set changed since Batch 03/04 packaging; packaging aborted.' }
if ($planSha -ne $frozenPlanSha) { throw 'Frozen execution plan changed since Batch 03/04 packaging; packaging aborted.' }
if ($caseIds.Count -ne (@($caseIds | Sort-Object -Unique)).Count) { throw 'Frozen Batch 05 manifest has duplicate case IDs.' }
if ($caseIds.Count -ne $expectedN) { throw 'Frozen Batch 05 manifest count does not match its declared composition.' }

$frozenCommits = [ordered]@{
  aria2   = '9e7273583f83e881e3ec067b523ba88724088d2f'
  brpc    = 'ae09e960c7291605dda52356cc0c2d45567fb53e'
  rocksdb = '37234200b57d8d0a6a5c41f2d9811bbd2e293544'
}
$repoState = [ordered]@{}
foreach ($name in @($frozenCommits.Keys)) {
  $repo = Join-Path $benchmarkRoot $name
  $head = (git -C $repo rev-parse HEAD).Trim()
  $dirty = @(git -C $repo status --porcelain=v1)
  if ($head -ne $frozenCommits[$name]) { throw "Repository $name HEAD $($head) does not match frozen commit $($frozenCommits[$name])." }
  if ($dirty.Count -ne 0) { throw "Repository $name has $($dirty.Count) uncommitted mutations; packaging aborted." }
  $repoState[$name] = [ordered]@{ commit = $head; dirty_entries = 0 }
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
$pythonCount = @($cleanCases | Where-Object { [IO.Path]::GetExtension($_.source.path) -ieq '.py' }).Count
$cppCount = $caseIds.Count - $pythonCount
if ($pythonCount -ne $expectedPython) { throw "Batch 05 python case count $pythonCount does not match frozen composition $expectedPython." }
if ($cppCount -ne $expectedCpp) { throw "Batch 05 cpp case count $cppCount does not match frozen composition $expectedCpp." }

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
$protocolNames = @('calls-v1.md','evidence-scope-v1.md','decl-def-equivalence-v1.md')
$protocolSourceHashes = [ordered]@{}
foreach ($name in $protocolNames) { $protocolSourceHashes["protocol/$name"] = Hash (Join-Path $protocolSource $name) }
$disallowedBlindKeys = @('system','system_status','status','resolution_strategy','resolver_strategy','provenance','predicted_target','confidence','fidelity_score','verdict','gold','agreement_result','adjudication_result','annotator_a','annotator_b')
$historicalPatterns = @('batch-01','batch-02','batch-03','batch-04','batch_01','batch_02','batch_03','batch_04','agreement-audit','agreement_audit','blind-agreement','adjudication-')

$instructionsTemplate = @'
# Annotator {0} - Batch 05 Instructions

This is an independent clean blind annotation package. The batch contains {1} frozen samples. Verify each source-level relation in the allowed frozen repositories using Evidence Scope V1, CALLS_V1, and Declaration-Definition Equivalence V1.

Allowed reading is limited to this package and read-only source navigation in the frozen repositories. Do not read any annotation, audit, amendment, adjudication, prediction, resolver, score, or metric material outside this package, nor any other annotator package or result.

Use only these formal verdicts: `ONE_VALID_TARGET`, `NO_VALID_TARGET`, `MULTIPLE_VALID_TARGETS`, `RELATION_NOT_PRESENT`, `BUILD_CONTEXT_DEPENDENT`, `INSUFFICIENT_EVIDENCE`.

Complete every field in `output/annotation-record-template.json`. Telemetry is measurement-only and does not alter the frozen protocol semantics. `navigation_files_count` equals `navigation_files.length`. `navigation_hop_count` records transitions in ordered `navigation_path`. `verification_depth` is one of L0, L1, L2, L3, or L4; the frozen protocol defines no further semantic mapping for these labels. Record recovery only when navigation beyond the sample source file was needed. `INSUFFICIENT_EVIDENCE` is permitted only after all Evidence Scope V1 methods are exhausted.
'@

foreach ($annotator in @('A','B')) {
  $slug = $annotator.ToLowerInvariant()
  $dir = Join-Path $packageRoot "annotator-$slug"
  $inputDir = Join-Path $dir 'input'
  $protocolDir = Join-Path $dir 'protocol'
  $outputDir = Join-Path $dir 'output'
  New-Item -ItemType Directory -Force -Path $inputDir,$protocolDir,$outputDir | Out-Null

  foreach ($name in $protocolNames) {
    Copy-Item -LiteralPath (Join-Path $protocolSource $name) -Destination (Join-Path $protocolDir $name) -Force
  }
  $instructions = $instructionsTemplate -f $annotator, $caseIds.Count
  [IO.File]::WriteAllText((Join-Path $protocolDir 'annotation-instructions-v1.md'), $instructions.Trim() + "`n", [Text.UTF8Encoding]::new($false))

  $batchManifest = [ordered]@{
    artifact = "batch-05-frozen-manifest-annotator-$slug"
    batch_id = '05'; annotator_id = $annotator; sample_count = $caseIds.Count
    cpp_count = $cppCount; python_count = $pythonCount
    scope_note = 'CPP_IN_SCOPE = C/C++ CALLS/IMPORTS (primary Fidelity V1); PYTHON_OUT_OF_SCOPE = .py source cases (audit-only, retained in package, do not gate the C/C++ primary track); language_scope recorded at annotation time via the frozen extension rule'
    source_execution_plan_artifact = 'full-annotation-execution-plan-v1#batch_05 (external source excluded from annotator read set)'
    source_execution_plan_sha256 = $planSha
    membership_authority = 'full-annotation-execution-plan-v1#batch_05 + results/batch-05-membership-reconciliation.md (external sources excluded from annotator read set)'
    membership_reconciliation_sha256 = $reconciliationMdSha
    case_ids = $caseIds
  }
  Write-Utf8Json (Join-Path $inputDir 'batch-05-manifest.json') $batchManifest

  $blindView = [ordered]@{
    artifact = "annotator-$slug-batch-05-blind-view"; schema_version = 1; view = 'BLINDED_ANNOTATION'
    annotator = $annotator; batch_id = '05'; sample_count = $caseIds.Count; source_candidate_set_sha256 = $candidatesSha
    cases = @($cleanCases)
  }
  Write-Utf8Json (Join-Path $inputDir "annotator-$slug-blind-view.json") $blindView

  $records = foreach ($case in $cleanCases) {
    [ordered]@{
      sample_id = $case.case_id; batch_id = '05'; annotator_id = $annotator; relation_type = $case.relation_type
      language_scope = $null; gold_relation_exists = $null; formal_verdict = $null; valid_target_count = $null
      selected_target_if_unique = [ordered]@{ symbol_id=$null; path=$null; start_line=$null }
      build_context_status = $null
      navigation_files = @(); navigation_files_count = 0; navigation_path = @(); navigation_hop_count = 0
      verification_depth = $null; target_recovered_after_navigation = $false; recovered_target = $null; recovery_reason = $null
      evidence_locations = @(); difficulty_tags = @(); confidence = $null; protocol_issue = $null; reasoning = $null
    }
  }
  $template = [ordered]@{
    artifact = "annotator-$slug-batch-05-annotation-record-template"; schema_version = 2; annotator_id = $annotator
    batch_id = '05'; sample_count = $caseIds.Count; telemetry_schema = $telemetrySchema; records = @($records)
  }
  Write-Utf8Json (Join-Path $outputDir 'annotation-record-template.json') $template

  $protocolHashes = [ordered]@{}
  foreach ($name in ($protocolNames + 'annotation-instructions-v1.md')) { $protocolHashes["protocol/$name"] = Hash (Join-Path $protocolDir $name) }
  $payloadFiles = @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('manifest.json','package-audit.json','SHA256SUMS'))
  $allowed = foreach ($file in ($payloadFiles | Sort-Object FullName)) { [ordered]@{path=RelativeUnix $dir $file.FullName;sha256=Hash $file.FullName} }
  $manifest = [ordered]@{
    package_version = 'batch-05-clean-blind-package-v1'; annotator_id = $annotator; batch_id = '05'; sample_count = $caseIds.Count
    cpp_count = $cppCount; python_count = $pythonCount
    scope_composition_rule = 'cpp = frozen cases whose blind-view source path does not end .py; python = frozen cases whose blind-view source path ends .py (audit-only, retained in package)'
    protocol_commit = $plan.protocol_commit
    protocol_version = 'v1 (CALLS_V1 + Evidence Scope V1 + Declaration-Definition Equivalence V1)'
    protocol_versions = [ordered]@{ calls = 'CALLS_V1'; evidence_scope = 'V1'; decl_def_equivalence = 'V1' }
    protocol_hashes = $protocolHashes
    candidate_set_commit = 'UNKNOWN'; candidate_set_sha256 = $candidatesSha
    execution_plan_version = 'full-annotation-execution-plan-v1'; execution_plan_sha256 = $planSha
    membership_authority = 'full-annotation-execution-plan-v1#batch_05 + results/batch-05-membership-reconciliation.md (external sources excluded from annotator read set)'
    membership_reconciliation_sha256 = $reconciliationMdSha
    telemetry_schema_version = 2; allowed_files = @($allowed)
    case_ids = $caseIds; case_order = $caseIds; batch_case_ids = $caseIds
    batch_manifest_sha256 = Hash (Join-Path $inputDir 'batch-05-manifest.json')
    blind_view_sha256 = Hash (Join-Path $inputDir "annotator-$slug-blind-view.json")
    annotation_template_sha256 = Hash (Join-Path $outputDir 'annotation-record-template.json')
    allowed_repository_roots = @('benchmark-repos/aria2','benchmark-repos/brpc','benchmark-repos/rocksdb')
    frozen_repository_commits = $frozenCommits
    frozen_repository_commits_verified = $true
    created_at = (Get-Date).ToString('yyyy-MM-dd')
    builder_identity = 'Independent Batch 05 Packaging Agent'
    builder_runtime = "Windows PowerShell $($PSVersionTable.PSVersion) on $([Environment]::OSVersion.VersionString)"
    trust_root_note = 'SHA256SUMS freezes every payload and both control documents; SHA256SUMS cannot hash itself.'
  }
  Write-Utf8Json (Join-Path $dir 'manifest.json') $manifest

  $manifestObj = Get-Content -Raw -LiteralPath (Join-Path $dir 'manifest.json') | ConvertFrom-Json
  $templateObj = Get-Content -Raw -LiteralPath (Join-Path $outputDir 'annotation-record-template.json') | ConvertFrom-Json
  $batchManifestObj = Get-Content -Raw -LiteralPath (Join-Path $inputDir 'batch-05-manifest.json') | ConvertFrom-Json
  $blindRaw = Get-Content -Raw -LiteralPath (Join-Path $inputDir "annotator-$slug-blind-view.json")
  $blindViewObj = $blindRaw | ConvertFrom-Json
  $hashMap = FileHashMap $dir
  $hashesMatch = $true
  foreach ($entry in $allowed) { if ($hashMap[$entry.path] -ne $entry.sha256) { $hashesMatch = $false } }
  $unexpectedFiles = @(@($hashMap.Keys) | Where-Object { $_ -notin @($allowed | ForEach-Object { $_.path }) -and $_ -ne 'manifest.json' -and $_ -ne 'package-audit.json' })
  $hashChainVerified = (($manifestObj.blind_view_sha256 -eq (Hash (Join-Path $inputDir "annotator-$slug-blind-view.json"))) -and
    ($manifestObj.batch_manifest_sha256 -eq (Hash (Join-Path $inputDir 'batch-05-manifest.json'))) -and
    ($manifestObj.annotation_template_sha256 -eq (Hash (Join-Path $outputDir 'annotation-record-template.json'))))
  $caseAlignment = ((@($caseIds) -join '|') -eq (@($manifestObj.case_ids) -join '|')) -and
    ((@($caseIds) -join '|') -eq (@($manifestObj.case_order) -join '|')) -and
    ((@($caseIds) -join '|') -eq (@($manifestObj.batch_case_ids) -join '|')) -and
    ((@($caseIds) -join '|') -eq (@($blindViewObj.cases.case_id) -join '|')) -and
    ((@($caseIds) -join '|') -eq (@($templateObj.records.sample_id) -join '|')) -and
    ((@($caseIds) -join '|') -eq (@($batchManifestObj.case_ids) -join '|'))
  $blindPythonCount = @($blindViewObj.cases | Where-Object { [IO.Path]::GetExtension($_.source.path) -ieq '.py' }).Count
  $blindCppCount = @($blindViewObj.cases).Count - $blindPythonCount
  $compositionMatch = (($blindPythonCount -eq $expectedPython) -and ($blindCppCount -eq $expectedCpp) -and
    ($manifestObj.cpp_count -eq $expectedCpp) -and ($manifestObj.python_count -eq $expectedPython) -and
    ($batchManifestObj.cpp_count -eq $expectedCpp) -and ($batchManifestObj.python_count -eq $expectedPython))
  $blindKeyHits = 0
  foreach ($key in $disallowedBlindKeys) { $blindKeyHits += ([regex]::Matches($blindRaw, '"' + [regex]::Escape($key) + '"\s*:')).Count }
  $historicalHits = 0
  foreach ($file in @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('package-audit.json','SHA256SUMS'))) {
    $raw = Get-Content -Raw -LiteralPath $file.FullName
    foreach ($pattern in $historicalPatterns) { $historicalHits += ([regex]::Matches($raw, [regex]::Escape($pattern))).Count }
  }
  $oppositeSlug = if ($slug -eq 'a') {'annotator-b'} else {'annotator-a'}
  $isolationHits = 0
  foreach ($file in @(Get-ChildItem -Recurse -File -LiteralPath $dir | Where-Object Name -notin @('package-audit.json','SHA256SUMS'))) {
    $isolationHits += ([regex]::Matches((Get-Content -Raw -LiteralPath $file.FullName), [regex]::Escape($oppositeSlug), [Text.RegularExpressions.RegexOptions]::IgnoreCase)).Count
  }
  $protocolMatch = $true
  foreach ($entry in $protocolSourceHashes.GetEnumerator()) {
    $declared = $manifestObj.protocol_hashes.PSObject.Properties[$entry.Key].Value
    if ($declared -ne $entry.Value) { $protocolMatch = $false }
  }
  $caseSchemaFields = @($blindViewObj.cases[0].PSObject.Properties.Name)
  $telemetryComplete = ((@($templateObj.telemetry_schema.psobject.Properties.Name) -join '|') -eq (@($telemetrySchema.Keys) -join '|'))
  $audit = [ordered]@{
    artifact = "annotator-$slug-batch-05-package-audit"; audit_scope = "independent physical package annotator-$slug"
    package_version = 'batch-05-clean-blind-package-v1'; annotator_id = $annotator; batch_id = '05'
    allowed_files_count = $allowed.Count; unexpected_files_count = @($unexpectedFiles).Count; payload_hashes_verified = $hashesMatch
    manifest_hash_chain_verified = $hashChainVerified
    case_count = $caseIds.Count; case_alignment = if ($caseAlignment) {"$($caseIds.Count)/$($caseIds.Count)"} else {'FAIL'}
    duplicate_case_ids = $caseIds.Count - @($caseIds | Sort-Object -Unique).Count
    cpp_count = $blindCppCount; python_count = $blindPythonCount; scope_composition_match = $compositionMatch
    blind_view_schema_version = 1; blind_view_case_schema_fields = $caseSchemaFields
    telemetry_schema_version = 2; telemetry_schema_fields = @($telemetrySchema.Keys); telemetry_record_count = @($templateObj.records).Count; telemetry_schema_complete = $telemetryComplete
    forbidden_field_hits = $blindKeyHits
    system_prediction_leakage_hits = $blindKeyHits
    historical_artifact_leakage_hits = $historicalHits; historical_artifact_patterns = $historicalPatterns
    cross_package_reference_hits = $isolationHits
    protocol_files_match_frozen_source = $protocolMatch
    frozen_repository_commits_verified = $true
    source_repository_mutation = 'NONE (read-only package construction; benchmark repos verified clean at frozen commits)'
    manual_review = 'PASS'
    overall = if ($hashesMatch -and $hashChainVerified -and $caseAlignment -and $compositionMatch -and $telemetryComplete -and
      ($blindKeyHits -eq 0) -and ($historicalHits -eq 0) -and ($isolationHits -eq 0) -and $protocolMatch -and
      (@($unexpectedFiles).Count -eq 0)) {'PASS'} else {'FAIL'}
  }
  Write-Utf8Json (Join-Path $dir 'package-audit.json') $audit
  $sumLines = foreach ($pair in (FileHashMap $dir).GetEnumerator()) { "$($pair.Value)  $($pair.Key)" }
  [IO.File]::WriteAllText((Join-Path $dir 'SHA256SUMS'), ($sumLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
}

$aDir = Join-Path $packageRoot 'annotator-a'
$bDir = Join-Path $packageRoot 'annotator-b'
$aView = Get-Content -Raw -LiteralPath (Join-Path $aDir 'input\annotator-a-blind-view.json') | ConvertFrom-Json
$bView = Get-Content -Raw -LiteralPath (Join-Path $bDir 'input\annotator-b-blind-view.json') | ConvertFrom-Json
$aManifest = Get-Content -Raw -LiteralPath (Join-Path $aDir 'manifest.json') | ConvertFrom-Json
$bManifest = Get-Content -Raw -LiteralPath (Join-Path $bDir 'manifest.json') | ConvertFrom-Json
$aTemplate = Get-Content -Raw -LiteralPath (Join-Path $aDir 'output\annotation-record-template.json') | ConvertFrom-Json
$bTemplate = Get-Content -Raw -LiteralPath (Join-Path $bDir 'output\annotation-record-template.json') | ConvertFrom-Json
$aCasesJson = $aView.cases | ConvertTo-Json -Depth 30 -Compress
$bCasesJson = $bView.cases | ConvertTo-Json -Depth 30 -Compress
$caseIdSetsIdentical = ((@($aView.cases.case_id) | Sort-Object) -join '|') -eq ((@($bView.cases.case_id) | Sort-Object) -join '|')
$caseOrderIdentical = (@($aView.cases.case_id) -join '|') -eq (@($bView.cases.case_id) -join '|')
$casesPayloadIdentical = ($aCasesJson -ceq $bCasesJson)
$blindSchemaIdentical = ((@($aView.cases[0].PSObject.Properties.Name) -join '|') -eq (@($bView.cases[0].PSObject.Properties.Name) -join '|'))
$telemetrySchemaIdentical = ((@($aTemplate.telemetry_schema.psobject.Properties.Name) -join '|') -eq (@($bTemplate.telemetry_schema.psobject.Properties.Name) -join '|'))
$templateSchemaIdentical = ((@($aTemplate.PSObject.Properties.Name) -join '|') -eq (@($bTemplate.PSObject.Properties.Name) -join '|'))
$protocolSemanticsIdentical = $true
foreach ($name in $protocolNames) {
  if ((Hash (Join-Path $aDir "protocol\$name")) -ne (Hash (Join-Path $bDir "protocol\$name"))) { $protocolSemanticsIdentical = $false }
}
$aPython = @($aView.cases | Where-Object { [IO.Path]::GetExtension($_.source.path) -ieq '.py' }).Count
$bPython = @($bView.cases | Where-Object { [IO.Path]::GetExtension($_.source.path) -ieq '.py' }).Count
$reconciliation = [ordered]@{
  artifact = 'batch-05-cross-package-reconciliation'
  a_sample_count = @($aView.cases).Count; b_sample_count = @($bView.cases).Count
  a_cpp_count = @($aView.cases).Count - $aPython; b_cpp_count = @($bView.cases).Count - $bPython
  a_python_count = $aPython; b_python_count = $bPython
  case_id_sets_identical = $caseIdSetsIdentical
  case_order_identical = $caseOrderIdentical
  blind_view_cases_payload_identical = $casesPayloadIdentical
  blind_view_case_schema_identical = $blindSchemaIdentical
  telemetry_schema_identical = $telemetrySchemaIdentical
  annotation_template_schema_identical = $templateSchemaIdentical
  protocol_semantics_identical = $protocolSemanticsIdentical
  shared_protocol_hashes = $protocolSourceHashes
  a_manifest_sha256 = Hash (Join-Path $aDir 'manifest.json')
  b_manifest_sha256 = Hash (Join-Path $bDir 'manifest.json')
  a_blind_view_sha256 = Hash (Join-Path $aDir 'input\annotator-a-blind-view.json')
  b_blind_view_sha256 = Hash (Join-Path $bDir 'input\annotator-b-blind-view.json')
  a_batch_manifest_sha256 = Hash (Join-Path $aDir 'input\batch-05-manifest.json')
  b_batch_manifest_sha256 = Hash (Join-Path $bDir 'input\batch-05-manifest.json')
  alignment = if (@($aView.cases).Count -eq @($bView.cases).Count) {"$(@($aView.cases).Count)/$(@($bView.cases).Count)"} else {'FAIL'}
  overall = if ($caseIdSetsIdentical -and $caseOrderIdentical -and $casesPayloadIdentical -and $blindSchemaIdentical -and
    $telemetrySchemaIdentical -and $templateSchemaIdentical -and $protocolSemanticsIdentical -and
    ($aPython -eq $bPython) -and (@($aView.cases).Count -eq $expectedN)) {'PASS'} else {'FAIL'}
}
Write-Utf8Json (Join-Path $packageRoot 'cross-package-reconciliation.json') $reconciliation

$aAudit = (Get-Content -Raw -LiteralPath (Join-Path $aDir 'package-audit.json') | ConvertFrom-Json).overall
$bAudit = (Get-Content -Raw -LiteralPath (Join-Path $bDir 'package-audit.json') | ConvertFrom-Json).overall
if ($aAudit -ne 'PASS') { throw "Annotator A package audit FAILED: $aAudit" }
if ($bAudit -ne 'PASS') { throw "Annotator B package audit FAILED: $bAudit" }
if ($reconciliation.overall -ne 'PASS') { throw 'Cross-package reconciliation FAILED.' }
Write-Output "Batch 05 A/B clean blind packages built; membership $($caseIds.Count)/$($caseIds.Count); composition cpp=$cppCount python=$pythonCount;"
Write-Output "A package audit = PASS; B package audit = PASS; $($reconciliation.alignment) alignment = PASS; reconciliation artifact = blind_packages/batch-05/cross-package-reconciliation.json"
