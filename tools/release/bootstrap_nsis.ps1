[CmdletBinding()]
param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path `
        $PSScriptRoot `
        "..\..\artifacts\tools\nsis-3.12"
}

$version = "3.12"
$sha256 = "3bc2b06253a7e4957111be152ac6a536e0c7478a706e19da814038db5d706495"
$url = (
    "https://downloads.sourceforge.net/project/nsis/" +
    "NSIS%203/$version/nsis-$version-setup.exe"
)
$installer = Join-Path ([System.IO.Path]::GetTempPath()) (
    "orkela-nsis-$version-setup.exe"
)

if (Test-Path -LiteralPath (Join-Path $Destination "makensis.exe")) {
    & (Join-Path $Destination "makensis.exe") /VERSION
    exit $LASTEXITCODE
}

# SourceForge's human-facing `/download` route can return an HTML interstitial
# to non-browser PowerShell clients. curl follows the immutable file redirect
# and fails closed before the pinned digest is checked below.
$curl = Get-Command curl.exe -ErrorAction Stop
& $curl.Source `
    --fail `
    --location `
    --retry 5 `
    --retry-all-errors `
    --silent `
    --show-error `
    --output $installer `
    $url
if ($LASTEXITCODE -ne 0) {
    throw "NSIS download failed with curl exit code $LASTEXITCODE"
}
$actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($actual -ne $sha256) {
    throw "NSIS checksum mismatch: expected $sha256, received $actual"
}

$parent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$process = Start-Process `
    -FilePath $installer `
    -ArgumentList @("/S", "/D=$Destination") `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
if ($process.ExitCode -ne 0) {
    throw "NSIS installation failed with exit code $($process.ExitCode)"
}

& (Join-Path $Destination "makensis.exe") /VERSION
exit $LASTEXITCODE
