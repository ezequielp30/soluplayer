"""Prueba de «quitar automáticamente las canciones y carpetas que ya no existen» (todo en carpetas temporales)."""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_cleanup_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup, converter
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
def tone(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(4000)))

music = os.path.join(work, "Musica")
keep = [os.path.join(music, "Rock", f"r{i}.wav") for i in range(30)]
loose = os.path.join(music, "Pop", "suelta.wav")
moved_dir = os.path.join(music, "Revisar")
in_folder = [os.path.join(moved_dir, f"Sub{i}", f"c{i}.wav") for i in range(12)]
for p in keep + [loose] + in_folder: tone(p)

def fresh_library():
    db = Database(database_path())
    db.add_tracks([scan_file(p)[0] for p in keep + [loose] + in_folder])
    return db

db = fresh_library()
pl = db.create_playlist("Mi lista")
loose_id = db.track_id_for_path(loose)
db.add_to_playlist(pl.id, [loose_id, db.track_id_for_path(keep[0])])
# Desaparecen: un archivo suelto y una carpeta entera (que en realidad se movió)
os.remove(loose)
new_place = os.path.join(work, "OtroLugar", "Revisar")
shutil.move(moved_dir, new_place)
# Una canción en un disco que no está conectado
db.add_tracks([scan_file(keep[1])[0]])
db.conn.execute("UPDATE tracks SET path = ?, path_key = ? WHERE id = ?", (r"Q:\Musica\usb.wav", r"q:\musica\usb.wav", db.track_id_for_path(keep[1])))
db.conn.commit()

print("[1. Al abrir: carpeta movida → «Buscar dónde está…»]")
answers = [new_place]
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: answers.pop(0) if answers else "")
expect(msg("ya no existe y tenía 12 canciones"), click("Buscar dónde está…"))
win = mw.MainWindow(db); win.show(); spin(200)
before_backups = len(backup.list_backups())
win.startup_checks(); spin(300)
paths = {t.path for t in win.library}
check("la carpeta movida se reubicó (12 canciones)", all(os.path.join(new_place, os.path.relpath(p, moved_dir)) in paths for p in in_folder))
check("el archivo suelto que falta se quitó de la lista", loose not in paths)
check("  y de la playlist (la otra canción sigue)", [t.path for t in db.playlist_tracks(pl.id)] == [keep[0]])
check("la canción del disco desconectado se conserva", r"Q:\Musica\usb.wav" in paths)
check("se hizo un respaldo antes de quitar", len(backup.list_backups()) > before_backups)
check("la carpeta «Pop» desapareció de la barra lateral", not any(i.text(0).startswith("Pop") for i in win.sidebar._folder_items()))
check("ningún archivo de música se tocó", all(os.path.exists(p) for p in keep[2:]) and not os.path.exists(loose))
win.close(); db.close()

print("[2. «Quitarlas de la lista» y «Conservarlas»]")
os.remove(database_path())
for p in [loose] + in_folder: tone(p)
db = fresh_library()
shutil.rmtree(moved_dir)
expect(msg("ya no existe"), click("Conservarlas"))
win = mw.MainWindow(db); win.show(); spin(200); win.startup_checks(); spin(300)
check("«Conservarlas» deja las 12 en la lista", sum(1 for t in win.library if moved_dir in t.path) == 12)
expect(msg("ya no existe"), click("Quitarlas de la lista"))
win.startup_checks(); spin(300)
check("«Quitarlas de la lista» las quita", not any(moved_dir in t.path for t in win.library))

print("[3. Protecciones]")
win.prefs.remove_missing_on_start = False
os.remove(keep[5]); spin(50)
win._reload_library(); win.startup_checks(); spin(200)
check("con la opción desactivada no se quita nada", any(t.path == keep[5] for t in win.library))
win.prefs.remove_missing_on_start = True
# Conversión que se puede deshacer: el MP3 falta pero el original está guardado → no se quita
conv_track = next(t for t in win.library if t.path == keep[6])
s = converter.new_session([conv_track]); s.items[0].done = True; s.status = converter.STATUS_DONE; s.save()
db.update_track_paths([(conv_track.id, s.items[0].mp3)])  # la biblioteca apunta al MP3, que no existe
win._reload_library(); win.startup_checks(); spin(200)
check("una conversión que se puede deshacer se conserva", any(t.id == conv_track.id for t in win.library))
check("una canción suelta que falta sí se quita", not any(t.path == keep[5] for t in win.library))
# Más de la mitad de un disco falta: se pregunta
for p in keep[7:]: os.remove(p)
expect(msg("no se encuentran"), click("Conservarlas"))
win._reload_library(); win.startup_checks(); spin(300)
check("si falta más de la mitad de un disco, pregunta (y se conservan)", sum(1 for t in win.library if t.path in keep[7:]) == len(keep[7:]))

win.close()
check("todos los diálogos esperados aparecieron", not pending, pending)
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
