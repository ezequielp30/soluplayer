"""1.12.2: correcciones de la revisión completa (superpowers), cada una reproducida antes de corregirla.
Todo en carpetas temporales; nunca la biblioteca, los ajustes ni la música del usuario."""
import hashlib, math, os, struct, sys, tempfile, time, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_1122_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
import lameenc, numpy as np
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import mp3gain
from app.config import database_path
from app.database import Database
from app.file_operations import FileOperations
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))
    return path
def mp3(path, secs=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    e = lameenc.Encoder(); e.set_bit_rate(128); e.set_in_sample_rate(44100); e.set_channels(1); e.set_quality(2)
    pcm = (0.3 * np.sin(2 * np.pi * 440 * np.arange(44100 * secs) / 44100) * 32767).astype("<i2").tobytes()
    open(path, "wb").write(e.encode(pcm) + e.flush())
    return path
def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()

music = os.path.join(work, "Musica")
db = Database(database_path())
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
by_path = lambda p: next(t for t in db.all_tracks() if os.path.normcase(t.path) == os.path.normcase(p))

print("[B · La nota de volumen no se escribe sola en un MP3]")
song = mp3(os.path.join(music, "Volumen", "sin-ajustar.mp3"))
db.add_tracks([scan_file(song)[0]])
db.set_norm_gains([(by_path(song).id, 3.0)])  # biblioteca vieja (respaldo restaurado) que dice «ajustada +3 dB»
before = sha(song)
ops.sync_volume_annotations(db.all_tracks(), None)
check("al arrancar no se escribe nada en un MP3 que no tiene nota de ajuste", sha(song) == before and mp3gain.read_applied_steps(song) == 0)
check("  la biblioteca se corrige según el archivo (sin ajuste)", by_path(song).norm_gain_db == 0, by_path(song).norm_gain_db)

print("[C · Ajustes de ventana dañados en el registro]")
from app.ui import main_window as mw
settings = QSettings("ReproductorMusicaTest", "ReproductorMusica")
for key in ("window/geometry", "window/splitter"):
    settings.setValue(key, "basura de un limpiador de registro")
settings.setValue("import/last_dir", 12345)
settings.sync()
try:
    win = mw.MainWindow(db); win.show(); spin(200); opened = True; error = ""
except Exception as exc:
    win, opened, error = None, False, repr(exc)
check("con la geometría y el divisor dañados el programa abre igual", opened, error)
if win is not None:
    check("  se usa un directorio válido para importar aunque el guardado esté dañado", os.path.isdir(win._import_start_dir()), win._import_start_dir())
    win.close(); spin(100)

print("[C · Una canción dañada no detiene la lista]")
from app.models import Track
from app.player import PlaybackController
def wait_until(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond(): return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
    return cond()
def tr(i, path): return Track(id=i, path=path, title=os.path.basename(path), artist="", album="", genre="", duration_ms=1000, added_at="")
bad = os.path.join(music, "Cola", "danada.mp3"); os.makedirs(os.path.dirname(bad), exist_ok=True)
open(bad, "wb").write(b"\x00 no es audio " * 4000)
queue = [tr(101, tone(os.path.join(music, "Cola", "1.wav"))), tr(102, bad), tr(103, tone(os.path.join(music, "Cola", "3.wav")))]
player = PlaybackController()
modal, quiet = [], []
player.error_occurred.connect(lambda t, m: modal.append(t and t.id))
if hasattr(player, "track_failed"):
    player.track_failed.connect(lambda t, m: quiet.append(t and t.id))
player.play_queue(queue, 0)
reached = wait_until(lambda: player.current_track is not None and player.current_track.id == 103 and player.is_playing, 8000)
check("al llegar sola a una canción dañada pasa a la siguiente", reached, player.current_track and player.current_track.title)
check("  sin aviso que detenga la música; se informa aparte", modal == [] and quiet == [102], (modal, quiet))
modal.clear(); quiet.clear()
player.play_queue([queue[1]], 0)
check("si el usuario elige la dañada sí se le avisa", wait_until(lambda: modal == [102], 5000), (modal, quiet))
modal.clear(); quiet.clear()
player.set_repeat(1)  # repetir todo: sin el tope daría vueltas para siempre
bads = []
for n in (4, 5, 6):
    p = os.path.join(music, "Cola", f"danada{n}.mp3"); open(p, "wb").write(b"\x00 no es audio " * 4000); bads.append(tr(100 + n, p))
player.play_queue(bads, 0)
wait_until(lambda: modal == [104], 5000)
modal.clear(); quiet.clear()
player._advance(1, user=False)  # como si la anterior hubiera terminado sola
wait_until(lambda: modal, 8000)
check("si fallan todas seguidas se avisa una vez (no da vueltas sin fin)", modal == [104] and quiet == [105, 106], (modal, quiet))
player.set_repeat(0); player.release_source(); spin(100)
modal.clear(); quiet.clear()
g1, g2 = tr(111, tone(os.path.join(music, "Cola", "g1.wav"))), tr(112, tone(os.path.join(music, "Cola", "g2.wav")))
player.play_queue([g1, g2], 0)
on_g2 = wait_until(lambda: player.current_track.id == 112 and player.is_playing, 6000)  # llegó sola a la 2.ª
player.release_source()  # el usuario la mueve o la convierte…
open(g2.path, "wb").write(b"\x00 ahora rota " * 4000)
player.play()  # …y toca Reproducir: es una canción que eligió él
check("al tocar Reproducir sobre una que llegó sola y ya no sirve, sí se avisa", on_g2 and wait_until(lambda: modal == [112], 5000), (modal, quiet))
modal.clear(); quiet.clear()
chosen = tr(113, tone(os.path.join(music, "Cola", "elegida.wav")))
def user_picks_other(_t, _m):
    if not quiet[1:]:
        player.play_queue([chosen, g1], 0)  # el usuario elige otra justo antes de que se salte la dañada
player.track_failed.connect(user_picks_other)
player.play_queue([g1, tr(114, bad), g1], 0)
wait_until(lambda: quiet, 6000); spin(300)
player.track_failed.disconnect(user_picks_other)
check("  saltar la dañada no se salta también la que el usuario acaba de elegir", player.current_track is not None and player.current_track.id == 113,
      player.current_track and player.current_track.id)
player.release_source(); spin(100)

print("[C · Cerrar la ventana durante una importación]")
many = os.path.join(music, "Muchas")
for n in range(150):
    tone(os.path.join(many, f"tono{n:03}.wav"))
db2 = Database(os.path.join(work, "data", "otra.db"))
win2 = mw.MainWindow(db2); win2.show(); spin(200)
errors = []
old_hook = sys.excepthook
sys.excepthook = lambda t, e, tb: errors.append(repr(e))
from app.ui.dialogs import ImportReportDialog
win2._start_import(folder=many, recursive=True); spin(150)
win2.close(); spin(1500)
sys.excepthook = old_hook
reports = [w for w in app.topLevelWidgets() if isinstance(w, ImportReportDialog) and w.isVisible()]
check("cerrar a mitad de una importación no da error ni usa la biblioteca ya cerrada", errors == [] and not reports, (errors, reports))

import shutil, sqlite3
from app import library_cleanup, review_folder
from app.file_operations import KIND_FILES
db3 = Database(os.path.join(work, "data", "mover.db"))
ops3 = FileOperations(db3, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
by_path3 = lambda p: next(t for t in db3.all_tracks() if os.path.normcase(t.path) == os.path.normcase(p))

print("[A · Mover a otro disco: si la biblioteca falla, el archivo vuelve de verdad]")
other = tempfile.mkdtemp(prefix="_mp_1122_", dir="D:\\") if os.path.splitdrive(work)[0].upper() != "D:" else tempfile.mkdtemp(prefix="_mp_1122_", dir="C:\\Users\\Public")
try:
    src = tone(os.path.join(music, "Mover", "vuelve.wav"))
    db3.add_tracks([scan_file(src)[0]])
    real_update = db3.update_track_paths
    db3.update_track_paths = lambda changes: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked"))
    r = ops3.move_tracks([by_path3(src)], other)
    db3.update_track_paths = real_update
    check("el archivo vuelve a su carpeta y no queda copia en el otro disco",
          os.path.exists(src) and not os.listdir(other), (os.path.exists(src), os.listdir(other)))
    check("  se informa el fallo y la biblioteca sigue apuntando al original", r.failed and by_path3(src).path == src, r.failed)
finally:
    shutil.rmtree(other, ignore_errors=True)

print("[A · Corte de luz a mitad de «Mover a otra carpeta»]")
class Corte(BaseException):
    pass
dest = os.path.join(music, "Destino"); os.makedirs(dest)
moving = [tone(os.path.join(music, "Mover", f"m{n}.wav")) for n in (1, 2, 3)]
db3.add_tracks([scan_file(p)[0] for p in moving])
pl = db3.create_playlist("Para el auto"); db3.add_to_playlist(pl.id, [by_path3(p).id for p in moving])
ids = [by_path3(p).id for p in moving]
calls = []
def cut(changes):
    calls.append(changes)
    if len(calls) == 2:
        raise Corte()  # se corta la luz justo después de mover la 2.ª (o con todas ya movidas, como antes)
    return real_update(changes)
db3.update_track_paths = cut
try:
    ops3.move_tracks([by_path3(p) for p in moving], dest)
except Corte:
    pass
db3.update_track_paths = real_update
# al abrir otra vez el programa
reconcile = getattr(ops3, "reconcile_interrupted_moves", None)
if reconcile is not None:
    reconcile()
lib = db3.all_tracks()
here = {t.id: t.path for t in lib}
moved_now = [p for p in moving if not os.path.exists(p)]
check("las canciones ya movidas apuntan a su lugar nuevo al abrir",
      moved_now and all(os.path.exists(here[i]) for i in ids), {os.path.basename(here[i]): os.path.exists(here[i]) for i in ids})
plan = library_cleanup.plan_missing(lib, ops3.undoable_track_ids())
check("  no se ofrece quitar ninguna (siguen en la playlist)", not plan.remove and len(db3.playlist_tracks(pl.id)) == 3, [t.path for t in plan.remove])
entries = [e for e in ops3.history(lib) if e.kind == KIND_FILES and e.title == "Mover a otra carpeta" and e.can_undo]
check("  el movimiento interrumpido queda en el Historial y se puede deshacer", entries and entries[0].count == len(moved_now),
      [(e.title, e.count) for e in entries])

print("[A · «Reunir repetidas» interrumpida: sus canciones no se ofrecen para quitar]")
dup = tone(os.path.join(music, "Rep", "copia.wav"))
db3.add_tracks([scan_file(dup)[0]])
dup_id = by_path3(dup).id
review = os.path.join(music, "_Repetidas para revisar", "copia"); os.makedirs(review)
moved_to = os.path.join(review, "copia.wav")
session = review_folder.Session(id="prueba", destination=os.path.dirname(review), status=review_folder.STATUS_RUNNING,
                                created_at="2026-10-25T10:00:00", moves=[review_folder.Move(dup_id, dup, moved_to, done=False)])
session.save()
os.rename(dup, moved_to)  # el corte llegó después de mover y antes de anotarlo
check("la canción reunida está protegida de «quitar faltantes»", dup_id in ops3.undoable_track_ids())
session.status = review_folder.STATUS_DONE; session.moves[0].done = True; session.save()
check("  también si la reunión quedó «Hecha» sin llegar a guardar la biblioteca", dup_id in ops3.undoable_track_ids())

print("[A · Movimiento interrumpido hacia un disco que al abrir no está conectado]")
from app import file_history
import string
offline = next(c for c in reversed(string.ascii_uppercase) if not os.path.exists(c + ":\\"))
usb = tone(os.path.join(music, "Mover", "al-usb.wav"))
db3.add_tracks([scan_file(usb)[0]])
usb_id = by_path3(usb).id
os.remove(usb)  # ya llegó al pendrive (que ahora no está conectado): no está ni en el origen ni en el destino visible
planned = file_history.begin(file_history.KIND_MOVE, [file_history.Change(usb, f"{offline}:\\Pendrive\\al-usb.wav", [usb_id])])
ops3.reconcile_interrupted_moves()
still = [s for s in file_history.interrupted_sessions() if s.id == planned.id]
check("el plan no se borra mientras no se puede saber dónde quedó", bool(still))
check("  y esa canción no se ofrece para quitar", usb_id in ops3.undoable_track_ids())
file_history.finish(planned, [])

print("[B · Antes de corregir un ajuste de volumen en la biblioteca se hace un respaldo]")
from app import backup
song2 = mp3(os.path.join(music, "Volumen", "sin-nota.mp3"))
db3.add_tracks([scan_file(song2)[0]])
db3.set_norm_gains([(by_path3(song2).id, 4.5)])
before_backups = set(os.listdir(backup.backup_dir()))
ops3.sync_volume_annotations(db3.all_tracks(), None)
new_backups = [n for n in os.listdir(backup.backup_dir()) if n not in before_backups]
check("hay un respaldo de la biblioteca con el ajuste que se corrige", any("volumen" in n for n in new_backups), new_backups)
db3.close()

print("[C · Un disco desconectado no congela la ventana]")
import string
used = {d[0] for d in os.listdrives()} if hasattr(os, "listdrives") else set()
free = next(c for c in reversed(string.ascii_uppercase) if c not in used and not os.path.exists(c + ":\\"))
gone = [tr(200 + n, f"{free}:\\Musica\\Album{n // 10}\\{n}.mp3") for n in range(40)]
ok_song = tr(299, tone(os.path.join(music, "Red", "buena.wav")))
asked = []
real_isfile, real_exists = os.path.isfile, os.path.exists
def counting(fn):
    def wrapper(p, *a):
        if str(p).upper().startswith(free + ":"):
            asked.append(p)  # en una red real, cada una de estas consultas puede esperar varios segundos
        return fn(p, *a)
    return wrapper
os.path.isfile, os.path.exists = counting(real_isfile), counting(real_exists)
try:
    player.play_queue(gone + [ok_song], 0)
    in_player = len(asked); asked.clear()
    win3 = mw.MainWindow(Database(os.path.join(work, "data", "red.db"))); win3.show(); spin(100)
    win3._on_shuffle_play(gone + [ok_song])
    in_shuffle = len(asked)
finally:
    os.path.isfile, os.path.exists = real_isfile, real_exists
check("la cola salta las canciones del disco que no responde sin consultarlo una por una",
      player.current_track is not None and player.current_track.id == 299 and in_player <= 2, f"{in_player} consultas")
check("  «aleatorio» tampoco lo consulta canción por canción", in_shuffle <= 6, f"{in_shuffle} consultas")
player.release_source(); win3.close(); spin(100)

print("[C · Ecualizador: si se pierde la salida de audio no queda «sonando» mudo]")
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudio, QAudioOutput, QMediaPlayer
from app.eq_player import EqPlayer
out = QAudioOutput()
eq = EqPlayer(out)
eq_errors = []
eq.errorOccurred.connect(lambda *a: eq_errors.append(a))
eq.setSource(QUrl.fromLocalFile(tone(os.path.join(music, "Eq", "larga.wav"), secs=8))); eq.play()
playing = wait_until(lambda: eq.playbackState() == QMediaPlayer.PlaybackState.PlayingState and eq.position() > 300, 8000)
sink = eq._sink
if playing and sink is not None:
    sink.error = lambda: QAudio.Error.IOError  # como al desconectar los auriculares USB o volver de suspensión
    sink.stateChanged.emit(QAudio.State.StoppedState)
    spin(200)
check("pasa a «Pausa» (la barra no muestra que suena cuando no suena)", playing and eq.playbackState() == QMediaPlayer.PlaybackState.PausedState,
      eq.playbackState())
check("  no se toma como error de la canción (no se salta a la siguiente)", eq_errors == [], eq_errors)
at = eq.position()
eq.play()
check("  al tocar Reproducir sigue desde el mismo punto", wait_until(lambda: eq.playbackState() == QMediaPlayer.PlaybackState.PlayingState
      and eq.position() >= at, 5000) and abs(eq.position() - at) < 1500, (at, eq.position()))
eq.stop(); eq.setSource(QUrl()); spin(100)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
db.close()
sys.exit(0 if all(results) else 1)
