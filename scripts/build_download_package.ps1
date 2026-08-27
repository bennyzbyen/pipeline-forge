param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'site_create\public\downloads')
)

$ErrorActionPreference = 'Stop'

$pluginRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$manifestPath = Join-Path $pluginRoot '.codex-plugin\plugin.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$outputDirectoryPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$stagingDirectory = [System.IO.Path]::GetFullPath(
    (Join-Path $temporaryRoot ("pipeline-forge-package-{0}" -f [System.Guid]::NewGuid().ToString('N')))
)

if (-not $stagingDirectory.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to create a staging directory outside the system temporary directory.'
}

$packageRoot = Join-Path $stagingDirectory 'pipeline-forge'
$archivePath = Join-Path $outputDirectoryPath 'pipeline-forge.zip'
$checksumPath = Join-Path $outputDirectoryPath 'pipeline-forge.zip.sha256'
$excludedDirectoryNames = @(
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.venv',
    'venv',
    'env'
)
$excludedFileExtensions = @('.pyc', '.pyo', '.pyd')

function Test-PackagePathExcluded {
    param([string]$RelativePath)

    $normalizedPath = $RelativePath -replace '\\', '/'
    $segments = $normalizedPath -split '/'
    foreach ($segment in $segments) {
        if ($excludedDirectoryNames -contains $segment) {
            return $true
        }
    }

    return $excludedFileExtensions -contains [System.IO.Path]::GetExtension($normalizedPath).ToLowerInvariant()
}

function Copy-PackagePath {
    param([string]$RelativePath)

    $sourcePath = Join-Path $pluginRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Required package path is missing: $RelativePath"
    }

    $sourceItem = Get-Item -LiteralPath $sourcePath
    if (-not $sourceItem.PSIsContainer) {
        Copy-Item -LiteralPath $sourcePath -Destination $packageRoot -Force
        return
    }

    $destinationRoot = Join-Path $packageRoot $RelativePath
    New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null
    Get-ChildItem -LiteralPath $sourcePath -Recurse -Force -File | ForEach-Object {
        $childRelativePath = [System.IO.Path]::GetRelativePath($sourcePath, $_.FullName)
        if (Test-PackagePathExcluded -RelativePath $childRelativePath) {
            return
        }

        $destinationPath = Join-Path $destinationRoot $childRelativePath
        $destinationParent = Split-Path -Parent $destinationPath
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destinationPath -Force
    }
}

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $outputDirectoryPath -Force | Out-Null

    foreach ($relativePath in @(
        'SOURCE_REVISION',
        '.codex-plugin',
        'assets',
        'skills',
        'install-pipeline-forge.ps1',
        'INSTALL.md',
        'LICENSE',
        'CHANGELOG.md',
        'VERSIONING.md',
        'README.md',
        'README.en.md',
        'README.zh-CN.md'
    )) {
        Copy-PackagePath -RelativePath $relativePath
    }

    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }

    Compress-Archive -LiteralPath $packageRoot -DestinationPath $archivePath -CompressionLevel Optimal
    $checksum = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($checksumPath, "$checksum  pipeline-forge.zip`n", $utf8NoBom)

    [PSCustomObject]@{
        Name = $manifest.name
        Version = $manifest.version
        Archive = $archivePath
        Sha256 = $checksum
    }
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        $resolvedStagingDirectory = [System.IO.Path]::GetFullPath($stagingDirectory)
        if ($resolvedStagingDirectory.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedStagingDirectory -Recurse -Force
        }
    }
}
