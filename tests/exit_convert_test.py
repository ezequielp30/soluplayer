import os, shutil, sys, tempfile
work = tempfile.mkdtemp(prefix="mp_exitloud_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data"); os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"; os.environ["MUSICPLAYER_SILENCIO"] = "1"  # ajustes (registro) aparte: no se tocan los del usuario
sys.path.insert(0, r"D:\soluplayer"); os.chdir(r"D:\soluplayer")
from PySide6.QtCore import QTimer, QSettings
QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", False)  # esta prueba no es sobre la pregunta de salir (ver confirmaciones_test)
from PySide6.QtWidgets import QApplication
import app.application as appmod
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from muestra_real import mp3_real  # la de siempre o, si ya no está, otro MP3 real
src = [mp3_real()]
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
            reached.append(True)
            d.reject()
            QTimer.singleShot(300, lambda: next(x for t in win.menuBar().actions() for x in t.menu().actions() if x.text().replace("&", "") == "Salir").trigger())
        QTimer.singleShot(500, wait_done)
    QTimer.singleShot(300, drive)
    win._open_convert()
reached = []  # la conversión terminó y se pidió salir: sin esto la prueba pasaba aunque no se convirtiera nada
orig = QApplication.exec
QApplication.exec = lambda self=None: (QTimer.singleShot(800, script), orig())[1]
code = appmod.run()
if not reached:
    print("FALLA la conversión no llegó a terminar antes de salir", flush=True)
print("run() devolvió", code, flush=True)
sys.exit(code if reached else 1)
