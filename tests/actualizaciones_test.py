"""Aviso de versión nueva: compara bien las versiones, no toca la red al probar, avisa solo cuando corresponde, respeta
la preferencia y no pregunta más de una vez al día. Nunca descarga nada. Todo en carpetas temporales."""
import io, json, os, sys, tempfile, time, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_actualizaciones_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import __version__, updates
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)

print("[Comparar versiones]")
check("más nueva", updates.is_newer("1.27.0", "1.26.9") and updates.is_newer("v2.0.0", "1.99.99") and updates.is_newer("1.10.0", "1.9.0"))
check("igual o anterior, no", not updates.is_newer("1.26.0", "1.26.0") and not updates.is_newer("1.25.9", "1.26.0"))
check("lo ilegible nunca es más nueva", not any(updates.is_newer(v, "1.0.0") for v in ("", None, "nueva", "2.0", "2.0.0-beta")))

print("[Lo que responde GitHub]")
real_open = updates._opener.open
class Answer(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
def answer(data):
    updates._opener.open = lambda request, timeout: Answer(json.dumps(data).encode())
answer({"tag_name": "v9.1.2", "html_url": updates.RELEASES_PAGE + "/tag/v9.1.2"})
check("lee la versión y su página", updates.fetch_latest() == updates.Release("9.1.2", updates.RELEASES_PAGE + "/tag/v9.1.2"))
answer({"tag_name": "v9.1.2", "html_url": "https://otro-sitio.example/virus.exe"})
check("nunca abre una página de otro sitio", updates.fetch_latest().url == updates.RELEASES_PAGE)
def fails(data=None, error=None):
    if error:
        def boom(request, timeout): raise error
        updates._opener.open = boom
    else:
        answer(data)
    try:
        updates.fetch_latest(); return False
    except updates.UpdateError:
        return True
check("respuesta rara: error claro", fails({"tag_name": "lo que sea"}) and fails(["lista"]))
check("sin conexión: error claro", fails(error=urllib.error.URLError("sin red")) and fails(error=TimeoutError()))
check("error de GitHub: error claro", fails(error=urllib.error.HTTPError(updates._LATEST_API, 500, "x", {}, None)))
updates._opener.open = real_open

print("[Al abrir]")
calls, latest = [], [updates.Release("99.0.0", updates.RELEASES_PAGE + "/tag/v99.0.0")]
def fake_fetch():
    calls.append(time.time())
    if latest[0] is None:
        raise updates.UpdateError("sin conexión")
    return latest[0]
updates.fetch_latest = fake_fetch
opened = []
mw.QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()))
win = mw.MainWindow(Database(database_path())); win.show(); spin(150)
idle = lambda: win._update_thread is None
check("el programa no pregunta solo por crear la ventana", not calls)
win.check_updates_on_start(); spin(5000, idle)
check("pregunta una vez", len(calls) == 1, len(calls))
check("muestra el aviso con la versión", win._update_notice.isVisible() and "99.0.0" in win._update_notice.text(), win._update_notice.text())
win._update_notice.click(); spin(50)
check("el aviso lleva a la página de descarga y nada más", opened == [updates.RELEASES_PAGE + "/tag/v99.0.0"], opened)
win.check_updates_on_start(); spin(300, idle)
check("no vuelve a preguntar el mismo día", len(calls) == 1, len(calls))
win._update_notice.hide(); win.check_updates_on_start(); spin(100)
check("  pero sigue avisando de lo que ya sabe", win._update_notice.isVisible())

print("[Sin versión nueva]")
win.settings.remove("updates/last_check"); win.settings.remove("updates/latest"); win._update_notice.hide()
latest[0] = updates.Release(__version__, updates.RELEASES_PAGE)
win.check_updates_on_start(); spin(5000, idle)
check("no molesta", len(calls) == 2 and not win._update_notice.isVisible(), len(calls))

print("[Sin internet]")
win.settings.remove("updates/last_check"); latest[0] = None
shown = []
real_ask, mw.ask = mw.ask, lambda parent, title, text, buttons, *a, **k: (shown.append(text), -1)[1]
real_warning, mw.QMessageBox.warning = mw.QMessageBox.warning, staticmethod(lambda p, t, text, *a: shown.append(text))
win.check_updates_on_start(); spin(5000, idle)
check("al abrir no sale ninguna ventana", not shown, shown)
check("  y se vuelve a intentar la próxima vez", not win.settings.contains("updates/last_check"))
win._act_check_updates(); spin(5000, idle); spin(50)
check("si lo pides tú, te dice qué pasó", shown and "sin conexión" in shown[-1], shown)

print("[Buscar a mano]")
shown.clear(); latest[0] = updates.Release(__version__, updates.RELEASES_PAGE)
win._act_check_updates(); spin(5000, idle); spin(50)
check("dice que está al día", shown and __version__ in shown[-1], shown)
shown.clear(); latest[0] = updates.Release("99.0.0", updates.RELEASES_PAGE); opened.clear()
mw.ask = lambda parent, title, text, buttons, *a, **k: (shown.append(text), 0)[1]
win._act_check_updates(); spin(5000, idle); spin(50)
check("ofrece la versión nueva y abre su página si aceptas", shown and "99.0.0" in shown[-1] and opened == [updates.RELEASES_PAGE], (shown, opened))

print("[Preferencia]")
count = len(calls); win.settings.remove("updates/last_check"); win.settings.remove("updates/latest"); win._update_notice.hide()
check("activada de fábrica", win.prefs.check_updates)
win.prefs.check_updates = False
win.check_updates_on_start(); spin(300, idle)
check("apagada: no pregunta ni avisa", len(calls) == count and not win._update_notice.isVisible())
win._act_check_updates(); spin(5000, idle)
check("  buscar a mano sigue funcionando", len(calls) == count + 1)
win.prefs.check_updates = True

print("[Cerrar a mitad de la consulta]")
win.settings.remove("updates/last_check")
slow = updates.fetch_latest
updates.fetch_latest = lambda: (time.sleep(0.4), latest[0])[1]
win.check_updates_on_start()
mw.ask, mw.QMessageBox.warning = real_ask, real_warning
win.close(); spin(800)
check("se cierra sin problemas", not win.isVisible())

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
