param(
    [string]$ArchivePath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'site_create\public\downloads\pipeline-forge.zip'),
    [string]$ChecksumPath
)

$ErrorActionPreference = 'Stop'

$pluginRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$expectedManifestPath = Join-Path $pluginRoot '.codex-plugin\plugin.json'
$expectedManifest = Get-Content -LiteralPath $expectedManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedSourceRevision = (Get-Content -LiteralPath (Join-Path $pluginRoot 'SOURCE_REVISION') -Raw -Encoding UTF8).Trim()
$archivePathResolved = (Resolve-Path -LiteralPath $ArchivePath).Path
if ([string]::IsNullOrWhiteSpace($ChecksumPath)) {
    $ChecksumPath = Join-Path (Split-Path -Parent $archivePathResolved) 'pipeline-forge.zip.sha256'
}
$checksumPathResolved = (Resolve-Path -LiteralPath $ChecksumPath).Path
$checksumRecord = (Get-Content -LiteralPath $checksumPathResolved -Raw -Encoding UTF8).Trim()
if ($checksumRecord -notmatch '^(?<hash>[0-9a-fA-F]{64})\s+\*?pipeline-forge\.zip$') {
    throw "Invalid checksum file format: $checksumPathResolved"
}
$expectedChecksum = $Matches['hash'].ToLowerInvariant()
$actualChecksum = (Get-FileHash -LiteralPath $archivePathResolved -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualChecksum -ne $expectedChecksum) {
    throw "Archive SHA256 mismatch: expected $expectedChecksum, found $actualChecksum"
}
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $temporaryRoot ("pipeline-forge-download-test-{0}" -f [System.Guid]::NewGuid().ToString('N')))
)

if (-not $testRoot.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to create a validation directory outside the system temporary directory.'
}

$extractRoot = Join-Path $testRoot 'extract'

try {
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -LiteralPath $archivePathResolved -DestinationPath $extractRoot

    $packageRoot = Join-Path $extractRoot 'pipeline-forge'
    $installerPath = Join-Path $packageRoot 'install-pipeline-forge.ps1'
    if (-not (Test-Path -LiteralPath $installerPath)) {
        throw 'The download archive is missing install-pipeline-forge.ps1.'
    }
    $sourceRevisionPath = Join-Path $packageRoot 'SOURCE_REVISION'
    if (-not (Test-Path -LiteralPath $sourceRevisionPath)) {
        throw 'The download archive is missing SOURCE_REVISION.'
    }
    $sourceRevision = (Get-Content -LiteralPath $sourceRevisionPath -Raw -Encoding UTF8).Trim()
    if ($sourceRevision -notmatch '^[0-9a-f]{40}$') {
        throw 'The download archive contains an invalid SOURCE_REVISION.'
    }
    if ($sourceRevision -ne $expectedSourceRevision) {
        throw "Archive SOURCE_REVISION '$sourceRevision' does not match '$expectedSourceRevision'."
    }

    $forbiddenPackageEntries = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
        $_.Name -in @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.venv', 'venv', 'env') -or
        (-not $_.PSIsContainer -and $_.Extension.ToLowerInvariant() -in @('.pyc', '.pyo', '.pyd'))
    }
    if ($forbiddenPackageEntries) {
        $forbiddenPaths = ($forbiddenPackageEntries | ForEach-Object {
            [System.IO.Path]::GetRelativePath($packageRoot, $_.FullName)
        }) -join ', '
        throw "The download archive contains generated runtime files: $forbiddenPaths"
    }

    $installerTestPath = Join-Path $PSScriptRoot 'test_installer_transaction.ps1'
    if (-not (Test-Path -LiteralPath $installerTestPath -PathType Leaf)) {
        throw "Installer transaction test is missing: $installerTestPath"
    }
    $installerTest = & $installerTestPath -PackageRoot $packageRoot
    if ($installerTest.Passed -ne 5) {
        throw "Installer transaction test count mismatch: expected 5, found $($installerTest.Passed)."
    }

    Write-Output "PipelineForge $($expectedManifest.version) download archive and Windows setup helper validation passed ($($installerTest.Passed) installer cases)"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
        if ($resolvedTestRoot.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        }
    }
}
