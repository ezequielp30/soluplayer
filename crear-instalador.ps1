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
$pyinstallerVersion = "6.22.3"  # versión probada: fijada para que el paquete sea reproducible
$found = (& $python -m PyInstaller --version 2>$null)
if ($LASTEXITCODE -ne 0 -or "$found".Trim() -ne $pyinstallerVersion) {
    Write-Host "Instalando PyInstaller $pyinstallerVersion..."
    & $python -m pip install --quiet "pyinstaller==$pyinstallerVersion"
}
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encuentra Inno Setup 6. Instálalo con: winget install --id JRSoftware.InnoSetup -e --scope user" }

# 2. Versión (desde app/__init__.py) y datos derivados
$version = (& $python -c "import app; print(app.__version__)").Trim()
Write-Host "Versión: $version"
& $python tools\version_info.py
if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar version_info.txt." }

& $python tools\make_icon.py
# Extensiones para «Abrir con» (las mismas que acepta el programa)
& $python -c @"
from app.config import SUPPORTED_EXTENSIONS
lines = ['; Generado por crear-instalador.ps1 a partir de app/config.py']
for ext in sorted(SUPPORTED_EXTENSIONS):
    lines.append('Root: HKA; Subkey: \"Software\\Classes\\' + ext + '\\OpenWithProgids\"; ValueType: string; ValueName: \"{#ProgId}\"; ValueData: \"\"; Flags: uninsdeletevalue; Tasks: openwith')
    lines.append('Root: HKA; Subkey: \"Software\\Classes\\Applications\\{#AppExe}\\SupportedTypes\"; ValueType: string; ValueName: \"' + ext + '\"; ValueData: \"\"; Tasks: openwith')
    lines.append('Root: HKA; Subkey: \"Software\\Clients\\Media\\{#ProgId}\\Capabilities\\FileAssociations\"; ValueType: string; ValueName: \"' + ext + '\"; ValueData: \"{#ProgId}\"; Tasks: openwith')
open('packaging/extensiones.iss', 'w', encoding='utf-8-sig').write('\n'.join(lines) + '\n')
"@

# El código fuente que se entrega tiene que ser exactamente el que se empaqueta (GPL): no se arma con
# cambios sin guardar. Solo se aceptan los archivos que este mismo script acaba de generar (entran al ZIP
# tal como quedan).
$generated = @("packaging/version_info.txt", "packaging/extensiones.iss", "assets/")
$status = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "No se pudo consultar git (¿está instalado?)." }
$dirty = @($status | Where-Object { $path = $_.Substring(3); -not ($generated | Where-Object { $path.StartsWith($_) }) })
if ($dirty) { throw "Hay cambios sin guardar en git; guárdalos (commit) antes de crear el instalador:`n$($dirty -join "`n")" }

# Código fuente de FFmpeg (LGPL 2.1): se entrega con el programa. Se descarga una vez y se comprueba que
# sea exactamente el publicado por FFmpeg (huella SHA-256 del archivo firmado por ffmpeg.org).
$ffmpegVersion = "9.0.1"
$ffmpegSha256 = "CF38E0E28C7E5605942C4A77755349B0145804A397AF37EB1FB4C77CB237F635"
$ffmpegSource = Join-Path $PSScriptRoot "build\terceros\ffmpeg-$ffmpegVersion.tar.xz"
if (-not (Test-Path $ffmpegSource)) {
    Write-Host "Descargando el código fuente de FFmpeg $ffmpegVersion..."
    New-Item -ItemType Directory -Force (Split-Path $ffmpegSource) | Out-Null
    Invoke-WebRequest "https://ffmpeg.org/releases/ffmpeg-$ffmpegVersion.tar.xz" -OutFile $ffmpegSource -UseBasicParsing
}
if ((Get-FileHash $ffmpegSource -Algorithm SHA256).Hash -ne $ffmpegSha256) {
    throw "El código fuente de FFmpeg ($ffmpegSource) no coincide con el publicado; bórralo y vuelve a crear el instalador."
}

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
# El código de FFmpeg que se entrega tiene que ser el de la versión que trae PySide6.
$avcodec = Get-ChildItem "build\dist\ReproductorMusica\_internal\PySide6\avcodec-*.dll" | Select-Object -First 1
& $python -c "import sys; sys.exit(0 if b'FFmpeg version $ffmpegVersion' in open(sys.argv[1], 'rb').read() else 1)" $avcodec.FullName
if ($LASTEXITCODE -ne 0) { throw "PySide6 trae otra versión de FFmpeg (no la $ffmpegVersion): actualiza la versión y su huella en este script y en licencias\TERCEROS.txt." }

# 4. Código fuente de esta versión (la licencia GPL exige entregarlo junto con el programa): el último commit
# más los archivos que generó este script, o sea exactamente lo que se empaquetó.
New-Item -ItemType Directory -Force "build\instalador" | Out-Null
$source = Join-Path $PSScriptRoot "build\instalador\ReproductorMusica-$version-codigo-fuente.zip"
$tree = "$(git stash create)".Trim()  # no toca el árbol de trabajo: solo arma un commit con lo generado
if (-not $tree) { $tree = "HEAD" }
git archive --format=zip --prefix="ReproductorMusica-$version/" -o $source $tree
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el ZIP del código fuente (¿está git instalado?)." }

# 5. Crear el instalador con Inno Setup (lleva también el código fuente: así lo recibe quien reciba solo
# el instalador).
Write-Host "Creando el instalador..."
& $iscc "/DAppVersion=$version" "/DSourceZip=$source" "/DFFmpegSource=$ffmpegSource" /Q packaging\instalador.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló." }

$setup = Get-Item "build\instalador\Instalar-ReproductorMusica-$version.exe"
Write-Host ""
Write-Host ("Listo: {0}  ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB)) -ForegroundColor Green
Write-Host ("Código fuente: {0}  (también va dentro del instalador)" -f (Get-Item $source).FullName) -ForegroundColor Green
