param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'site_create\public\downloads')
)

$ErrorActionPreference = 'Stop'

$pluginRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$manifestPath = Join-Path $pluginRoot '.codex-plugin\plugin.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$outputDirectoryPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$archivePath = Join-Path $outputDirectoryPath 'pipeline-forge.zip'
$checksumPath = Join-Path $outputDirectoryPath 'pipeline-forge.zip.sha256'
New-Item -ItemType Directory -Path $outputDirectoryPath -Force | Out-Null

$builderPath = Join-Path $PSScriptRoot 'build_reproducible_zip.py'
& python $builderPath --root $pluginRoot --output $archivePath
if ($LASTEXITCODE -ne 0) {
    throw "Reproducible archive builder failed with exit code $LASTEXITCODE."
}

$checksum = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($checksumPath, "$checksum  pipeline-forge.zip`n", $utf8NoBom)

[PSCustomObject]@{
    Name = $manifest.name
    Version = $manifest.version
    Archive = $archivePath
    Sha256 = $checksum
}
