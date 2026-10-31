"""Etapa 2 de la auditoría de sonido: volumen en decibeles, igualar volumen que también sube, más margen
contra cortes y pasar a la siguiente canción sin silencio. Señales sintéticas y salida real a volumen 0."""
import math, os, sys, tempfile, time, wave
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_etapa2_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
import numpy as np
from PySide6.QtCore import QEventLoop, QSettings, QUrl
from PySide6.QtMultimedia import QAudioFormat, QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import eq_player as eqp
from app import player as pl
from app.models import Track

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
def db(x): return 20 * math.log10(x)

print("[Volumen en decibeles]")
steps = [db(pl.volume_gain(p + 1)) - db(pl.volume_gain(p)) for p in range(1, 100)]
check("cada paso del deslizador cambia lo mismo (0,5 dB), también a volumen bajo (antes del 1 % al 2 %: 6 dB)",
      max(steps) < 0.51 and min(steps) > 0.49, f"{min(steps):.2f}–{max(steps):.2f} dB")
check("0 = silencio y 100 = sin atenuar", pl.volume_gain(0) == 0.0 and pl.volume_gain(100) == 1.0)
same = [abs(db(pl.volume_gain(pl.percent_from_linear(old))) - db(old / 100)) for old in range(10, 101)]
check("el volumen guardado antes se convierte y suena igual (±0,25 dB)", max(same) <= 0.26, f"máx {max(same):.2f} dB")

s = QSettings("ReproductorMusicaTest", "ReproductorMusica")
s.setValue("player/volume", 30)  # como lo dejó una versión anterior (escala lineal)
s.sync()
from app.config import database_path
from app.database import Database
os.makedirs(os.path.dirname(database_path()), exist_ok=True)
db_ = Database(database_path())
from app.ui import main_window as mw
win = mw.MainWindow(db_); spin(200)
check("al actualizar, el 30 % de antes pasa a 79 % (mismo volumen)", win.player_bar.volume.value() == 79, win.player_bar.volume.value())
check("  y se convierte una sola vez", s.value("player/volume_scale") == "db")
win.close(); spin(100)
db_ = Database(database_path())  # cerrar la ventana cierra la base
win = mw.MainWindow(db_); spin(200)
check("  al volver a abrir no se convierte de nuevo", win.player_bar.volume.value() == 79, win.player_bar.volume.value())
win.close(); spin(100)

print("[Más margen contra cortes]")
check("la salida tiene 750 ms por delante (antes 250)", eqp._BUFFER_MS == 750)

print("[Igualar volumen que también sube]")
audio = QAudioOutput(QMediaDevices.defaultAudioOutput())
probe = eqp.EqPlayer(audio)
RATE = probe._rate
probe.deleteLater()

