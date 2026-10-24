"""Pruebas de los pasos 3 a 5 del arquitecto: WorkerRunner en las ventanas, coordinador de operaciones
sobre archivos, Historial, menús reorganizados y ajustes de interfaz. Todo en carpetas temporales."""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_step3_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
import lameenc
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QToolButton
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup, converter, mp3gain
from app.config import database_path
from app.database import Database
from app.file_operations import FileOperations
from app.importer import scan_file
from app.metadata import Quality
from app.ui import main_window as mw
from app.ui.dialogs import PreferencesDialog
from app.ui.duplicates_dialog import DuplicatesDialog
from app.ui.history_dialog import HistoryDialog
from app.ui.loudness_dialog import LoudnessDialog
from app.ui.player_bar import PlayerBar

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def wait_until(cond, timeout=60000):
    end = time.time() + timeout / 1000
    while time.time() < end and not cond(): app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.01)
    return cond()
pending = []
def expect(pred, handler): pending.append((pred, handler))
def pump():
    QTimer.singleShot(40, pump)
    w = QApplication.activeModalWidget()
    if pending and w is not None and w.isVisible() and pending[0][0](w):
        _, h = pending.pop(0)
        try: h(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, pump)
def msg(text): return lambda w: isinstance(w, QMessageBox) and text in (w.text() + w.informativeText())
def is_(cls): return lambda w: isinstance(w, cls)
def click(label):
    def h(box):
        for b in box.buttons():
            if b.text().replace("&", "") == label: b.click(); return
        raise AssertionError([b.text() for b in box.buttons()])
    return h

def make_mp3(path, seconds=4, amp=0.05, title="Prueba"):
    enc = lameenc.Encoder()
    enc.set_bit_rate(128); enc.set_in_sample_rate(44100); enc.set_channels(2); enc.set_quality(2)
    frames = bytearray()
    for i in range(44100 * seconds):
        v = int(amp * 32767 * math.sin(2 * math.pi * 440 * i / 44100))
        frames += struct.pack("<hh", v, v)
    open(path, "wb").write(enc.encode(bytes(frames)) + enc.flush())

music = os.path.join(work, "Musica"); os.makedirs(music)
for name in ("Uno", "Dos", "Tres"):
    make_mp3(os.path.join(music, f"{name}.mp3"))
db = Database(database_path())
db.add_tracks([scan_file(os.path.join(music, f))[0] for f in sorted(os.listdir(music))])
win = mw.MainWindow(db); win.show(); spin(200)

# ---------------------------------------------------------------- 1. menús
print("[1. Menús reorganizados]")
menus = {a.text().replace("&", ""): a.menu() for a in win.menuBar().actions()}
def labels(menu): return [a.text().replace("&", "") if not a.isSeparator() else "—" for a in menu.actions()]
tools = labels(menus["Herramientas"])
check("Herramientas: 4 herramientas + Historial", tools == [
    "Buscar datos en internet…", "Buscar canciones repetidas…", "Analizar y ajustar volumen…", "Convertir a MP3…",
    "—", "Historial de cambios en archivos…"], tools)
archivo = labels(menus["Archivo"])
sub = next(a.menu() for a in menus["Archivo"].actions() if a.menu() is not None)
check("Archivo → Respaldos de la biblioteca (submenú)", "Respaldos de la biblioteca" in archivo
      and labels(sub) == ["Crear un respaldo ahora", "Abrir la carpeta de respaldos"], (archivo, labels(sub)))
check("Probar sonido pasó a Reproducción", "Probar sonido…" in labels(menus["Reproducción"]) and "Probar sonido…" not in labels(menus["Ayuda"]))
check("ya no existe «Devolver repetidas a su lugar»", not any("Devolver" in t for m in menus.values() for t in labels(m)))
hist_action = next(a for a in menus["Herramientas"].actions() if a.text().startswith("&Historial"))
check("Historial tiene atajo Ctrl+Mayús+H", hist_action.shortcut().toString() == "Ctrl+Shift+H", hist_action.shortcut().toString())

