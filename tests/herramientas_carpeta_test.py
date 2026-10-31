"""Herramientas: primero se elige qué analizar (toda la biblioteca o una carpeta, con «Seleccionar carpeta…») y,
cuando la herramienta crea o mueve archivos, la carpeta destino se puede cambiar. Todo en carpetas temporales."""
import math, os, struct, sys, tempfile, time, wave
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_herramientas_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import converter
from app.config import database_path
from app.database import Database
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, freq=440, secs=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / 8000))) for i in range(8000 * secs)))
    return path

rock = os.path.join(work, "Musica", "Rock")
pop = os.path.join(work, "Musica", "Pop")
otra = os.path.join(work, "Otra")
files = [tone(os.path.join(rock, f"r{n}.wav"), 300 + n * 50) for n in range(3)] + \
        [tone(os.path.join(pop, f"p{n}.wav"), 600 + n * 50) for n in range(2)]
os.makedirs(otra)
os.makedirs(os.path.dirname(database_path()), exist_ok=True)
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in files])
from app.ui import main_window as mw
from app.ui.dialogs import FolderScopeDialog
win = mw.MainWindow(db); win.show(); spin(300)

print("[¿Qué analizar?]")
count = lambda folder: len(win.library) if folder is None else len(win.ops.tracks_in(folder, win.library))
d = FolderScopeDialog("Canciones repetidas", count, None, work, win)
check("sin carpeta elegida, propone toda la biblioteca", d.all_songs.isChecked() and d.folder() is None and d.btn_ok.isEnabled())
check("  y dice cuántas canciones", "5 canciones" in d.all_songs.text(), d.all_songs.text())
check("tiene el botón «Seleccionar carpeta…»", d.btn_choose.text() == "Seleccionar carpeta…")
d.one_folder.setChecked(True)
check("«Una carpeta» sin elegirla todavía: no deja continuar", not d.btn_ok.isEnabled() and "Seleccionar carpeta" in d.detail.text())
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: rock)
d.btn_choose.click()
check("al seleccionar una carpeta: la muestra, cuenta sus canciones y deja continuar",
      d.folder() == os.path.normpath(rock) and "3 canciones" in d.detail.text() and d.btn_ok.isEnabled(), d.detail.text())
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: otra)
d.btn_choose.click()
check("una carpeta sin canciones en la biblioteca: lo explica y no deja continuar",
      not d.btn_ok.isEnabled() and "no tiene canciones" in d.detail.text())
d.deleteLater()
d = FolderScopeDialog("Convertir a MP3", count, pop, work, win)
check("si estás viendo una carpeta, la propone", d.one_folder.isChecked() and d.folder() == pop)
d.deleteLater()

def answer_scope(folder):
    """Contesta el primer paso de la próxima herramienta eligiendo `folder` (None = toda la biblioteca)."""
    def go():
        box = QApplication.activeModalWidget()
        if not isinstance(box, FolderScopeDialog):
            QTimer.singleShot(30, go); return
        if folder is None:
            box.all_songs.setChecked(True)
        else:
            QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: folder)
            box.btn_choose.click()
        box.btn_ok.click()
    QTimer.singleShot(50, go)

answer_scope(rock)
scope = win._choose_scope("Canciones repetidas")
tracks, folder = scope
check("con una carpeta elegida, la herramienta ve solo sus canciones (y sus subcarpetas)",
      folder == os.path.normpath(rock) and sorted(t.path for t in tracks()) == sorted(files[:3]),
      [os.path.basename(t.path) for t in tracks()])
answer_scope(None)
tracks, folder = win._choose_scope("Canciones repetidas")
check("con «Toda la biblioteca», todas", folder is None and len(tracks()) == 5)

class Fake(QDialog):
    pass
fake = Fake(); fake.setWindowTitle("Canciones repetidas")
check("el título de la herramienta dice qué carpeta analiza",
      win._scoped_title(fake, rock).windowTitle() == "Canciones repetidas — carpeta «Rock»", fake.windowTitle())

