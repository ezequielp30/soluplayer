"""1.12.8: igualar el volumen DENTRO de los MP3 (sube las bajas y baja las fuertes), sin pérdida y reversible,
para que suenen parejas en cualquier reproductor. Copias en carpetas temporales; nunca la música real."""
import hashlib, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_igarch_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
import lameenc, numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
app = QCoreApplication(sys.argv)
from app import loudness, mp3gain
from app.loudness import RATE, LoudnessMeter, decide
from app.models import Track

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()
def make_mp3(path, amp, secs=6):
    t = np.arange(44100 * secs) / 44100
    sig = amp * (0.7 * np.sin(2 * np.pi * 330 * t) + 0.3 * np.sin(2 * np.pi * 2500 * t))
    e = lameenc.Encoder(); e.set_bit_rate(192); e.set_in_sample_rate(44100); e.set_channels(1); e.set_quality(2)
    open(path, "wb").write(e.encode((sig * 32767).astype("<i2").tobytes()) + e.flush())
    return path
def measure(path):
    fmt = QAudioFormat(); fmt.setSampleRate(RATE); fmt.setChannelCount(2); fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    meter, st = LoudnessMeter(), {"done": False}
    dec = QAudioDecoder(); dec.setAudioFormat(fmt)
    dec.bufferReady.connect(lambda: meter.add(np.frombuffer(bytes(dec.read().constData()), dtype=np.float32)))
    dec.finished.connect(lambda: st.update(done=True)); dec.error.connect(lambda *_: st.update(done=True))
    dec.setSource(QUrl.fromLocalFile(path)); dec.start()
    while not st["done"]:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    dec.stop(); dec.setSource(QUrl()); app.processEvents()
    return meter.result()

print("[Decisión: igualar todas, subiendo y bajando]")
loud = decide(-8.0, -0.3, -12.0)
check("una canción fuerte (−8 LUFS, referencia −12) se baja −4,5 dB (pasos de 1,5)", loud.status == "alto" and loud.gain_db == -4.5, loud)
quiet = decide(-17.0, -8.0, -12.0)
check("una baja (−17 LUFS, picos −8 dBTP) se sube +4,5 dB", quiet.status == "bajo" and quiet.gain_db == 4.5, quiet)
peak = decide(-17.0, -3.0, -12.0)
check("  si sus picos llegan a −3 dBTP solo +1,5 dB (nunca pasa de −1 dBTP)", peak.gain_db == 1.5 and peak.limited_by_peak, peak)
check("a menos de medio paso (0,75 dB) de la referencia: no se toca", decide(-12.5, -3.0, -12.0).gain_db == 0.0)
check("una ya bajada −10,5 dB no se baja más de −12 dB en total", decide(-6.0, -1.0, -12.0, applied=-10.5).gain_db == -1.5,
      decide(-6.0, -1.0, -12.0, applied=-10.5))
check("una ya subida +12 dB no se sube más", decide(-20.0, -20.0, -12.0, applied=12.0).gain_db == 0.0)

print("[En el archivo: bajar sin pérdida, cualquier reproductor lo respeta, y revertir exacto]")
from app.loudness_job import AdjustWorker
from app.loudness_job import REVERT
song = make_mp3(os.path.join(work, "fuerte.mp3"), 0.9)
original = sha(song)
l0, _tp0 = measure(song)
def T(i, p): return Track(id=i, path=p, title="x", artist="", album="", genre="", duration_ms=6000, added_at="")
got = []
w = AdjustWorker([(T(1, song), -2)]); w.adjusted.connect(lambda *a: got.append(a)); w.run()
l1, _tp1 = measure(song)
check("bajar 2 pasos deja el MP3 3 dB más bajo", got and got[-1][1] == -2 and l0 is not None and abs((l0 - l1) - 3.0) < 0.2,
      (got, l0, l1))
check("  y la nota para revertir queda dentro del propio archivo (−2 pasos)", mp3gain.read_applied_steps(song) == -2,
      mp3gain.read_applied_steps(song))
got.clear()
w = AdjustWorker([(T(1, song), REVERT)]); w.adjusted.connect(lambda *a: got.append(a)); w.run()
check("Revertir lo devuelve byte a byte a como estaba", sha(song) == original and got and got[-1][2] == 0, got)
got.clear()
w = AdjustWorker([(T(1, song), -1), (T(1, song), -1)]); w.adjusted.connect(lambda *a: got.append(a)); w.run()
check("  dos bajadas seguidas suman en la nota (−2 en total)", mp3gain.read_applied_steps(song) == -2, mp3gain.read_applied_steps(song))
w = AdjustWorker([(T(1, song), REVERT)]); w.run()
check("  y revertir deshace las dos", sha(song) == original)

print("[La biblioteca recuerda las bajadas]")
from app.config import database_path
from app.database import Database
from app.file_operations import FileOperations
from app.importer import scan_file
db = Database(database_path())
db.add_tracks([scan_file(song)[0]])
t = db.all_tracks()[0]
db.save_loudness([(t.id, -8.0, -0.3)])
t = db.all_tracks()[0]
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
ops.record_volume(t, -3, -3)
t = db.all_tracks()[0]
check("guarda la ganancia negativa (−4,5 dB) y la nueva medición (−12,5 LUFS)", t.norm_gain_db == -4.5 and t.loudness_lufs == -12.5,
      (t.norm_gain_db, t.loudness_lufs))
