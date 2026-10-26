"""1.12.0: Historial de renombres y movimientos (con deshacer), limpieza de temporales sobrantes al abrir,
revisión rápida de qué canciones existen, y textos de Qt en español. Todo en carpetas temporales."""
import math, os, shutil, struct, sys, tempfile, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_hist_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import file_history, library_cleanup
from app.config import database_path
from app.database import Database, available_paths
from app.file_operations import KIND_FILES, FileOperations
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def tone(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000)))
    return path

music = os.path.join(work, "Musica")
a = tone(os.path.join(music, "Rock", "uno.wav"))
b = tone(os.path.join(music, "Rock", "dos.wav"))
c = tone(os.path.join(music, "Pop", "tres.wav"))
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in (a, b, c)])
pl = db.create_playlist("Favoritas"); db.add_to_playlist(pl.id, [t.id for t in db.all_tracks()])
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
by_path = lambda p: next(t for t in db.all_tracks() if os.path.normcase(t.path) == os.path.normcase(p))
def entry(title):
    return next(e for e in ops.history(db.all_tracks()) if e.kind == KIND_FILES and e.title == title and e.can_undo)

print("[Renombrar un archivo y deshacer]")
new_path = ops.rename_track_file(by_path(a), "primera")
e = entry("Renombrar archivo")
check("el renombre aparece en el Historial y se puede deshacer", e.detail == "uno.wav → primera.wav", e.detail)
out = ops.undo(e)
check("deshacer: vuelve el nombre y la biblioteca con él", os.path.exists(a) and not os.path.exists(new_path) and any(t.path == a for t in db.all_tracks()), out.message)
check("  la playlist sigue con las 3 canciones", len(db.playlist_tracks(pl.id)) == 3)
check("  ya no figura como para deshacer", not any(x.kind == KIND_FILES and x.can_undo for x in ops.history(db.all_tracks())))

print("[Renombrar una carpeta y deshacer]")
rock = os.path.join(music, "Rock")
new_folder = ops.rename_folder(rock, "Rock clásico", db.all_tracks())
check("las canciones pasan a la carpeta nueva", all(t.path.startswith(new_folder) for t in db.all_tracks() if "uno" in t.path or "dos" in t.path))
ops.undo(entry("Renombrar carpeta"))
check("deshacer: la carpeta y sus 2 canciones vuelven", os.path.isdir(rock) and not os.path.exists(new_folder)
      and sum(1 for t in db.all_tracks() if os.path.dirname(t.path) == rock) == 2)

print("[Mover a otro disco y deshacer]")
other = tempfile.mkdtemp(prefix="_mp_hist_", dir="D:\\")
res = ops.move_tracks([by_path(c)], other)
moved = os.path.join(other, "tres.wav")
check("se movió a otro disco", res.moved and os.path.exists(moved) and not os.path.exists(c), res.failed)
ops.undo(entry("Mover a otra carpeta"))
check("deshacer: vuelve a su carpeta (y la biblioteca)", os.path.exists(c) and not os.path.exists(moved) and any(t.path == c for t in db.all_tracks()))
shutil.rmtree(other, ignore_errors=True)  # en cuanto se termina con ella (no esperar al final)

print("[Deshacer nunca pisa nada]")
ops.rename_track_file(by_path(b), "segunda")
tone(b)  # alguien puso otro archivo con el nombre original
latest = next(x for x in ops.history(db.all_tracks()) if x.kind == KIND_FILES and x.session.changes[0].target.endswith("segunda.wav"))
check("si el lugar original está ocupado, el Historial ya no ofrece deshacer", not latest.can_undo, latest.status)
restored, problems = file_history.undo(latest.session, on_restored=lambda _c: None)  # forzado
check("  y aun forzándolo no se toca nada (se avisa)", not restored and problems and os.path.exists(os.path.join(rock, "segunda.wav")), problems)

print("[Temporales sobrantes al abrir]")
leftovers = [os.path.join(rock, n) for n in ("x.mp3.convirtiendo.tmp", "y.mp3.ajuste-volumen.tmp", "z.wav.moviendo.tmp")]
for p in leftovers: open(p, "wb").write(b"a medias")
keep = os.path.join(rock, "notas.tmp"); open(keep, "wb").write(b"del usuario")
removed = library_cleanup.remove_leftover_temps(db.all_tracks())
check("se borran los temporales que deja el programa", sorted(removed) == sorted(leftovers) and not any(os.path.exists(p) for p in leftovers), removed)
check("  y ningún otro archivo (p. ej. «notas.tmp» del usuario)", os.path.exists(keep))

print("[Revisión rápida de qué canciones existen]")
paths = [t.path for t in db.all_tracks()] + [os.path.join(rock, "no-existe.wav"), r"Q:\Musica\x.wav"]
check("detecta igual que mirar archivo por archivo", available_paths(paths) == {p for p in paths if os.path.isfile(p)})
check("  sin distinguir mayúsculas (como Windows)", available_paths([a.upper()]) == {a.upper()})

print("[Textos de Qt en español]")
from app.application import _install_spanish
_install_spanish(app)
copy, cancel = QCoreApplication.translate("QLineEdit", "&Copy"), QCoreApplication.translate("QPlatformTheme", "Cancel")
check("el menú del clic derecho y los botones estándar salen en español", copy == "&Copiar" and cancel == "Cancelar", (copy, cancel))

QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
db.close(); shutil.rmtree(work, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
