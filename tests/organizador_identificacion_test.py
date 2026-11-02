"""Organizador, fase 3: decide bien con varias señales, no inventa, guarda en caché, retoma y pide la clave. AcoustID está
simulado: esta prueba no toca la red ni la música. Lo real se mide aparte, en el piloto."""
import io, json, os, sys, tempfile, time, urllib.error
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_identificacion_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import acoustid_lookup as al, online_lookup
from app.organizer import DECISION_AUTO, DECISION_REVIEW, Confidence, identify, version_of
from app.organizer_db import OrganizerDb
from app.organizer_job import IdentifyWorker
from app.preferences import Preferences

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def rec(title="Santo", artists=("New Wine",), duration=200.0, types=(), rid="r1"):
    return al.Recording(rid, title, tuple(artists), duration, tuple(types))
def match(score=1.0, *recordings):
    return al.Match(score, recordings or (rec(),))
conf = Confidence()

print("[Decidir]")
item = identify([match()], 200, ["Santo - New Wine"], conf)
check("coincide todo: automática", item.decision == DECISION_AUTO and (item.title, item.artist) == ("Santo", "New Wine"), item)
item = identify([match()], 200, ["track01", "Pista 3", ""], conf)
check("con nombre genérico también: no se confía en el nombre", item.decision == DECISION_AUTO, item)
item = identify([match(0.99)], 200, ["Otra Cancion Distinta - Alguien"], conf)
check("contradice el nombre, huella casi exacta: acepta (el nombre puede estar mal)", item.decision == DECISION_AUTO, item)
item = identify([match(0.93)], 200, ["Otra Cancion Distinta - Alguien"], conf)
check("contradice el nombre, huella normal: a revisar", item.decision == DECISION_REVIEW and "contradice" in item.reason, item)

print("[Dudosas: no inventa]")
item = identify([], 200, ["x"], conf)
check("sin coincidencia", item.decision == DECISION_REVIEW and not item.title and not item.artist, item)
item = identify([al.Match(0.99, ())], 200, ["x"], conf)
check("huella sin datos", item.decision == DECISION_REVIEW and not item.title, item)
item = identify([match(0.8)], 200, ["Santo"], conf)
check("parecido bajo: guarda posibles coincidencias, sin título", item.decision == DECISION_REVIEW and not item.title and item.candidates == ("Santo - New Wine",), item)
item = identify([match(1.0, rec(duration=260))], 200, ["Santo"], conf)
check("duración distinta", item.decision == DECISION_REVIEW and "duración" in item.reason, item)
item = identify([match(1.0, rec("Santo"), rec("Otra Cosa Muy Distinta", rid="r2"))], 200, ["x y z"], conf)
check("títulos en conflicto", item.decision == DECISION_REVIEW and "títulos" in item.reason and len(item.candidates) == 2, item)
item = identify([match(1.0, rec(artists=("New Wine",)), rec(artists=("Otro Grupo",), rid="r2"))], 200, ["Santo"], conf)
check("artistas en conflicto", item.decision == DECISION_REVIEW and "artistas" in item.reason, item)

print("[Elegir bien]")
item = identify([match(1.0, rec(duration=300, rid="lejos"), rec(duration=201, rid="cerca"))], 200, ["Santo"], conf)
check("la grabación de duración más cercana", item.recording_id == "cerca", item)
item = identify([match(1.0, rec(artists=("Marcos Witt", "Danilo Montero")))], 200, ["Santo"], conf)
check("un solo artista: el primero de los créditos", item.artist == "Marcos Witt", item)
item = identify([match(1.0, rec(artists=("Israel & New Breed",)))], 200, ["Santo"], conf)
check("  un nombre con «&» que la base da como uno se conserva", item.artist == "Israel & New Breed", item)
item = identify([match(1.0, rec("Santo (feat. Otro)"))], 200, ["Santo"], conf)
check("sin colaboradores en el título", item.title == "Santo", item)

