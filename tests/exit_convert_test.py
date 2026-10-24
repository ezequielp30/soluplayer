import os, shutil, sys, tempfile
work = tempfile.mkdtemp(prefix="mp_exitloud_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data"); os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"; os.environ["MUSICPLAYER_SILENCIO"] = "1"  # ajustes (registro) aparte: no se tocan los del usuario
sys.path.insert(0, r"D:\reproductor-musica"); os.chdir(r"D:\reproductor-musica")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import app.application as appmod
src = [r"D:\Musica Cristiana\Padre Celestial (Variado)\01 - Track 1.mp3"]
lib = os.path.join(work, "m"); os.makedirs(lib)
copies = [shutil.copy2(p, os.path.join(lib, f"c{i}" + os.path.splitext(p)[1])) for i, p in enumerate(src)]
def script():
    a = QApplication.instance()
    win = next(w for w in a.topLevelWidgets() if w.__class__.__name__ == "MainWindow")
    from app.importer import scan_file
    from app.ui.convert_dialog import ConvertDialog as LoudnessDialog
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    import app.ui.convert_dialog as cd; cd.ask = lambda *a, **k: 0
    win.db.add_tracks([scan_file(p)[0] for p in copies]); win._reload_library()
    def drive():
        d = next(w for w in a.topLevelWidgets() if isinstance(w, LoudnessDialog))
        d.btn_convert.click()
        def wait_done():
            if d.runner.busy: QTimer.singleShot(200, wait_done); return
            print("convertidas:", sum(1 for t in win.library if t.path.endswith(".mp3")), flush=True)
            d.reject()
            QTimer.singleShot(300, lambda: next(x for t in win.menuBar().actions() for x in t.menu().actions() if x.text().replace("&", "") == "Salir").trigger())
        QTimer.singleShot(500, wait_done)
    QTimer.singleShot(300, drive)
    win._open_convert()
orig = QApplication.exec
QApplication.exec = lambda self=None: (QTimer.singleShot(800, script), orig())[1]
code = appmod.run()
print("run() devolvió", code, flush=True)
sys.exit(code)
