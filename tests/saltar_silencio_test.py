"""Saltar el silencio grabado al principio y al final de cada canción (muchos archivos traen segundos de
silencio y entre una canción y otra se oían 4–9 s sin música). Señales sintéticas; no toca archivos."""
import os, sys, tempfile, time, wave
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_silencio_")
import numpy as np
from PySide6.QtCore import QEventLoop, QSettings, QUrl
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QMediaDevices
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import eq_player as eqp

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def wait(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end and not cond(): app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5); time.sleep(0.002)
    return cond()

audio = QAudioOutput(QMediaDevices.defaultAudioOutput()); audio.setVolume(0)
probe = eqp.EqPlayer(audio); RATE = probe._rate; probe.deleteLater()

def song(name, parts):
    """parts: [(segundos, frecuencia o None = silencio)]"""
    pieces = []
    for secs, freq in parts:
        t = np.arange(int(RATE * secs)) / RATE
        pieces.append(np.zeros_like(t) if freq is None else 0.3 * np.sin(2 * np.pi * freq * t))
    x = (np.concatenate(pieces) * 32767).astype("<i2")
    path = os.path.join(work, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(np.repeat(x, 2).tobytes())
    return path

def play_all(first, second=None, skip=True, pos_ms=None):
    """Toda la salida del motor (una canción, o dos seguidas sin silencio entre archivos)."""
    p = eqp.EqPlayer(QAudioOutput(QMediaDevices.defaultAudioOutput()))
    p.set_skip_silence(skip)
    p.setSource(QUrl.fromLocalFile(first)); wait(lambda: p._decode_done, 5000)
    if second:
        p.preload(QUrl.fromLocalFile(second)); wait(lambda: p._next is not None and p._next.done, 5000)
    if pos_ms is not None:
        p.setPosition(pos_ms)
    p._ready_to_start()  # lo que hace «Reproducir» antes de abrir la salida
    bpf = p._format.bytesPerFrame(); raw = []
    for _ in range(5000):
        b = p._produce(4096 * bpf)
        if not b:
            break
        raw.append(b)
    dtype = "<i2" if p._format.sampleFormat() == QAudioFormat.SampleFormat.Int16 else "<f4"
    out = np.frombuffer(b"".join(raw), dtype).astype(np.float32).reshape(-1, 2)[:, 0]
    p.setSource(QUrl()); p.deleteLater()
    return out / 32767 if dtype == "<i2" else out

def silences(x, min_ms=50):
    """[(inicio s, duración s)] de los tramos de silencio de más de min_ms."""
    quiet = np.abs(x) < 10 ** (-50 / 20)
    runs, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start > RATE * min_ms / 1000:
                runs.append((round(start / RATE, 2), round((i - start) / RATE, 2)))
            start = None
    return runs

a = song("a.wav", [(0.5, None), (1.0, 440), (3.0, None)])     # como tus archivos: 0,5 s antes, 3 s después
b = song("b.wav", [(0.7, None), (1.0, 660), (2.0, None)])

print("[Entre dos canciones]")
before = play_all(a, b, skip=False)
gaps_before = [d for s, d in silences(before) if 0.5 < s < 3.5]
after = play_all(a, b, skip=True)
gaps_after = silences(after)
middle = [d for s, d in gaps_after if 0.5 < s < len(after) / RATE - 0.5]
check("sin saltar: entre una y otra se oyen ~3,7 s de silencio (lo que traen los archivos)",
      gaps_before and gaps_before[0] > 3.5, gaps_before)
check("saltando el silencio grabado: entre una y otra quedan menos de 0,3 s", not middle or max(middle) < 0.3, middle)
check("  y la primera empieza enseguida (sin los 0,5 s del principio)",
      not gaps_after or gaps_after[0][0] > 0.05 or gaps_after[0][1] < 0.06, gaps_after[:1])
check("  la música de las dos sigue entera (1 s cada una)", abs(len(after) / RATE - 2.0) < 0.4, f"{len(after) / RATE:.2f} s en total")

print("[Silencio a mitad de canción]")
hidden = song("oculta.wav", [(1.0, 440), (3.0, None), (0.5, 550), (2.0, None)])  # pista «oculta» al final
out = play_all(hidden)
inner = [d for s, d in silences(out) if 0.5 < s < 2.0]
check("un silencio a mitad de canción (o antes de una pista oculta) se respeta", inner and inner[0] > 2.8, silences(out))
check("  y solo se quita el del final", abs(len(out) / RATE - 4.65) < 0.2, f"{len(out) / RATE:.2f} s (archivo 6,5 s)")

print("[Saltos]")
from_start = play_all(a, pos_ms=0)
check("«desde el principio» también salta el silencio inicial", silences(from_start, 30)[:1] == [] or silences(from_start, 30)[0][0] > 0.05)
mid = play_all(a, pos_ms=200)
check("si el usuario salta a un punto, empieza ahí (aunque sea silencio)", silences(mid, 100)[:1] and silences(mid, 100)[0][0] == 0.0,
      silences(mid, 100)[:1])

print("[Preferencias]")
from app.preferences import Preferences
from app.ui.dialogs import PreferencesDialog
prefs = Preferences(QSettings("ReproductorMusicaTest", "ReproductorMusica"))
d = PreferencesDialog(prefs)
check("Preferencias → Reproducción: «Saltar el silencio grabado…», encendido de fábrica", d.skip_silence.isChecked())
d.skip_silence.setChecked(False); d._save()
check("  y se guarda", prefs.skip_silence is False)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
