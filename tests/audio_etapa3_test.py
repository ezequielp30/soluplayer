"""Etapa 3 de la auditoría de sonido: graves precisos en el ecualizador sin reforzar lo inaudible, dither al
pasar a 16 bits, pico real exacto, cambio de salida con otro formato, volver del Bluetooth y aviso de doble
compresión al convertir. Señales sintéticas y salida real a volumen 0."""
import math, os, sys, tempfile, time, wave
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_etapa3_")
import numpy as np
from PySide6.QtCore import QEventLoop, QUrl
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from app.equalizer import BANDS_HZ, EqProcessor, EqSettings, PRESETS, design_fir, response_db, to_pcm16
from app.loudness import RATE as LRATE, LoudnessMeter

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

def gain_db(gains, hz, rate, preamp=0.0):
    h = design_fir(EqSettings(tuple(gains), preamp=preamp, prevent_clipping=False), rate)
    spec = np.abs(np.fft.rfft(h, n=1 << 20)); f = np.fft.rfftfreq(1 << 20, 1 / rate)
    return 20 * math.log10(spec[np.argmin(np.abs(f - hz))])

print("[Ecualizador: graves precisos]")
ALT = (12, -12, 12, -12, 12, -12, 12, -12, 12, -12)
target = response_db(EqSettings(ALT), np.array(BANDS_HZ, float))
for rate, tol in ((44100, 0.5), (48000, 0.6), (96000, 1.1)):
    b31 = gain_db((12,) + (0,) * 9, 31, rate)
    b62 = gain_db((0, 12) + (0,) * 8, 62, rate)
    err = max(abs(gain_db(ALT, b, rate) - t) for b, t in zip(BANDS_HZ, target))
    check(f"a {rate // 1000} kHz: 31 y 62 Hz a +12 dB dan lo pedido, y la curva más exigente queda dentro de ±{tol} dB",
          abs(b31 - 12) <= tol and abs(b62 - 12) <= tol and err <= tol,
          f"31 Hz {b31:+.2f} · 62 Hz {b62:+.2f} · error {err:.2f} dB (antes 1,97/2,14/4,29)")
sub = gain_db((12,) + (0,) * 9, 10, 44100)
check("subir 31 Hz ya no refuerza lo inaudible: 10 Hz casi sin cambio (antes +12 dB)", sub <= 1.0, f"{sub:+.1f} dB")
cut = gain_db((-12,) + (0,) * 9, 12, 44100)
check("  bajar los graves sí sigue bajando por debajo de 20 Hz", cut <= -10, f"{cut:+.1f} dB")
for rate in (44100, 48000, 96000):
    eq = EqProcessor(rate, 2, EqSettings(PRESETS["Rock"]))
    x = (np.random.default_rng(0).standard_normal((rate * 4, 2)) * 0.1).astype(np.float32)
    t0 = time.perf_counter(); eq.process(x); cost = (time.perf_counter() - t0) / 4
    check(f"a {rate // 1000} kHz responde en ≤ 0,2 s y usa poco (≤ 25 % de un núcleo)",
          eq.block / rate <= 0.2 and cost <= 0.25, f"bloque {eq.block / rate * 1000:.0f} ms · {cost * 100:.1f} %")

print("[Pasar a 16 bits con dither]")
t = np.arange(44100) / 44100
quiet = 10 ** (-90 / 20) * np.sin(2 * np.pi * 1000 * t)
def harmonics(pcm):
    spec = np.abs(np.fft.rfft(np.frombuffer(pcm, "<i2").astype(float))) ** 2
    return max(10 * math.log10(spec[1000 * k] / spec[1000]) for k in (3, 5, 7))
truncated = (np.clip(quiet, -1, 1) * 32767).astype("<i2").tobytes()
dithered = to_pcm16(quiet, np.random.default_rng(1))
check("un sonido muy suave (−90 dBFS) ya no sale distorsionado al pasar a 16 bits",
      harmonics(dithered) < -30 < harmonics(truncated), f"armónicos {harmonics(truncated):.1f} → {harmonics(dithered):.1f} dBc")
