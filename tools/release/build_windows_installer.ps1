[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("x64", "arm64")]
    [string]$Architecture,

    [Parameter(Mandatory = $true)]
    [string]$Executable,

    [string]$OutputDirectory = "",

    [string]$NsisDirectory = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $PSScriptRoot "..\..\out\installers"
}
if ([string]::IsNullOrWhiteSpace($NsisDirectory)) {
    $NsisDirectory = Join-Path `
        $PSScriptRoot `
        "..\..\artifacts\tools\nsis-3.12"
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$executablePath = (Resolve-Path $Executable).Path
$version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw).Trim()
$makensis = Join-Path $NsisDirectory "makensis.exe"

if (-not (Test-Path -LiteralPath $makensis)) {
    & (Join-Path $PSScriptRoot "bootstrap_nsis.ps1") `
        -Destination $NsisDirectory
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$output = Join-Path (
    (Resolve-Path $OutputDirectory).Path
) "Orkela-Windows-$Architecture-$version-Setup.exe"

Push-Location $root
try {
    & $makensis `
        "/DORKELA_VERSION=$version" `
        "/DORKELA_ARCH=$Architecture" `
        "/DORKELA_SOURCE_EXE=$executablePath" `
        "/DORKELA_OUTPUT_FILE=$output" `
        "packaging\windows\Orkela.nsi"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLower()
[pscustomobject]@{
    path = $output
    bytes = (Get-Item -LiteralPath $output).Length
    sha256 = $hash
    architecture = $Architecture
    version = $version
} | Format-List
