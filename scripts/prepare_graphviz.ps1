[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$GraphvizHome
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VendorRoot = Join-Path $ProjectRoot "vendor\graphviz"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Graphviz for the portable build must be prepared on Windows."
}

if ([string]::IsNullOrWhiteSpace($GraphvizHome)) {
    $DotCommand = Get-Command dot.exe -ErrorAction SilentlyContinue
    if ($null -eq $DotCommand) {
        throw "dot.exe was not found. Install Graphviz or pass -GraphvizHome C:\path\to\Graphviz."
    }
    $GraphvizHome = Split-Path -Parent (Split-Path -Parent $DotCommand.Source)
}

$GraphvizHome = (Resolve-Path $GraphvizHome).Path
$DotPath = Join-Path $GraphvizHome "bin\dot.exe"
$NeatoPath = Join-Path $GraphvizHome "bin\neato.exe"
if (-not (Test-Path $DotPath)) {
    throw "dot.exe was not found under $GraphvizHome\bin."
}
if (-not (Test-Path $NeatoPath)) {
    throw "neato.exe was not found under $GraphvizHome\bin."
}

if (Test-Path $VendorRoot) {
    Remove-Item $VendorRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $VendorRoot -Force | Out-Null

Write-Host "Copying Graphviz from $GraphvizHome"
Copy-Item (Join-Path $GraphvizHome "*") $VendorRoot -Recurse -Force

$VendorBin = Join-Path $VendorRoot "bin"
$VendorDot = Join-Path $VendorBin "dot.exe"
$VendorNeato = Join-Path $VendorBin "neato.exe"
$OldPath = $env:Path
$OldGvBinDir = $env:GVBINDIR
$SmokeOutput = Join-Path $env:TEMP ("historical-bloodlines-graphviz-smoke-{0}.svg" -f [guid]::NewGuid().ToString("N"))

# Windows Graphviz packages have used more than one plug-in layout over time.
# Most put gvplugin_*.dll beside dot.exe, while some packages use another
# directory. Discover the actual directory instead of assuming bin\config6.
$PluginCandidates = New-Object System.Collections.Generic.List[string]
$PluginDlls = Get-ChildItem -Path $VendorRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "*gvplugin*.dll" }

foreach ($PluginDll in $PluginDlls) {
    if (-not $PluginCandidates.Contains($PluginDll.DirectoryName)) {
        $PluginCandidates.Add($PluginDll.DirectoryName)
    }
}
if (-not $PluginCandidates.Contains($VendorBin)) {
    $PluginCandidates.Add($VendorBin)
}

$SelectedPluginDirectory = $null
$Diagnostics = New-Object System.Collections.Generic.List[string]

try {
    foreach ($PluginDirectory in $PluginCandidates) {
        $env:GVBINDIR = $PluginDirectory
        $env:Path = "$VendorBin;$PluginDirectory;$OldPath"
        Remove-Item $SmokeOutput -Force -ErrorAction SilentlyContinue

        Push-Location $PluginDirectory
        try {
            $ConfigOutput = (& $VendorDot -c 2>&1 | Out-String).Trim()
            $ConfigExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }

        $SmokeOutputText = (
            "graph portable_probe { a -- b }" |
                & $VendorDot -Kneato -Tsvg -o $SmokeOutput 2>&1 |
                Out-String
        ).Trim()
        $SmokeExitCode = $LASTEXITCODE

        if ($SmokeExitCode -eq 0 -and (Test-Path $SmokeOutput)) {
            $SelectedPluginDirectory = $PluginDirectory
            break
        }

        $Diagnostics.Add(
            "Candidate: $PluginDirectory`n" +
            "dot -c exit code: $ConfigExitCode`n" +
            "dot -c output: $ConfigOutput`n" +
            "smoke exit code: $SmokeExitCode`n" +
            "smoke output: $SmokeOutputText"
        )
    }

    if ([string]::IsNullOrWhiteSpace($SelectedPluginDirectory)) {
        $DiagnosticText = $Diagnostics -join "`n---`n"
        throw (
            "Portable Graphviz smoke test failed for every discovered plug-in directory.`n" +
            "Graphviz home: $GraphvizHome`n" +
            "Discovered plugin DLLs: $($PluginDlls.Count)`n" +
            "$DiagnosticText`n" +
            "Install the current 64-bit Graphviz release and pass its root with -GraphvizHome."
        )
    }

    $VendorRootFull = [System.IO.Path]::GetFullPath($VendorRoot).TrimEnd([char[]]"\/")
    $SelectedPluginDirectoryFull = [System.IO.Path]::GetFullPath($SelectedPluginDirectory)
    if (-not $SelectedPluginDirectoryFull.StartsWith($VendorRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Selected Graphviz plug-in directory is outside vendor\graphviz."
    }
    $RelativePluginDirectory = $SelectedPluginDirectoryFull.Substring($VendorRootFull.Length).TrimStart([char[]]"\/")
    $PluginMarker = Join-Path $VendorRoot ".historical-bloodlines-plugin-dir"
    [System.IO.File]::WriteAllText(
        $PluginMarker,
        $RelativePluginDirectory,
        [System.Text.Encoding]::ASCII
    )

    Write-Host "Graphviz plug-ins: $SelectedPluginDirectory"
    & $VendorDot -V
    & $VendorNeato -V
}
finally {
    $env:Path = $OldPath
    if ($null -eq $OldGvBinDir) {
        Remove-Item Env:GVBINDIR -ErrorAction SilentlyContinue
    }
    else {
        $env:GVBINDIR = $OldGvBinDir
    }
    Remove-Item $SmokeOutput -Force -ErrorAction SilentlyContinue
}

Write-Host "Bundled Graphviz prepared at $VendorRoot"
