[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageRoot
)

$ErrorActionPreference = 'Stop'

function Assert-Condition {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function New-LegacyInstallation {
    param(
        [Parameter(Mandatory = $true)][string]$TestHome,
        [Parameter(Mandatory = $true)][string]$MarketplaceJson
    )

    $legacyRoot = Join-Path $TestHome '.codex\plugins\pipeline-forge'
    New-Item -ItemType Directory -Path (Join-Path $legacyRoot '.codex-plugin') -Force | Out-Null
    Write-Utf8NoBom -Path (Join-Path $legacyRoot '.codex-plugin\plugin.json') -Value @'
{
  "name": "pipeline-forge",
  "version": "0.0.1"
}
'@
    Write-Utf8NoBom -Path (Join-Path $legacyRoot 'legacy-marker.txt') -Value 'original-plugin-state'
    Write-Utf8NoBom -Path (Join-Path $TestHome '.agents\plugins\marketplace.json') -Value $MarketplaceJson
}

function Assert-NoTransactionArtifacts {
    param([Parameter(Mandatory = $true)][string]$TestHome)

    $pluginParent = Join-Path $TestHome '.codex\plugins'
    $marketplaceParent = Join-Path $TestHome '.agents\plugins'
    $artifacts = @()
    if (Test-Path -LiteralPath $pluginParent) {
        $artifacts += @(Get-ChildItem -LiteralPath $pluginParent -Force | Where-Object {
            $_.Name -like '.pipeline-forge.staging.*' -or $_.Name -like '.pipeline-forge.backup.*'
        })
    }
    if (Test-Path -LiteralPath $marketplaceParent) {
        $artifacts += @(Get-ChildItem -LiteralPath $marketplaceParent -Force | Where-Object {
            $_.Name -like '.marketplace.pipeline-forge.staging.*' -or
            $_.Name -like '.marketplace.pipeline-forge.backup.*'
        })
    }
    Assert-Condition -Condition ($artifacts.Count -eq 0) -Message 'Installer transaction artifacts were not cleaned up.'
}

function Assert-InstalledIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$TestHome,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion,
        [Parameter(Mandatory = $true)][string]$ExpectedRevision
    )

    $installedRoot = Join-Path $TestHome '.codex\plugins\pipeline-forge'
    $manifestPath = Join-Path $installedRoot '.codex-plugin\plugin.json'
    $revisionPath = Join-Path $installedRoot 'SOURCE_REVISION'
    Assert-Condition -Condition (Test-Path -LiteralPath $manifestPath -PathType Leaf) -Message 'Installed manifest is missing.'
    Assert-Condition -Condition (Test-Path -LiteralPath $revisionPath -PathType Leaf) -Message 'Installed SOURCE_REVISION is missing.'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $revision = (Get-Content -LiteralPath $revisionPath -Raw -Encoding UTF8).Trim()
    Assert-Condition -Condition ($manifest.version -eq $ExpectedVersion) -Message 'Installed version does not match the package.'
    Assert-Condition -Condition ($revision -eq $ExpectedRevision) -Message 'Installed SOURCE_REVISION does not match the package.'
}

function Invoke-ExpectedFailure {
    param(
        [Parameter(Mandatory = $true)][string]$InstallerPath,
        [Parameter(Mandatory = $true)][string]$TestHome,
        [Parameter(Mandatory = $true)][string]$FailurePoint,
        [Parameter(Mandatory = $true)][string]$ExpectedMessage
    )

    $failed = $false
    try {
        & $InstallerPath -HomeDirectory $TestHome -InternalTestFailurePoint $FailurePoint
    }
    catch {
        if ($_.Exception.Message -notlike $ExpectedMessage) {
            throw
        }
        $failed = $true
    }
    Assert-Condition -Condition $failed -Message "Expected installer failure '$FailurePoint' did not occur."
}

$packageRootPath = (Resolve-Path -LiteralPath $PackageRoot).Path
$installerPath = Join-Path $packageRootPath 'install-pipeline-forge.ps1'
$manifestPath = Join-Path $packageRootPath '.codex-plugin\plugin.json'
$sourceRevisionPath = Join-Path $packageRootPath 'SOURCE_REVISION'
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "Installer is missing: $installerPath"
}

$expectedManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedRevision = (Get-Content -LiteralPath $sourceRevisionPath -Raw -Encoding UTF8).Trim()
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $temporaryRoot ("pfi-{0}" -f [System.Guid]::NewGuid().ToString('N').Substring(0, 8)))
)
$temporaryPrefix = $temporaryRoot.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar
if (-not $testRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to create installer tests outside the system temporary directory.'
}

$legacyMarketplace = @'
{
  "name": "personal",
  "interface": {
    "displayName": "Personal",
    "theme": "preserve-me"
  },
  "customTopLevel": {
    "owner": "fixture"
  },
  "plugins": [
    {
      "name": "other-plugin",
      "source": {
        "source": "local",
        "path": "./.codex/plugins/other-plugin"
      },
      "custom": "keep-this-entry"
    },
    {
      "name": "pipeline-forge",
      "source": {
        "source": "local",
        "path": "./old/pipeline-forge"
      }
    }
  ]
}
'@

