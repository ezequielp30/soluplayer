"""Compatibilidad de códecs: genera archivos reales en cada formato codificable, los importa y los reproduce
(en silencio) con los DOS motores del programa (el propio, que es el de siempre desde 1.17.0, y el de Qt);
prueba variantes (24 bits, 96 kHz, mono, 5.1, MP3 mono/48 kHz/320 kbps) y archivos dañados. Con
MUSICPLAYER_PRUEBA_REAL=1 prueba además muestras de la biblioteca del usuario (solo lectura)."""
import math, os, sqlite3, struct, sys, tempfile, time
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_codecs_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QByteArray, QEventLoop, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import (QAudioBuffer, QAudioBufferInput, QAudioFormat, QAudioOutput, QMediaCaptureSession,
                                  QMediaFormat, QMediaPlayer, QMediaRecorder)
app = QApplication(sys.argv)
from app.config import SUPPORTED_EXTENSIONS
from app.importer import scan_file

def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
        if until and until(): return True
    return bool(until and until())

FF, AC = QMediaFormat.FileFormat, QMediaFormat.AudioCodec
targets = [  # (nombre, contenedor, códec, extensión)
    ("MP3", FF.MP3, AC.MP3, ".mp3"),
    ("AAC (ADTS)", FF.AAC, AC.AAC, ".aac"),
    ("M4A con AAC", FF.Mpeg4Audio, AC.AAC, ".m4a"),
    ("M4A con ALAC (Apple Lossless)", FF.Mpeg4Audio, AC.ALAC, ".m4a"),
    ("FLAC", FF.FLAC, AC.FLAC, ".flac"),
    ("Ogg FLAC", FF.Ogg, AC.FLAC, ".oga"),
    ("WAV", FF.Wave, AC.Wave, ".wav"),
    ("MKA con FLAC", FF.Matroska, AC.FLAC, ".mka"),
    ("MKA con AC3", FF.Matroska, AC.AC3, ".mka"),
    ("MKA con E-AC3", FF.Matroska, AC.EAC3, ".mka"),
]

def encode(name, ff, codec, ext, secs=3):
    path = os.path.join(work, name.replace(" ", "_").replace("(", "").replace(")", "") + ext)
    fmt = QAudioFormat(); fmt.setSampleRate(44100); fmt.setChannelCount(2); fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    session = QMediaCaptureSession(); inp = QAudioBufferInput(fmt); session.setAudioBufferInput(inp)
    rec = QMediaRecorder(); session.setRecorder(rec)
    mf = QMediaFormat(ff); mf.setAudioCodec(codec); rec.setMediaFormat(mf)
    rec.setOutputLocation(QUrl.fromLocalFile(path))
    rec.setAudioSampleRate(44100); rec.setAudioChannelCount(2)
    errors = []; rec.errorOccurred.connect(lambda e, s: errors.append(s))
    total = 44100 * secs; chunk = 4410; sent = {"n": 0}
    def feed():
        while sent["n"] < total:
            frames = bytearray()
            for i in range(sent["n"], min(total, sent["n"] + chunk)):
                v = int(6000 * math.sin(2 * math.pi * 440 * i / 44100)); frames += struct.pack("<hh", v, v)
            buf = QAudioBuffer(QByteArray(bytes(frames)), fmt, int(sent["n"] / 44.1 * 1000))
            if not inp.sendAudioBuffer(buf): return
            sent["n"] += chunk
        rec.stop()
    inp.readyToSendAudioBuffer.connect(feed)
    rec.record(); spin(200); feed()
    spin(15000, lambda: rec.recorderState() == QMediaRecorder.RecorderState.StoppedState and sent["n"] >= total)
    spin(500)
    real = rec.actualLocation().toLocalFile() or path
    return real if os.path.exists(real) and os.path.getsize(real) > 0 else None, errors

def play_eq(path, secs=1.8):
    """Con el motor propio (el que usa el programa para reproducir, con o sin ecualizador)."""
    from app.eq_player import EqPlayer
    out = QAudioOutput(); out.setVolume(0.0)
    p = EqPlayer(out); errs = []
    p.errorOccurred.connect(lambda e, s: errs.append(s))
    p.setSource(QUrl.fromLocalFile(path)); p.play(); spin(secs * 1000)
    result = (p.playbackState().name, p.position(), p.duration(), errs, p.mediaStatus().name)
    p.stop(); p.setSource(QUrl()); p.deleteLater(); spin(100)
    return result

def eq_ok(path, secs=1.8):
    state, pos, dur, errs, status = play_eq(path, secs)
    to_end = status == "EndOfMedia" or (state == "StoppedState" and dur > 0 and pos >= dur - 150)
    return (state == "PlayingState" and pos > 600 or to_end) and not errs, f"propio: {state} pos={pos}ms {errs or ''}"

def play(path, secs=1.8):
    out = QAudioOutput(); out.setVolume(0.0)  # en silencio
    p = QMediaPlayer(); p.setAudioOutput(out); errs = []
    p.errorOccurred.connect(lambda e, s: errs.append(s))
    p.setSource(QUrl.fromLocalFile(path)); p.play(); spin(secs * 1000)
    result = (p.playbackState().name, p.position(), p.duration(), errs, p.hasAudio())
    p.stop(); p.setSource(QUrl()); spin(100)
    return result

