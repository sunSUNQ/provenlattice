param(
    [string]$BenchmarkRoot = "$(Split-Path -Parent $PSScriptRoot)\benchmark-repos"
)

$excluded = '(^|/)(\.git|build|out|dist|target|node_modules|\.cache|third_party|third-party|deps|vendor)(/|$)'
$cExt = @('.c')
$cppExt = @('.cc', '.cpp', '.cxx', '.c++')
$headerExt = @('.h', '.hh', '.hpp', '.hxx', '.inc')
$textExt = @(
    '.c', '.cc', '.cpp', '.cxx', '.c++', '.h', '.hh', '.hpp', '.hxx', '.inc',
    '.m', '.mm', '.s', '.asm', '.py', '.sh', '.bash', '.pl', '.rb', '.go', '.rs',
    '.java', '.cs', '.js', '.jsx', '.ts', '.tsx', '.proto', '.cmake', '.bzl',
    '.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.rst', '.txt'
)

function Measure-CodeLines([string]$Path, [bool]$CStyle) {
    $count = 0
    $blockComment = $false
    try {
        foreach ($line in [System.IO.File]::ReadLines($Path)) {
            $work = $line
            if ($CStyle) {
                while ($true) {
                    if ($blockComment) {
                        $end = $work.IndexOf('*/')
                        if ($end -lt 0) { $work = ''; break }
                        $work = $work.Substring($end + 2)
                        $blockComment = $false
                        continue
                    }
                    $start = $work.IndexOf('/*')
                    $slash = $work.IndexOf('//')
                    if ($slash -ge 0 -and ($start -lt 0 -or $slash -lt $start)) {
                        $work = $work.Substring(0, $slash)
                        break
                    }
                    if ($start -ge 0) {
                        $before = $work.Substring(0, $start)
                        $end = $work.IndexOf('*/', $start + 2)
                        if ($end -ge 0) {
                            $work = $before + ' ' + $work.Substring($end + 2)
                            continue
                        }
                        $work = $before
                        $blockComment = $true
                    }
                    break
                }
            } else {
                $trimmed = $work.TrimStart()
                if ($trimmed.StartsWith('#') -or $trimmed.StartsWith('//')) { $work = '' }
            }
            if (-not [string]::IsNullOrWhiteSpace($work)) { $count++ }
        }
    } catch { }
    return $count
}

