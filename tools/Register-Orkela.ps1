param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ExePath
)

$resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
$classesRoot = 'HKCU:\Software\Classes'
$applicationKey = Join-Path $classesRoot 'Applications\Orkela.exe'

# Register Orkela once as a Windows application. The command contains "%1"
# literally so Explorer passes the selected media file to the player.
New-Item -Path $applicationKey -Force | Out-Null
New-ItemProperty `
    -Path $applicationKey `
    -Name 'FriendlyAppName' `
    -Value 'Orkela' `
    -PropertyType String `
    -Force | Out-Null
New-Item -Path (Join-Path $applicationKey 'shell\open\command') -Force |
    Out-Null
Set-Item `
    -LiteralPath (Join-Path $applicationKey 'shell\open\command') `
    -Value ('"{0}" "%1"' -f $resolvedExe)

$formats = @(
    @{
        Extension = '.resonith'
        ProgId = 'Orkela.Resonith'
        Description = 'Resonith audio'
    },
    @{
        Extension = '.scenelith'
        ProgId = 'Orkela.SceneLith'
        Description = 'SceneLith visual media'
    },
    @{
        Extension = '.orka'
        ProgId = 'Orkela.Package'
        Description = 'Orkela synchronized media package'
    }
)

foreach ($format in $formats) {
    $extensionKey = Join-Path $classesRoot $format.Extension
    $progIdKey = Join-Path $classesRoot $format.ProgId

    New-Item -Path $extensionKey -Force | Out-Null
    Set-Item -LiteralPath $extensionKey -Value $format.ProgId
    New-Item `
        -Path (Join-Path $extensionKey 'OpenWithProgids') `
        -Force | Out-Null
    New-ItemProperty `
        -Path (Join-Path $extensionKey 'OpenWithProgids') `
        -Name $format.ProgId `
        -Value ([byte[]]@()) `
        -PropertyType Binary `
        -Force | Out-Null

    New-Item -Path $progIdKey -Force | Out-Null
    Set-Item -LiteralPath $progIdKey -Value $format.Description
    New-Item -Path (Join-Path $progIdKey 'DefaultIcon') -Force | Out-Null
    Set-Item `
        -LiteralPath (Join-Path $progIdKey 'DefaultIcon') `
        -Value ('"{0}",0' -f $resolvedExe)
    New-Item -Path (Join-Path $progIdKey 'shell\open\command') -Force |
        Out-Null
    Set-Item `
        -LiteralPath (Join-Path $progIdKey 'shell\open\command') `
        -Value ('"{0}" "%1"' -f $resolvedExe)
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ShellAssociationNotifier {
    [DllImport("shell32.dll")]
    public static extern void SHChangeNotify(
        uint eventId,
        uint flags,
        IntPtr item1,
        IntPtr item2
    );
}
'@
[ShellAssociationNotifier]::SHChangeNotify(
    0x08000000,
    0x0000,
    [IntPtr]::Zero,
    [IntPtr]::Zero
)

Write-Host "Orkela now handles .resonith, .scenelith, and .orka for this user."
