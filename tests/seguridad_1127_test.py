"""1.12.7: correcciones de la auditoría de seguridad y privacidad, cada una reproducida antes de corregirla.
Todo en carpetas temporales: nunca la biblioteca, los Documentos ni las carpetas reales del usuario."""
import logging, math, os, shutil, struct, sys, tempfile, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_seg_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from PySide6.QtGui import Qt as _Qt
from app import backup, file_manager
from app.config import database_path
from app.database import Database
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
def looks_html(text):
    return _Qt.mightBeRichText(text)

music = os.path.join(work, "Musica")
db = Database(database_path())

print("[Etiquetas que parecen HTML no se dibujan como HTML]")
evil = '<img src="file://atacante.example/s/a.png">'
song = tone(os.path.join(music, "rara.wav"))
db.add_tracks([scan_file(song)[0]])
tid = db.all_tracks()[0].id
db.update_track_info(tid, title=evil, artist=evil, album=evil)  # p. ej. un MP3 con etiquetas preparadas
t = db.all_tracks()[0]
check("título, artista y álbum de la biblioteca nunca parecen HTML", not any(looks_html(x) for x in (t.title, t.artist, t.album)),
      (t.title, t.artist, t.album))
check("  y se siguen leyendo casi igual", "img src" in t.title, t.title)

print("[Playlists ajenas con rutas de red]")
from app import playlist_files as pf
m3u = os.path.join(work, "ajena.m3u8")
open(m3u, "w", encoding="utf-8").write("#EXTM3U\n#PLAYLIST:<b>Fiesta</b>\n\\\\atacante.example\\share\\x.mp3\n//otro.example/s/y.mp3\n" + song + "\n")
touched = []
real_isfile, real_exists = os.path.isfile, os.path.exists
def spy(fn):
    def wrapper(p, *a):
        if str(p).startswith(("\\\\", "//")):
            touched.append(p)
        return fn(p, *a)
    return wrapper
os.path.isfile, os.path.exists = spy(real_isfile), spy(real_exists)
try:
    plans = pf.plan_restore(pf.read_folder(work), db.all_tracks())
finally:
    os.path.isfile, os.path.exists = real_isfile, real_exists
check("al revisar una playlist ajena no se consulta ninguna ruta de red", touched == [], touched)
plan = next(p for p in plans if "Fiesta" in p.name)
check("  esas canciones cuentan como no encontradas", plan.found == 1 and plan.missing == 2, (plan.found, plan.missing))
check("  y el nombre de la playlist no parece HTML", not looks_html(plan.name), plan.name)
big = os.path.join(work, "enorme", "gigante.m3u8"); os.makedirs(os.path.dirname(big))
with open(big, "wb") as f:
    f.write(b"#EXTM3U\n" + b"C:\\x.mp3\n" * 3_000_000)  # unos 27 MB
start = time.time()
found = pf.read_folder(os.path.dirname(big))
check("una «playlist» enorme se omite (no se carga entera en memoria)", found == [] and time.time() - start < 5, len(found))

print("[Carpetas importantes protegidas]")
guard = getattr(file_manager, "protected_reason", None)
home = os.path.expanduser("~")
cases = [home, os.path.join(home, "Documents"), os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
         os.path.join(home, "Music"), os.path.splitdrive(home)[0] + "\\", os.path.dirname(home)]
refused = [c for c in cases if guard is not None and guard(c)]
check("el perfil, Documentos, Escritorio, Descargas, Música, la raíz y la carpeta de usuarios están protegidas",
      len(refused) == len(cases), [c for c in cases if c not in refused])
check("  una carpeta de música cualquiera no", guard is not None and not guard(music))
if guard is not None:
    fake = os.path.join(work, "FalsoEscritorio"); os.makedirs(fake); open(os.path.join(fake, "nota.txt"), "w").write("x")
    real_list = file_manager._protected_folders
    file_manager._protected_folders = lambda: [fake]  # sin tocar nunca las carpetas reales
    errors = []
    for action in (lambda: file_manager.trash_folder(fake), lambda: file_manager.rename_folder(fake, "Otro")):
        try:
            action(); errors.append("no se negó")
        except file_manager.FileManagerError as exc:
            errors.append(str(exc))
    file_manager._protected_folders = real_list
    check("  enviar a la Papelera o renombrar una protegida se niega y no la toca", os.path.isdir(fake)
          and all("protegida" in e or "Windows" in e for e in errors), errors)
else:
    check("  enviar a la Papelera o renombrar una protegida se niega y no la toca", False, "sin protección")

print("[En los avisos que borran, el botón marcado es «Cancelar»]")
from app.ui.dialogs import ask
seen = []
def peek():
    box = QApplication.activeModalWidget()
    if box is None:
        QTimer.singleShot(50, peek); return
    seen.append(box.defaultButton().text() if box.defaultButton() else "")
    box.reject()
QTimer.singleShot(100, peek)
ask(None, "Enviar a la Papelera", "¿Seguro?", [("Enviar a la Papelera", QMessageBox.ButtonRole.DestructiveRole),
                                              ("Cancelar", QMessageBox.ButtonRole.RejectRole)])
