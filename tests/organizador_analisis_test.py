"""Organizador, fase 2: recorrer carpetas, calcular huellas, guardarlas y retomar. Nunca modifica la música. Todo en
carpetas temporales. Si está fpcalc (tools/obtener_fpcalc.py) también se prueba de verdad; si no, se dice que no se probó."""
import hashlib, json, os, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_analisis_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QCoreApplication, QEventLoop, QThread
app = QCoreApplication(sys.argv)
import audio_sintetico as synth
from app import fingerprint, organizer
from app.organizer_db import STATUS_ANALYZED, STATUS_DAMAGED, STATUS_NEW, OrganizerDb
from app.organizer_job import BATCH_SIZE, AnalyzeWorker

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

music = os.path.join(work, "Coleccion"); deep = os.path.join(music, "a", "b", "c"); os.makedirs(deep)
def fake_mp3(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(content); return path
top = fake_mp3(os.path.join(music, "Uno.mp3")); low = fake_mp3(os.path.join(deep, "Dos.MP3"))
fake_mp3(os.path.join(music, "foto.jpg")); fake_mp3(os.path.join(music, "tres.wav"))
for skipped in (organizer.PENDING_FOLDER, organizer.BACKUP_FOLDER, "_Repetidas para revisar", "_originales convertidos", "AppData", "$RECYCLE.BIN"):
    fake_mp3(os.path.join(music, skipped, "no.mp3"))

print("[Recorrer carpetas]")
paths = [e[0] for e in organizer.collect_mp3([music])]
check("encuentra MP3 en subcarpetas, y solo MP3", sorted(paths) == sorted([top, low]), paths)
check("omite pendientes, respaldos y carpetas del sistema", not any(os.path.basename(p) == "no.mp3" for p in paths))
check("raíces repetidas no duplican", len(list(organizer.collect_mp3([music, music]))) == 2)
check("varias carpetas a la vez", len(list(organizer.collect_mp3([deep, os.path.join(music, "a")]))) == 1)
problems = []
list(organizer.collect_mp3([os.path.join(work, "no-existe"), music], on_problem=lambda p, e: problems.append(p)))
check("una carpeta inaccesible se avisa y se sigue", len(problems) == 1 and len(list(organizer.collect_mp3([os.path.join(work, "no-existe"), music]))) == 2)
stop = [False]; walker = organizer.collect_mp3([music], lambda: stop[0]); next(walker); stop[0] = True
check("se puede detener", not list(walker))

print("[Analizar]")
db_file = os.path.join(work, "org.db")
def run(roots, compute, cancel_after=None):
    worker = AnalyzeWorker(roots, db_file, compute); got = []
    worker.finished.connect(got.append)
    if cancel_after is not None:
        original = worker._compute; seen = [0]
        def counting(p):
            seen[0] += 1
            if seen[0] >= cancel_after: worker.cancel()
            return original(p)
        worker._compute = counting
    worker.run()
    return got[0]
calls = []
def good(path):
    calls.append(path); return fingerprint.Fingerprint(10.0, "HUELLA-" + os.path.basename(path))
before = {p: sha(p) for p in (top, low)}
first = run([music], good)
check("calcula todas las huellas", first.found == 2 and first.computed == 2 and first.damaged == 0, first)
db = OrganizerDb(db_file)
check("quedan guardadas", db.fingerprint(db.file(top).id) == (10.0, "HUELLA-Uno.mp3"))
calls.clear(); second = run([music], good)
check("la segunda vez no repite nada", not calls and second.computed == 0 and second.reused == 2, second)
os.utime(top, (1500000000, 1500000000)); calls.clear(); third = run([music], good)
check("si el archivo cambió, se analiza de nuevo", calls == [top] and third.computed == 1, calls)
check("el análisis no modifica la música", {p: sha(p) for p in (low,)} == {low: before[low]} and sha(top) == before[top])

print("[Archivos dañados]")
broken = fake_mp3(os.path.join(music, "Roto.mp3"))
def some_broken(path):
    if path == broken: raise fingerprint.DamagedFile("parece dañado")
    return good(path)
result = run([music], some_broken)
row = db.file(broken)
check("se marca y no detiene lo demás", result.damaged == 1 and row.status == STATUS_DAMAGED and row.problem == "parece dañado", result)
calls.clear(); run([music], good)
check("  no se reintenta si no cambió", broken not in calls and db.file(broken).status == STATUS_DAMAGED, calls)
fake_mp3(broken, b"reparado"); run([music], good)
check("  si cambia, se vuelve a mirar", db.file(broken).status == STATUS_ANALYZED)

print("[Sin fpcalc]")
def no_tool(path): raise fingerprint.ToolMissing("falta fpcalc")
fresh = fake_mp3(os.path.join(music, "Nueva.mp3")); result = run([music], no_tool)
check("se avisa y no se marca nada como dañado", result.problems == ["falta fpcalc"] and db.file(fresh).status == STATUS_NEW, result)

print("[Detener y retomar]")
many = os.path.join(work, "Muchas"); os.makedirs(many)
for i in range(BATCH_SIZE * 3):
    fake_mp3(os.path.join(many, f"{i:04d}.mp3"))
calls.clear(); stopped = run([many], good, cancel_after=BATCH_SIZE)
check("se detiene sin terminar", stopped.cancelled and stopped.computed < BATCH_SIZE * 3, stopped)
done_first = stopped.computed; calls.clear(); resumed = run([many], good)
check("al retomar solo hace lo que faltaba", resumed.computed == BATCH_SIZE * 3 - done_first and len(calls) == resumed.computed, resumed)
stats = db.counts()
check("no queda nada a medias", stats.get(STATUS_NEW, 0) == 1, stats)  # «Nueva.mp3», la de la prueba sin fpcalc
check("no toca lo pendiente de otras carpetas", db.file(fresh).status == STATUS_NEW and fresh not in calls)

print("[En su propio hilo]")
worker = AnalyzeWorker([deep], db_file, good); thread = QThread(); got = []; main_thread = QThread.currentThread()
class Receiver(type(worker).__mro__[1]):
    def done(self, result): got.append((result, QThread.currentThread() == main_thread))
receiver = Receiver(); worker.moveToThread(thread); thread.started.connect(worker.run)
worker.finished.connect(receiver.done); worker.finished.connect(thread.quit); thread.start()
end = time.time() + 10
while time.time() < end and not got:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
thread.wait(5000)
check("avisa al terminar, en el hilo principal", got and got[0][1], got)

print("[Miles de canciones]")
scale = os.path.join(work, "scale.db"); big = OrganizerDb(scale); t = time.time()
rows = [(os.path.join(work, "x", f"{i}.mp3"), 1000 + i, i) for i in range(5000)]
big.register(rows); took = time.time() - t
t = time.time(); big.register(rows); again = time.time() - t
check("anotar 5.000 archivos es rápido", took < 15 and again < 15, f"{took:.1f} s y {again:.1f} s")
pend = big.pending_analysis(); t = time.time()
for s in range(0, 5000, BATCH_SIZE):
    big.save_results([(r.id, 200.0, "H" * 3500) for r in pend[s:s + BATCH_SIZE]], [])
check("guardar 5.000 huellas es rápido", time.time() - t < 30 and big.counts() == {STATUS_ANALYZED: 5000}, f"{time.time() - t:.1f} s")
check("  ocupa lo razonable", os.path.getsize(scale) < 40_000_000, os.path.getsize(scale))
big.close()

print("[Caché de consultas]")
db.store_cached("acoustid", "k", '{"r": 1}')
check("responde lo guardado", db.cached("acoustid", "k", 60) == '{"r": 1}')
check("no si caducó u otra fuente", db.cached("acoustid", "k", -1) is None and db.cached("otro", "k", 60) is None and db.cached("acoustid", "z", 60) is None)
db.close(); db = OrganizerDb(db_file)
check("sobrevive a cerrar y abrir", db.cached("acoustid", "k", 60) == '{"r": 1}' and db.file(top).status == STATUS_ANALYZED)
db.close()

print("[Con fpcalc de verdad]")
if fingerprint.available():
    os.makedirs(os.path.join(work, "real"))
    real = synth.mp3(os.path.join(work, "real", "Real.mp3"), 5, title="Real", artist="A")
    digest = sha(real); print_fp = fingerprint.compute(real)
    check("calcula la huella y la duración", abs(print_fp.duration_s - 5) < 0.5 and len(print_fp.value) > 20, print_fp.duration_s)
    check("no cambia el archivo", sha(real) == digest)
    check("la misma música da la misma huella", fingerprint.compute(real).value == print_fp.value)
    trash = fake_mp3(os.path.join(work, "real", "Basura.mp3"), b"esto no es audio" * 100)
    try:
        fingerprint.compute(trash); check("un archivo dañado se detecta", False)
    except fingerprint.DamagedFile as exc:
        check("un archivo dañado se detecta", True, exc)
    tiny = synth.mp3(os.path.join(work, "real", "Corta.mp3"), 1, title="Corta", artist="A")
    try:
        fingerprint.compute(tiny); check("una canción muy corta", False)
    except fingerprint.DamagedFile as exc:
        check("una canción muy corta se explica como tal, no como dañada", "poco" in str(exc), exc)
    accented = synth.mp3(os.path.join(work, "real", "¿Canción Ñandú, 7 Días?".replace("?", "") + ".mp3"), 3, title="A", artist="B")
    check("nombres con tildes y signos", fingerprint.compute(accented).duration_s > 0)
else:
    print("  NO SE PROBÓ con fpcalc de verdad: falta. Córrelo con tools/obtener_fpcalc.py")

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
