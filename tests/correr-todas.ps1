# Corre todas las pruebas y muestra un resumen. Uso (desde la carpeta del proyecto):
#     powershell -ExecutionPolicy Bypass -File tests\correr-todas.ps1
# Las salidas completas quedan en tests\salidas\. Termina con código 0 solo si todas pasan.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$out = Join-Path $PSScriptRoot "salidas"
New-Item -ItemType Directory -Force $out | Out-Null
$env:PYTHONUTF8 = "1"

$tests = @(
    "menu_all_test", "menu_test", "menus_test", "fixes_test", "filemgr_test", "cleanup_test",
    "eq_dsp_test", "eq_player_test", "eq_ui_test", "theme_contrast_test", "theme_test",
    "step2_test", "step3_test", "folders_test", "titles_test", "dup_test", "review_test", "repair_test",
    "convert_test", "loudness_ui_test", "online_test", "mp3gain_test", "codec_test", "breaker_test",
    "exit_test", "exit_loud_test", "exit_convert_test", "exit_convert2_test", "exit_trash_test",
    "si_real", "loudness_validate", "runner_probe", "robustez_test", "historial_archivos_test", "revision_1122_test", "menores_1124_test", "playlists_respaldo_test", "limite_playlists_test", "seguridad_1127_test", "igualar_volumen_test", "igualar_archivos_test", "apartar_test", "confirmaciones_test", "carpetas_orden_test", "audio_transparencia_test", "herramientas_carpeta_test", "audio_etapa2_test", "audio_etapa3_test", "saltar_silencio_test", "orden_visible_test", "titulos_archivo_test", "titulo_cantante_test", "localizar_test", "actualizaciones_test", "organizador_reglas_test", "organizador_analisis_test", "organizador_identificacion_test", "organizador_respaldo_test", "organizador_pendientes_test", "organizador_ventana_test"
)
$failed = @()
foreach ($t in $tests) {
    $file = Join-Path $out "$t.txt"
    $p = Start-Process $python -ArgumentList "-u", (Join-Path $PSScriptRoot "$t.py") -WorkingDirectory $root `
        -RedirectStandardOutput $file -RedirectStandardError "$file.err" -NoNewWindow -PassThru
    $null = $p.Handle  # sin esto, Windows PowerShell 5.1 deja ExitCode vacío
    if (-not $p.WaitForExit(420000)) { $p.Kill(); $code = "tiempo agotado" } else { $code = $p.ExitCode }
    $text = Get-Content $file -Encoding UTF8 -ErrorAction SilentlyContinue
    $summary = ($text | Select-String -Pattern "RESULTADO|run\(\) devolvió|VALIDACIÓN|cerradas las copias|^6 fin" | Select-Object -Last 1).Line
    $fallas = @($text | Select-String -Pattern "^\s*FALLA\b" -CaseSensitive).Count  # la marca, no la palabra «falla» en un nombre
    # Estricto: solo vale código 0. Un cierre anómalo (p. ej. 139 o -1073741819, violación de acceso)
    # cuenta como falla aunque se haya impreso el resultado: puede esconder un cierre real del programa.
    # Un resumen «RESULTADO: FALLA» o «VALIDACIÓN: FALLA» también es falla, aunque el código de salida sea 0.
    $ok = ($fallas -eq 0) -and $summary -and ($summary -cnotmatch '\bFALLA\b') -and ($code -eq 0)
    if (-not $ok) { $failed += $t }
    $extra = if ($code -ne 0 -and $summary) { " (código de salida $code)" } else { "" }
    "{0,-22} {1,-6} {2}{3}" -f $t, ($(if ($ok) { "OK" } else { "FALLA" })), $summary, $extra
}
""
if ($failed.Count) { "Fallaron: $($failed -join ', ')"; exit 1 } else { "Todas las pruebas pasaron ($($tests.Count))."; exit 0 }
