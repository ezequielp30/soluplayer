"""1.12.10: confirmar antes de detener una tarea, al cerrar una ventana que trabaja (también con Esc) y al salir
del programa; la pregunta habla del tema y el botón marcado es siempre el seguro. Todo en carpetas temporales."""
import math, os, struct, sys, tempfile, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_confirmar_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def wait_until(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond(): return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
    return cond()
def tone(path, secs=8):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(44100)
        f.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(3000 * math.sin(i / 7)) for i in range(44100 * secs))))
    return path

asked = []  # (texto, botón marcado, botones)
def answer(choice, check_box=False):
    """Contesta la próxima pregunta con el botón cuyo texto empieza con `choice` (y anota lo que preguntó)."""
    def go():
        box = QApplication.activeModalWidget()
        if box is not None and not isinstance(box, QMessageBox) and type(box).__name__ != "QProgressDialog":
            box.reject()  # otra ventana (p. ej. el resumen de una importación): no es la pregunta
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(50, go); return
        buttons = [b.text() for b in box.buttons()]
        default = box.defaultButton().text() if box.defaultButton() else ""
        asked.append((box.text() + " " + box.informativeText(), default, buttons))
        if check_box and box.checkBox() is not None:
            box.checkBox().setChecked(True)
        target = next((b for b in box.buttons() if b.text().startswith(choice)), None)
        (target or box.buttons()[0]).click()
    QTimer.singleShot(100, go)

music = os.path.join(work, "Musica")
files = [tone(os.path.join(music, f"tema{n:02}.wav")) for n in range(30)]
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in files])
from app.ui import main_window as mw
from app.ui.loudness_dialog import LoudnessDialog
win = mw.MainWindow(db); win.show(); spin(200)

print("[Detener una tarea]")
dialog = LoudnessDialog(win.ops, lambda: win.library, win); dialog.show(); spin(100)
dialog._start_analysis(only_new=False); spin(300)
answer("Seguir")
dialog.btn_stop.click(); spin(400)
q = asked[-1] if asked else ("", "", [])
check("«Detener» pregunta antes, sobre el análisis de volumen y su avance", "análisis de volumen" in q[0] and " de 30" in q[0], q[0][:120])
check("  el botón marcado es «Seguir analizando» (un Enter de más no detiene nada)", q[1].startswith("Seguir"), q[1])
check("  y si se elige seguir, sigue", dialog.runner.busy)

print("[Cerrar una ventana que trabaja]")
answer("Seguir")
dialog.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)); spin(400)
q = asked[-1] if len(asked) > 1 else ("", "", [])
check("Esc ya no la corta en silencio: pregunta si cerrar y detener", "cerrar" in q[0].lower() and "análisis" in q[0], q[0][:120])
check("  si se elige seguir, la ventana queda abierta y trabajando", dialog.isVisible() and dialog.runner.busy)
answer("Detener")
dialog.btn_stop.click()
wait_until(lambda: not dialog.runner.busy, 20000)
check("  y «Detener» confirmado la detiene", not dialog.runner.busy)
dialog.reject(); spin(100)

print("[Salir del programa]")
count = len(asked)
answer("Cancelar")
win.act_quit.trigger() if hasattr(win, "act_quit") else next(a for a in win.findChildren(mw.QAction) if a.objectName() == "act_quit").trigger()
spin(400)
q = asked[-1] if len(asked) > count else ("", "", [])
check("Archivo → Salir pregunta «¿Salir del Reproductor de Música?»", "Salir" in q[0], q[0][:80])
check("  con «Cancelar» marcado, y si se cancela no se cierra", q[1] == "Cancelar" and win.isVisible(), (q[1], win.isVisible()))
count = len(asked)
answer("Salir", check_box=True)
next(a for a in win.findChildren(mw.QAction) if a.objectName() == "act_quit").trigger(); spin(400)
check("  «No volver a preguntar» se recuerda", len(asked) > count and win.prefs.confirm_exit is False if hasattr(win.prefs, "confirm_exit") else False)
check("  y al elegir Salir se cierra", not win.isVisible())

print("[Salir con una importación en curso]")
import app.importer as importer
real_scan = importer.scan_file
importer.scan_file = lambda path: (time.sleep(0.3), real_scan(path))[1]  # importación lenta: sigue en curso al salir
db2 = Database(os.path.join(work, "data", "otra.db"))
win2 = mw.MainWindow(db2); win2.show(); spin(200)
if hasattr(win2.prefs, "confirm_exit"):
    win2.prefs.confirm_exit = False  # aunque no se pregunte al salir, con algo en curso sí
win2._start_import(folder=music, recursive=True); spin(150)
count = len(asked)
answer("Seguir")
next(a for a in win2.findChildren(mw.QAction) if a.objectName() == "act_quit").trigger(); spin(400)
q = asked[-1] if len(asked) > count else ("", "", [])
check("si hay una importación en curso, siempre pregunta y dice qué se pierde", "importación" in q[0] and win2.isVisible(), q[0][:120])
count = len(asked)
answer("Seguir")
win2._cancel_import(); spin(400)
q = asked[-1] if len(asked) > count else ("", "", [])
check("«Cancelar» la importación también pregunta", "importación" in q[0] and win2._import_worker is not None, q[0][:120])
importer.scan_file = real_scan
win2.close(); spin(300)  # cerrar desde el programa (no la persona): cancela la importación sin preguntar

QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()  # no dejar «No volver a preguntar» a otras pruebas
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
