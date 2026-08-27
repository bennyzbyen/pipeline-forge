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
$homeRoot = Join-Path $testRoot 'home'

try {
    New-Item -ItemType Directory -Path $extractRoot, $homeRoot -Force | Out-Null
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

    & $installerPath -HomeDirectory $homeRoot

    $installedManifest = Join-Path $homeRoot '.codex\plugins\pipeline-forge\.codex-plugin\plugin.json'
    $installedSourceRevision = Join-Path $homeRoot '.codex\plugins\pipeline-forge\SOURCE_REVISION'
    $marketplacePath = Join-Path $homeRoot '.agents\plugins\marketplace.json'
    if (-not (Test-Path -LiteralPath $installedManifest)) {
        throw 'The installer did not copy the plugin manifest.'
    }
    if (-not (Test-Path -LiteralPath $installedSourceRevision)) {
        throw 'The installer did not copy SOURCE_REVISION.'
    }
    if (-not (Test-Path -LiteralPath $marketplacePath)) {
        throw 'The installer did not create the personal marketplace file.'
    }

    $installedPlugin = Get-Content -LiteralPath $installedManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($installedPlugin.name -ne $expectedManifest.name) {
        throw "Installed plugin name '$($installedPlugin.name)' does not match '$($expectedManifest.name)'."
    }
    if ($installedPlugin.version -ne $expectedManifest.version) {
        throw "Installed plugin version '$($installedPlugin.version)' does not match '$($expectedManifest.version)'."
    }
    $installedRevision = (Get-Content -LiteralPath $installedSourceRevision -Raw -Encoding UTF8).Trim()
    if ($installedRevision -ne $expectedSourceRevision) {
        throw "Installed SOURCE_REVISION '$installedRevision' does not match '$expectedSourceRevision'."
    }

    $marketplace = Get-Content -LiteralPath $marketplacePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $entry = $marketplace.plugins | Where-Object {
        $_.name -eq 'pipeline-forge' -and $_.source.path -eq './.codex/plugins/pipeline-forge'
    }
    if (-not $entry) {
        throw 'The installer did not create the expected PipelineForge marketplace entry.'
    }

    Write-Output "PipelineForge $($installedPlugin.version) download archive and Windows setup helper validation passed"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
        if ($resolvedTestRoot.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        }
    }
}