print("[Versiones: solo lo que consta]")
for title, types, want in (("Santo (En Vivo)", (), "En Vivo"), ("Santo (Live)", (), "En Vivo"), ("Santo", ("Live",), "En Vivo"), ("Santo - Remix", (), "Remix"),
                           ("Santo (Cover)", (), "Cover"), ("Santo Instrumental", (), "Instrumental"), ("Santo (Acústico)", (), "Acustico"),
                           ("Santo", (), ""), ("Santo", ("Compilation",), ""), ("Live Like That", (), "")):
    check(f"«{title}» {types} → «{want}»", version_of(rec(title, types=types)) == want, version_of(rec(title, types=types)))
item = identify([match(1.0, rec("Santo", types=("Live",)))], 200, ["Santo"], conf)
check("la versión queda en el título", item.title == "Santo (En Vivo)" and item.version == "En Vivo", item)
for title in ("Santo (Live)", "Santo (Acústico)", "Santo (Acoustic)", "Santo (En Vivo)", "Santo - Remix"):
    item = identify([match(1.0, rec(title))], 200, ["Santo"], conf)
    check(f"«{title}» no se duplica", item.title == title, item.title)
item = identify([match(1.0, rec("En La Pista"))], 200, ["En La Pista"], conf)
check("«En La Pista» no se inventa que sea instrumental", item.title == "En La Pista" and item.version == "", item)
item = identify([match(1.0, rec("99 - Problems"))], 200, ["99 Problems"], conf)
check("un número que dice la base de datos no se recorta", item.title == "99 - Problems", item.title)
item = identify([match(1.0, rec(artists=("Earth, Wind & Fire",)))], 200, ["Santo"], conf)
check("un artista que la base da como uno se conserva, aunque lleve coma", item.artist == "Earth, Wind & Fire", item.artist)

print("[Niveles configurables]")
item = identify([match(0.8)], 200, ["Santo"], Confidence(auto_score=0.7))
check("cambia el mínimo de la huella", item.decision == DECISION_AUTO, item)
item = identify([match(1.0, rec(duration=260))], 200, ["Santo"], Confidence(max_duration_diff_s=90))
check("cambia la tolerancia de duración", item.decision == DECISION_AUTO, item)
s = QSettings("ReproductorMusicaTest", "ReproductorMusica"); prefs = Preferences(s)
check("de fábrica", prefs.confidence == Confidence() and prefs.acoustid_key == "")
prefs.confidence = Confidence(0.8, 0.95, 7); prefs.acoustid_key = "  clave  "
check("se guardan", prefs.confidence == Confidence(0.8, 0.95, 7) and prefs.acoustid_key == "clave")
s.setValue(Preferences.AUTO_SCORE, "roto"); s.setValue(Preferences.STRONG_SCORE, 9)
check("un valor dañado no rompe nada", prefs.confidence.auto_score == Confidence().auto_score and prefs.confidence.strong_score == 1.0, prefs.confidence)
prefs.confidence = Confidence(); prefs.acoustid_key = ""

print("[Respuestas de AcoustID]")
raw = json.dumps({"status": "ok", "results": [
    {"id": "a", "score": 0.5, "recordings": [{"id": "x", "title": "Baja", "duration": 200, "artists": [{"name": "B"}]}]},
    {"id": "b", "score": 0.98, "recordings": [{"id": "r", "title": "Santo", "duration": 201, "artists": [{"name": "New Wine", "joinphrase": " & "}, {"name": "Otro"}],
                                               "releasegroups": [{"id": "g", "title": "Disco", "secondarytypes": ["Live"]}]},
                                              {"id": "sin-datos"}]},
    {"id": "c", "score": 0.97}]})
parsed = al.parse(raw)
check("ordena, y descarta grabaciones sin datos", parsed[0].score == 0.98 and len(parsed[0].recordings) == 1 and parsed[0].recordings[0].artists == ("New Wine", "Otro"), parsed[0])
check("lee el tipo de álbum", parsed[0].recordings[0].secondary_types == ("Live",))
check("una huella sin grabaciones no se pierde", parsed[1].recordings == () and parsed[1].score == 0.97)
for bad in ("no es json", '{"sin": "status"}', '{"status": "error"}', '{"status": "ok", "results": "x"}', "[]"):
    try:
        al.parse(bad); check(f"respuesta rara: {bad}", False)
    except al.ServiceError:
        check(f"respuesta rara es error del servicio: {bad}", True)
