"""1.12.9: apartar las canciones que no se pueden igualar (otro formato, no se pudieron medir, o bajas con picos
altos ya en su límite) a «_Volumen sin igualar» en la carpeta principal de la música. Todo en carpetas temporales."""
import math, os, struct, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_apartar_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import loudness
from app.config import database_path
from app.database import Database
from app.file_operations import KIND_FILES, FileOperations
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def tone(path, secs=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))
    return path
def fake_mp3(path):  # para estas pruebas basta con que exista y tenga la extensión (no se decodifica)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(b"\xff\xfb\x90\x00" * 200)
    return path

root = os.path.join(work, "Musica Cristiana")
paths = {
    "ok": fake_mp3(os.path.join(root, "Alabanza", "bien.mp3")),
    "loud": fake_mp3(os.path.join(root, "Alabanza", "fuerte.mp3")),
    "peaky": fake_mp3(os.path.join(root, "Coros", "baja con picos.mp3")),
    "broken": fake_mp3(os.path.join(root, "Coros", "danada.mp3")),
    "wav": tone(os.path.join(root, "Grabaciones", "ensayo.wav")),
    "twin": fake_mp3(os.path.join(root, "Otro album", "danada.mp3")),  # mismo nombre que «danada.mp3»
}
db = Database(database_path())
from app.models import Track
with db.conn:
    for key, p in paths.items():
        db.conn.execute("INSERT INTO tracks (path, path_key, title, artist, album, genre, duration_ms, added_at) VALUES (?,?,?,?,?,?,?,?)",
                        (p, os.path.normcase(p), key, "", "", "", 1000, "2026-10-28"))
by_name = {t.title: t for t in db.all_tracks()}
unmeasurable = getattr(loudness, "UNMEASURABLE_LUFS", None)
db.save_loudness([
    (by_name["ok"].id, -16.2, -3.0), (by_name["loud"].id, -8.0, -0.2), (by_name["peaky"].id, -24.0, -1.4),
    (by_name["broken"].id, unmeasurable, None), (by_name["twin"].id, unmeasurable, None), (by_name["wav"].id, -30.0, -12.0),
])
pl = db.create_playlist("Domingo"); db.add_to_playlist(pl.id, [t.id for t in db.all_tracks()])
library = db.all_tracks()

print("[Cuáles no se pueden igualar]")
why = getattr(loudness, "why_not_equalizable", None)
from app.loudness_job import can_adjust
reasons = {t.title: why(t, can_adjust(t.path)) for t in library} if why else {}
check("se apartan: otro formato, no se pudo medir y bajas con picos altos", why is not None
      and set(k for k, r in reasons.items() if r) == {"wav", "broken", "twin", "peaky"}, reasons)
check("  no se apartan las que se pueden igualar (bien, o fuerte que se puede bajar)", reasons.get("ok") is None and reasons.get("loud") is None)
partial = Track(id=99, path=paths["peaky"], title="p", artist="", album="", genre="", duration_ms=1, added_at="",
                loudness_lufs=-24.0, true_peak_db=-6.0)
check("  una baja que todavía puede subir algo NO se aparta (primero se iguala)", why is not None and why(partial, True) is None)

print("[Mover a «_Volumen sin igualar»]")
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
set_aside = getattr(ops, "set_aside", None)
items = [(t, r) for t in library if (r := reasons.get(t.title))]
outcome = set_aside(items, library) if set_aside else None
from app.utils import long_path
folder = long_path(os.path.join(root, "_Volumen sin igualar")) if os.path.isdir(os.path.join(root, "_Volumen sin igualar")) else os.path.join(long_path(root), "_Volumen sin igualar")
check("la carpeta está en la principal de la música, con su nombre", outcome is not None and os.path.normcase(outcome.folder) == os.path.normcase(folder),
      outcome and outcome.folder)
moved_names = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
check("  ahí quedan las canciones apartadas (y un LEEME.txt)", moved_names == sorted(["LEEME.txt", "baja con picos.mp3", "danada.mp3", "ensayo.wav"]),
      moved_names)
check("  si dos se llaman igual, la segunda no se mueve (nunca se pisa nada) y se avisa", os.path.exists(paths["twin"]) and outcome
      and len(outcome.failed) == 1, outcome and outcome.failed)
