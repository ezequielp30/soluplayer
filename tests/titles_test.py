import math, os, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_titles_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")

from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()

from app.titles import suggest_from_filename
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw
from app.ui.dialogs import FolderImportDialog, ImportReportDialog, PreferencesDialog, TitleReviewDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

# ---- propuestas desde el nombre de archivo
for name, expected in [
    ("03 - Queen - Bohemian Rhapsody.mp3", ("Bohemian Rhapsody", "Queen")),
    ("07_mi_cancion.flac", ("mi cancion", None)),
    ("01. Intro.wav", ("Intro", None)),
    ("Soda Stereo - De música ligera.m4a", ("De música ligera", "Soda Stereo")),
    ("CD1-04 Tema.mp3", ("Tema", None)),
    ("2001.mp3", ("2001", None)),
]:
    got = suggest_from_filename(name)
    check(f"propuesta para «{name}»", got == expected, got)
check("sin detectar artista", suggest_from_filename("Queen - Song.mp3", False) == ("Queen - Song", None))

# ---- archivos de prueba: tonos sin etiquetas + uno con título
def tone(path):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(5000*math.sin(i/3))) for i in range(8000)))
folders = []
for n in range(3):
    d = os.path.join(work, f"carpeta{n}"); os.makedirs(d); folders.append(d)
tone(os.path.join(folders[0], "05 - Sin preferencia.wav"))
tone(os.path.join(folders[1], "03 - Queen - Bohemian Rhapsody.wav"))
tone(os.path.join(folders[1], "07_mi_cancion.wav"))
tagged = os.path.join(folders[1], "con_titulo.wav"); tone(tagged)
from mutagen.wave import WAVE; from mutagen.id3 import TIT2
wf = WAVE(tagged); wf.add_tags(); wf.tags.add(TIT2(encoding=3, text="Título de la etiqueta")); wf.save()
tone(os.path.join(folders[2], "09 - Otro - Omitida.wav"))

# ---- automatización de diálogos
pending = []
def expect(cls, handler): pending.append((cls, handler))
def pump():
    QTimer.singleShot(40, pump)
    w = QApplication.activeModalWidget()
    if pending and w is not None and w.isVisible() and isinstance(w, pending[0][0]):
        _, h = pending.pop(0)
        try: h(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, pump)
def wait_until(cond, timeout=10000):
    end = time.time() + timeout/1000
    while time.time() < end and not cond():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
    return cond()

answers = []
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: answers.pop(0))
db = Database(database_path()); win = mw.MainWindow(db); win.show()
def action(text):
    for top in win.menuBar().actions():
        for a in top.menu().actions():
            if a.text().replace("&", "") == text: return a

review = {}
def import_folder(folder):
    done = {}
    answers.append(folder)
    expect(FolderImportDialog, lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
    expect(ImportReportDialog, lambda d: (done.setdefault("ok", 1), d.accept()))
    action("Importar carpeta…").trigger()
    wait_until(lambda: "ok" in done)

def titles(): return {t.title: t.artist for t in db.all_tracks()}

# 1) Preferencia desactivada por defecto: no pregunta
check("Preferencia desactivada por defecto", win.prefs.ask_titles_on_import is False)
import_folder(folders[0])
check("Sin preferencia: no aparece el diálogo y usa el nombre del archivo", "05 - Sin preferencia" in titles() and not pending, titles())

# 2) Activar desde Archivo → Preferencias…
seen = {}
def prefs_handler(d):
    seen["detect_enabled_before"] = d.detect_artist.isEnabled()
    d.ask_titles.setChecked(True)
    seen["detect_enabled_after"] = d.detect_artist.isEnabled()
    d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
expect(PreferencesDialog, prefs_handler)
action("Preferencias…").trigger(); wait_until(lambda: not pending)
check("Archivo → Preferencias… activa la opción", win.prefs.ask_titles_on_import is True)
check("  la opción de artista se habilita al marcar la principal", seen == {"detect_enabled_before": False, "detect_enabled_after": True}, seen)
check("  se guarda en los ajustes", QSettings("ReproductorMusicaTest", "ReproductorMusica").value("preferences/ask_titles_on_import", type=bool))

# 3) Importar con canciones sin título: pregunta, se edita una y se acepta
def review_handler(d):
    t = d.table
    review["rows"] = [(t.item(r, 1).text(), t.item(r, 2).text(), t.item(r, 3).text()) for r in range(t.rowCount())]
    for r in range(t.rowCount()):
        if t.item(r, 1).text() == "07_mi_cancion.wav":
            t.item(r, 2).setText("Mi canción (editada)")
    [b for b in d.findChild(QDialogButtonBox).buttons() if b.text().startswith("Agregar")][0].click()
done = {}
answers.append(folders[1])
expect(FolderImportDialog, lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
expect(TitleReviewDialog, review_handler)
expect(ImportReportDialog, lambda d: (done.setdefault("ok", 1), d.accept()))
action("Importar carpeta…").trigger(); wait_until(lambda: "ok" in done)
check("Diálogo muestra solo las 2 canciones sin título (no la etiquetada)", len(review.get("rows", [])) == 2, review.get("rows"))
check("  propone título y artista desde el nombre", ("03 - Queen - Bohemian Rhapsody.wav", "Bohemian Rhapsody", "Queen") in review.get("rows", []), review.get("rows"))
tt = titles()
check("  títulos aplicados (incluida la edición)", tt.get("Bohemian Rhapsody") == "Queen" and "Mi canción (editada)" in tt, tt)
check("  la canción etiquetada conserva su título", "Título de la etiqueta" in tt)
check("  el archivo original no se modificó", WAVE(os.path.join(folders[1], "07_mi_cancion.wav")).tags is None)

# 4) «Omitir» deja el nombre del archivo
done = {}
answers.append(folders[2])
expect(FolderImportDialog, lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
expect(TitleReviewDialog, lambda d: [b for b in d.findChild(QDialogButtonBox).buttons() if b.text().startswith("Omitir")][0].click())
expect(ImportReportDialog, lambda d: (done.setdefault("ok", 1), d.accept()))
action("Importar carpeta…").trigger(); wait_until(lambda: "ok" in done)
check("«Omitir» importa igual con el nombre del archivo", "09 - Otro - Omitida" in titles(), titles())

check("todos los diálogos esperados aparecieron", not pending, pending)
win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.exit(0 if all(results) and not errors else 1)
