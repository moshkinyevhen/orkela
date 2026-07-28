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
$sha256 = "56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f"
$url = (
    "https://downloads.sourceforge.net/project/nsis/" +
    "NSIS%203/$version/nsis-$version.zip"
)
$archive = Join-Path ([System.IO.Path]::GetTempPath()) (
    "orkela-nsis-$version.zip"
)

if (Test-Path -LiteralPath (Join-Path $Destination "makensis.exe")) {
    & (Join-Path $Destination "makensis.exe") /VERSION
    exit $LASTEXITCODE
}

# SourceForge's human-facing `/download` route can return an HTML interstitial
# to non-browser clients. curl follows the immutable binary-file redirect and
# fails closed before the pinned digest is checked below.
$curl = Get-Command curl.exe -ErrorAction Stop
& $curl.Source `
    --fail `
    --location `
    --retry 5 `
    --retry-all-errors `
    --silent `
    --show-error `
    --output $archive `
    $url
if ($LASTEXITCODE -ne 0) {
    throw "NSIS download failed with curl exit code $LASTEXITCODE"
}
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($actual -ne $sha256) {
    throw "NSIS checksum mismatch: expected $sha256, received $actual"
}

$extract_root = Join-Path ([System.IO.Path]::GetTempPath()) (
    "orkela-nsis-extract-" + [Guid]::NewGuid().ToString("N")
)
Expand-Archive `
    -LiteralPath $archive `
    -DestinationPath $extract_root
$source = Join-Path $extract_root "nsis-$version"
if (!(Test-Path -LiteralPath (Join-Path $source "makensis.exe"))) {
    throw "Verified NSIS archive does not contain makensis.exe"
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item `
    -Path (Join-Path $source "*") `
    -Destination $Destination `
    -Recurse `
    -Force

& (Join-Path $Destination "makensis.exe") /VERSION
exit $LASTEXITCODE