check("  y el redondeo no corre el nivel (sin componente continua)",
      abs(np.frombuffer(to_pcm16(np.zeros(100000), np.random.default_rng(2)), "<i2").mean()) < 0.02)
check("  igual semilla, igual resultado (la conversión a MP3 da siempre el mismo archivo)",
      to_pcm16(quiet, np.random.default_rng(0)) == to_pcm16(quiet, np.random.default_rng(0)))

print("[Pico real]")
def true_peak(freq, fade):
    x = np.sin(2 * np.pi * freq * np.arange(LRATE * 3) / LRATE + 0.3)
    if fade:
        n = int(LRATE * 0.05); r = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n)); x[:n] *= r; x[-n:] *= r[::-1]
    m = LoudnessMeter(); m.add(np.repeat(x.astype(np.float32), 2)); return m.result()[1]
smooth = [true_peak(f, True) for f in (1000, 11000, 15000, 19000)]
check("seno a 0 dBFS con entrada suave: 0,0 dBTP en todas las frecuencias (±0,05)",
      all(abs(v) <= 0.05 for v in smooth), [f"{v:+.2f}" for v in smooth])
abrupt = true_peak(19000, False)
check("  un agudo que empieza de golpe sí tiene un sobrepico real (el conversor también lo produce)", abrupt > 0.3, f"{abrupt:+.2f} dBTP")

print("[Cambiar de salida con otro formato]")
from app import eq_player as eqp
audio = QAudioOutput(QMediaDevices.defaultAudioOutput()); audio.setVolume(0)
p = eqp.EqPlayer(audio)
rate0 = p._rate
path = os.path.join(work, "tono.wav")
tt = np.arange(rate0 * 6) / rate0
with wave.open(path, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate0)
    w.writeframes(np.repeat((0.3 * np.sin(2 * np.pi * 440 * tt) * 32767).astype("<i2"), 2).tobytes())
p.setSource(QUrl.fromLocalFile(path)); wait(lambda: p._decode_done, 5000)
p.play(); spin(1200)
before = p.position()
other = 48000 if rate0 != 48000 else 44100
fmt = QAudioFormat(); fmt.setSampleRate(other); fmt.setChannelCount(2); fmt.setSampleFormat(p._format.sampleFormat())
real_choose = p._choose_format
p._choose_format = lambda: fmt
p._device_changed()
spin(800)
check("una salida que prefiere otra frecuencia: se decodifica de nuevo a esa frecuencia",
      p._rate == other and p._eq.rate == other and p._format.sampleRate() == other, (rate0, p._rate))
check("  y sigue sonando desde el mismo punto", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState
      and abs(p.position() - before - 800) < 500, (before, p.position()))
p._choose_format = real_choose

print("[Volver del Bluetooth]")
p.pause(); spin(100)
p.paused_by_device = True  # como si la salida se hubiera caído sola
p.resume_after_device(); spin(400)
check("si la pausa la causó la salida que se cayó, al volver sigue sola", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
p.pause(); spin(100)
p.resume_after_device(); spin(300)
check("  si la pausó el usuario, no", p.playbackState() == QMediaPlayer.PlaybackState.PausedState and not p.paused_by_device)
p.stop(); p.setSource(QUrl())

print("[Convertir algo ya comprimido]")
from app.ui.convert_dialog import _DETAILS, is_lossy
check("WMA, AAC y OGG cuentan como ya comprimidos; FLAC y WAV no",
      all(is_lossy(f"x{e}") for e in (".wma", ".aac", ".ogg", ".opus")) and not any(is_lossy(f"x{e}") for e in (".flac", ".wav", ".aiff")))
check("la ventana ya no promete «sin pérdida audible» para todo: explica la segunda compresión",
      "SEGUNDA compresión" in _DETAILS and "no añadir pérdida audible" not in _DETAILS)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
