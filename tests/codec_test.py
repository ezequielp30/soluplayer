"""Compatibilidad de códecs: genera archivos reales en cada formato codificable, los importa y los reproduce
(en silencio) con el mismo motor del programa; además prueba muestras de la biblioteca real del usuario (solo lectura)."""
import math, os, sqlite3, struct, sys, tempfile, time
sys.path.insert(0, r"D:\reproductor-musica")
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
    ok = scanned is not None and (state == "PlayingState" and pos > 800 or played_to_end) and not errs and has_audio
    results.append(ok)
    print(f"  {'OK' if ok else 'FALLA':5s} {name:32s} {os.path.splitext(path)[1]:6s} importa={'sí' if scanned else 'NO: ' + failure.reason} "
          f"duración={(scanned.metadata.duration_ms if scanned else 0)/1000:.1f}s  suena={state} pos={pos}ms  {errs or ''}")

print("\n=== Archivos reales de tu biblioteca (solo lectura, en silencio) ===")
db = os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
for ext in (".mp3", ".wma", ".m4a"):
    rows = con.execute("select path from tracks where lower(path) like ? order by random() limit 3", (f"%{ext}",)).fetchall()
    for (path,) in rows:
        state, pos, dur, errs, has_audio = play(path, 1.5)
        ok = state == "PlayingState" and pos > 600 and not errs and has_audio
        results.append(ok)
        print(f"  {'OK' if ok else 'FALLA':5s} {ext:5s} pos={pos:5d}ms dur={dur/1000:6.1f}s  {os.path.basename(path)[:60]}  {errs or ''}")

print("\nExtensiones aceptadas por el programa:", " ".join(sorted(SUPPORTED_EXTENSIONS)))
print(f"\nRESULTADO: {sum(results)}/{len(results)} formatos/archivos reproducidos correctamente")
os._exit(0 if all(results) else 1)