results = []
print("\n=== Formatos generados aquí (codificar → importar → reproducir) ===")
for name, ff, codec, ext in targets:
    path, enc_err = encode(name, ff, codec, ext)
    if not path:
        print(f"  ··  {name:32s} no se pudo generar ({enc_err})"); continue
    scanned, failure = scan_file(path)
    state, pos, dur, errs, has_audio = play(path)
    played_to_end = state == "StoppedState" and dur > 0 and pos >= dur - 150  # archivo corto: sonó entero
    own, own_detail = eq_ok(path)
    ok = scanned is not None and (state == "PlayingState" and pos > 800 or played_to_end) and not errs and has_audio and own
    results.append(ok)
    print(f"  {'OK' if ok else 'FALLA':5s} {name:32s} {os.path.splitext(path)[1]:6s} importa={'sí' if scanned else 'NO: ' + failure.reason} "
          f"duración={(scanned.metadata.duration_ms if scanned else 0)/1000:.1f}s  Qt: {state} pos={pos}ms  {errs or ''}  {own_detail}")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import audio_sintetico as sint
import wave
import numpy as np

print("\n=== Variantes (generadas): profundidad, frecuencia, canales, MP3 ===")
def wav_variant(name, rate, channels, width, secs=3):
    path = os.path.join(work, name + ".wav")
    x = sint.music(secs, 0.5, seed=channels * 7 + rate % 97, rate=rate, channels=min(channels, 2))
    if channels > 2:  # 5.1: los canales extra con la misma música, más baja
        x = np.concatenate([x] + [x[:, :1] * 0.5] * (channels - 2), axis=1)
    scale = {2: 32767, 3: 8388607}[width]
    ints = np.round(x * scale).astype("<i4")
    raw = ints.astype("<i2").tobytes() if width == 2 else b"".join(v.to_bytes(4, "little", signed=True)[:3] for v in ints.reshape(-1).tolist())
    with wave.open(path, "wb") as f:
        f.setnchannels(channels); f.setsampwidth(width); f.setframerate(rate); f.writeframes(raw)
    return path
variants = [
    ("WAV 24 bits", wav_variant("wav24", 44100, 2, 3)),
    ("WAV 96 kHz", wav_variant("wav96k", 96000, 2, 2)),
    ("WAV mono 22 kHz", wav_variant("wavmono", 22050, 1, 2)),
    ("WAV 5.1 (6 canales)", wav_variant("wav51", 48000, 6, 2)),
    ("MP3 mono 128 kbps", sint.mp3(os.path.join(work, "mono.mp3"), 3, seed=11, channels=1, bitrate=128)),
    ("MP3 48 kHz", sint.mp3(os.path.join(work, "48k.mp3"), 3, seed=12, rate=48000)),
    ("MP3 320 kbps", sint.mp3(os.path.join(work, "320.mp3"), 3, seed=13, bitrate=320)),
]
for name, path in variants:
    scanned, failure = scan_file(path)
    state, pos, dur, errs, has_audio = play(path)
    played_to_end = state == "StoppedState" and dur > 0 and pos >= dur - 150
    own, own_detail = eq_ok(path)
    ok = scanned is not None and (state == "PlayingState" and pos > 800 or played_to_end) and not errs and own
    results.append(ok)
    print(f"  {'OK' if ok else 'FALLA':5s} {name:32s} importa={'sí' if scanned else 'NO: ' + failure.reason}  Qt: {state} pos={pos}ms  {own_detail}")

print("\n=== Archivos dañados: avisan o suenan lo que se pueda, sin colgarse ===")
good = sint.mp3(os.path.join(work, "entero.mp3"), 6, seed=21)
data = open(good, "rb").read()
damaged = {
    "MP3 cortado a la mitad": data[: len(data) // 2],
    "MP3 cortado al 2 %": data[: len(data) // 50],
    "basura con extensión .mp3": b"\x00 no es audio " * 4000,
    "archivo vacío": b"",
}
for name, content in damaged.items():
    path = os.path.join(work, "danado_" + str(abs(hash(name)) % 10000) + ".mp3")
    open(path, "wb").write(content)
    t0 = time.time()
    scanned, failure = scan_file(path)
    if scanned is None:
        ok = bool(failure and failure.reason)  # no se importa, con un motivo para el usuario
        detail = f"no se importa: {failure.reason if failure else '(sin motivo)'}"
    else:
        state, pos, dur, errs, status = play_eq(path, 1.5)
        ok = state in ("PlayingState", "StoppedState", "PausedState")  # suena lo que hay, o se detiene/avisa
        detail = f"se importa · propio: {state} pos={pos}ms {status} {errs or ''}"
    ok = ok and time.time() - t0 < 10  # nunca se cuelga
    results.append(ok)
    print(f"  {'OK' if ok else 'FALLA':5s} {name:32s} {detail}  ({time.time() - t0:.1f} s)")

REAL = sint.usar_reales()
print("\n=== Archivos reales de tu biblioteca (solo lectura, en silencio) ===" if REAL else
      "\n(sin archivos reales de tu biblioteca: MUSICPLAYER_PRUEBA_REAL=1 para probarlos también)")
db = os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True) if REAL else None
for ext in ((".mp3", ".wma", ".m4a") if REAL else ()):
    rows = con.execute("select path from tracks where lower(path) like ? order by random() limit 3", (f"%{ext}",)).fetchall()
    for (path,) in rows:
        state, pos, dur, errs, has_audio = play(path, 1.5)
        ok = state == "PlayingState" and pos > 600 and not errs and has_audio
        results.append(ok)
        print(f"  {'OK' if ok else 'FALLA':5s} {ext:5s} pos={pos:5d}ms dur={dur/1000:6.1f}s  {os.path.basename(path)[:60]}  {errs or ''}")

print("\nExtensiones aceptadas por el programa:", " ".join(sorted(SUPPORTED_EXTENSIONS)))
print(f"\nRESULTADO: {sum(results)}/{len(results)} formatos/archivos reproducidos correctamente")
os._exit(0 if all(results) else 1)
