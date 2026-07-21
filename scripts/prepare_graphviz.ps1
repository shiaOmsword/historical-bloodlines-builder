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

& (Join-Path $VendorRoot "bin\dot.exe") -V
& (Join-Path $VendorRoot "bin\neato.exe") -V
Write-Host "Bundled Graphviz prepared at $VendorRoot"
