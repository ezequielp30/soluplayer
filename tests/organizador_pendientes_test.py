"""Organizador, fase 5: PENDIENTES_REVISION. Mover sin cambiar nombre ni etiquetas, registrar todo, reintentar y devolver a
su ubicación ya normalizada, sin pisar nada ni tras un corte. AcoustID simulado y todo en carpetas temporales."""
import hashlib, json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_pendientes_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QCoreApplication
app = QCoreApplication(sys.argv)
from mutagen.id3 import ID3
import audio_sintetico as synth
from app import normalizer, organizer, pending_review as pr
from app.normalizer import SongJob
from app.organizer import DECISION_AUTO, DECISION_REVIEW, PENDING_FOLDER, Confidence, Identification
from app.organizer_db import PENDING_MOVING, PENDING_RETURNED, PENDING_RETURNING, PENDING_WAITING, OrganizerDb, cache_key
from app.organizer_job import AnalyzeWorker, IdentifyWorker, MoveToPendingWorker, ResolvePendingWorker

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
root = os.path.join(work, "Coleccion"); backups = os.path.join(work, "Respaldos")
db_file = os.path.join(work, "org.db"); db = OrganizerDb(db_file)
counter = [0]
def song(relative="Rara.mp3", title="Titulo raro", artist="canal123"):
    counter[0] += 1
    path = os.path.join(root, relative); os.makedirs(os.path.dirname(path), exist_ok=True)
    synth.mp3(path, 3, title=title, artist=artist, seed=counter[0]); os.utime(path, (1500000000, 1500000000))
    info = os.stat(path); db.register([(path, info.st_size, info.st_mtime_ns)]); fid = db.file(path).id
    db.save_results([(fid, 3.0, f"HUELLA{fid}")], [])
    return path, fid
DOUBT = Identification(DECISION_REVIEW, "La huella se parece solo en un 60%.", 0.6, candidates=("Santo - New Wine", "Santo - Otro"))

print("[Mover a pendientes]")
path, fid = song(os.path.join("sub", "carpeta", "Rara (Video Oficial).mp3"))
original = sha(path)
pending = pr.move_to_pending(db, fid, root, DOUBT)
expected = os.path.join(root, PENDING_FOLDER, "sub", "carpeta", "Rara (Video Oficial).mp3")
check("va a la carpeta física, conservando subcarpetas", pending.pending_path == expected and os.path.isfile(expected) and not os.path.exists(path), pending.pending_path)
check("sin cambiar nombre ni contenido", os.path.basename(expected) == os.path.basename(path) and sha(expected) == original)
check("  ni su fecha", int(os.path.getmtime(expected)) == 1500000000)
check("registra nombre, ubicación, metadatos, motivo y coincidencias", pending.original_path == path and "Titulo raro" in pending.original_tags and "60%" in pending.reason and pending.candidates == DOUBT.candidates, pending)
check("los metadatos anotados se pueden leer", isinstance(json.loads(pending.original_tags), dict))
check("queda como pendiente", [p.file_id for p in db.pending_songs()] == [fid] and pending.state == PENDING_WAITING)
check("el análisis apunta a su lugar nuevo y conserva la huella", db.file_by_id(fid).path == expected and db.fingerprint(fid) is not None)
check("al volver a examinar no se analiza como canción nueva", expected not in [e[0] for e in organizer.collect_mp3([root])])
try:
    pr.move_to_pending(db, fid, root, DOUBT); check("moverla dos veces", False)
except pr.PendingError:
    check("moverla dos veces: se rechaza", sha(expected) == original)

print("[No pisa nada]")
first, f1 = song(os.path.join("a", "Igual.mp3")); second, f2 = song(os.path.join("b", "Igual.mp3"))
p1 = pr.move_to_pending(db, f1, root, DOUBT); p2 = pr.move_to_pending(db, f2, root, DOUBT)
check("mismo nombre en distintas carpetas: no chocan ni cambian de nombre", os.path.isfile(p1.pending_path) and os.path.isfile(p2.pending_path) and p1.pending_path != p2.pending_path and os.path.basename(p2.pending_path) == "Igual.mp3")
clash, cfid = song("Choque.mp3"); occupied = os.path.join(root, PENDING_FOLDER, "Choque.mp3")
os.makedirs(os.path.dirname(occupied), exist_ok=True); open(occupied, "wb").write(b"otro archivo"); before = sha(clash)
try:
    pr.move_to_pending(db, cfid, root, DOUBT); check("destino ocupado", False)
