"""Localizar archivo: lo muestra si está, lo busca solo si se movió o renombró, nunca toma el de otra canción y
conserva las playlists. Todo en carpetas temporales: la búsqueda no recorre los discos de verdad."""
import os, shutil, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_localizar_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
import audio_sintetico as synth
from app import file_locator
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import locate_dialog, main_window as mw

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)

music = os.path.join(work, "Musica"); disk = os.path.join(work, "OtroDisco", "lejos", "muy lejos")
os.makedirs(music); os.makedirs(disk)
db = Database(database_path())
def add(name, seconds=2, title=None, artist="Lilly Goodman"):
    path = synth.mp3(os.path.join(music, name), seconds, title=title or os.path.splitext(name)[0], artist=artist)
    db.add_tracks([scan_file(path)[0]])
    return path, db.track_id_for_path(path)
def track(track_id):
    return next(t for t in db.all_tracks() if t.id == track_id)
def path_of(track_id):
    return db.conn.execute("select path from tracks where id=?", (track_id,)).fetchone()[0]

tiers = [[music], [os.path.join(work, "OtroDisco")]]
locate_dialog.search_tiers = lambda t, library: tiers
explorer = []
mw.subprocess.Popen = lambda *a, **k: explorer.append(a[0])
asked = []
real_ask, mw.ask = mw.ask, lambda parent, title, text, buttons, *a, **k: (asked.append(text), asked_answer[0])[1]
asked_answer = [1]
chosen_file = []
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (chosen_file.pop() if chosen_file else "", ""))
pick = []
QInputDialog.getItem = staticmethod(lambda parent, title, text, items, *a, **k: (pick.append(list(items)), items[-1], True)[1:])

win = mw.MainWindow(db); win.show(); spin(200)

print("[El archivo está en su sitio]")
here, here_id = add("Aquí - Lilly Goodman.mp3"); win._reload_library()
win._locate_track(track(here_id))
check("se muestra directo, seleccionado en el Explorador", explorer and "/select" in explorer[-1] and os.path.normpath(here) in explorer[-1], explorer[-1:])

print("[Se movió]")
moved, moved_id = add("Movida - Lilly Goodman.mp3")
playlist = db.create_playlist("Favoritas"); db.add_to_playlist(playlist.id, [moved_id])
target = os.path.join(disk, "Movida - Lilly Goodman.mp3"); shutil.move(moved, target); win._reload_library()
win._locate_track(track(moved_id)); spin(100)
check("lo encuentra aunque esté en otro disco", path_of(moved_id) == target, path_of(moved_id))
check("  y lo muestra", os.path.normpath(target) in explorer[-1], explorer[-1:])
check("  conserva la playlist", [t.id for t in db.playlist_tracks(playlist.id)] == [moved_id])
check("  sin preguntar nada", not asked, asked)

print("[Se renombró]")
renamed, renamed_id = add("Antes - Lilly Goodman.mp3", title="Santo Eres - Lilly Goodman")
target = os.path.join(disk, "cualquier nombre.mp3"); shutil.move(renamed, target); win._reload_library()
win._locate_track(track(renamed_id)); spin(100)
check("con otro nombre: lo reconoce por el título de su etiqueta", path_of(renamed_id) == target, path_of(renamed_id))
signs, signs_id = add("¿Quién - Lilly Goodman.mp3", title="Quién - Lilly Goodman")
target = os.path.join(music, "Quién - Lilly Goodman.mp3"); shutil.move(signs, target); win._reload_library()
win._locate_track(track(signs_id)); spin(100)
check("sin los signos del inicio, también", path_of(signs_id) == target, path_of(signs_id))

print("[Lo que no se debe tomar]")
twin, twin_id = add("Dudosa - Lilly Goodman.mp3")
short = os.path.join(disk, "Dudosa - Lilly Goodman.mp3"); os.remove(twin)
synth.mp3(short, 6, title="Dudosa - Lilly Goodman", artist="Lilly Goodman"); win._reload_library()
win._locate_track(track(twin_id)); spin(100)
check("mismo nombre pero otra duración: no es esa canción", path_of(twin_id) == twin and asked, path_of(twin_id))
check("  y avisa", asked and "No se encontró" in asked[-1], asked[-1:])
os.remove(short); asked.clear()
owner, owner_id = add("Dueña - Lilly Goodman.mp3")
lost_id = db.conn.execute("select id from tracks where id=?", (twin_id,)).fetchone()[0]
db.conn.execute("update tracks set title='Dueña - Lilly Goodman' where id=?", (lost_id,)); db.conn.commit(); win._reload_library()
win._locate_track(track(lost_id)); spin(100)
check("el archivo de otra canción de la biblioteca nunca se ofrece", path_of(lost_id) == twin and path_of(owner_id) == owner, path_of(lost_id))

