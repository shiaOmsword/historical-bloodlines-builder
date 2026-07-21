[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$GraphvizHome,

    [Parameter(Mandatory = $false)]
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "The Windows executable must be built on Windows."
}
if ($null -eq (Get-Command poetry -ErrorAction SilentlyContinue)) {
    throw "Poetry was not found in PATH."
}

poetry install --with dev
if ($LASTEXITCODE -ne 0) {
    throw "poetry install failed."
}

poetry run python -m pip install --disable-pip-version-check -r packaging\requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Build dependency installation failed."
}

if (-not $SkipTests) {
    poetry run pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed."
    }
}

& (Join-Path $PSScriptRoot "prepare_graphviz.ps1") -GraphvizHome $GraphvizHome

Remove-Item (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ProjectRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue

poetry run pyinstaller --noconfirm --clean packaging\HistoricalBloodlines.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

& (Join-Path $PSScriptRoot "test_portable_windows.ps1")

$ReleaseDirectory = Join-Path $ProjectRoot "release"
New-Item -ItemType Directory -Path $ReleaseDirectory -Force | Out-Null
$ArchivePath = Join-Path $ReleaseDirectory "HistoricalBloodlines-windows-x64.zip"
Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $ProjectRoot "dist\HistoricalBloodlines\*") -DestinationPath $ArchivePath -CompressionLevel Optimal

Write-Host "Build complete: $ArchivePath"