entries = [e for e in ops.history(db.all_tracks()) if e.kind == "volumen"]
check("  y figura en el Historial para revertirla", entries and entries[0].count == 1, [(e.title, e.count) for e in entries])
db.close()

print("[Revisión: referencia estable, medio paso, etiquetas, límites e ID3v1]")
import random
random.seed(3)
lib = [Track(id=i, path=f"C:\\m\\{i}.mp3", title="x", artist="", album="", genre="", duration_ms=1, added_at="",
             loudness_lufs=round(random.gauss(-11.5, 3), 2), true_peak_db=round(random.uniform(-6, 0.5), 2)) for i in range(400)]
lib_ref = getattr(loudness, "library_reference", None)
def one_click(tracks):
    ref = lib_ref(tracks) if lib_ref else loudness.reference_level([t.loudness_lufs for t in tracks])
    changed = 0
    for i, t in enumerate(tracks):
        d = decide(t.loudness_lufs, t.true_peak_db, ref, t.norm_gain_db)
        if d.gain_db:
            changed += 1
            tracks[i] = t.copy(loudness_lufs=t.loudness_lufs + d.gain_db, true_peak_db=t.true_peak_db + d.gain_db,
                               norm_gain_db=t.norm_gain_db + d.gain_db)
    return changed, ref
first, ref1 = one_click(lib)
second, ref2 = one_click(lib)
check("pulsar «Igualar» otra vez no vuelve a tocar archivos (la referencia no se corre)", first > 0 and second == 0 and ref1 == ref2,
      (first, second, ref1, ref2))
check("justo a medio paso (0,75 dB) cuenta como igual, sin motivo falso", decide(-12.75, -10.0, -12.0).status == "correcto"
      and decide(-11.25, -1.0, -12.0).status == "correcto", (decide(-12.75, -10.0, -12.0).reason, decide(-11.25, -1.0, -12.0).reason))
from app.ui.loudness_dialog import LoudnessDialog
flac = Track(id=900, path="C:\\m\\fuerte.flac", title="x", artist="", album="", genre="", duration_ms=1, added_at="", loudness_lufs=-6.0, true_peak_db=-0.1)
gone = Track(id=901, path="C:\\m\\no-esta.mp3", title="x", artist="", album="", genre="", duration_ms=1, added_at="", loudness_lufs=-20.0,
             true_peak_db=-10.0, available=False)
s_flac = LoudnessDialog._state(flac, decide(-6.0, -0.1, -12.0), 0)
s_gone = LoudnessDialog._state(gone, decide(-20.0, -10.0, -12.0), 0)
check("un FLAC fuerte dice «No se puede ajustar (FLAC)» (no «No se puede bajar»)", s_flac[0].startswith("No se puede ajustar"), s_flac)
check("  un MP3 que no está en el disco dice «No disponible» (no «Casi bien»)", s_gone[0] == "No disponible", s_gone)
v1 = make_mp3(os.path.join(work, "con-id3v1.mp3"), 0.9)
with open(v1, "ab") as f:
    f.write(b"TAG" + b"Titulo".ljust(30, b"\0") + b"Artista".ljust(30, b"\0") + b"\0" * 65)  # ID3v1 de 128 bytes
v1_original = sha(v1)
w = AdjustWorker([(T(5, v1), -2)]); w.run()
tail = open(v1, "rb").read()[-128:]
check("con ID3v1, la nota se escribe antes: la ID3v1 sigue al final (la leen los autorradios)", tail.startswith(b"TAG") and b"Artista" in tail)
check("  y la nota se encuentra igual", mp3gain.read_applied_steps(v1) == -2, mp3gain.read_applied_steps(v1))
w = AdjustWorker([(T(5, v1), REVERT)]); w.run()
check("  revertir la deja idéntica", sha(v1) == v1_original)
info = mp3gain.inspect(song)
try:
    mp3gain.apply_steps(song, -info.min_gain); clamped = False
except mp3gain.Mp3GainError:
    clamped = True
check("bajar nunca deja un tramo en 0 (si no, revertir no sería exacto)", clamped and info.max_down_steps == info.min_gain - 1, (clamped, info))
got = []
w = AdjustWorker([(T(1, song), REVERT)]); w.adjusted.connect(lambda *a: got.append(a)); w.run()
check("revertir una canción sin ajuste da un aviso y no toca nada", got and got[-1][2] == -1 and sha(song) == original, got)
from mutagen.apev2 import APEv2
mg = make_mp3(os.path.join(work, "de-mp3gain.mp3"), 0.3)
tag = APEv2(); tag["MP3GAIN_UNDO"] = "-003,-003,N"; tag.save(mg)  # como lo deja el programa MP3Gain tras subir 3 pasos
check("una nota escrita por MP3Gain se entiende (subida de 3 pasos)", mp3gain.read_applied_steps(mg) == 3, mp3gain.read_applied_steps(mg))

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