check("con un Enter de más no se borra nada", seen == ["Cancelar"], seen)

print("[Respaldos también fuera de la carpeta del programa]")
docs_copy = os.path.join(work, "Documentos", "Respaldos")
os.environ["MUSICPLAYER_BACKUPS_COPY_DIR"] = docs_copy
for n in range(5):
    for f in backup.list_backups():
        f.unlink()  # sin respaldo de hoy: backup_if_due lo hace (como al abrir el programa cada día)
    backup.backup_if_due(db.conn)
    time.sleep(1.1)  # cada respaldo con su segundo
mine = str(backup.outside_copies_dir()) if hasattr(backup, "outside_copies_dir") else docs_copy
copies = sorted(f for f in os.listdir(mine) if f.endswith(".db")) if os.path.isdir(mine) else []
check("el respaldo diario se copia también a Documentos", copies and copies[-1] == backup.list_backups()[0].name, copies)
check("  y allí se guardan solo los 3 más recientes", len(copies) == 3, len(copies))
check("  en una subcarpeta de esta PC (con OneDrive, otra PC no la pisa ni la ofrece)",
      os.path.normcase(os.path.dirname(os.path.join(mine, "x"))) != os.path.normcase(docs_copy)
      and os.environ.get("COMPUTERNAME", "").lower() in mine.lower(), mine)
lost = os.path.join(work, "perdida", "biblioteca.db")  # como si se hubiera borrado la carpeta del programa
os.makedirs(os.path.dirname(lost))
from app import application
offer = getattr(application, "_offer_outside_copy", None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
if offer is not None:
    offer(__import__("pathlib").Path(lost))
check("al abrir sin biblioteca, se ofrece recuperarla desde la copia de Documentos", os.path.exists(lost)
      and backup.check_database(lost) is None)

print("[Lo que se escribe conserva el texto original]")
tid2 = db.all_tracks()[0].id
db.update_track_info(tid2, title="Te quiero <3", artist="A>B", album="Álbum")
raw = db.with_raw_text(db.all_tracks())[0] if hasattr(db, "with_raw_text") else db.all_tracks()[0]
check("la conversión y los datos de internet usan el título original («<3», no «‹3»)", raw.title == "Te quiero <3" and raw.artist == "A>B",
      (raw.title, raw.artist))
check("  y en pantalla se ve la versión segura", db.all_tracks()[0].title == "Te quiero ‹3", db.all_tracks()[0].title)
from app.online_lookup import Candidate
c = Candidate("musicbrainz", '<img src="file://x/y.png">', "<b>A</b>", "<i>B</i>", 1000)
check("los datos que llegan de internet nunca parecen HTML", not any(looks_html(x) for x in (c.title, c.artist, c.album)), c.title)
pl_evil = db.create_playlist("x")
with db.conn:
    db.conn.execute("UPDATE playlists SET name = ? WHERE id = ?", ("<img src=x>", pl_evil.id))  # de antes de 1.12.7
check("los nombres de playlist guardados antes tampoco", not any(looks_html(p.name) for p in db.playlists()), [p.name for p in db.playlists()])
db.delete_playlist(pl_evil.id)

print("[Carpetas protegidas: nombres cortos, Pública y aviso antes de confirmar]")
import ctypes
buf = ctypes.create_unicode_buffer(32768)
short_home = buf.value if ctypes.windll.kernel32.GetShortPathNameW(os.path.expanduser("~"), buf, 32768) else ""
check("el perfil escrito con su nombre corto también está protegido", not short_home or bool(file_manager.protected_reason(short_home)), short_home)
public = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Music")
check("  las carpetas de Acceso público también", bool(file_manager.protected_reason(public)), public)
reason = file_manager.protected_reason(os.path.expanduser("~"))
check("  el aviso muestra el nombre tal cual (no en minúsculas)", os.path.basename(os.path.expanduser("~")) in reason, reason)

print("[Privacidad y convivencia]")
from app.preferences import Preferences
fresh = Preferences(QSettings("ReproductorMusicaTest", "PrefsNuevas"))
check("las teclas multimedia globales vienen apagadas (no se les quitan a YouTube o Spotify)", fresh.global_media_keys is False)
records = []
class Catch(logging.Handler):
    def emit(self, r): records.append(r)
catcher = Catch(level=logging.INFO); logging.getLogger().addHandler(catcher); logging.getLogger().setLevel(logging.INFO)
from app.player import PlaybackController
player = PlaybackController()
player.play_queue(db.all_tracks(), 0); spin(500); player.release_source()
logging.getLogger().removeHandler(catcher)
listened = [r.getMessage() for r in records if r.levelno >= logging.INFO and song in r.getMessage()]
check("el registro del programa no guarda qué canciones se escucharon", listened == [], listened)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
db.close()
shutil.rmtree(work, ignore_errors=True)
sys.exit(0 if all(results) else 1)
