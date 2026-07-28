[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [Parameter(Mandatory = $true)]
    [ValidateSet("x64", "arm64")]
    [string]$ExpectedArchitecture,

    [Parameter(Mandatory = $true)]
    [string]$ProbeInput,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedExecutable,

    [Parameter(Mandatory = $true)]
    [uint64]$ExpectedFrames,

    [Parameter(Mandatory = $true)]
    [uint32]$ExpectedSampleRate,

    [Parameter(Mandatory = $true)]
    [uint16]$ExpectedChannels,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedPcmFnv64,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedPcmSha256
)

$ErrorActionPreference = "Stop"

$setup = (Resolve-Path $Installer).Path
$probe = (Resolve-Path $ProbeInput).Path
$builtExecutable = (Resolve-Path $ExpectedExecutable).Path
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
$extensionKey = "HKCU:\Software\Classes\.resonith\OpenWithProgids"
$shortcutDirectory = Join-Path `
    $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Orkela"

function Start-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$ArgumentList = @(),

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WindowStyle Hidden `
        -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            & "$env:SystemRoot\System32\taskkill.exe" `
                /PID $process.Id /T /F 2>$null | Out-Null
        } catch {
            try {
                $process.Kill()
                $process.WaitForExit()
            } catch {
                Write-Warning "Failed to terminate timed-out process tree: $_"
            }
        }
        throw "Process exceeded the ${TimeoutSeconds}s gate: $FilePath"
    }
    return $process
}

function Get-PeMachine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $reader = [System.IO.BinaryReader]::new($stream)
        if ($reader.ReadUInt16() -ne 0x5A4D) {
            throw "Payload is not a PE image: $Path"
        }
        $stream.Position = 0x3C
        $peOffset = $reader.ReadUInt32()
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Payload has no valid PE signature: $Path"
        }
        return $reader.ReadUInt16()
    } finally {
        $stream.Dispose()
    }
}

foreach ($existing in @(
    $productKey,
    $uninstallKey,
    $progIdKey,
    $shortcutDirectory
)) {
    if (Test-Path -LiteralPath $existing) {
        throw "Installer gate refuses to overwrite existing state: $existing"
    }
}
if (
    (Test-Path -LiteralPath $extensionKey) -and
    (Get-ItemProperty -LiteralPath $extensionKey).PSObject.Properties.Name `
        -contains "Orkela.Resonith"
) {
    throw "Installer gate refuses to overwrite an existing association"
}

$uninstaller = Join-Path $installDirectory "Uninstall.exe"
$uninstalled = $false
try {
    $install = Start-BoundedProcess `
        -FilePath $setup `
        -ArgumentList @("/S", "/D=$installDirectory") `
        -TimeoutSeconds 45
    if ($install.ExitCode -ne 0) {
        throw "Installer returned exit code $($install.ExitCode)"
    }

    $executable = Join-Path $installDirectory "Orkela.exe"
    $installDeadline = [DateTime]::UtcNow.AddSeconds(15)
    while (
        (
            -not (Test-Path -LiteralPath $executable) -or
            -not (Test-Path -LiteralPath $uninstaller)
        ) -and
        [DateTime]::UtcNow -lt $installDeadline
    ) {
        Start-Sleep -Milliseconds 100
    }
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

    $expectedMachine = if ($ExpectedArchitecture -eq "arm64") {
        0xAA64
    } else {
        0x8664
    }
    $actualMachine = Get-PeMachine -Path $executable
    if ($actualMachine -ne $expectedMachine) {
        throw (
            "Expected PE machine 0x{0:X4}, received 0x{1:X4}" -f
            $expectedMachine,
            $actualMachine
        )
    }

    $builtHash = (Get-FileHash `
        -LiteralPath $builtExecutable `
        -Algorithm SHA256).Hash
    $installedHash = (Get-FileHash `
        -LiteralPath $executable `
        -Algorithm SHA256).Hash
    if ($installedHash -ne $builtHash) {
        throw "Installed executable differs from the tested build payload"
    }

    $report = Join-Path $testRoot "installed-self-test.json"
    $selfTest = Start-BoundedProcess `
        -FilePath $executable `
        -ArgumentList @(
            "--self-test",
            "`"$probe`"",
            "--report",
            "`"$report`""
        ) `
        -TimeoutSeconds 60
    if ($selfTest.ExitCode -ne 0) {
        throw "Installed self-test returned exit code $($selfTest.ExitCode)"
    }
    if (-not (Test-Path -LiteralPath $report)) {
        throw "Installed self-test did not create its evidence report"
    }
    $evidence = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (
        $evidence.schema -ne "org.scenelith.orkela.self-test.v1" -or
        $evidence.status -ne "pass" -or
        [uint64]$evidence.frames -ne $ExpectedFrames -or
        [uint32]$evidence.sample_rate -ne $ExpectedSampleRate -or
        [uint16]$evidence.channels -ne $ExpectedChannels -or
        "$($evidence.pcm_fnv64)" -ne $ExpectedPcmFnv64 -or
        "$($evidence.pcm_sha256)" -ne $ExpectedPcmSha256
    ) {
        throw "Installed self-test evidence is incomplete or malformed"
    }

    $uninstall = Start-BoundedProcess `
        -FilePath $uninstaller `
        -ArgumentList "/S" `
        -TimeoutSeconds 45
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller returned exit code $($uninstall.ExitCode)"
    }
    $uninstalled = $true

    $removalTargets = @(
        $installDirectory,
        $productKey,
        $uninstallKey,
        $progIdKey,
        $shortcutDirectory
    )
    $uninstallDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $remaining = @(
            $removalTargets |
                Where-Object { Test-Path -LiteralPath $_ }
        )
        $associationRemains = (
            (Test-Path -LiteralPath $extensionKey) -and
            (
                (Get-ItemProperty -LiteralPath $extensionKey).
                    PSObject.Properties.Name -contains "Orkela.Resonith"
            )
        )
        if ($remaining.Count -eq 0 -and -not $associationRemains) {
            break
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $uninstallDeadline)

    foreach ($removed in $removalTargets) {
        if (Test-Path -LiteralPath $removed) {
            throw "Uninstall transaction left state behind: $removed"
        }
    }
    if ($associationRemains) {
        throw "Uninstall transaction left the .resonith association behind"
    }

    Write-Output (
        "installer_gate=pass architecture=$ExpectedArchitecture " +
        "version=$ExpectedVersion"
    )
} finally {
    if (-not $uninstalled -and (Test-Path -LiteralPath $uninstaller)) {
        try {
            $cleanup = Start-BoundedProcess `
                -FilePath $uninstaller `
                -ArgumentList "/S" `
                -TimeoutSeconds 45
            if ($cleanup.ExitCode -ne 0) {
                Write-Warning (
                    "Cleanup uninstaller returned $($cleanup.ExitCode)"
                )
            }
        } catch {
            Write-Warning "Cleanup uninstall failed: $_"
        }
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