except pr.PendingError:
    check("destino ocupado: no pisa, y la canción se queda", open(occupied, "rb").read() == b"otro archivo" and sha(clash) == before and db.open_pending(cfid) is None)
os.remove(occupied)
inuse, ufid = song("EnUso.mp3"); holder = open(inuse, "rb")
try:
    pr.move_to_pending(db, ufid, root, DOUBT); check("archivo en uso", False)
except pr.PendingError:
    check("archivo en uso: se queda y no queda anotada", os.path.isfile(inuse) and db.open_pending(ufid) is None)
holder.close()
gone, gfid = song("Borrada.mp3"); os.remove(gone)
try:
    pr.move_to_pending(db, gfid, root, DOUBT); check("ya no está", False)
except pr.PendingError:
    check("ya no está: lo dice", db.open_pending(gfid) is None)
deep_name = "x" * 200; longp, lfid = song("Larga.mp3")
try:
    pr.move_to_pending(db, lfid, os.path.join(root, deep_name) if False else root, DOUBT); db.remove_pending(db.open_pending(lfid).id); os.rename(pr.pending_path_for(longp, root), longp)
    check("ruta normal se mueve", True)
except pr.PendingError as exc:
    check("ruta normal se mueve", False, exc)
real_max = pr.MAX_PATH; pr.MAX_PATH = 10
try:
    pr.move_to_pending(db, lfid, root, DOUBT); check("ruta demasiado larga", False)
except pr.PendingError:
    check("ruta demasiado larga: se queda donde está", os.path.isfile(longp))
pr.MAX_PATH = real_max

print("[Raíz correcta]")
check("la carpeta elegida más específica", pr.root_of(os.path.join(root, "a", "b.mp3"), [root, os.path.join(root, "a")]) == os.path.join(root, "a"))
check("sin carpeta elegida: la del archivo", pr.root_of(os.path.join(work, "z", "b.mp3"), [root]) == os.path.join(work, "z"))
check("no confunde «Coleccion2» con «Coleccion»", pr.root_of(os.path.join(work, "Coleccion2", "b.mp3"), [root]) == os.path.join(work, "Coleccion2"))

print("[Devolver a su ubicación]")
back = pr.return_to_origin(db, pending)
check("vuelve a su lugar, idéntica", back.state == PENDING_RETURNED and sha(path) == original and not os.path.exists(expected))
check("y el análisis apunta a su lugar", db.file_by_id(fid).path == path and db.open_pending(fid) is None)
check("se borran las subcarpetas vacías de pendientes, y solo esas", not os.path.exists(os.path.dirname(expected)) and os.path.isfile(p1.pending_path), os.path.dirname(expected))
other = os.path.join(root, "a", "Igual.mp3"); open(other, "wb").write(b"alguien puso otro")
try:
    pr.return_to_origin(db, p1); check("origen ocupado", False)
except pr.PendingError:
    check("origen ocupado: no pisa y sigue pendiente", open(other, "rb").read() == b"alguien puso otro" and os.path.isfile(p1.pending_path) and db.open_pending(f1).state == PENDING_WAITING)
os.remove(other); os.rmdir(os.path.join(root, "a"))
p1b = pr.return_to_origin(db, db.open_pending(f1))
check("su carpeta original se había borrado: la vuelve a crear", os.path.isfile(first) and p1b.state == PENDING_RETURNED)
lost = db.open_pending(f2); os.remove(lost.pending_path)
try:
    pr.return_to_origin(db, lost); check("ya no está en pendientes", False)
except pr.PendingError:
    check("ya no está en pendientes: lo dice", True)
db.remove_pending(lost.id)

