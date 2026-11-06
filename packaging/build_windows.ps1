param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$OutputDirectory = "",
    [string]$PythonVersion = "3.12.10"
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Paczke buduje sie na Windows x64." }
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $ProjectRoot "dist" }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$PackageRoot = Join-Path $OutputDirectory "Raport_energetyczny_Windows"
if (Test-Path (Join-Path $PackageRoot "data")) {
    throw "Folder poprzedniej paczki zawiera dane uzytkownika. Wybierz inny OutputDirectory."
}
if (Test-Path $PackageRoot) { Remove-Item $PackageRoot -Recurse -Force }
$AppRoot = Join-Path $PackageRoot "app"
$RuntimeRoot = Join-Path $PackageRoot "runtime"
$PackagesRoot = Join-Path $RuntimeRoot "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $AppRoot, $PackagesRoot | Out-Null
$TemporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("energy-build-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
try {
    Write-Host "Pobieranie przenosnego Pythona $PythonVersion..."
    $PythonArchive = Join-Path $TemporaryRoot "python.zip"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $PythonArchive
    Expand-Archive -Path $PythonArchive -DestinationPath $RuntimeRoot -Force
    $VersionParts = $PythonVersion.Split('.')
    $PythonName = "python" + $VersionParts[0] + $VersionParts[1]
    @("$PythonName.zip", ".", "Lib\site-packages", "..\app", "import site") |
        Set-Content -Path (Join-Path $RuntimeRoot "$PythonName._pth") -Encoding ascii

    Write-Host "Instalowanie zaleznosci wewnatrz paczki..."
    & python -m pip install --disable-pip-version-check --only-binary=:all: --target $PackagesRoot -r (Join-Path $ProjectRoot "packaging\requirements-windows.txt")
    if ($LASTEXITCODE -ne 0) { throw "Nie udalo sie przygotowac zaleznosci." }

    Get-ChildItem $ProjectRoot -Filter "*.py" | Where-Object { $_.Name -notlike "test_*" } |
        ForEach-Object { Copy-Item $_.FullName $AppRoot }
    foreach ($Name in @("market_dashboard_template.html", "prompt_market_data.txt", "prompt_biomass.txt", "prompt_biomass_sources.txt")) {
        Copy-Item (Join-Path $ProjectRoot $Name) $AppRoot
    }
    Copy-Item (Join-Path $ProjectRoot "vendor") (Join-Path $AppRoot "vendor") -Recurse
    Copy-Item (Join-Path $ProjectRoot "DataMaster.xlsx") (Join-Path $AppRoot "DataMaster.start.xlsx")
    Copy-Item (Join-Path $ProjectRoot "packaging\launcher.py") $PackageRoot
    Copy-Item (Join-Path $ProjectRoot "packaging\Uruchom.cmd") $PackageRoot
    Copy-Item (Join-Path $ProjectRoot "packaging\INSTRUKCJA.txt") $PackageRoot
    Copy-Item (Join-Path $ProjectRoot "packaging\requirements-windows.txt") $PackageRoot

    Write-Host "Dolaczanie przegladarki do generowania PDF..."
    $PreviousBrowserPath = $env:PLAYWRIGHT_BROWSERS_PATH
    try {
        $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RuntimeRoot "browsers"
        & (Join-Path $RuntimeRoot "python.exe") -m playwright install chromium --only-shell
        if ($LASTEXITCODE -ne 0) { throw "Nie udalo sie dolaczyc przegladarki PDF." }
    } finally {
        $env:PLAYWRIGHT_BROWSERS_PATH = $PreviousBrowserPath
    }
    $Manifest = @{
        python = $PythonVersion
        python_archive_sha256 = (Get-FileHash $PythonArchive -Algorithm SHA256).Hash
        built_at_utc = [DateTime]::UtcNow.ToString("o")
        architecture = "windows-x64"
    }
    $Manifest | ConvertTo-Json | Set-Content (Join-Path $PackageRoot "build-info.json") -Encoding utf8
    $Archive = Join-Path $OutputDirectory "Raport_energetyczny_Windows.zip"
    Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $Archive -Force
    Write-Host "Gotowa paczka: $Archive"
} finally {
    Remove-Item $TemporaryRoot -Recurse -Force
}