class Answer(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
real_open = al._opener.open; sent = []; real_wait = al._RETRY_WAIT_S; al._RETRY_WAIT_S = 0
def http_error(code, body):
    return urllib.error.HTTPError(al._LOOKUP_URL, code, "x", {}, io.BytesIO(body))
def answers(*queue):
    queue = list(queue)
    def fake(request, timeout):
        sent.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception): raise item
        return Answer(item)
    al._opener.open = fake
INVALID = b'{"error": {"code": 4, "message": "invalid API key"}, "status": "error"}'
BAD_FP = b'{"error": {"code": 3, "message": "invalid fingerprint"}, "status": "error"}'
answers(b'{"status": "ok", "results": []}')
check("envía clave, duración y huella; nunca audio", al.lookup_raw("K", 200.4, "HUELLA") and b"client=K" in sent[-1].data and b"duration=200" in sent[-1].data and b"fingerprint=HUELLA" in sent[-1].data)
check("se identifica con contacto, como pide MusicBrainz", "github.com" in online_lookup.USER_AGENT)
answers(http_error(503, b""), urllib.error.URLError("x"), b'{"status": "ok"}')
check("reintenta lo pasajero", al.lookup_raw("K", 1, "H") == '{"status": "ok"}')
answers(http_error(503, b""), http_error(503, b""), http_error(503, b""))
try:
    al.lookup_raw("K", 1, "H"); check("se rinde tras varios intentos", False)
except al.ServiceError:
    check("se rinde tras varios intentos", True)
answers(http_error(400, INVALID))
try:
    al.lookup_raw("K", 1, "H"); check("clave rechazada", False)
except al.InvalidKey:
    check("clave rechazada: no reintenta", True)
answers(http_error(400, INVALID))
try:
    al.check_key("K"); check("comprobar: clave mala", False)
except al.InvalidKey:
    check("comprobar: clave mala", True)
answers(http_error(400, BAD_FP)); al.check_key("K"); check("comprobar: pasa la clave y solo falla la huella de prueba, sirve", True)
check("  sin enviar ninguna canción", b"fingerprint=AQAA" in sent[-1].data)
answers(urllib.error.URLError("sin red"))
try:
    al.check_key("K"); check("comprobar: sin internet", False)
except al.ServiceError:
    check("comprobar: sin internet no dice que la clave es mala", True)
al._opener.open = real_open; al._RETRY_WAIT_S = real_wait
t = time.perf_counter(); al._wait_turn(); al._wait_turn(); al._wait_turn()
check("máximo 3 consultas por segundo", time.perf_counter() - t >= 2 * al._MIN_INTERVAL_S * 0.95)

print("[Identificar por lotes]")
db_file = os.path.join(work, "org.db"); db = OrganizerDb(db_file)
def add(n):
    rows = [(os.path.join(work, f"cancion {i}.mp3"), 1, i) for i in range(n)]
    db.register(rows); ids = [r.id for r in db.pending_analysis()]
    db.save_results([(i, 200.0, f"H{i}") for i in ids], []); return ids
ids = add(50)
OK = json.dumps({"status": "ok", "results": [{"id": "a", "score": 1.0, "recordings": [{"id": "r", "title": "Santo", "duration": 200, "artists": [{"name": "New Wine"}]}]}]})
NONE = '{"status": "ok", "results": []}'
calls = []
def service(key, duration, value):
    calls.append(value); return NONE if value.endswith("7") else OK
def run(lookup, key="K", cancel_after=None):
    worker = IdentifyWorker(key, Confidence(), db_file, lookup); got = []; worker.finished.connect(got.append)
    if cancel_after is not None:
        inner = lookup; seen = [0]
        def counting(*a):
            seen[0] += 1
            if seen[0] >= cancel_after: worker.cancel()
            return inner(*a)
        worker._lookup = counting
    worker.run(); return got[0]