opened = []
orig_run = win._run_dialog
def capture(dialog):
    if isinstance(dialog, FolderScopeDialog):
        return orig_run(dialog)
    opened.append((type(dialog).__name__, dialog.windowTitle())); dialog.deleteLater(); return 0
win._run_dialog = capture
for tool, opener in (("Canciones repetidas", win._open_duplicates), ("Analizar y ajustar volumen", win._open_loudness),
                     ("Convertir a MP3", win._open_convert)):
    answer_scope(pop); opener(); spin(100)
check("Herramientas → repetidas, volumen y convertir: preguntan la carpeta y la muestran en su título",
      [t for _n, t in opened] == ["Canciones repetidas — carpeta «Pop»", "Analizar y ajustar volumen — carpeta «Pop»",
                                  "Convertir a MP3 — carpeta «Pop»"], opened)
def cancel_scope():
    def go():
        box = QApplication.activeModalWidget()
        if not isinstance(box, FolderScopeDialog):
            QTimer.singleShot(30, go); return
        box.reject()
    QTimer.singleShot(50, go)
opened.clear(); cancel_scope(); win._open_duplicates(); spin(100)
check("Cancelar en el primer paso no abre la herramienta", not opened)
win._run_dialog = orig_run

print("[Carpeta destino]")
asked = []
def answers(*choices):
    queue = list(choices)
    def fake(parent, title, text, buttons, icon=None, informative=""):
        asked.append((title, text, informative, [b[0] for b in buttons])); return queue.pop(0)
    return fake
from app.duplicates import DuplicateGroup
rock_tracks = win.ops.tracks_in(rock, win.library)
groups = [DuplicateGroup(rock_tracks[:2], rock_tracks[0].id)]
mw.ask = answers(2)
win._gather_for_review(groups)
check("repetidas: la carpeta de revisión se propone en la carpeta analizada",
      os.path.join(rock, "_Repetidas para revisar") in asked[-1][2] and "Elegir otra carpeta…" in asked[-1][3], asked[-1][2][:80])

dest_parent = os.path.join(work, "Destino")
os.makedirs(dest_parent)
target = os.path.join(dest_parent, "_Volumen sin igualar")
pop_tracks = win.ops.tracks_in(pop, win.library)
outcome = win.ops.set_aside([(pop_tracks[0], "Otro formato")], win.library, target)
win._reload_library()
moved_path = os.path.join(target, os.path.basename(pop_tracks[0].path))
check("volumen → apartar: va a la carpeta destino elegida", outcome.folder == target and os.path.isfile(moved_path)
      and not os.path.exists(pop_tracks[0].path), (outcome.folder, outcome.failed))
check("  y la biblioteca sigue a la canción", db.track_id_for_path(moved_path) == pop_tracks[0].id)
check("  sin carpeta elegida usa la de siempre (carpeta principal)",
      win.ops.set_aside_folder(win.library).endswith("_Volumen sin igualar"))

session = converter.new_session(rock_tracks, db.known_path_keys())
check("convertir: propone guardar los originales junto a la música", session.originals_root.startswith(os.path.normpath(rock)), session.originals_root)
session.originals_root = os.path.join(dest_parent, converter.ORIGINALS_FOLDER_NAME)
where = converter.original_target(session.items[0], session.originals_root)
check("  con otra carpeta destino elegida, el original va allí", where.startswith(session.originals_root), where)

from app.ui import convert_dialog as cd
asked.clear()
dlg = cd.ConvertDialog(win.ops, lambda: win.ops.tracks_in(rock, win.library), win)
cd.ask = answers(1, 2)
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: dest_parent)
dlg._convert()
texts = [a[2] for a in asked]
check("convertir: «Elegir otra carpeta…» cambia el destino de los originales antes de confirmar",
      len(asked) == 2 and "Elegir otra carpeta…" in asked[0][3] and dest_parent in texts[1], texts[-1][:120] if texts else asked)
check("  y Cancelar no convierte nada", all(os.path.isfile(p) for p in files[:3]))
dlg.deleteLater()

win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
