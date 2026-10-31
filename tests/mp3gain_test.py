"""Prueba de mp3gain sobre COPIAS de MP3 reales (los originales no se tocan)."""
import hashlib, os, shutil, sqlite3, sys, tempfile, time
sys.path.insert(0, r"D:\soluplayer")
import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
import mutagen
from app.loudness import RATE, LoudnessMeter
from app import mp3gain

app = QCoreApplication(sys.argv)
fmt = QAudioFormat(); fmt.setSampleRate(RATE); fmt.setChannelCount(2); fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)

def measure(path):
    meter, st = LoudnessMeter(), {"done": False, "err": None}
    dec = QAudioDecoder(); dec.setAudioFormat(fmt)
    dec.bufferReady.connect(lambda: meter.add(np.frombuffer(bytes(dec.read().constData()), dtype=np.float32)))
    dec.finished.connect(lambda: st.update(done=True))
    dec.error.connect(lambda e: st.update(done=True, err=dec.errorString()))
    dec.setSource(QUrl.fromLocalFile(path)); dec.start()
    deadline = time.time() + 120  # un decodificador que nunca termina no cuelga la prueba
    while not st["done"]:
        if time.time() > deadline:
            st.update(done=True, err="el decodificador no terminó en 120 s"); break
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    lufs, tp = meter.result()
    dec.stop(); dec.setSource(QUrl()); dec.deleteLater(); app.processEvents()  # suelta el archivo
    return lufs, tp, meter.frames / RATE, st["err"]

def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import audio_sintetico as sint  # audio generado, igual en cualquier PC
gen = tempfile.mkdtemp(prefix="mp_gain_gen_")
# Variedad: baja y fuerte, estéreo y mono, 128 y 320 kbps, 44,1 y 48 kHz (todas con etiquetas).
samples = [sint.mp3(os.path.join(gen, "baja.mp3"), 15, peak=0.15, seed=1),
           sint.mp3(os.path.join(gen, "media_mono.mp3"), 15, peak=0.5, seed=2, channels=1, bitrate=128),
           sint.mp3(os.path.join(gen, "fuerte_320.mp3"), 15, peak=0.6, seed=3, bitrate=320),
           sint.mp3(os.path.join(gen, "media_48k.mp3"), 15, peak=0.4, seed=4, rate=48000)]
if sint.usar_reales():  # opcional: también copias de MP3 reales de la biblioteca
    from muestra_real import mp3_existentes
    samples += mp3_existentes(3)
else:
    print("(sin archivos reales: MUSICPLAYER_PRUEBA_REAL=1 para probar también con copias de tu biblioteca)")
originals = {p: sha(p) for p in samples}  # antes de tocar nada: así se ve si algo escribió en el original
work = tempfile.mkdtemp(prefix="mp_gain_")
ok_all = True
for src in samples:
    copy = os.path.join(work, os.path.basename(src)); shutil.copy2(src, copy)
    original_hash, original_tags = sha(copy), dict(mutagen.File(copy, easy=True) or {})
    info = mp3gain.inspect(copy)
    l0, tp0, d0, e0 = measure(copy)
    steps = min(2, info.max_up_steps)  # +3 dB
    mp3gain.apply_steps(copy, steps)
    l1, tp1, d1, e1 = measure(copy)
    tags_ok = dict(mutagen.File(copy, easy=True) or {}) == original_tags
    rise = (l1 - l0) if l0 is not None and l1 is not None else None
    mp3gain.apply_steps(copy, -steps)
    back = sha(copy) == original_hash
    ok = e1 is None and rise is not None and abs(rise - steps * 1.5) < 0.15 and abs(d1 - d0) < 0.05 and tags_ok and back
    ok_all &= ok
    print(f"{'OK ' if ok else 'FALLA'} {os.path.basename(src)[:48]:48s} tramas={info.frames:5d} gain={info.min_gain}-{info.max_gain} | "
          f"{l0} → {l1} LUFS (subió {rise and round(rise,2)} dB, esperado {steps*1.5}) | pico {tp0} → {tp1} dBTP | "
          f"duración igual={abs(d1-d0)<0.05} | etiquetas intactas={tags_ok} | deshacer exacto={back}")
untouched = all(sha(p) == h for p, h in originals.items())
print("originales sin tocar:", untouched)
ok_all &= untouched
print("RESULTADO:", "OK" if ok_all else "FALLA")
sys.exit(0 if ok_all else 1)