stopped = run(service, cancel_after=10)
check("se detiene sin perder lo hecho", stopped.cancelled and len(db.pending_identification()) == 40, len(db.pending_identification()))
calls.clear(); result = run(service)
check("retoma donde iba", len(calls) == 40 and not db.pending_identification(), len(calls))
check("reparte automáticas y a revisar", result.automatic + result.review == 40 and db.identification(7).decision == DECISION_REVIEW and db.identification(1).decision == DECISION_AUTO, result)
check("  y lo guarda", db.identification(ids[0]).title == "Santo")
db.forget_identifications(); calls.clear(); result = run(service)
check("decidir otra vez no repite consultas (caché)", not calls and result.from_cache == 50 and result.automatic + result.review == 50, result)
db.forget_identifications()
def boom(*a): raise al.ServiceError("sin internet")
result = run(boom)
check("con lo guardado en caché funciona sin internet", not result.problem and result.from_cache == 50 and not db.pending_identification(), result)
db.conn.execute("DELETE FROM api_cache"); db.conn.commit(); db.forget_identifications()
result = run(boom)
check("sin caché ni internet: nada queda como dudosa", result.problem == "sin internet" and result.review == 0 and len(db.pending_identification()) == 50, result)
def rejected(*a): raise al.InvalidKey
result = run(rejected)
check("clave mala: lo dice y no marca nada", result.invalid_key and result.review == 0 and len(db.pending_identification()) == 50, result)
def strange(*a): return "no es json"
result = run(strange)
check("respuesta rara: no se guarda en caché", result.problem and db.conn.execute("select count(*) from api_cache").fetchone()[0] == 0, result)
db.register([(os.path.join(work, "cancion 0.mp3"), 2, 0)])
check("si el archivo cambió, se olvida lo identificado", db.identification(ids[0]) is None and db.fingerprint(ids[0]) is None)
old = os.path.join(work, "vieja.db"); import sqlite3
c = sqlite3.connect(old); c.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, path_key TEXT UNIQUE, size INT, mtime_ns INT, status TEXT, problem TEXT)")
c.execute("INSERT INTO files VALUES (1,'a','a',1,1,'nuevo',NULL)"); c.execute("PRAGMA user_version = 1"); c.commit(); c.close()
migrated = OrganizerDb(old)
check("una base de la versión anterior se actualiza conservando los datos", migrated.counts() == {"nuevo": 1} and migrated.identification(1) is None); migrated.close()
db.close()

print("[Pedir la clave]")
from app.ui import acoustid_dialog as ad
opened = []; QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()))
checks = []
def fake_check(key):
    checks.append(key)
    if key == "mala": raise al.InvalidKey
    if key == "sinred": raise al.ServiceError("Sin conexión")
ad.acoustid_lookup.check_key = fake_check
dialog = ad.AcoustIdKeyDialog(prefs); dialog.show(); spin(50)
check("sin clave no se puede guardar", not dialog.btn_save.isEnabled())
check("explica que es gratis y qué se envía", "gratuito" in dialog.findChildren(ad.QLabel)[0].text() or any("gratuito" in l.text() for l in dialog.findChildren(ad.QLabel)))
dialog.btn_register.click(); spin(20)
check("«Registrarme gratis» abre la página de AcoustID", opened == ["https://acoustid.org/new-application"], opened)
dialog.key.setText("mala"); dialog.btn_save.click(); spin(3000, lambda: not dialog.runner.busy); spin(20)
check("clave rechazada: lo explica, no la guarda y sigue abierta", "aplicación" in dialog.message.text() and not prefs.acoustid_key and dialog.isVisible(), dialog.message.text())
dialog.key.setText("sinred"); dialog.btn_save.click(); spin(3000, lambda: not dialog.runner.busy); spin(20)
check("sin internet: no dice que la clave sea mala", dialog.message.text() == "Sin conexión" and not prefs.acoustid_key, dialog.message.text())
dialog.key.setText("  buena  "); dialog.btn_save.click(); spin(3000, lambda: not dialog.runner.busy); spin(20)
check("clave aceptada: la guarda y se cierra", prefs.acoustid_key == "buena" and not dialog.isVisible() and dialog.result() == 1, prefs.acoustid_key)
check("se comprueba la clave sin los espacios sobrantes", checks[-1] == "buena")
dialog = ad.AcoustIdKeyDialog(prefs); dialog.show(); spin(50)
check("la próxima vez ya aparece puesta", dialog.key.text() == "buena"); dialog.reject(); spin(20)
prefs.acoustid_key = ""

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
