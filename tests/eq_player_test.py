"""Prueba del motor con ecualizador sobre la salida de audio real (con volumen 0: no suena nada)."""
import math, os, struct, sys, tempfile, time, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_eqp_")
from PySide6.QtCore import QEventLoop, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from app.eq_player import EqPlayer
from app.equalizer import PRESETS, EqSettings

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def wait(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end and not cond(): app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
    return cond()

path = os.path.join(work, "tono.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
    w.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(8000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100 * 3))))

audio = QAudioOutput(QMediaDevices.defaultAudioOutput())
audio.setVolume(0.0)
p = EqPlayer(audio, EqSettings(PRESETS["Rock"]))
states, statuses, errors, positions = [], [], [], []
p.playbackStateChanged.connect(lambda s: states.append(s))
p.mediaStatusChanged.connect(lambda s: statuses.append(s))
p.errorOccurred.connect(lambda e, t: errors.append((e, t)))
p.positionChanged.connect(lambda ms: positions.append(ms))

p.setSource(QUrl.fromLocalFile(path))
check("carga el archivo", wait(lambda: p.mediaStatus() == QMediaPlayer.MediaStatus.BufferedMedia, 3000), statuses[-1:])
wait(lambda: p.duration() > 0, 3000)
check("duración ≈ 3 s", abs(p.duration() - 3000) < 100, p.duration())
p.play()
check("reproduce", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
spin(1000)
pos = p.position()
check("la posición avanza al ritmo real (≈ 1 s)", 700 < pos < 1300, pos)
try:
    os.rename(path, path + ".x"); os.rename(path + ".x", path); free = True
except OSError:
    free = False
check("el archivo queda libre mientras suena (se puede mover)", free)
p.pause(); spin(400); a = p.position(); spin(400); b = p.position()
check("pausa: la posición no avanza", abs(b - a) < 30 and p.playbackState() == QMediaPlayer.PlaybackState.PausedState, (a, b))
p.setPosition(2500); p.play(); spin(150)
check("saltar a 2,5 s", 2400 <= p.position() <= 2800, p.position())
p.set_settings(EqSettings(PRESETS["Vocal"]))
check("cambiar el ecualizador en vivo no corta", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
check("termina: «fin del archivo»", wait(lambda: QMediaPlayer.MediaStatus.EndOfMedia in statuses, 3000), statuses[-3:])
check("  y se detiene", p.playbackState() == QMediaPlayer.PlaybackState.StoppedState)
p.play(); spin(300)
check("volver a reproducir empieza de nuevo", p.playbackState() == QMediaPlayer.PlaybackState.PlayingState and p.position() < 800, p.position())
p.stop()
check("detener vuelve a 0", p.position() == 0)
bad = os.path.join(work, "roto.mp3"); open(bad, "wb").write(b"no es audio" * 100)
p.setSource(QUrl.fromLocalFile(bad))
check("archivo dañado: error comprensible, sin colgarse", wait(lambda: bool(errors), 5000), errors[:1])
p.setSource(QUrl())
check("sin archivo: estado vacío", p.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
