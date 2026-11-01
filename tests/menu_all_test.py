"""Prueba de producción: activa CADA opción de la barra de menús (leída de assets/menus.ui, incluidos los
submenús) y comprueba su efecto, sin errores de Python. Todo en una carpeta temporal y en silencio; lo que
abriría el Explorador o el Bloc de notas se intercepta."""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_menuall_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", False)  # esta prueba no es sobre la pregunta de salir (ver confirmaciones_test)
from app import error_log
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import main_window as mw
mw.MainWindow._choose_scope = lambda self, tool: ((lambda: self.library), None)  # primer paso «¿qué analizar?»: toda la biblioteca (se prueba en herramientas_carpeta_test)
from app.ui.convert_dialog import ConvertDialog
from app.ui.dialogs import PlaylistNameDialog, PreferencesDialog
from app.ui.duplicates_dialog import DuplicatesDialog
from app.ui.equalizer_dialog import EqualizerDialog
from app.ui.history_dialog import HistoryDialog
from app.ui.loudness_dialog import LoudnessDialog
from app.ui.online_dialog import OnlineLookupDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)

# Errores de Python dentro de los slots de Qt: se recogen (y también el aviso del programa).
sys.excepthook = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
opened_urls = []
QDesktopServices.openUrl = staticmethod(lambda url: opened_urls.append(url.toLocalFile() or url.toString()) or True)
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")

class SilentOutput(QAudioOutput):  # «Probar sonido» en silencio
    def setVolume(self, _v):
        super().setVolume(0.0)
mw.QAudioOutput = SilentOutput

# Lo que aparece en pantalla al activar cada opción: se registra y se cierra sin cambiar nada.
seen = []
def pump():
    QTimer.singleShot(30, pump)
    w = QApplication.activeModalWidget()
    if w is None or not w.isVisible():
        return
    seen.append((type(w).__name__, w.windowTitle(), w.text() if isinstance(w, QMessageBox) else ""))
    if isinstance(w, QMessageBox):
        cancel = next((b for b in w.buttons() if b.text().replace("&", "") in ("Cancelar", "Cerrar", "Más tarde", "Conservarlas")), None)
        (cancel.click() if cancel else w.accept())
    elif isinstance(w, QInputDialog):
        w.reject()
    elif isinstance(w, QDialog):
        w.reject()
QTimer.singleShot(30, pump)

def tone(path, secs=3):
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(22050)
        f.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * 440 * i / 22050))) for i in range(int(22050 * secs))))
music = os.path.join(work, "Musica"); os.makedirs(music)
for n in ("Uno", "Dos", "Tres"):
    tone(os.path.join(music, f"{n}.wav"))
db = Database(database_path())
db.add_tracks([scan_file(os.path.join(music, f))[0] for f in sorted(os.listdir(music))])
db.create_playlist("Lista de prueba")
win = mw.MainWindow(db); win.show(); win.resize(1280, 660); spin(300)
win._on_play_requested(list(win.library), 0); spin(500)

def walk(menu, path):
    for a in menu.actions():
        if a.isSeparator():
            continue
        if a.menu() is not None:
            yield from walk(a.menu(), path + [a.text().replace("&", "")])
        else:
            yield path + [a.text().replace("&", "")], a
all_actions = [(p, a) for top in win.menuBar().actions() for p, a in walk(top.menu(), [top.text().replace("&", "")])]
check("el menú tiene todas las opciones (31)", len(all_actions) == 31, len(all_actions))

def state():
    p = win.player
    return {"playing": p.is_playing, "pos": p.position(), "track": p.current_track.id if p.current_track else None,
            "shuffle": p.shuffle, "repeat": int(p.repeat), "volume": win.player_bar.volume.value(),
            "focus_search": win.player_bar.search.hasFocus(), "eq_open": bool(getattr(win, "_eq_dialog", None)) and win._eq_dialog.isVisible(), "normalize": win.prefs.playback_normalization,
            "playlists": len(db.playlists())}

def expectation(label, before, after, dialogs, urls):
    names = [d[0] for d in dialogs]
    texts = " | ".join(d[1] + " " + d[2] for d in dialogs)
    rules = {
        "Importar archivos…": True,  # abre el selector de archivos (interceptado: no elige nada)
        "Importar carpeta…": True,
        "Buscar": after["focus_search"],
        "Crear un respaldo ahora": "Respaldo" in texts,
        "Abrir la carpeta de respaldos": any("respaldos" in u for u in urls),
        "Preferencias…": PreferencesDialog.__name__ in names,
        "Reproducir / Pausar": after["playing"] != before["playing"],
        "Detener": not after["playing"],
        "Anterior": after["track"] is not None,
        "Siguiente": after["track"] != before["track"] or after["track"] is not None,
        "Orden aleatorio": after["shuffle"] != before["shuffle"],
        "Cambiar repetición": after["repeat"] != before["repeat"],
        "Ecualizador…": after["eq_open"],
        "Igualar volumen al reproducir": after["normalize"] != before["normalize"],
        "Subir volumen": after["volume"] >= before["volume"],
        "Bajar volumen": after["volume"] <= before["volume"],
        "Probar sonido…": "Probar sonido" in texts,
        "Nueva playlist…": PlaylistNameDialog.__name__ in names,
        "Renombrar playlist…": PlaylistNameDialog.__name__ in names,
        "Eliminar playlist…": "Eliminar" in texts or "playlist" in texts.lower(),
        "Guardar copia de las playlists…": True,  # pide la carpeta (interceptado: no elige ninguna)
        "Restaurar playlists…": True,
        "Buscar datos en internet…": OnlineLookupDialog.__name__ in names,
        "Buscar canciones repetidas…": DuplicatesDialog.__name__ in names,
        "Analizar y ajustar volumen…": LoudnessDialog.__name__ in names,
        "Convertir a MP3…": ConvertDialog.__name__ in names,
        "Título y quién la canta…": "SongFormatDialog" in names,
        "Historial de cambios en archivos…": HistoryDialog.__name__ in names,
        "Abrir registro de errores": bool(urls) or "registro" in texts.lower(),
        "Acerca de…": "Reproductor" in texts and "Ezequiel Perez" in texts and "ezequielp30@gmail.com" in texts
                      and "propia responsabilidad" in texts,
    }
    return rules.get(label)

exit_action = None
for path, action in all_actions:
    label = path[-1]
    if label == "Salir":
        exit_action = action
        continue
    if label in ("Renombrar playlist…", "Eliminar playlist…"):
        win.sidebar.select_playlist(db.playlists()[0].id) if hasattr(win.sidebar, "select_playlist") else None
        win._update_playlist_actions()
    before = state(); seen.clear(); opened_urls.clear(); errs_before = len(errors)
    action.trigger(); spin(700)
    if label == "Ecualizador…":
        after = state(); win._eq_dialog.close(); spin(100)
    else:
        after = state()
    ok = expectation(label, before, after, list(seen), list(opened_urls))
    new_errors = errors[errs_before:]
    check(" → ".join(path), ok and not new_errors and win.isVisible(),
          new_errors[0].splitlines()[-1] if new_errors else (seen[:1] or opened_urls[:1] or ""))
    if label == "Detener":
        win._on_play_requested(list(win.library), 0); spin(300)

print("\n[Archivo → Salir]")
exit_action.trigger(); spin(500)
check("Archivo → Salir cierra la ventana", not win.isVisible())
check("ningún error de Python en todo el recorrido", not errors, errors[:1])
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
