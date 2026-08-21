param(
    [string]$HomeDirectory = $HOME
)

$ErrorActionPreference = 'Stop'

$sourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$manifestPath = Join-Path $sourceRoot '.codex-plugin\plugin.json'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'Run this script from the extracted PipelineForge plugin folder.'
}

$homeDirectoryPath = [System.IO.Path]::GetFullPath($HomeDirectory)
$pluginsRoot = [System.IO.Path]::GetFullPath((Join-Path $homeDirectoryPath '.codex\plugins'))
$destinationRoot = [System.IO.Path]::GetFullPath((Join-Path $pluginsRoot 'pipeline-forge'))
$marketplaceDirectory = [System.IO.Path]::GetFullPath((Join-Path $homeDirectoryPath '.agents\plugins'))
$marketplacePath = Join-Path $marketplaceDirectory 'marketplace.json'

if (-not $destinationRoot.StartsWith($pluginsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refusing to install outside the personal Codex plugins directory.'
}

New-Item -ItemType Directory -Path $pluginsRoot -Force | Out-Null

if (-not $sourceRoot.Equals($destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    if (Test-Path -LiteralPath $destinationRoot) {
        $resolvedDestination = [System.IO.Path]::GetFullPath($destinationRoot)
        if (-not $resolvedDestination.StartsWith($pluginsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to replace a plugin directory outside the personal Codex plugins directory.'
        }
        Remove-Item -LiteralPath $resolvedDestination -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceRoot -Destination $destinationRoot -Recurse -Force
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

New-Item -ItemType Directory -Path $marketplaceDirectory -Force | Out-Null

if (Test-Path -LiteralPath $marketplacePath) {
    $marketplace = Get-Content -LiteralPath $marketplacePath -Raw -Encoding UTF8 | ConvertFrom-Json
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

$marketplace | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $marketplacePath -Encoding UTF8

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "PipelineForge $($manifest.version) is ready in your Personal plugin source." -ForegroundColor Green
Write-Host 'Restart the ChatGPT desktop app, open Plugins > Personal, and install PipelineForge.'
Write-Host 'In Codex CLI, enter /plugins after restarting the session.'
