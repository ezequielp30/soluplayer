"""Ecualizador dentro del programa: activar/desactivar a mitad de canción, presets, guardar presets propios,
archivos muy largos y que la configuración se recuerde al volver a abrir. (Volumen del programa en 0.)"""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_equi_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.eq_player import EqPlayer
from app.importer import scan_file
from app.ui import main_window as mw

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)

def tone(path, secs):
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(6000 * math.sin(2 * math.pi * 330 * i / 44100)) for i in range(int(44100 * secs)))))

a = os.path.join(work, "a.wav"); tone(a, 6)
b = os.path.join(work, "b.wav"); tone(b, 2)
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in (a, b)])
win = mw.MainWindow(db); win.show(); spin(200)
check("al empezar el ecualizador está apagado (motor de siempre)", not win.player.eq_active)
win._on_play_requested(list(win.library), 0); spin(1500)
before = win.player.position()

print("[Activar a mitad de canción]")
win._open_equalizer(); spin(200)
d = win._eq_dialog
check("la ventana no bloquea el programa", not d.isModal() and d.isVisible())
d.enabled.setChecked(True); spin(500)
check("al activarlo cambia al motor con ecualizador", win.player.eq_active and isinstance(win.player._player, EqPlayer))
check("  sigue sonando en el mismo punto", win.player.is_playing and abs(win.player.position() - before) < 700, (before, win.player.position()))
check("  el botón de la barra lo muestra activo", "activado" in win.player_bar.btn_eq.toolTip())
d.preset.setCurrentIndex(d.preset.findText("Rock")); d._preset_chosen(0); spin(300)
check("elegir un preset cambia el sonido en vivo", tuple(win.player._eq_player._settings.gains) == (5, 4, 2, -1, -2, -1, 2, 3, 4, 4))
d.sliders[6].setValue(-60); spin(300)
check("mover una banda pasa a «Personalizado»", d.preset.currentText() == "Personalizado" and win.player._eq_player._settings.gains[5] == -6.0)
QInputDialog.getText = staticmethod(lambda *a_, **k: ("Mi sala", True))
d._save_preset(); spin(100)
check("guardar un preset propio", "Mi sala" in win.prefs.equalizer()["custom"] and d.preset.currentText() == "Mi sala")
d._reset(); spin(200)
check("Restablecer vuelve todo a 0", all(s.value() == 0 for s in d.sliders[1:]) and d.preset.currentText() == "Normal")

print("[Siguiente canción y fin]")
win.player.next(); spin(600)
check("la siguiente canción también suena con ecualizador", win.player.eq_active and win.player.current_track.path == b and win.player.is_playing)
spin(2600)
check("al terminar la cola se detiene (fin de archivo detectado)", not win.player.is_playing)

print("[Desactivar]")
win._on_play_requested([next(t for t in win.library if t.path == a)], 0); spin(1500)
pos = win.player.position()
d.enabled.setChecked(False); spin(500)
check("al desactivarlo vuelve al motor de siempre en el mismo punto", not win.player.eq_active and win.player.is_playing and abs(win.player.position() - pos) < 700, (pos, win.player.position()))
check("  el botón de la barra lo muestra apagado", "desactivado" in win.player_bar.btn_eq.toolTip())

print("[Archivo muy largo]")
d.enabled.setChecked(True); spin(300)
long_track = next(t for t in win.library if t.path == b).copy(duration_ms=45 * 60_000)
win.player.play_queue([long_track], 0); spin(400)
check("un archivo de más de 30 min también suena ecualizado (sin límite)", win.player.eq_active and win.player.is_playing)
win.player.stop(); d.close(); win.close(); spin(200)

print("[Se recuerda al volver a abrir]")
win2 = mw.MainWindow(Database(database_path())); spin(200)
state = win2.prefs.equalizer()
check("queda activado y con los presets propios", state["enabled"] and "Mi sala" in state["custom"])
win2._on_play_requested(list(win2.library)[:1], 0); spin(600)
check("  y la música suena con ecualizador desde el principio", win2.player.eq_active and win2.player.is_playing)
win2.player.stop(); win2.close()
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
