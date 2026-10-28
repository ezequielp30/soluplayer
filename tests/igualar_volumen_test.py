"""1.12.8: igualar el volumen al reproducir (lineal, por canción, sin tocar los archivos y sin pasar de
−1 dBTP al subir). Todo en carpetas temporales."""
import hashlib, math, os, struct, sys, tempfile, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_igualar_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import loudness
from app.models import Track

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))
    return path
def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()
def tr(i, path, lufs, tp): return Track(id=i, path=path, title=os.path.basename(path), artist="", album="", genre="",
                                         duration_ms=2000, added_at="", loudness_lufs=lufs, true_peak_db=tp)

print("[Cálculo de la ganancia]")
gain = getattr(loudness, "playback_gain", None)
if gain is None:
    check("existe el cálculo de la ganancia al reproducir", False)
else:
    check("una canción fuerte (−8 LUFS) con objetivo −14 baja 6 dB", gain(-8.0, -0.5, -14.0) == -6.0, gain(-8.0, -0.5, -14.0))
    check("una baja (−20 LUFS) con picos bajos (−10 dBTP) sube 6 dB", gain(-20.0, -10.0, -14.0) == 6.0, gain(-20.0, -10.0, -14.0))
    check("  si sus picos llegan a −2 dBTP solo sube 1 dB (nunca pasa de −1 dBTP)", gain(-20.0, -2.0, -14.0) == 1.0, gain(-20.0, -2.0, -14.0))
    check("  sin pico conocido no se sube", gain(-20.0, None, -14.0) == 0.0, gain(-20.0, None, -14.0))
    check("una medición no fiable o sin medir no cambia nada", gain(None, None, -14.0) == 0.0 and gain(5.0, 9.0, -14.0) == 0.0)
    check("nunca más de 12 dB hacia arriba ni de 20 hacia abajo", gain(-60.0, -50.0, -14.0) == 12.0 and gain(-0.5, -0.1, -30.0) == -20.0)

print("[Validación con medición de doble pasada (EBU R128, el mismo medidor del programa)]")
import numpy as np
from app.loudness import RATE, LoudnessMeter
def measure(stereo):
    m = LoudnessMeter(); m.add(stereo.astype(np.float32).reshape(-1)); return m.result()
rng = np.random.default_rng(7)
t = np.arange(RATE * 20) / RATE
music = (0.6 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 1760 * t)) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.25 * t))
music += 0.05 * rng.standard_normal(t.size)  # «música» con dinámica (sube y baja cada 4 s)
for name, level in (("baja", 0.15), ("fuerte", 0.9)):
    sig = np.stack([music * level, music * level * 0.9], axis=1)
    lufs1, tp1 = measure(sig)
    g = gain(lufs1, tp1, -14.0) if gain else 0.0
    lufs2, tp2 = measure(sig * 10 ** (g / 20))
    print(f"    {name}: 1.ª pasada {lufs1:.2f} LUFS / {tp1:.2f} dBTP → ganancia {g:+.1f} dB → 2.ª pasada {lufs2:.2f} LUFS / {tp2:.2f} dBTP")
    reached = abs(lufs2 - -14.0) <= 0.15 or (g > 0 and abs(tp2 - -1.0) <= 0.1)  # o lo frenó el pico (justo en −1)
    check(f"  canción {name}: llega al objetivo (o lo frena el pico) y el pico real queda ≤ −1 dBTP al subir",
          gain is not None and reached and (g <= 0 or tp2 <= -1.0 + 0.05), (lufs2, tp2))
check("  la ganancia es lineal: la dinámica (diferencia entre lo más bajo y lo más alto) no cambia",
      gain is not None and abs((measure(np.stack([music * 0.5] * 2, 1))[0] + 6.02) - measure(np.stack([music] * 2, 1))[0]) < 0.05)

print("[Al reproducir]")
from app.player import PlaybackController
music = os.path.join(work, "Musica")
loud = tr(1, tone(os.path.join(music, "fuerte.wav")), -8.0, -0.5)
quiet = tr(2, tone(os.path.join(music, "baja.wav")), -20.0, -12.0)
unknown = tr(3, tone(os.path.join(music, "sin-medir.wav")), None, None)
before = {t.path: sha(t.path) for t in (loud, quiet, unknown)}
player = PlaybackController()
player.set_volume(80)
setter = getattr(player, "set_normalization", None)
if setter is not None:
    setter(True, -14.0)
player.play_queue([loud, quiet, unknown], 0); spin(300)
vol = player._audio.volume()
check("una canción fuerte suena 6 dB más baja (el volumen elegido es 80 %)", abs(vol - 0.8 * 10 ** (-6 / 20)) < 0.01, round(vol, 3))
player.set_volume(50); spin(50)
check("  y mover la barra de volumen la sigue igualando", abs(player._audio.volume() - 0.5 * 10 ** (-6 / 20)) < 0.01, round(player._audio.volume(), 3))
player.next(); spin(300)
check("una baja sube 6 dB sobre el volumen elegido", abs(player._audio.volume() - 0.5 * 10 ** (6 / 20)) < 0.01, round(player._audio.volume(), 3))
player.set_volume(90); spin(50)
check("  sin pasar del máximo de Windows (100 %): sube hasta el tope, no más", abs(player._audio.volume() - 1.0) < 1e-6
      and player.track_gain_db == 6.0, (player._audio.volume(), player.track_gain_db))
before_reload = player._audio.volume()
player.set_normalization(True, -20.0, None, now=False)  # p. ej. termina un análisis y cambia la referencia
spin(50)
check("  si la biblioteca cambia mientras suena, el volumen no salta a mitad de canción", player._audio.volume() == before_reload)
player.next(); spin(300)
check("una canción sin analizar suena al volumen elegido", abs(player._audio.volume() - 0.9) < 0.01, player._audio.volume())
if setter is not None:
    setter(False, -14.0)
player.play_queue([loud], 0); spin(300)
check("con «Igualar volumen» apagado, todas al volumen elegido", abs(player._audio.volume() - 0.9) < 0.01, player._audio.volume())
player.release_source(); spin(100)
check("ningún archivo se modifica", all(sha(p) == h for p, h in before.items()))

print("[En la ventana]")
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw
win = mw.MainWindow(Database(database_path())); win.show(); spin(200)
actions = {a.objectName(): a for a in win.findChildren(mw.QAction)}
act = actions.get("act_normalize")
check("Reproducción → «Igualar volumen al reproducir» es una casilla, apagada de fábrica (lo principal va en los archivos)",
      act is not None and act.isCheckable() and not act.isChecked())
if act is not None:
    act.setChecked(True); spin(50)
check("  y se recuerda en Preferencias", hasattr(win.prefs, "playback_normalization") and win.prefs.playback_normalization is True)
win.close(); spin(100)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
