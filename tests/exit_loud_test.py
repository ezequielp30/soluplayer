import os, shutil, sys, tempfile
work = tempfile.mkdtemp(prefix="mp_exitloud_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data"); os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"; os.environ["MUSICPLAYER_SILENCIO"] = "1"  # ajustes (registro) aparte: no se tocan los del usuario
sys.path.insert(0, r"D:\soluplayer"); os.chdir(r"D:\soluplayer")
from PySide6.QtCore import QTimer, QSettings
QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", False)  # esta prueba no es sobre la pregunta de salir (ver confirmaciones_test)
from PySide6.QtWidgets import QApplication
import app.application as appmod
src = [r"D:\Musica Cristiana\Padre Celestial (Variado)\01 - Track 1.mp3"]
lib = os.path.join(work, "m"); os.makedirs(lib)
copies = [shutil.copy2(p, os.path.join(lib, f"c{i}.mp3")) for i, p in enumerate(src * 3)]
def script():
    a = QApplication.instance()
    win = next(w for w in a.topLevelWidgets() if w.__class__.__name__ == "MainWindow")
    from app.importer import scan_file
    from app.ui.loudness_dialog import LoudnessDialog
    win.db.add_tracks([scan_file(p)[0] for p in copies]); win._reload_library()
    def drive():
        d = next(w for w in a.topLevelWidgets() if isinstance(w, LoudnessDialog))
        d.btn_analyze_new.click()
        def wait_done():
            if d.runner.busy: QTimer.singleShot(200, wait_done); return
            print("analizadas:", sum(1 for t in win.library if t.loudness_lufs is not None), flush=True)
            d.reject()
            QTimer.singleShot(300, lambda: next(x for t in win.menuBar().actions() for x in t.menu().actions() if x.text().replace("&", "") == "Salir").trigger())
        QTimer.singleShot(500, wait_done)
    QTimer.singleShot(300, drive)
    win._open_loudness()
orig = QApplication.exec
QApplication.exec = lambda self=None: (QTimer.singleShot(800, script), orig())[1]
code = appmod.run()
print("run() devolvió", code, flush=True)
sys.exit(code)
