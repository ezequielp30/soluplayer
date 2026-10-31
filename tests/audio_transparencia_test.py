"""Etapa 1 de la auditoría de sonido: el ecualizador y su motor no alteran lo que no deben. Con señales
sintéticas y la salida de audio real a volumen 0 (no suena nada). No usa la música del usuario."""
import math, os, struct, sys, tempfile, time
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # también fuera de correr-todas.ps1 (consola cp1252)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_transparencia_")
import numpy as np
from PySide6.QtCore import QEventLoop, QUrl
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from app import eq_player as eqp
from app.equalizer import BLOCK, LATENCY_FRAMES, EqProcessor, EqSettings, soft_limit

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5); time.sleep(0.002)
def wait(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end and not cond(): app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5); time.sleep(0.002)
    return cond()

RATE = 44100
def sine(amp, secs=1.5, freq=1000.0):
    t = np.arange(int(RATE * secs)) / RATE
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([x, x], axis=1)

def run(settings, x):
    """La señal por el ecualizador, alineada con la entrada (sin el retardo fijo del filtro)."""
    eq = EqProcessor(RATE, 2, settings)
    y = np.concatenate([eq.process(x), eq.flush()])
    return y[LATENCY_FRAMES:LATENCY_FRAMES + len(x)]

def thd_db(y, freq=1000.0):
    """Distorsión + ruido (dB) de un seno: todo lo que no es la fundamental, con ventana."""
    s = y[RATE // 4: RATE // 4 + RATE, 0].astype(np.float64)  # 1 s exacto: ciclos enteros, sin ventana ni fugas
    spec = np.abs(np.fft.rfft(s)) ** 2
    k = int(round(freq * len(s) / RATE))
    fund = spec[k]
    rest = spec.sum() - fund - spec[0]
    return 10 * math.log10(max(rest, 1e-30) / fund)

print("[Transparencia del ecualizador]")
flat = EqSettings()
x = sine(0.99)
y = run(flat, x)
check("curva plana con un seno a 0,99 (−0,09 dBFS): la salida es igual a la entrada",
      np.max(np.abs(y - x)) < 1e-6, f"error máx {np.max(np.abs(y - x)):.2e}")
x = sine(1.0)
check("  y a 0 dBFS también (antes el limitador lo redondeaba: THD −48 dB)", thd_db(run(flat, x)) < -90, f"{thd_db(run(flat, x)):.1f} dB")
check("el limitador no toca lo que no pasaría de 1.0", np.array_equal(soft_limit(x), x))
over = np.array([[1.3, -1.6], [0.5, 0.2]], dtype=np.float32)
limited = soft_limit(over)
check("  y lo que pasaría de 1.0 queda por debajo, sin recorte duro", np.max(np.abs(limited)) <= 1.0 and limited[1, 0] == 0.5)

print("[Evitar saturación con nivel general positivo]")
s = EqSettings(preamp=6.0, prevent_clipping=True)
check("nivel general +6 dB con «evitar saturación»: no sube por encima de 0 dB", s.total_preamp_db == 0.0, s.total_preamp_db)
y = run(s, sine(0.7))
check("  un seno a 0,7 sale sin distorsión (antes THD −17,7 dB)", thd_db(y) < -90, f"{thd_db(y):.1f} dB")
s = EqSettings(gains=(6, 0, 0, 0, 0, 0, 0, 0, 0, 0), preamp=-3.0, prevent_clipping=True)
check("bandas +6 y nivel general −3: se baja solo lo que falta (−6 dB en total, antes −9)", s.total_preamp_db == -6.0, s.total_preamp_db)
y = run(EqSettings(gains=(12,) * 10, prevent_clipping=False), sine(0.9))
check("sin «evitar saturación» el limitador igual evita pasar de 1.0", np.max(np.abs(y)) <= 1.0, f"pico {np.max(np.abs(y)):.3f}")

print("[Cambiar el ecualizador mientras suena]")
x = sine(0.5, secs=2.0)
natural = np.max(np.abs(np.diff(x[:, 0])))
eq = EqProcessor(RATE, 2, flat)
first = eq.process(x[:BLOCK * 3])
eq.set_settings(EqSettings(preamp=-12.0))
rest = eq.process(x[BLOCK * 3:])
y = np.concatenate([first, rest])[:, 0]
jump = np.max(np.abs(np.diff(y)))
check("bajar el nivel general de 0 a −12 dB en vivo no salta (fundido cruzado; antes 5,4 veces el máximo)",
      jump <= natural * 1.05, f"salto máx {jump:.4f} · natural {natural:.4f}")
tail = y[-BLOCK:]
check("  y después queda en −12 dB", abs(20 * math.log10(np.max(np.abs(tail)) / 0.5) + 12) < 0.1,
      f"{20 * math.log10(np.max(np.abs(tail)) / 0.5):.2f} dB")

print("[Decodificar sin perder resolución]")
raw = np.array([0.5, -0.25, 1.5, -1.5], dtype="<f4").tobytes()
check("float del decodificador: tal cual, también picos > 0 dBFS",
      np.allclose(eqp._as_float(raw, QAudioFormat.SampleFormat.Float), [0.5, -0.25, 1.5, -1.5]))
check("si llegara en 16 bits, se convierte bien",
      np.allclose(eqp._as_float(np.array([16384, -32768], "<i2").tobytes(), QAudioFormat.SampleFormat.Int16), [0.5, -1.0]))
store = eqp._PcmStore(RATE, 2)
store.append(np.array([[1e-5, 1.5]], dtype=np.float32))
check("el audio guardado conserva valores pequeños (24 bits) y picos > 1.0", np.allclose(store.read(0, 1), [[1e-5, 1.5]]))
store.close()

def float_wav(path, data):
    """WAV en float de 32 bits (formato 3), que puede guardar picos por encima de 0 dBFS."""
    frames = data.astype("<f4").tobytes()
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(frames), b"WAVE", b"fmt ", 16, 3, 2, RATE,
                         RATE * 8, 8, 32, b"data", len(frames))
    with open(path, "wb") as f:
        f.write(header + frames)