# ---------------------------------------------------------------- 2. historial vacío
print("[2. Historial]")
seen = {}
def empty_history(d):
    try:
        seen["empty"] = d.stack.currentWidget() is d.empty and not d.btn_undo.isEnabled()
    finally:
        d.accept()
expect(is_(HistoryDialog), empty_history)
hist_action.trigger(); spin(200)
check("sin cambios: estado vacío y «Deshacer» desactivado", seen.get("empty"))

# ---------------------------------------------------------------- 3. volumen: estado vacío, botón principal, cierre
print("[3. Volumen]")
def loud_empty(d):
    try:
        seen["loud_empty"] = d.stack.currentWidget() is d.empty
        seen["primary_analyze"] = (d.btn_analyze_new.objectName(), d.btn_apply.objectName())
        d.btn_analyze_new.click()
        wait_until(lambda: not d.runner.busy, 60000)
        seen["primary_after"] = (d.btn_analyze_new.objectName(), d.btn_apply.objectName())
        d.filter.setCurrentIndex(d.filter.findData("all")); spin(50)
        seen["rows_all"] = d.table.rowCount()
        # cerrar mientras analiza: se detiene y se cierra
        d.btn_analyze_all.click(); spin(30)
        seen["busy_when_closing"] = d.runner.busy
    finally:
        d.reject(); seen["closed"] = not d.isVisible()
expect(is_(LoudnessDialog), loud_empty)
win._open_loudness(); spin(300)
check("antes de analizar: estado vacío en vez de tabla en blanco", seen.get("loud_empty"))
check("un solo botón ámbar: Analizar mientras falte", seen.get("primary_analyze") == ("PrimaryButton", ""), seen.get("primary_analyze"))
check("  después del análisis el ámbar pasa a «Subir volumen»", seen.get("primary_after") == ("", "PrimaryButton"), seen.get("primary_after"))
check("  la tabla muestra las 3 analizadas", seen.get("rows_all") == 3, seen.get("rows_all"))
check("cerrar durante el análisis lo detiene y cierra la ventana", seen.get("closed"), seen.get("busy_when_closing"))
win._reload_library()
check("  lo medido antes de cerrar quedó guardado", all(t.loudness_lufs is not None for t in win.library))

# Ajuste real de una canción → aparece en el Historial → «Revertir volumen…» abre la ventana filtrada
quiet = next(t for t in win.library if t.title == "Uno")
def adjust(d):
    try:
        d._run_adjust([(quiet, 2)])
        expect(msg("Se están modificando archivos"), lambda b: (seen.setdefault("blocked", True), b.accept()))
        d.reject()  # mientras modifica archivos no se puede cerrar
        seen["still_open"] = d.isVisible()
        # El resultado queda en la franja de la ventana (ya no hay aviso emergente al terminar).
        wait_until(lambda: "blocked" in seen and not d.runner.busy and "Se subió" in d.banner.text(), 60000)
    finally:
        d.reject()
expect(is_(LoudnessDialog), adjust)
win._open_loudness(); spin(500)
check("mientras ajusta MP3 la ventana no se cierra (aviso)", seen.get("still_open") is True, seen.get("blocked"))
win._reload_library()
check("  la canción quedó ajustada (+3 dB) y anotada en el archivo",
      next(t for t in win.library if t.id == quiet.id).norm_gain_db == 3.0 and mp3gain.read_applied_steps(quiet.path) == 2)

def history_volume(d):
    try:
        e = d._selected()
        seen["vol_entry"] = (e.kind, e.count, d.btn_undo.text()) if e else None
        expect(is_(LoudnessDialog), lambda l: (seen.setdefault("vol_filter", l.filter.currentData()), l.reject()))
        d.btn_undo.click(); spin(200)
    finally:
        d.accept()
expect(is_(HistoryDialog), history_volume)
hist_action.trigger(); spin(400)
check("Historial muestra el ajuste de volumen", seen.get("vol_entry") == ("volumen", 1, "Revertir volumen…"), seen.get("vol_entry"))
check("  «Revertir volumen…» abre Volumen filtrado en «ya ajustadas»", seen.get("vol_filter") == "done", seen.get("vol_filter"))