print("[Varios posibles]")
asked.clear(); pick.clear()
many, many_id = add("Doble - Lilly Goodman.mp3"); near = os.path.join(disk, "Doble - Lilly Goodman.mp3")
shutil.move(many, near); far = os.path.join(work, "OtroDisco", "Doble - Lilly Goodman.mp3"); shutil.copy(near, far); win._reload_library()
win._locate_track(track(many_id)); spin(100)
check("se elige de una lista", pick and len(pick[-1]) == 2 and path_of(many_id) == pick[-1][-1], pick[-1:])

print("[La ventana de búsqueda se libera]")
from PySide6.QtCore import QCoreApplication, QEvent
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # lo que hace el programa al volver a su bucle
check("no queda para la recolección de basura, que cerraba el programa", not win.findChildren(locate_dialog.LocateDialog),
      len(win.findChildren(locate_dialog.LocateDialog)))

print("[Más cerca primero]")
close, close_id = add("Cerca - Lilly Goodman.mp3"); data = open(close, "rb").read(); os.remove(close)
near = os.path.join(music, "Cerca (copia) - Lilly Goodman.mp3"); open(near, "wb").write(data)
far = os.path.join(disk, "Cerca (copia) - Lilly Goodman.mp3"); open(far, "wb").write(data)
walked = []; real_walk = file_locator.FindFileWorker._walk
file_locator.FindFileWorker._walk = lambda self, root, found: (walked.append(root), real_walk(self, root, found))[1]
worker = file_locator.FindFileWorker(track(close_id), db.all_tracks(), tiers)
done = []; worker.finished.connect(lambda found, stopped: done.append((found, stopped))); worker.run()
file_locator.FindFileWorker._walk = real_walk
check("si lo encuentra cerca no sigue buscando", walked == [music] and done and done[0][0] == [near], (walked, done))
os.remove(near); os.remove(far)

print("[Detener]")
stopping = file_locator.FindFileWorker(track(close_id), db.all_tracks(), tiers)
done.clear(); stopping.finished.connect(lambda found, stopped: done.append((found, stopped))); stopping.cancel(); stopping.run()
check("se detiene y avisa", done == [([], True)], done)
real_tiers = file_locator.search_tiers(track(close_id), db.all_tracks())
check("en la búsqueda real van primero sus carpetas y al final los discos", real_tiers[0][0] == music and real_tiers[-1] and all(os.path.isabs(d) for d in real_tiers[-1]), real_tiers[-1])
check("  sin Papelera ni carpetas del sistema", {"$recycle.bin", "windows", "appdata"} <= file_locator._SKIPPED_FOLDERS)

print("[Detener en la ventana]")
asked.clear()
real_exec = locate_dialog.LocateDialog.exec
def stopped_exec(self):
    self.stopped = True
locate_dialog.LocateDialog.exec = stopped_exec
stop_id = close_id; win._reload_library()
win._locate_track(track(stop_id)); spin(50)
locate_dialog.LocateDialog.exec = real_exec
check("si la detienes sin resultados, no dice «no se encontró»", not asked, asked)

print("[A mano, si no aparece]")
asked.clear(); asked_answer[0] = 0
gone, gone_id = add("Perdida - Lilly Goodman.mp3"); data = open(gone, "rb").read(); os.remove(gone)
other_name = os.path.join(work, "OtroDisco", "desconocida.wav"); shutil.copy(here, other_name.replace(".wav", ".mp3")); other_name = other_name.replace(".wav", ".mp3")
db.conn.execute("delete from tracks where id=?", (here_id,)); db.conn.commit()
chosen_file.append(other_name); win._reload_library()
win._locate_track(track(gone_id)); spin(100)
check("se puede elegir el archivo y queda mostrado", path_of(gone_id) == other_name and os.path.normpath(other_name) in explorer[-1], path_of(gone_id))

mw.ask = real_ask
win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
