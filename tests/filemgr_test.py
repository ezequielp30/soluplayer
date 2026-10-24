"""Prueba de la gestión de archivos y carpetas: renombrar, crear carpeta, mover y enviar a la Papelera.
Todo en carpetas temporales (la Papelera de Windows recibe solo archivos de prueba)."""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_filemgr_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import file_manager
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import main_window as mw

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
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
def click(label):
    def h(box):
        for b in box.buttons():
            if b.text().replace("&", "") == label: b.click(); return
        raise AssertionError([b.text() for b in box.buttons()])
    return h
def tone(path, secs=3):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))

music = os.path.join(work, "Musica")
a, b, c = (os.path.join(music, "Rock", n) for n in ("uno.wav", "dos.wav", "tres.wav"))
d = os.path.join(music, "Pop", "cuatro.wav")
for p in (a, b, c, d): tone(p)
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in (a, b, c, d)])
pl = db.create_playlist("Lista")
ids = {p: db.track_id_for_path(p) for p in (a, b, c, d)}
db.add_to_playlist(pl.id, [ids[a], ids[d]])
win = mw.MainWindow(db); win.show(); spin(200)
names = iter([])
win._ask_name = lambda *args: next(names, None)
by = lambda tid: next(t for t in win.library if t.id == tid)

print("[Renombrar archivo]")
win._on_play_requested([by(ids[a])], 0); spin(400)
names = iter(["Mi canción"])
win._rename_track_file(by(ids[a])); spin(300)
new_a = os.path.join(music, "Rock", "Mi canción.wav")
check("se renombra conservando la extensión", os.path.exists(new_a) and not os.path.exists(a))
check("  la biblioteca y la playlist usan el nombre nuevo", by(ids[a]).path == new_a and db.playlist_tracks(pl.id)[0].path == new_a)
check("  el reproductor sigue con la canción (ruta nueva)", win.player.current_track.path == new_a)
spin(600)
check("  y sigue sonando después de renombrarla", win.player.is_playing)
expect(msg("Ya existe «dos.wav»"), lambda box: box.accept())
names = iter(["dos"])
win._rename_track_file(by(ids[c])); spin(300)
check("nombre repetido: aviso y no cambia nada", os.path.exists(c) and by(ids[c]).path == c)
expect(msg("no puede contener"), lambda box: box.accept())
names = iter(["mal:nombre?"])
win._rename_track_file(by(ids[c])); spin(300)
check("caracteres no válidos: aviso", os.path.exists(c))
win.player.release_source()
handle = open(c, "rb")  # en Windows un archivo abierto así no se puede renombrar
import msvcrt  # noqa: F401  (solo para dejar claro que es Windows)
expect(msg("está abierto en otro programa"), lambda box: box.accept())
names = iter(["en uso"])
try:
    os.rename(c, c + ".x"); os.rename(c + ".x", c); locked = False
except OSError:
    locked = True
win._rename_track_file(by(ids[c])); spin(300)
handle.close()
if locked:
    check("archivo en uso: aviso comprensible", by(ids[c]).path == c)
else:
    pending.clear()
    check("archivo en uso (Windows permitió renombrar con el archivo abierto)", True)

print("[Mover]")
QFileDialog.getExistingDirectory = staticmethod(lambda *a_, **k: os.path.join(music, "Pop"))
win._move_track_files([by(ids[b]), by(ids[c])]); spin(300)
check("se mueven a otra carpeta", os.path.exists(os.path.join(music, "Pop", "dos.wav")) and not os.path.exists(b))
check("  la biblioteca se actualiza", by(ids[b]).path == os.path.join(music, "Pop", "dos.wav"))
tone(os.path.join(music, "Otra", "dos.wav"))
QFileDialog.getExistingDirectory = staticmethod(lambda *a_, **k: os.path.join(music, "Otra"))
expect(msg("ya hay un archivo llamado «dos.wav»"), lambda box: box.accept())
win._move_track_files([by(ids[b])]); spin(300)
check("destino con el mismo nombre: no se sobrescribe y se avisa", by(ids[b]).path == os.path.join(music, "Pop", "dos.wav"))

print("[Carpetas]")
names = iter(["Rock clásico"])
win._rename_folder(os.path.join(music, "Rock")); spin(300)
check("renombrar carpeta actualiza sus canciones", by(ids[a]).path == os.path.join(music, "Rock clásico", "Mi canción.wav"))
check("  la carpeta aparece con el nombre nuevo", any(i.text(0).startswith("Rock clásico") for i in win.sidebar._folder_items()))
names = iter(["Nueva"])
expect(msg("Se creó"), lambda box: box.accept())
win._create_subfolder(os.path.join(music, "Pop")); spin(300)
check("crear subcarpeta", os.path.isdir(os.path.join(music, "Pop", "Nueva")))
expect(msg("Ya existe"), lambda box: box.accept())
names = iter(["Nueva"])
win._create_subfolder(os.path.join(music, "Pop")); spin(300)
check("  repetida: aviso", True)

print("[Enviar a la Papelera]")
expect(msg("¿Enviar 1 archivo"), click("Cancelar"))
win._trash_track_files([by(ids[d])]); spin(300)
check("Cancelar no borra nada", os.path.exists(d))
expect(lambda w: isinstance(w, QMessageBox) and "cuatro.wav" in w.informativeText() and "Pop" in w.informativeText(), click("Enviar a la Papelera"))
win._trash_track_files([by(ids[d])]); spin(300)
check("la confirmación muestra nombre y ubicación; el archivo va a la Papelera", not os.path.exists(d))
check("  se quita de la biblioteca y de la playlist", not any(t.id == ids[d] for t in win.library) and [t.id for t in db.playlist_tracks(pl.id)] == [ids[a]])
pop = os.path.join(music, "Pop")
expect(lambda w: isinstance(w, QMessageBox) and "Contiene 2 archivos" in w.informativeText() and "Se borrarán 2 archivos" in w.informativeText(),
       click("Enviar a la Papelera"))
win._trash_folder(pop); spin(300)
check("enviar carpeta: indica cuántos archivos se borran y la envía", not os.path.exists(pop))
check("  sus canciones salen de la biblioteca", not any(t.path.startswith(pop) for t in win.library))
check("  la carpeta desaparece de la barra lateral", not any(i.text(0).startswith("Pop") for i in win.sidebar._folder_items()))

print("[Validación de nombres]")
for bad in ("", "  ", "a|b", "CON", "nul.mp3", "fin."):
    try:
        file_manager.check_name(bad); ok = False
    except file_manager.FileManagerError:
        ok = True
    check(f"nombre no válido rechazado: {bad!r}", ok)

win.close()
check("todos los diálogos esperados aparecieron", not pending, pending)
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
