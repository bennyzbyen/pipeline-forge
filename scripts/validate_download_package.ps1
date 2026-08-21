param(
    [string]$ArchivePath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'site_create\public\downloads\pipeline-forge.zip')
)

$ErrorActionPreference = 'Stop'

$pluginRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$expectedManifestPath = Join-Path $pluginRoot '.codex-plugin\plugin.json'
$expectedManifest = Get-Content -LiteralPath $expectedManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$archivePathResolved = (Resolve-Path -LiteralPath $ArchivePath).Path
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

    & $installerPath -HomeDirectory $homeRoot

    $installedManifest = Join-Path $homeRoot '.codex\plugins\pipeline-forge\.codex-plugin\plugin.json'
    $marketplacePath = Join-Path $homeRoot '.agents\plugins\marketplace.json'
    if (-not (Test-Path -LiteralPath $installedManifest)) {
        throw 'The installer did not copy the plugin manifest.'
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