leeme = open(os.path.join(folder, "LEEME.txt"), encoding="utf-8").read() if os.path.isdir(folder) else ""
check("  el LEEME explica qué es y el motivo de cada una", "baja con picos.mp3" in leeme and "Picos altos" in leeme and "Otro formato" in leeme
      and "No se pudo medir" in leeme, leeme[:200])
check("  siguen en la biblioteca y en la playlist, con la ruta nueva", len(db.playlist_tracks(pl.id)) == 6
      and any(os.path.normcase(os.path.dirname(t.path)) == os.path.normcase(folder) for t in db.all_tracks()))
entry = next((e for e in ops.history(db.all_tracks()) if e.kind == KIND_FILES and e.can_undo), None)
check("  y se puede deshacer desde el Historial", entry is not None and entry.count == 3, entry and (entry.title, entry.count))
if entry is not None:
    ops.undo(entry)
check("  deshacer las devuelve a su lugar", all(os.path.exists(p) for p in paths.values()))

print("[Marca de «no se pudo medir»]")
d = loudness.decide(unmeasurable, None, -16.0) if unmeasurable is not None else None
check("una canción que no se pudo medir queda marcada (no como «sin analizar»)", unmeasurable is not None and d.status == "sin datos")

print("[Revisión: LEEME, marca, segunda vez, carpeta principal y otros formatos]")
raw_leeme = open(os.path.join(folder, "LEEME.txt"), "rb").read() if os.path.isdir(folder) else b""
check("el LEEME tiene saltos de línea normales de Windows (sin líneas en blanco de más)", raw_leeme and b"\r\r\n" not in raw_leeme)
store = getattr(loudness, "measurement_to_store", None)
check("si el archivo no está (USB desconectado), no se marca como dañado: queda pendiente",
      store is not None and store(None, os.path.join(work, "no-esta.mp3")) is None)
check("  si está pero no se pudo leer o no tiene audio, sí se marca", store is not None and store(None, paths["ok"]) == unmeasurable)
db.save_loudness([(by_name["broken"].id, unmeasurable, None)])
broken = next(t for t in db.all_tracks() if t.title == "broken")
ops.record_volume(broken, -3, 0)  # p. ej. «Revertir» de una que se había subido antes
broken = next(t for t in db.all_tracks() if t.title == "broken")
check("revertir no convierte la marca en una medición falsa", not loudness.plausible(broken.loudness_lufs, broken.true_peak_db), broken.loudness_lufs)
if set_aside:
    library = db.all_tracks()
    first = set_aside([(t, r) for t in library if (r := why(t, can_adjust(t.path)))], library)
    again = [(t, r) for t in db.all_tracks() if (r := why(t, can_adjust(t.path)))]
    in_folder = [t for t, _r in again if os.path.basename(os.path.dirname(t.path)) == "_Volumen sin igualar"]
    check("las ya apartadas no se vuelven a ofrecer (el contador llega a cero)", in_folder == [], [t.title for t in in_folder])
library_root = getattr(__import__("app.file_operations", fromlist=["library_root"]), "library_root")
def T(p): return Track(id=0, path=p, title="", artist="", album="", genre="", duration_ms=1, added_at="")
many = [T(f"D:\\Musica Cristiana\\Album {n}\\c.mp3") for n in range(40)] + [T("D:\\Descargas\\suelta.mp3")]
for t in many:
    t.available = True
check("una canción suelta en Descargas no lleva la carpeta a la raíz del disco", library_root(many).lower() == "d:\\musica cristiana",
      library_root(many))
spread_out = [T(f"D:\\{n}\\c.mp3") for n in range(10)]
try:
    root_answer = library_root(spread_out)
except Exception as exc:
    root_answer = f"rechazada: {exc}"
check("  si la única carpeta común es la raíz del disco, no se usa", not str(root_answer).rstrip("\\").endswith(":"), root_answer)
flac_unanalyzed = Track(id=1, path="C:\\m\\x.flac", title="", artist="", album="", genre="", duration_ms=1, added_at="")
flac_ok = Track(id=2, path="C:\\m\\y.flac", title="", artist="", album="", genre="", duration_ms=1, added_at="",
                loudness_lufs=-16.2, true_peak_db=-3.0)
check("un archivo de otro formato sin analizar, o ya al volumen correcto, no se aparta",
      why(flac_unanalyzed, False) is None and why(flac_ok, False) is None, (why(flac_unanalyzed, False), why(flac_ok, False)))

db.close()
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
