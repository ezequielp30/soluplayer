"""Arranca main.py de verdad, importa, reproduce y cierra con Archivo → Salir. Comprueba el código de salida."""
import math, os, struct, sys, tempfile, wave
work = tempfile.mkdtemp(prefix="mp_exit_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data"); os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"  # ajustes (registro) aparte: no se tocan los del usuario
folder = os.path.join(work, "m"); os.makedirs(folder)
for n in range(3):
    with wave.open(os.path.join(folder, f"t{n}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(4000*math.sin(i/(3+n)))) for i in range(8000*5)))
sys.path.insert(0, r"D:\soluplayer"); os.chdir(r"D:\soluplayer")
from PySide6.QtCore import QCoreApplication, QTimer, QSettings
QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", False)  # esta prueba no es sobre la pregunta de salir (ver confirmaciones_test)
from PySide6.QtWidgets import QApplication
import app.application as appmod

def script():
    a = QApplication.instance(); a.setOrganizationName("ReproductorMusicaTest")
    win = next(w for w in a.topLevelWidgets() if w.__class__.__name__ == "MainWindow")
    from app.importer import scan_file
    win.db.add_tracks([scan_file(os.path.join(folder, f"t{n}.wav"))[0] for n in range(3)])
    win._reload_library(); win.sidebar.select_library("songs")
    win._on_play_requested(win.content.visible_tracks(), 0)
    junk = os.path.join(work, "PRUEBA_reproductor_papelera.bin"); open(junk, "wb").write(b"x")
    from app.file_ops import move_to_trash
    print("papelera:", move_to_trash([junk]))
    QTimer.singleShot(1500, lambda: next(x for t in win.menuBar().actions() for x in t.menu().actions() if x.text().replace("&", "") == "Salir").trigger())

_orig_exec = QApplication.exec
def _exec(self=None):
    QTimer.singleShot(800, script)
    return _orig_exec()
QApplication.exec = _exec
code = appmod.run()
print("run() devolvió", code)
sys.exit(code)
