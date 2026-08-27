[CmdletBinding()]
param(
    [string]$HomeDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile),
    [Parameter(DontShow = $true)]
    [ValidateSet('', 'CorruptStagedManifest', 'AfterMarketplaceSwitch')]
    [string]$InternalTestFailurePoint = ''
)

$ErrorActionPreference = 'Stop'

function Test-PathWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $candidatePath = [System.IO.Path]::GetFullPath($Candidate)
    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $parentPrefix = $parentPath + [System.IO.Path]::DirectorySeparatorChar
    return $candidatePath.StartsWith($parentPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Read-PluginIdentity {
    param([Parameter(Mandatory = $true)][string]$PluginRoot)

    $manifestPath = Join-Path $PluginRoot '.codex-plugin\plugin.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Plugin manifest is missing: $manifestPath"
    }

    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Plugin manifest is not valid JSON: $manifestPath. $($_.Exception.Message)"
    }

    if ($manifest.name -ne 'pipeline-forge') {
        throw "Plugin manifest name must be 'pipeline-forge', found '$($manifest.name)'."
    }
    if ([string]::IsNullOrWhiteSpace([string]$manifest.version)) {
        throw 'Plugin manifest version is missing.'
    }

    $sourceRevisionPath = Join-Path $PluginRoot 'SOURCE_REVISION'
    if (-not (Test-Path -LiteralPath $sourceRevisionPath -PathType Leaf)) {
        throw "Plugin SOURCE_REVISION is missing: $sourceRevisionPath"
    }
    $sourceRevision = (Get-Content -LiteralPath $sourceRevisionPath -Raw -Encoding UTF8).Trim()
    if ($sourceRevision -notmatch '^[0-9a-f]{40}$') {
        throw "Plugin SOURCE_REVISION must be a lowercase 40-character Git SHA: $sourceRevisionPath"
    }

    return [PSCustomObject]@{
        Manifest = $manifest
        Version = [string]$manifest.version
        SourceRevision = $sourceRevision
    }
}

function Invoke-InternalTestFailure {
    param([Parameter(Mandatory = $true)][string]$Point)

    if ($InternalTestFailurePoint -eq $Point) {
        throw "Internal installer test failure at $Point."
    }
}

$sourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$sourceIdentity = Read-PluginIdentity -PluginRoot $sourceRoot

$homeDirectoryPath = [System.IO.Path]::GetFullPath($HomeDirectory)
$pluginsRoot = [System.IO.Path]::GetFullPath((Join-Path $homeDirectoryPath '.codex\plugins'))
$destinationRoot = [System.IO.Path]::GetFullPath((Join-Path $pluginsRoot 'pipeline-forge'))
$marketplaceDirectory = [System.IO.Path]::GetFullPath((Join-Path $homeDirectoryPath '.agents\plugins'))
$marketplacePath = [System.IO.Path]::GetFullPath((Join-Path $marketplaceDirectory 'marketplace.json'))

if (-not (Test-PathWithin -Candidate $destinationRoot -Parent $pluginsRoot)) {
    throw 'Refusing to install outside the personal Codex plugins directory.'
}
if (-not (Test-PathWithin -Candidate $marketplacePath -Parent $marketplaceDirectory)) {
    throw 'Refusing to update a marketplace outside the personal plugin directory.'
}

$entry = [PSCustomObject]@{
    name = 'pipeline-forge'
    source = [PSCustomObject]@{
        source = 'local'
        path = './.codex/plugins/pipeline-forge'
    }
    policy = [PSCustomObject]@{
        installation = 'AVAILABLE'
        authentication = 'ON_INSTALL'
    }
    category = 'Productivity'
}

New-Item -ItemType Directory -Path $pluginsRoot, $marketplaceDirectory -Force | Out-Null

$transactionId = [System.Guid]::NewGuid().ToString('N')
$pluginStagingRoot = Join-Path $pluginsRoot ('.pipeline-forge.staging.{0}' -f $transactionId)
$pluginBackupRoot = Join-Path $pluginsRoot ('.pipeline-forge.backup.{0}' -f $transactionId)
$marketplaceStagingPath = Join-Path $marketplaceDirectory ('.marketplace.pipeline-forge.staging.{0}.json' -f $transactionId)
$marketplaceBackupPath = Join-Path $marketplaceDirectory ('.marketplace.pipeline-forge.backup.{0}.json' -f $transactionId)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$destinationExisted = Test-Path -LiteralPath $destinationRoot -PathType Container
$marketplaceExisted = Test-Path -LiteralPath $marketplacePath -PathType Leaf
$marketplaceOriginalBytes = $null
$pluginBackupCreated = $false
$pluginInstalled = $false
$marketplaceBackupCreated = $false
$marketplaceInstalled = $false
$transactionCommitted = $false