print("[Corte de luz]")
c1, c1id = song("Corte1.mp3")
row = db.add_pending(c1id, c1, pr.pending_path_for(c1, root), "{}", "r", "[]")
check("  (a medias, sin llegar a moverse)", row.state == PENDING_MOVING)
c2, c2id = song("Corte2.mp3"); target2 = pr.pending_path_for(c2, root)
row2 = db.add_pending(c2id, c2, target2, "{}", "r", "[]"); os.makedirs(os.path.dirname(target2), exist_ok=True); os.rename(c2, target2)
c3, c3id = song("Corte3.mp3"); row3 = pr.move_to_pending(db, c3id, root, DOUBT); db.set_pending_state(row3.id, PENDING_RETURNING); os.rename(row3.pending_path, c3)
c4, c4id = song("Corte4.mp3"); row4 = pr.move_to_pending(db, c4id, root, DOUBT); db.set_pending_state(row4.id, PENDING_RETURNING)
check("resuelve cada caso", pr.reconcile(db) == 4)
check("no llegó a moverse: sigue en su sitio, sin anotar", db.open_pending(c1id) is None and os.path.isfile(c1))
check("ya se había movido: queda pendiente", db.open_pending(c2id).state == PENDING_WAITING and db.file_by_id(c2id).path == target2)
check("ya había vuelto: queda devuelta", db.open_pending(c3id) is None and db.file_by_id(c3id).path == c3)
check("no llegó a volver: sigue pendiente", db.open_pending(c4id).state == PENDING_WAITING)
check("no queda nada a medias", not db.unfinished_pending() and pr.reconcile(db) == 0)
check("la biblioteca se puede poner al día tras el corte", c2id in {p.file_id for p in db.unsynced_pending()})
db.mark_pending_synced(db.open_pending(c2id).id); check("  y se anota", c2id not in {p.file_id for p in db.unsynced_pending()})

print("[Reintentar]")
db.close(); db_fresh = os.path.join(work, "flujo.db"); db = OrganizerDb(db_fresh); root = os.path.join(work, "Flujo")
sure = song("Segura.mp3", "Algo", "x"); doubt = song("Dudosa.mp3", "Pista 3", "y"); doubt2 = song("Dudosa2.mp3", "Pista 4", "z")
OK = lambda t: json.dumps({"status": "ok", "results": [{"id": "a", "score": 1.0, "recordings": [{"id": "r", "title": t, "duration": 3, "artists": [{"name": "New Wine"}]}]}]})
known = {f"HUELLA{sure[1]}": "Santa Cancion"}; calls = []
def service(key, duration, value):
    calls.append(value)
    return OK(known[value]) if value in known else '{"status": "ok", "results": []}'
def identify():
    worker = IdentifyWorker("K", Confidence(), db_fresh, service); got = []; worker.finished.connect(got.append); worker.run(); return got[0]
got = identify()
check("una segura y dos dudosas", got.automatic == 1 and got.review == 2, got)
moved = []; worker = MoveToPendingWorker([root], None, db_fresh); done = []; worker.moved.connect(moved.append); worker.finished.connect(done.append); worker.run()
check("solo las dudosas van a pendientes", done[0].moved == 2 and os.path.isfile(sure[0]) and {p.file_id for p in db.pending_songs()} == {doubt[1], doubt2[1]}, done[0])
check("  con el motivo que dio la identificación", all("AcoustID" in p.reason for p in db.pending_songs()))
check("  avisa, para actualizar la biblioteca", len(moved) == 2)
worker = MoveToPendingWorker([root], None, db_fresh); done = []; worker.finished.connect(done.append); worker.run()
check("  otra vez no hace nada", done[0].moved == 0 and not done[0].failed, done[0])
known[f"HUELLA{doubt[1]}"] = "Por Fin"
check("una sola: reintento individual", db.prepare_retry([doubt[1]]) == [doubt[1]] and db.identification(doubt[1]) is None and db.identification(doubt2[1]) is not None)
calls.clear(); got = identify()
check("  vuelve a preguntar de verdad, sin usar la respuesta vieja", calls == [f"HUELLA{doubt[1]}"] and got.automatic == 1, calls)
check("todas: reintento masivo", set(db.prepare_retry()) == {doubt[1], doubt2[1]})
known[f"HUELLA{doubt2[1]}"] = "Tambien"; got = identify()
check("  identifica las dos", got.automatic == 2 and got.review == 0, got)
check("  cuenta los intentos", {p.file_id: p.retries for p in db.pending_songs()} == {doubt[1]: 2, doubt2[1]: 1})