hot = os.path.join(work, "picos.wav")
float_wav(hot, sine(1.5, secs=2.0))
audio = QAudioOutput(QMediaDevices.defaultAudioOutput())
audio.setVolume(0.0)
p = eqp.EqPlayer(audio, EqSettings())
p.setSource(QUrl.fromLocalFile(hot))
done = wait(lambda: p._decode_done or p._store.frames >= RATE, 5000)
stored = p._store.read(0, p._store.frames)
peak = float(np.max(np.abs(stored))) if len(stored) else 0.0
same_rate = p._rate == RATE
check("un WAV con picos a 1,5 llega al ecualizador sin recortar (antes: 54 % de muestras clavadas en 1.0)",
      done and (peak > 1.2 or not same_rate), f"pico guardado {peak:.3f} · salida a {p._rate} Hz")

print("[Fundidos]")
p.setPosition(500)
want = p._fade_frames() * 3
chunk = b""
for _ in range(50):
    chunk += p._produce(want * p._format.bytesPerFrame())
    if len(chunk) >= want * p._format.bytesPerFrame():
        break
if p._format.sampleFormat() == QAudioFormat.SampleFormat.Int16:
    out = np.frombuffer(chunk, "<i2").astype(np.float32).reshape(-1, 2) / 32767
else:
    out = np.frombuffer(chunk, "<f4").reshape(-1, 2)
n = p._fade_frames()
first_peak = float(np.max(np.abs(out[: max(1, n // 8)]))) if len(out) else 1.0
later_peak = float(np.max(np.abs(out[n: n * 2]))) if len(out) >= n * 2 else 0.0
check("al saltar, el sonido entra con un fundido (no a mitad de onda)", first_peak < 0.25 * max(later_peak, 1e-9),
      f"comienzo {first_peak:.3f} · después {later_peak:.3f}")

p.play(); spin(300)
sink = p._sink
check("reproduce", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState and sink is not None)
p.pause()
check("pausa: el estado cambia en el acto", p.playbackState() == QMediaPlayer.PlaybackState.PausedState)
fades = wait(lambda: sink.state().name == "SuspendedState", 1000)  # enum de QtAudio en Qt 6.12
check("  y la salida se suspende después de bajar el volumen (fundido)", fades and p._gain == 0.0, (sink.state(), p._gain))
p.play(); spin(200)
check("reanudar sube el volumen de nuevo", p._gain == 1.0 and p.playbackState() == QMediaPlayer.PlaybackState.PlayingState, p._gain)
p.stop()
check("detener es inmediato (suelta el archivo en el acto)", p._sink is None and p._gain == 1.0)
p.setSource(QUrl())

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
