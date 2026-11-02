"""Organizador, fase 7: 5.000 canciones. Análisis e identificación con huella y AcoustID simulados, la tabla, y normalizar
un lote con archivos de verdad para calcular cuánto tardarían todas. La ventana debe seguir respondiendo. Carpetas temporales."""
import json, os, shutil, sys, tempfile, time, tracemalloc
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_escala_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
import audio_sintetico as synth
from app import fingerprint, normalizer, organizer, song_backup
from app.organizer import Confidence
from app.organizer_db import OrganizerDb
from app.organizer_job import AnalyzeWorker, IdentifyWorker, NormalizeWorker
from app.ui.organizer_dialog import ResultRow, ResultsModel

SONGS, REAL_BATCH = 5000, 200
results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def run_threaded(worker):
    """Como en el programa: el trabajador en su hilo y un reloj midiendo si la ventana se traba."""
    thread, done = QThread(), []
    gaps, last = [0.0], [time.perf_counter()]
    def tick():
        now = time.perf_counter(); gaps[0] = max(gaps[0], now - last[0]); last[0] = now
    timer = QTimer(); timer.setInterval(10); timer.timeout.connect(tick); timer.start()
    worker.moveToThread(thread); thread.started.connect(worker.run)
    class Receiver(type(worker).__mro__[1]):
        def finished(self, result): done.append(result)
    receiver = Receiver(); worker.finished.connect(receiver.finished); worker.finished.connect(thread.quit)
    start = time.perf_counter(); thread.start()
    while not done:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    took = time.perf_counter() - start; timer.stop(); thread.wait(5000)
    return done[0], took, gaps[0]

root = os.path.join(work, "Coleccion")
for i in range(SONGS):
    folder = os.path.join(root, f"Disco {i // 100:03d}"); os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, f"{i:05d} cancion.mp3"), "wb").close()
db_file = os.path.join(work, "org.db")

print("[Analizar]")
tracemalloc.start()
walked = time.perf_counter(); count = sum(1 for _ in organizer.collect_mp3([root])); walked = time.perf_counter() - walked
_, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
check("recorrer las carpetas no llena la memoria", count == SONGS and peak < 30_000_000, f"{walked:.1f} s, pico {peak / 1e6:.1f} MB")
result, took, gap = run_threaded(AnalyzeWorker([root], db_file, lambda p: fingerprint.Fingerprint(200.0, "H" * 3500 + os.path.basename(p))))
check("5.000 huellas guardadas por lotes", result.computed == SONGS, f"{took:.1f} s sin contar fpcalc")
check("la ventana sigue respondiendo", gap < 1.5, f"pausa máxima {gap * 1000:.0f} ms")
again, took2, _ = run_threaded(AnalyzeWorker([root], db_file, lambda p: 1 / 0))
check("la segunda vez no repite nada y es rápida", again.computed == 0 and again.reused == SONGS and took2 < 30, f"{took2:.1f} s")

print("[Identificar]")
OK = json.dumps({"status": "ok", "results": [{"id": "a", "score": 1.0, "recordings": [{"id": "r", "title": "Cancion", "duration": 200, "artists": [{"name": "Grupo"}]}]}]})
result, took, gap = run_threaded(IdentifyWorker("K", Confidence(), db_file, lambda k, d, v: OK))
check("5.000 identificaciones", result.total == SONGS, f"{took:.1f} s sin contar la red")
check("la ventana sigue respondiendo", gap < 1.5, f"pausa máxima {gap * 1000:.0f} ms")
print(f"      con el límite de AcoustID, 5.000 consultas tardarían unos {SONGS * 0.34 / 60:.0f} min")

print("[La tabla]")
db = OrganizerDb(db_file)
t = time.perf_counter(); rows = db.result_rows([root]); read = time.perf_counter() - t
check("leer los resultados", len(rows) == SONGS and read < 5, f"{read:.2f} s")
t = time.perf_counter(); items = db.identifications(); query = time.perf_counter() - t
check("leer las identificaciones de una vez", len(items) == SONGS and query < 5, f"{query:.2f} s")
model = ResultsModel(lambda: None)
model.load([ResultRow(r["id"], r["path"], r["title"] or "", r["artist"] or "", r["version"] or "", r["score"], r["decision"] or "", r["reason"] or "", False) for r in rows])
t = time.perf_counter(); model.set_filter(1); model.set_filter(0); model.check_visible(True); changed = time.perf_counter() - t
check("filtrar y marcar 5.000 filas", changed < 2, f"{changed:.2f} s")
db.close()

print("[Normalizar: un lote de archivos de verdad]")
source = synth.mp3(os.path.join(work, "base.mp3"), 60, title="Base", artist="x")
real_db = os.path.join(work, "real.db"); rdb = OrganizerDb(real_db); batch = os.path.join(work, "Reales"); os.makedirs(batch)
paths = []
for i in range(REAL_BATCH):
    p = os.path.join(batch, f"{i:04d} original.mp3"); shutil.copy2(source, p); paths.append(p)
rdb.register([(p, os.stat(p).st_size, os.stat(p).st_mtime_ns) for p in paths])
jobs = [normalizer.SongJob(r.id, f"Cancion {r.id}", "Grupo") for r in rdb.pending_analysis()]
rdb.close()
digest = song_backup.audio_digest(source)
result, took, gap = run_threaded(NormalizeWorker(jobs, os.path.join(work, "Respaldos"), real_db))
check(f"{REAL_BATCH} canciones de 1 minuto normalizadas", result.done == REAL_BATCH and not result.failed, f"{took:.1f} s; {took / REAL_BATCH * 1000:.0f} ms cada una")
check("la ventana sigue respondiendo", gap < 1.5, f"pausa máxima {gap * 1000:.0f} ms")
check("ninguna perdió su audio", all(song_backup.audio_digest(os.path.join(batch, f"Cancion {j.file_id} - Grupo.mp3")) == digest for j in jobs))
check("no quedó ningún original a medias", len(os.listdir(batch)) == REAL_BATCH and not [f for f in os.listdir(batch) if "original" in f or "tmp" in f])
print(f"      5.000 canciones de este tamaño tardarían unos {took / REAL_BATCH * SONGS / 60:.0f} min (en este disco)")

shutil.rmtree(work, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
