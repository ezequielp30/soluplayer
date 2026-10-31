"""Programa real: convierte copias de un WMA y un M4A desde la ventana y sale con Archivo → Salir."""
import os, shutil, sqlite3, sys, tempfile
work = tempfile.mkdtemp(prefix="mp_exitconv_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data"); os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"; os.environ["MUSICPLAYER_SILENCIO"] = "1"  # ajustes (registro) aparte: no se tocan los del usuario
sys.path.insert(0, r"D:\soluplayer"); os.chdir(r"D:\soluplayer")
from PySide6.QtCore import QTimer, QSettings
QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", False)  # esta prueba no es sobre la pregunta de salir (ver confirmaciones_test)
from PySide6.QtWidgets import QApplication, QMessageBox
import app.application as appmod
from app.ui import main_window as mw
mw.MainWindow._choose_scope = lambda self, tool: ((lambda: self.library), None)  # primer paso «¿qué analizar?»: toda la biblioteca (se prueba en herramientas_carpeta_test)
import app.ui.convert_dialog as cd
con = sqlite3.connect("file:" + os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db") + "?mode=ro", uri=True)
def _real_originals(ext):
    """Archivos reales de ese formato: de la biblioteca o, si ya se convirtieron, de «_Originales convertidos»."""
    import glob as _glob
    found = [r[0] for r in con.execute("select path from tracks where lower(path) like ?", ("%" + ext,)) if os.path.isfile(r[0])]
    for root in (r"D:\Musica Cristiana", os.path.expanduser("~\\Music")):
        found += _glob.glob(os.path.join(root, "**", "_Originales convertidos", "**", "*" + ext), recursive=True)
    return found
lib = os.path.join(work, "m"); os.makedirs(lib)
# Originales reales si quedan (WMA/M4A); si ya no hay en la máquina, tonos WAV generados (también se convierten).
src = [found[0] for found in (_real_originals(ext) for ext in (".wma", ".m4a")) if found]
copies = [shutil.copy2(p, os.path.join(lib, f"c{i}{os.path.splitext(p)[1]}")) for i, p in enumerate(src)]
if len(copies) < 2:
    import math, struct, wave
    for i in range(len(copies), 2):
        path = os.path.join(lib, f"tono{i}.wav")
        with wave.open(path, "wb") as f:
            f.setnchannels(2); f.setsampwidth(2); f.setframerate(44100)
            f.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(8000 * math.sin(2 * math.pi * 440 * n / 44100)) for n in range(44100 * 4))))
        copies.append(path)
print("archivos a convertir:", [os.path.basename(p) for p in copies], flush=True)
cd.ask = lambda *a, **k: 0
QMessageBox.information = staticmethod(lambda *a, **k: None)
def script():
    a = QApplication.instance()
    win = next(w for w in a.topLevelWidgets() if w.__class__.__name__ == "MainWindow")
    from app.importer import scan_file
    win.db.add_tracks([scan_file(p)[0] for p in copies]); win._reload_library()
    def drive():
        d = next(w for w in a.topLevelWidgets() if isinstance(w, cd.ConvertDialog))
        d.btn_convert.click()
        def wait_done():
            if d.runner.busy:
                QTimer.singleShot(200, wait_done); return
            print("convertidas:", sum(1 for t in win.library if t.path.endswith(".mp3")), "de", len(copies), flush=True)
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