$results = @()
foreach ($repo in Get-ChildItem -Directory -LiteralPath $BenchmarkRoot | Sort-Object Name) {
    $tracked = @(git -C $repo.FullName ls-files | Where-Object { $_ -notmatch $excluded })
    $disk = [int64]0
    $cFiles = $cppFiles = $headerFiles = 0
    $cLoc = $cppLoc = $headerLoc = $totalLoc = $includeEdges = 0
    $maxDepth = $srcFiles = $testFiles = 0
    $hasMock = $hasDocs = $false
    $top = [System.Collections.Generic.HashSet[string]]::new()
    $modules = [System.Collections.Generic.HashSet[string]]::new()
    $build = [System.Collections.Generic.HashSet[string]]::new()

    foreach ($relative in $tracked) {
        $normalized = $relative.Replace('\', '/')
        $full = Join-Path $repo.FullName $relative
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
        $disk += (Get-Item -LiteralPath $full).Length
        $parts = $normalized.Split('/')
        $directoryCount = $parts.Count - 1
        if ($directoryCount -gt $maxDepth) { $maxDepth = $directoryCount }
        if ($parts.Count -gt 1 -and -not $parts[0].StartsWith('.')) { [void]$top.Add($parts[0]) }
        if ($normalized -match '^(src|source)/') { $srcFiles++ }
        $name = $parts[-1]
        $inTestTree = $normalized -match '(^|/)(test|tests|unittest|unittests)(/|$)'
        $testNamed = $name -match '(^|[_-])(test|tests)([_\.-]|$)|(_test\.|test_)'
        if ($inTestTree -or $testNamed) { $testFiles++ }
        if ($normalized -match '(^|/)(mock|mocks|stub|stubs)(/|$)|(^|/)[^/]*(mock|stub)[^/]*$') { $hasMock = $true }
        if ($normalized -match '^(doc|docs)/') { $hasDocs = $true }
        if ($directoryCount -gt 0) {
            if ($parts[0] -in @('src', 'source', 'include', 'test', 'tests') -and $directoryCount -gt 1) {
                [void]$modules.Add($parts[0] + '/' + $parts[1])
            } else {
                [void]$modules.Add($parts[0])
            }
        }
        if ($name -match '^(BUILD|BUILD\.bazel|WORKSPACE|WORKSPACE\.bazel|MODULE\.bazel)$' -or $normalized -match '\.bzl$') { [void]$build.Add('Bazel') }
        if ($name -eq 'CMakeLists.txt' -or $normalized -match '\.cmake$') { [void]$build.Add('CMake') }
        if ($name -eq 'meson.build') { [void]$build.Add('Meson') }
        if ($name -match '^(Makefile|GNUmakefile)$' -or $name -eq 'configure.ac') { [void]$build.Add('Make/Autotools') }

        $ext = [System.IO.Path]::GetExtension($name).ToLowerInvariant()
        $isC = $cExt -contains $ext
        $isCpp = $cppExt -contains $ext
        $isHeader = $headerExt -contains $ext
        if ($isC) { $cFiles++ }
        if ($isCpp) { $cppFiles++ }
        if ($isHeader) { $headerFiles++ }
        $knownBuild = $name -match '^(BUILD|BUILD\.bazel|WORKSPACE|WORKSPACE\.bazel|MODULE\.bazel|Makefile|GNUmakefile|CMakeLists\.txt|meson\.build|configure\.ac)$'
        if (($textExt -contains $ext) -or $knownBuild) {
            $loc = Measure-CodeLines $full ($isC -or $isCpp -or $isHeader -or $ext -in @('.m', '.mm'))
            $totalLoc += $loc
            if ($isC) { $cLoc += $loc }
            if ($isCpp) { $cppLoc += $loc }
            if ($isHeader) { $headerLoc += $loc }
        }
        if ($isC -or $isCpp -or $isHeader) {
            try {
                $includeEdges += @(
                    [System.IO.File]::ReadLines($full) |
                        Where-Object { $_ -match '^\s*#\s*include\s*[<"]' }
                ).Count
            } catch { }
        }
    }

    $familyLoc = $cLoc + $cppLoc + $headerLoc
    $familyFiles = $cFiles + $cppFiles + $headerFiles
    $results += [ordered]@{
        repository = $repo.Name
        url = git -C $repo.FullName remote get-url origin
        commit = git -C $repo.FullName rev-parse HEAD
        primary_language = $(if ($cppLoc -gt $cLoc) { 'C++' } else { 'C' })
        disk_size_bytes = $disk
        disk_size_mb = [math]::Round($disk / 1MB, 2)
        total_files = $tracked.Count
        c_files = $cFiles
        cpp_files = $cppFiles
        header_files = $headerFiles
        c_cpp_files = $familyFiles
        c_cpp_loc = $familyLoc
        total_loc = $totalLoc
        c_family_ratio = $(if ($totalLoc) { [math]::Round($familyLoc / $totalLoc, 4) } else { 0 })
        src_files = $srcFiles
        test_files = $testFiles
        directory_depth = $maxDepth
        top_level_modules = @($top | Sort-Object)
        top_level_module_count = $top.Count
        approximate_module_count = $modules.Count
        build_system = @($build | Sort-Object)
        has_tests = ($testFiles -gt 0)
        has_mock = $hasMock
        has_docs = $hasDocs
        average_source_file_loc = $(if ($familyFiles) { [math]::Round($familyLoc / $familyFiles, 1) } else { 0 })
        include_edges = $includeEdges
    }
}

$results | ConvertTo-Json -Depth 5
