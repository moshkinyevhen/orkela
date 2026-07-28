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
    "https://sourceforge.net/projects/nsis/files/" +
    "NSIS%203/$version/nsis-$version-setup.exe/download"
)
$installer = Join-Path ([System.IO.Path]::GetTempPath()) (
    "orkela-nsis-$version-setup.exe"
)

if (Test-Path -LiteralPath (Join-Path $Destination "makensis.exe")) {
    & (Join-Path $Destination "makensis.exe") /VERSION
    exit $LASTEXITCODE
}

Invoke-WebRequest -Uri $url -OutFile $installer
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