print("[Identificada: procesar y devolver]")
backup_before = sha(db.open_pending(doubt[1]).pending_path); audio_name = doubt[0]
returned, applied = [], []
worker = ResolvePendingWorker([SongJob(doubt[1], "Por Fin", "New Wine")], backups, db_fresh); done = []
worker.returned.connect(returned.append); worker.applied.connect(applied.append); worker.finished.connect(done.append); worker.run()
final = os.path.join(root, "Por Fin - New Wine.mp3")
check("vuelve a su carpeta y queda normalizada", done[0].returned == 1 and done[0].normalized == 1 and os.path.isfile(final) and not os.path.exists(doubt[0]), done[0])
check("  con sus etiquetas", str(ID3(final)["TIT2"]) == "Por Fin" and str(ID3(final)["TPE1"]) == "New Wine")
check("  el respaldo es el original", sha(applied[0].backup_path) == backup_before)
check("  se puede restaurar a su nombre original", normalizer.restore(db, db.item(applied[0].id)) and os.path.isfile(doubt[0]) and sha(doubt[0]) == backup_before)
check("  avisa, para actualizar la biblioteca", len(returned) == 1 and len(applied) == 1)
worker = ResolvePendingWorker(None, backups, db_fresh); done = []; worker.finished.connect(done.append); worker.run()
check("sin decir cuáles: las identificadas como seguras", done[0].returned == 1 and done[0].normalized == 1 and os.path.isfile(os.path.join(root, "Tambien - New Wine.mp3")), done[0])
check("no queda nada en pendientes", not db.pending_songs())
check("la carpeta de pendientes vacía se quita", not os.path.exists(os.path.join(root, PENDING_FOLDER)))
check("no toca las que nunca estuvieron pendientes", os.path.isfile(sure[0]))

print("[Corrección a mano]")
hand = song("AMano.mp3", "Pista 9", "w"); db.save_identifications([(hand[1], DOUBT)]); pending = pr.move_to_pending(db, hand[1], root, DOUBT)
worker = ResolvePendingWorker([SongJob(hand[1], "Elegida A Mano", "Quien Sea")], backups, db_fresh); done = []; worker.finished.connect(done.append); worker.run()
check("la persona decide el título y el artista", os.path.isfile(os.path.join(root, "Elegida A Mano - Quien Sea.mp3")) and done[0].normalized == 1, done[0])

print("[Si falla al devolver]")
stuck = song("Atascada.mp3", "Pista 8", "v"); pending = pr.move_to_pending(db, stuck[1], root, DOUBT); open(stuck[0], "wb").write(b"ocupado"); kept = sha(pending.pending_path)
worker = ResolvePendingWorker([SongJob(stuck[1], "Atascada", "A")], backups, db_fresh); done = []; worker.finished.connect(done.append); worker.run()
check("sigue pendiente, intacta, y se avisa", done[0].failed and sha(pending.pending_path) == kept and db.open_pending(stuck[1]).state == PENDING_WAITING and open(stuck[0], "rb").read() == b"ocupado", done[0].failed)
db.close()

print("[Base de la versión anterior]")
import sqlite3
old = os.path.join(work, "vieja.db"); c = sqlite3.connect(old)
c.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, path_key TEXT UNIQUE, size INT, mtime_ns INT, status TEXT, problem TEXT)")
c.execute("INSERT INTO files VALUES (1,'a','a',1,1,'nuevo',NULL)"); c.execute("PRAGMA user_version = 3"); c.commit(); c.close()
m = OrganizerDb(old); check("se actualiza conservando los datos", m.counts() == {"nuevo": 1} and m.pending_songs() == []); m.close()

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