try {
    if ($marketplaceExisted) {
        $marketplaceOriginalBytes = [System.IO.File]::ReadAllBytes($marketplacePath)
        try {
            $marketplace = Get-Content -LiteralPath $marketplacePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            throw "Personal marketplace is not valid JSON: $marketplacePath. $($_.Exception.Message)"
        }
        $otherPlugins = @($marketplace.plugins | Where-Object { $_.name -ne 'pipeline-forge' })
        $plugins = @($otherPlugins) + @($entry)
        if ($marketplace.PSObject.Properties.Name -contains 'plugins') {
            $marketplace.plugins = $plugins
        }
        else {
            $marketplace | Add-Member -NotePropertyName plugins -NotePropertyValue $plugins
        }
    }
    else {
        $marketplace = [PSCustomObject]@{
            name = 'personal'
            interface = [PSCustomObject]@{
                displayName = 'Personal'
            }
            plugins = @($entry)
        }
    }

    $marketplaceJson = $marketplace | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($marketplaceStagingPath, $marketplaceJson + [Environment]::NewLine, $utf8NoBom)
    $null = Get-Content -LiteralPath $marketplaceStagingPath -Raw -Encoding UTF8 | ConvertFrom-Json

    Copy-Item -LiteralPath $sourceRoot -Destination $pluginStagingRoot -Recurse -Force
    if ($InternalTestFailurePoint -eq 'CorruptStagedManifest') {
        $stagedManifestPath = Join-Path $pluginStagingRoot '.codex-plugin\plugin.json'
        [System.IO.File]::WriteAllText($stagedManifestPath, '{invalid-json', $utf8NoBom)
    }
    $stagedIdentity = Read-PluginIdentity -PluginRoot $pluginStagingRoot
    if ($stagedIdentity.Version -ne $sourceIdentity.Version -or
        $stagedIdentity.SourceRevision -ne $sourceIdentity.SourceRevision) {
        throw 'Staged plugin identity does not match the source package.'
    }

    if ($destinationExisted) {
        Move-Item -LiteralPath $destinationRoot -Destination $pluginBackupRoot
        $pluginBackupCreated = $true
    }
    Move-Item -LiteralPath $pluginStagingRoot -Destination $destinationRoot
    $pluginInstalled = $true

    if ($marketplaceExisted) {
        $currentMarketplaceBytes = [System.IO.File]::ReadAllBytes($marketplacePath)
        if ([Convert]::ToBase64String($currentMarketplaceBytes) -ne
            [Convert]::ToBase64String($marketplaceOriginalBytes)) {
            throw 'Personal marketplace changed during installation; no marketplace update was applied.'
        }
        [System.IO.File]::Replace(
            $marketplaceStagingPath,
            $marketplacePath,
            $marketplaceBackupPath,
            $true
        )
        $marketplaceBackupCreated = $true
        $marketplaceInstalled = $true
    }
    else {
        Move-Item -LiteralPath $marketplaceStagingPath -Destination $marketplacePath
        $marketplaceInstalled = $true
    }
    Invoke-InternalTestFailure -Point 'AfterMarketplaceSwitch'
    $transactionCommitted = $true
}
catch {
    $installError = $_
    $rollbackErrors = New-Object System.Collections.Generic.List[string]

    try {
        if ($marketplaceInstalled -and (Test-Path -LiteralPath $marketplacePath)) {
            Remove-Item -LiteralPath $marketplacePath -Force
        }
        if ($marketplaceBackupCreated -and (Test-Path -LiteralPath $marketplaceBackupPath)) {
            Move-Item -LiteralPath $marketplaceBackupPath -Destination $marketplacePath
        }
    }
    catch {
        $rollbackErrors.Add("marketplace rollback failed: $($_.Exception.Message)")
    }

    try {
        if ($pluginInstalled -and (Test-Path -LiteralPath $destinationRoot)) {
            Remove-Item -LiteralPath $destinationRoot -Recurse -Force
        }
        if ($pluginBackupCreated -and (Test-Path -LiteralPath $pluginBackupRoot)) {
            Move-Item -LiteralPath $pluginBackupRoot -Destination $destinationRoot
        }
    }
    catch {
        $rollbackErrors.Add("plugin rollback failed: $($_.Exception.Message)")
    }

    foreach ($pendingPath in @($marketplaceStagingPath, $pluginStagingRoot)) {
        try {
            if (Test-Path -LiteralPath $pendingPath) {
                Remove-Item -LiteralPath $pendingPath -Recurse -Force
            }
        }
        catch {
            $rollbackErrors.Add("staging cleanup failed for '$pendingPath': $($_.Exception.Message)")
        }
    }

    if ($rollbackErrors.Count -gt 0) {
        throw "$($installError.Exception.Message) Rollback was incomplete: $($rollbackErrors -join '; ')"
    }
    throw $installError
}
finally {
    if ($transactionCommitted) {
        foreach ($obsoletePath in @($marketplaceBackupPath, $pluginBackupRoot)) {
            if (Test-Path -LiteralPath $obsoletePath) {
                try {
                    Remove-Item -LiteralPath $obsoletePath -Recurse -Force
                }
                catch {
                    Write-Warning "Installation succeeded, but the transaction backup could not be removed: $obsoletePath"
                }
            }
        }
    }
}

Write-Host "PipelineForge $($sourceIdentity.Version) is ready in your Personal plugin source." -ForegroundColor Green
Write-Host 'Restart the ChatGPT desktop app, open Plugins > Personal, and install PipelineForge.'
Write-Host 'In Codex CLI, enter /plugins after restarting the session.'
