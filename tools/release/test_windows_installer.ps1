[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [Parameter(Mandatory = $true)]
    [ValidateSet("x64", "arm64")]
    [string]$ExpectedArchitecture,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion
)

$ErrorActionPreference = "Stop"

$setup = (Resolve-Path $Installer).Path
$testRoot = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    ("orkela-installer-gate-" + [Guid]::NewGuid().ToString("N"))
$installDirectory = Join-Path $testRoot "Orkela"
$productKey = "HKCU:\Software\SceneLith\Orkela"
$uninstallKey = (
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\" +
    "Uninstall\Orkela"
)
$progIdKey = "HKCU:\Software\Classes\Orkela.Resonith"

if (
    (Test-Path -LiteralPath $productKey) -or
    (Test-Path -LiteralPath $uninstallKey)
) {
    throw "Installer gate refuses to overwrite an existing Orkela installation"
}

$uninstaller = Join-Path $installDirectory "Uninstall.exe"
try {
    $install = Start-Process `
        -FilePath $setup `
        -ArgumentList @("/S", "/D=$installDirectory") `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Installer returned exit code $($install.ExitCode)"
    }

    $executable = Join-Path $installDirectory "Orkela.exe"
    foreach ($required in @(
        $executable,
        $uninstaller,
        (Join-Path $installDirectory "README.md"),
        (Join-Path $installDirectory "CHANGELOG.md"),
        (Join-Path $installDirectory "VERSION")
    )) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Installed payload is missing: $required"
        }
    }

    $version = (Get-Item -LiteralPath $executable).VersionInfo.ProductVersion
    if ($version -ne $ExpectedVersion) {
        throw "Expected version $ExpectedVersion, received $version"
    }

    $product = Get-ItemProperty -LiteralPath $productKey
    if ($product.Architecture -ne $ExpectedArchitecture) {
        throw (
            "Expected architecture $ExpectedArchitecture, received " +
            $product.Architecture
        )
    }
    if ($product.InstallLocation -ne $installDirectory) {
        throw "InstallLocation does not match the transaction target"
    }
    if (-not (Test-Path -LiteralPath $progIdKey)) {
        throw "Resonith ProgID was not registered"
    }

    $uninstall = Start-Process `
        -FilePath $uninstaller `
        -ArgumentList "/S" `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller returned exit code $($uninstall.ExitCode)"
    }
    Start-Sleep -Milliseconds 500

    foreach ($removed in @(
        (Join-Path $installDirectory "Orkela.exe"),
        $productKey,
        $uninstallKey,
        $progIdKey
    )) {
        if (Test-Path -LiteralPath $removed) {
            throw "Uninstall transaction left state behind: $removed"
        }
    }

    Write-Output (
        "installer_gate=pass architecture=$ExpectedArchitecture " +
        "version=$ExpectedVersion"
    )
} finally {
    if (Test-Path -LiteralPath $uninstaller) {
        Start-Process `
            -FilePath $uninstaller `
            -ArgumentList "/S" `
            -WindowStyle Hidden `
            -Wait | Out-Null
    }

    $resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
    $resolvedTemp = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::GetTempPath()
    )
    if (
        (Test-Path -LiteralPath $testRoot) -and
        $resolvedTestRoot.StartsWith(
            $resolvedTemp,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