def sine_wav(path, secs, freq, amp=0.3):
    t = np.arange(int(RATE * secs)) / RATE
    x = (amp * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(np.repeat(x, 2).tobytes())
    return path

a = sine_wav(os.path.join(work, "a.wav"), 1.2, 440)
b = sine_wav(os.path.join(work, "b.wav"), 1.2, 660)
c = sine_wav(os.path.join(work, "c.wav"), 1.0, 550)
def track(i, path, lufs=None, peak=None):
    return Track(i, path, f"t{i}", "a", "b", "g", 1200, "", loudness_lufs=lufs, true_peak_db=peak)

ctl = pl.PlaybackController()
ctl.set_volume(100)
quiet = track(1, a, lufs=-26.0, peak=-12.0)
ctl.set_normalization(True, -16.0, {1: quiet})
ctl.play_queue([quiet], 0); spin(300)
check("igualar volumen usa el motor propio (puede subir por encima del 100 %)", ctl._player is ctl._eq_player)
gain = ctl.track_gain_db
check("  una canción a −26 LUFS sube hacia −16", gain > 5.0, f"{gain:+.1f} dB")
check("  la salida de Windows queda al 100 % y el resto lo pone el motor",
      abs(ctl._audio.volume() - 1.0) < 1e-6 and abs(db(ctl._eq_player._boost) - gain) < 0.05,
      f"salida {ctl._audio.volume():.2f} · motor {db(ctl._eq_player._boost):+.1f} dB")
ctl.set_volume(50)
check("  con el volumen al 50 % no hace falta ganancia extra", ctl._eq_player._boost == 1.0 or db(ctl._eq_player._boost) < 0.01)
ctl.stop() if hasattr(ctl, "stop") else ctl._player.stop()
ctl.set_normalization(False, -16.0)
ctl.set_volume(0)

print("[Sin silencio entre canciones: motor]")
p = eqp.EqPlayer(QAudioOutput(QMediaDevices.defaultAudioOutput()))
p.setSource(QUrl.fromLocalFile(a))
wait(lambda: p._decode_done, 5000)
p.preload(QUrl.fromLocalFile(b))
wait(lambda: p._next is not None and p._next.done, 5000)
check("prepara la siguiente mientras suena la actual", p._next is not None and p._next.done and p._next.store.frames > 0)
bpf = p._format.bytesPerFrame()
chunks = []
for _ in range(2000):
    raw = p._produce(4096 * bpf)
    if not raw:
        break
    chunks.append(raw)
dtype = "<i2" if p._format.sampleFormat() == QAudioFormat.SampleFormat.Int16 else "<f4"
out = np.frombuffer(b"".join(chunks), dtype).astype(np.float32).reshape(-1, 2)[:, 0]
if dtype == "<i2":
    out = out / 32767
expected = int(RATE * 1.2) * 2
silent = np.abs(out) < 1e-4
longest, run = 0, 0
for v in silent[int(RATE * 0.1): -int(RATE * 0.1)]:
    run = run + 1 if v else 0
    longest = max(longest, run)
check("las dos canciones salen de corrido, sin silencio en el medio", abs(len(out) - expected) <= RATE // 100 and longest < RATE // 1000 * 2,
      f"{len(out)} frames (esperados {expected}) · silencio más largo {longest / RATE * 1000:.1f} ms")
check("  y al final, como siempre, termina", p._flushed and p._source == QUrl.fromLocalFile(b))
p.setSource(QUrl())

print("[Sin silencio entre canciones: reproductor]")
events = []
ctl = pl.PlaybackController()
ctl.set_volume(0)
ctl.current_track_changed.connect(lambda t: events.append(("track", t.path if t else None)))
ctl.track_started.connect(lambda t: events.append(("started", t.path)))
ta, tb, tc = track(10, a), track(11, b), track(12, c)
ctl.play_queue([ta, tb, tc], 0)
check("sin ecualizador ni igualar volumen, también usa el motor propio", wait(lambda: ctl._player is ctl._eq_player, 2000))
loads = []
orig = ctl._eq_player.setSource
ctl._eq_player.setSource = lambda url: (loads.append(url.toLocalFile()), orig(url))[1]
states = []
ctl._eq_player.playbackStateChanged.connect(lambda st: states.append(st))
reached = wait(lambda: ctl.current_track is not None and ctl.current_track.path == c, 8000)
check("pasa por las tres canciones sola", reached, [os.path.basename(e[1] or "") for e in events if e[0] == "track"])
check("  sin volver a cargar ni detener la salida entre una y otra",
      not loads and QMediaPlayer.PlaybackState.StoppedState not in states, (loads, states))
check("  cada una cuenta como reproducida al empezar a sonar", [e[1] for e in events if e[0] == "started"] == [a, b, c],
      [os.path.basename(e[1]) for e in events if e[0] == "started"])
ctl._eq_player.setSource = orig
ctl._player.stop()

print("[Si el motor propio no puede con un archivo]")
ctl.play_queue([ta, tb], 0); spin(300)
ctl._on_error(QMediaPlayer.Error.FormatError, "prueba")
spin(300)
check("ese archivo pasa a sonar con el motor de Qt", ctl._player is ctl._qt_player and a in ctl._qt_only)
ctl._player.stop()
ctl.set_gapless(False)
ctl.play_queue([tb], 0); spin(300)
check("con «sin silencios» apagado (y sin ecualizador) suena con Qt, como antes", ctl._player is ctl._qt_player)
ctl._player.stop()

from app.preferences import Preferences
from app.ui.dialogs import PreferencesDialog
prefs = Preferences(QSettings("ReproductorMusicaTest", "ReproductorMusica"))
d = PreferencesDialog(prefs)
check("Preferencias → Reproducción tiene «sin silencio entre canciones», encendido de fábrica",
      any(d.nav.item(i).text() == "Reproducción" for i in range(d.nav.count())) and d.gapless.isChecked())
d.gapless.setChecked(False); d._save()
check("  y se guarda", prefs.gapless is False)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
