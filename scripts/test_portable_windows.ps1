[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$BuildDirectory
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BuildDirectory)) {
    $BuildDirectory = Join-Path $ProjectRoot "dist\HistoricalBloodlines"
}
$BuildDirectory = (Resolve-Path $BuildDirectory).Path
$Executable = Join-Path $BuildDirectory "HistoricalBloodlines.exe"

if (-not (Test-Path $Executable)) {
    throw "Portable executable was not found: $Executable"
}
if (-not (Test-Path (Join-Path $BuildDirectory "_internal\graphviz\bin\dot.exe"))) {
    throw "Bundled dot.exe is missing from the onedir build."
}
if (-not (Test-Path (Join-Path $BuildDirectory "_internal\graphviz\bin\neato.exe"))) {
    throw "Bundled neato.exe is missing from the onedir build."
}

$PortableTestRoot = Join-Path $env:TEMP "Historical Bloodlines portable тест"
if (Test-Path $PortableTestRoot) {
    Remove-Item $PortableTestRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $PortableTestRoot -Force | Out-Null
Copy-Item (Join-Path $BuildDirectory "*") $PortableTestRoot -Recurse -Force

$OldPath = $env:Path
try {
    # Deliberately remove Python and system Graphviz from PATH. The executable
    # must complete the full Excel -> Graphviz -> PDF self-test using only its
    # own _internal directory and standard Windows components.
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    & (Join-Path $PortableTestRoot "HistoricalBloodlines.exe") --self-test
    if ($LASTEXITCODE -ne 0) {
        throw "Portable self-test failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:Path = $OldPath
    if (Test-Path $PortableTestRoot) {
        Remove-Item $PortableTestRoot -Recurse -Force
    }
}

Write-Host "Portable test passed with Python and system Graphviz removed from PATH."
