# Crea el instalador de Windows de Reproductor de Música.
#
# Uso (PowerShell, en la carpeta del proyecto):
#     .\crear-instalador.ps1
#
# Resultado: build\instalador\Instalar-ReproductorMusica-<versión>.exe
# Requisitos: entorno virtual .venv con las dependencias, PyInstaller e Inno Setup 6.
#   pip install pyinstaller
#   winget install --id JRSoftware.InnoSetup -e --scope user

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No se encuentra el entorno virtual .venv. Créalo primero (ver README)." }

# 1. Herramientas
& $python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Instalando PyInstaller..."; & $python -m pip install --quiet pyinstaller }
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encuentra Inno Setup 6. Instálalo con: winget install --id JRSoftware.InnoSetup -e --scope user" }

# 2. Versión (desde app/__init__.py) y datos derivados
$version = (& $python -c "import app; print(app.__version__)").Trim()
Write-Host "Versión: $version"
$parts = ($version.Split(".") + @("0", "0", "0", "0"))[0..3] -join ", "
(Get-Content packaging\version_info.txt -Raw) `
    -replace "filevers=\([^)]*\)", "filevers=($parts)" `
    -replace "prodvers=\([^)]*\)", "prodvers=($parts)" `
    -replace "'(FileVersion|ProductVersion)', '[^']*'", "'`$1', '$version'" |
    Set-Content packaging\version_info.txt -Encoding utf8

& $python tools\make_icon.py
# Extensiones para «Abrir con» (las mismas que acepta el programa)
& $python -c @"
from app.config import SUPPORTED_EXTENSIONS
lines = ['; Generado por crear-instalador.ps1 a partir de app/config.py']
for ext in sorted(SUPPORTED_EXTENSIONS):
    lines.append('Root: HKA; Subkey: \"Software\\Classes\\' + ext + '\\OpenWithProgids\"; ValueType: string; ValueName: \"{#ProgId}\"; ValueData: \"\"; Flags: uninsdeletevalue; Tasks: openwith')
    lines.append('Root: HKA; Subkey: \"Software\\Classes\\Applications\\{#AppExe}\\SupportedTypes\"; ValueType: string; ValueName: \"' + ext + '\"; ValueData: \"\"; Tasks: openwith')
open('packaging/extensiones.iss', 'w', encoding='utf-8-sig').write('\n'.join(lines) + '\n')
"@

# 3. Empaquetar con PyInstaller
Write-Host "Empaquetando el programa (1-2 minutos)..."
& $python -m PyInstaller packaging\ReproductorMusica.spec --noconfirm --clean --distpath build\dist --workpath build\work --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }
$exe = "build\dist\ReproductorMusica\ReproductorMusica.exe"
foreach ($needed in @("_internal\PySide6\avcodec-*.dll", "_internal\PySide6\plugins\multimedia\ffmpegmediaplugin.dll", "_internal\PySide6\plugins\platforms\qwindows.dll")) {
    if (-not (Get-ChildItem (Join-Path "build\dist\ReproductorMusica" $needed) -ErrorAction SilentlyContinue)) {
        throw "Falta $needed en el paquete: el programa no podría reproducir audio."
    }
}

# 4. Crear el instalador con Inno Setup
Write-Host "Creando el instalador..."
& $iscc "/DAppVersion=$version" /Q packaging\instalador.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló." }

$setup = Get-Item "build\instalador\Instalar-ReproductorMusica-$version.exe"
Write-Host ""
Write-Host ("Listo: {0}  ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB)) -ForegroundColor Green
