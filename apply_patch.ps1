param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$RepositoryRoot = "."
)

$ErrorActionPreference = "Stop"
$PatchPath = Join-Path $PSScriptRoot "historical-bloodlines-ghostscript-outlines.patch"
$RepositoryRoot = (Resolve-Path $RepositoryRoot).Path

Push-Location $RepositoryRoot
try {
    git apply --check $PatchPath
    if ($LASTEXITCODE -ne 0) {
        throw "git apply --check failed. The repository does not match the patch base."
    }

    git apply $PatchPath
    if ($LASTEXITCODE -ne 0) {
        throw "git apply failed."
    }

    Write-Host "Patch applied successfully."
    Write-Host "Next: poetry run pytest -q"
}
finally {
    Pop-Location
}