# ---------------------------------------------------------------- 4. repetidas: estado vacío y botón de peligro
print("[4. Repetidas]")
def dups(d):
    try:
        wait_until(lambda: not d.runner.busy)
        seen["dup_empty"] = d.stack.currentWidget() is d.empty
        seen["danger"] = d.btn_trash.objectName()
        seen["intro_gather"] = any("Reunir para revisar" in w.toolTip() for w in d.findChildren(QToolButton, "InfoButton"))
    finally:
        d.accept()
expect(is_(DuplicatesDialog), dups)
win._open_duplicates(); spin(300)
check("sin repetidas: estado vacío", seen.get("dup_empty"))
check("«Enviar a la papelera» se distingue (botón de peligro)", seen.get("danger") == "DangerButton")
check("la explicación («?») menciona «Reunir para revisar»", seen.get("intro_gather"))

# ---------------------------------------------------------------- 5. preferencias
print("[5. Preferencias]")
def prefs(d):
    try:
        seen["save"] = [b.objectName() for b in d.findChildren(QPushButton) if b.text() == "Guardar"]
    finally:
        d.reject()
expect(is_(PreferencesDialog), prefs)
win._open_preferences(); spin(200)
check("«Guardar» es el botón principal", seen.get("save") == ["PrimaryButton"], seen.get("save"))

# ---------------------------------------------------------------- 6. coordinador: respaldo fallido
print("[6. Coordinador de operaciones]")
real = backup.create_backup
backup.create_backup = lambda conn, reason: None
asked = []
ops = FileOperations(db, lambda ids: None, lambda ids: None, lambda: None, lambda: (asked.append(1), False)[1])
before = len(db.all_tracks())
tracks = db.all_tracks()
out = ops.remove_duplicates([(tracks[0].id, [tracks[1]])], False, tracks)
check("si el respaldo falla y el usuario cancela, no se toca nada", out is None and len(db.all_tracks()) == before and asked == [1])
session = converter.new_session([tracks[0]])
check("  tampoco empieza una conversión", ops.begin_conversion(session) is False and not session.path.exists())
check("  ni un ajuste de volumen", ops.begin_volume_adjust({tracks[0].id}) is False)
backup.create_backup = real
released = []
ops2 = FileOperations(db, lambda ids: released.append(set(ids)), lambda ids: None, lambda: None, lambda: False)
check("con respaldo correcto: respaldo → soltar archivos → seguir", ops2.begin_volume_adjust({tracks[2].id}) and released == [{tracks[2].id}])

# ---------------------------------------------------------------- 7. reglas de interfaz y de calidad
print("[7. Detalles]")
tb = converter.target_bitrate
check("WAV 8 kHz mono → 128 kbps (antes 320)", tb("x.wav", Quality(128, 8000, 1, "WAV")) == 128)
check("FLAC estéreo 44,1 kHz → 320 kbps", tb("x.flac", Quality(900, 44100, 2, "FLAC")) == 320)
check("WMA 64 kbps estéreo → 128; WMA 128 → 256", tb("x.wma", Quality(64, 44100, 2, "WMA")) == 128 and tb("x.wma", Quality(128, 44100, 2, "WMA")) == 256)
check("M4A mono 96 kbps → 160 (tope mono)", tb("x.m4a", Quality(96, 44100, 1, "M4A")) == 160)
check("WMA 22 kHz estéreo 96 kbps → 192 (tope baja frecuencia)", tb("x.wma", Quality(96, 22050, 2, "WMA")) == 192)
bar = win.player_bar
bar._duration = 19_980; bar._show_remaining = True; bar._update_time_labels(0)
check("tiempo restante redondeado hacia arriba (−0:20, no −0:19)", bar.remaining.text() == "−0:20", bar.remaining.text())
check("ventana principal sin acceso a etiquetas internas del panel", "self.content.title." not in open(mw.__file__, encoding="utf-8").read())

win.player.stop(); win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
check("todos los diálogos esperados aparecieron", not pending, pending)
shutil.rmtree(work, ignore_errors=True)
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
