"""Cambio de tema desde Preferencias: claro, oscuro, automático; iconos y colores se actualizan sin cerrar."""
import os, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_themetest_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDialogButtonBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest"); app.setStyle("Fusion")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import theme
from app.ui import main_window as mw
from app.ui.dialogs import PreferencesDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
pending = []
def pump():
    QTimer.singleShot(40, pump)
    w = QApplication.activeModalWidget()
    if pending and isinstance(w, PreferencesDialog) and w.isVisible():
        h = pending.pop(0)
        try: h(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, pump)
def spin(ms):
    end = time.time() + ms/1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)

p = os.path.join(work, "t.wav")
with wave.open(p, "wb") as w:
    w.setnchannels(1); w.setsampwidth(1); w.setframerate(2000); w.writeframes(b"\x80" * 20000)
db = Database(database_path()); db.add_tracks([scan_file(p)[0]])
theme.apply(app, "auto")
win = mw.MainWindow(db); win.show(); spin(200)
win.sidebar.select_library("songs"); spin(100)
win._on_play_requested(win.content.visible_tracks(), 0); spin(400)
system = "dark" if theme.system_is_dark() else "light"
check("Arranque en «Automático» sigue a Windows", theme.current().dark == (system == "dark"), f"Windows={system}, tema={theme.current().name}")

def choose(value):
    def h(d):
        d.theme_buttons[value].setChecked(True)
        d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    return h
pref = next(a for t in win.menuBar().actions() for a in t.menu().actions() if a.text().replace("&", "") == "Preferencias…")

for value, expect_dark, name in (("dark", True, "Oscuro"), ("light", False, "Claro"), ("dark", True, "Oscuro otra vez")):
    pending.append(choose(value)); pref.trigger(); spin(250)
    bg = app.palette().color(QPalette.ColorRole.Window)
    title_color = win.content.model.data(win.content.proxy.mapToSource(win.content.proxy.index(0, 0)), Qt.ItemDataRole.ForegroundRole)
    check(f"Preferencias → {name}", theme.current().dark == expect_dark and (bg.lightness() < 80) == expect_dark,
          f"{theme.current().name}, fondo {bg.name()}")
    check("  canción actual en ámbar del tema", title_color is not None and title_color.name() == theme.color("accent_text"), title_color and title_color.name())
    check("  se guarda en preferencias", win.prefs.theme == value)
    ss = app.styleSheet()
    check("  hoja de estilos con la paleta nueva", theme.color("bg") in ss and theme.color("accent") in ss)

pending.append(choose("auto")); pref.trigger(); spin(250)
check("Preferencias → Automático vuelve a seguir a Windows", theme.mode() == "auto" and theme.current().dark == (system == "dark"), theme.current().name)

# Simula que Windows cambia de modo con el programa abierto
other = theme.GRAPHITE if not theme.current().dark else theme.ALUMINIUM
orig = theme.system_is_dark
theme.system_is_dark = lambda: other.dark
win._on_system_scheme_changed(None); spin(150)
check("Windows cambia de modo → el programa cambia solo", theme.current() is other, theme.current().name)
theme.system_is_dark = orig
pending.append(choose("light")); pref.trigger(); spin(150)
theme.system_is_dark = lambda: True
win._on_system_scheme_changed(None); spin(100)
check("  con un tema fijo, no cambia aunque Windows sí", theme.current() is theme.ALUMINIUM)
theme.system_is_dark = orig

win.player.stop(); win.close(); spin(100)
theme.apply(app, "dark")
check("Cambiar de tema con la ventana cerrada no falla (sin oyentes colgados)", True)
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
os._exit(0 if all(results) and not errors else 1)