$results = New-Object System.Collections.Generic.List[string]
try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

    $freshHome = Join-Path $testRoot 'f\h'
    New-Item -ItemType Directory -Path $freshHome -Force | Out-Null
    & $installerPath -HomeDirectory $freshHome
    Assert-InstalledIdentity -TestHome $freshHome -ExpectedVersion $expectedManifest.version -ExpectedRevision $expectedRevision
    $freshMarketplacePath = Join-Path $freshHome '.agents\plugins\marketplace.json'
    $freshMarketplace = Get-Content -LiteralPath $freshMarketplacePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $freshEntries = @($freshMarketplace.plugins | Where-Object { $_.name -eq 'pipeline-forge' })
    Assert-Condition -Condition ($freshEntries.Count -eq 1) -Message 'Fresh install did not create exactly one PipelineForge entry.'
    Assert-NoTransactionArtifacts -TestHome $freshHome
    $results.Add('fresh install')

    $upgradeHome = Join-Path $testRoot 'u\h'
    New-LegacyInstallation -TestHome $upgradeHome -MarketplaceJson $legacyMarketplace
    & $installerPath -HomeDirectory $upgradeHome
    Assert-InstalledIdentity -TestHome $upgradeHome -ExpectedVersion $expectedManifest.version -ExpectedRevision $expectedRevision
    Assert-Condition -Condition (-not (Test-Path -LiteralPath (Join-Path $upgradeHome '.codex\plugins\pipeline-forge\legacy-marker.txt'))) -Message 'Upgrade left content from the old plugin directory.'
    $upgradedMarketplace = Get-Content -LiteralPath (Join-Path $upgradeHome '.agents\plugins\marketplace.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $otherEntry = @($upgradedMarketplace.plugins | Where-Object { $_.name -eq 'other-plugin' })
    $pipelineEntries = @($upgradedMarketplace.plugins | Where-Object { $_.name -eq 'pipeline-forge' })
    Assert-Condition -Condition ($otherEntry.Count -eq 1) -Message 'Upgrade did not preserve the unrelated marketplace entry.'
    Assert-Condition -Condition ($otherEntry[0].custom -eq 'keep-this-entry') -Message 'Upgrade changed an unrelated marketplace entry.'
    Assert-Condition -Condition ($upgradedMarketplace.customTopLevel.owner -eq 'fixture') -Message 'Upgrade changed unrelated top-level marketplace state.'
    Assert-Condition -Condition ($upgradedMarketplace.interface.theme -eq 'preserve-me') -Message 'Upgrade changed unrelated marketplace interface state.'
    Assert-Condition -Condition ($pipelineEntries.Count -eq 1) -Message 'Upgrade did not replace the PipelineForge entry exactly once.'
    Assert-Condition -Condition ($pipelineEntries[0].source.path -eq './.codex/plugins/pipeline-forge') -Message 'Upgrade wrote an unexpected PipelineForge source path.'
    Assert-NoTransactionArtifacts -TestHome $upgradeHome
    $results.Add('upgrade install')
    $results.Add('preserve unrelated marketplace entry')

    $validationHome = Join-Path $testRoot 'v\h'
    New-LegacyInstallation -TestHome $validationHome -MarketplaceJson $legacyMarketplace
    $validationMarketplacePath = Join-Path $validationHome '.agents\plugins\marketplace.json'
    $validationMarketplaceBefore = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($validationMarketplacePath))
    Invoke-ExpectedFailure -InstallerPath $installerPath -TestHome $validationHome -FailurePoint 'CorruptStagedManifest' -ExpectedMessage 'Plugin manifest is not valid JSON:*'
    $validationMarketplaceAfter = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($validationMarketplacePath))
    Assert-Condition -Condition ($validationMarketplaceAfter -eq $validationMarketplaceBefore) -Message 'Staging validation failure changed marketplace bytes.'
    $validationMarker = Get-Content -LiteralPath (Join-Path $validationHome '.codex\plugins\pipeline-forge\legacy-marker.txt') -Raw -Encoding UTF8
    Assert-Condition -Condition ($validationMarker -eq 'original-plugin-state') -Message 'Staging validation failure changed the installed plugin.'
    Assert-NoTransactionArtifacts -TestHome $validationHome
    $results.Add('staging validation rollback')

    $midFailureHome = Join-Path $testRoot 'r\h'
    New-LegacyInstallation -TestHome $midFailureHome -MarketplaceJson $legacyMarketplace
    $midMarketplacePath = Join-Path $midFailureHome '.agents\plugins\marketplace.json'
    $midMarketplaceBefore = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($midMarketplacePath))
    Invoke-ExpectedFailure -InstallerPath $installerPath -TestHome $midFailureHome -FailurePoint 'AfterMarketplaceSwitch' -ExpectedMessage 'Internal installer test failure at AfterMarketplaceSwitch.'
    $midMarketplaceAfter = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($midMarketplacePath))
    Assert-Condition -Condition ($midMarketplaceAfter -eq $midMarketplaceBefore) -Message 'Mid-transaction failure changed marketplace bytes.'
    $midMarker = Get-Content -LiteralPath (Join-Path $midFailureHome '.codex\plugins\pipeline-forge\legacy-marker.txt') -Raw -Encoding UTF8
    Assert-Condition -Condition ($midMarker -eq 'original-plugin-state') -Message 'Mid-transaction failure did not restore the original plugin.'
    Assert-NoTransactionArtifacts -TestHome $midFailureHome
    $results.Add('mid-transaction rollback')

    [PSCustomObject]@{
        PackageRoot = $packageRootPath
        Cases = @($results)
        Passed = $results.Count
    }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
        if ($resolvedTestRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        }
    }
}
