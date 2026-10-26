"""Regresión: cada fallo reportado por los 4 agentes revisores, reproducido y comprobado como corregido."""
import math, os, shutil, sqlite3, struct, sys, tempfile, time, wave
from types import SimpleNamespace
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_fixes_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MUSICPLAYER_SILENCIO"] = "1"
import lameenc
import numpy as np
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication, QMainWindow
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup, converter, file_ops, importer, metadata, mp3gain, online_lookup
from app.database import Database
from app.duplicates import find_duplicates
from app.file_operations import FileOperations
from app.importer import scan_file, collect_folder
from app.loudness import LoudnessMeter, decide
from app.loudness_job import AdjustWorker, AnalyzeWorker
from app.models import Track
from app.online_job import CoverWorker
from app.online_lookup import Candidate
from app.player import PlaybackController, RepeatMode
from app.titles import suggest_from_filename
from app.ui import menu_loader
from app.utils import normalize_text

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def tone_wav(path, secs=2.0, rate=22050, channels=1, freq=440):
    with wave.open(path, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
        frame = lambda i: struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate))) * channels
        w.writeframes(b"".join(frame(i) for i in range(int(rate * secs))))
def make_mp3(path, seconds=3, amp=0.05):
    enc = lameenc.Encoder(); enc.set_bit_rate(128); enc.set_in_sample_rate(44100); enc.set_channels(2); enc.set_quality(2)
    pcm = b"".join(struct.pack("<hh", v, v) for v in (int(amp * 32767 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100 * seconds)))
    open(path, "wb").write(enc.encode(pcm) + enc.flush())
def T(i, path, title="t", artist="a", album="b", dur=2000, **kw):
    return Track(id=i, path=path, title=title, artist=artist, album=album, genre="", duration_ms=dur, added_at="x", **kw)

music = os.path.join(work, "Musica"); os.makedirs(music)

print("[Conversión]")
wav, flac = os.path.join(music, "Cancion.wav"), os.path.join(music, "Cancion.flac")
tone_wav(wav); shutil.copy(wav, flac)
s = converter.new_session([T(1, wav), T(2, flac)])
names = [os.path.basename(i.mp3) for i in s.items]
check("dos originales con el mismo nombre reciben MP3 distintos", len(set(names)) == 2, names)
ghost = converter.path_key(os.path.join(music, "Otra.mp3"))
s = converter.new_session([T(3, os.path.join(music, "Otra.wma"))], {ghost})
check("no se elige la ruta de una canción de la biblioteca que ya no está en el disco", os.path.basename(s.items[0].mp3) != "Otra.mp3", s.items[0].mp3)

db = Database(os.path.join(work, "lib.db"))
db.add_tracks([scan_file(wav)[0]])
wav_id = db.all_tracks()[0].id
other = os.path.join(music, "Ocupada.mp3"); make_mp3(other)
db.add_tracks([scan_file(other)[0]])
ops = FileOperations(db, lambda ids: None, lambda ids: None, lambda: None, lambda: True)
s = converter.new_session([db.all_tracks()[0]])
item = s.items[0]; item.mp3 = other  # forzar: la biblioteca ya usa esa ruta (UNIQUE)
shutil.copy(other, other + ".bak")
problem = ops.record_converted(item, s)
shutil.copy(other + ".bak", other)
check("si la biblioteca no acepta el MP3, el original no se mueve", problem and os.path.exists(wav) and not item.moved_to, problem)

# El original dura 60 s según la biblioteca pero solo se leen 2 s: no se usa el MP3
short = os.path.join(music, "Corto.wav"); tone_wav(short, secs=2.0)
s2 = converter.new_session([T(10, short, dur=60000)])
errors = []
w = converter.ConvertWorker(list(zip(s2.items, [T(10, short, dur=60000)])))
w.converted.connect(lambda i, e: errors.append(e))
w.run()
leftovers = [f for f in os.listdir(music) if f.endswith(".tmp")]
check("un original que se lee incompleto no se convierte", errors and "Solo se pudieron leer" in errors[0], errors)
check("  no quedan temporales junto a la música", not leftovers and not os.path.exists(s2.items[0].mp3), leftovers)

print("[Repetidas]")
pistas = [T(i, rf"C:\M\Disco{i}\01.mp3", "Pista 1", "Artista desconocido", "Álbum desconocido", d) for i, d in enumerate([180000, 182500, 185000, 187500, 190000])]
check("«Pista 1» de 5 discos distintos no son repetidas", find_duplicates(pistas) == [])
cadena = [T(i, rf"C:\x\{i}.mp3", "Tema X", "Banda", "A", 180000 + i * 2500) for i in range(5)]
check("las duraciones no se encadenan sin límite", all(max(t.duration_ms for t in g.tracks) - min(t.duration_ms for t in g.tracks) <= 3000 for g in find_duplicates(cadena)))
reales = [T(1, r"C:\A\x.wav", "Dios manda lluvia", "Artista desconocido", "Álbum desconocido", 200000), T(2, r"C:\B\x.wav", "Dios manda lluvia", "Artista desconocido", "Álbum desconocido", 200500)]
check("una repetida real sin artista sí se detecta", len(find_duplicates(reales)) == 1)

print("[Volumen]")
check("el tope de +12 dB es en total", decide(-28, -13, -14, applied=12).gain_db == 0 and decide(-30, -20, -14, applied=6).gain_db == 6.0)
check("sin pico conocido no falla", decide(-30.0, None, -14.0).gain_db == 0.0)
mp3 = os.path.join(music, "baja.mp3"); make_mp3(mp3)
orig = open(mp3, "rb").read()
real_write = mp3gain.write_applied_steps
mp3gain.write_applied_steps = lambda p, n: (_ for _ in ()).throw(mp3gain.MutagenError("simulado"))
try:
    mp3gain.apply_steps(mp3, 2, annotate_total=2); raised = False
except mp3gain.Mp3GainError:
    raised = True
mp3gain.write_applied_steps = real_write
check("si la anotación falla, el audio tampoco cambia (una sola escritura)", raised and open(mp3, "rb").read() == orig)
mp3gain.apply_steps(mp3, 2, annotate_total=2)
check("audio y anotación juntos", mp3gain.read_applied_steps(mp3) == 2)
real_ape = mp3gain.APEv2
mp3gain.APEv2 = lambda p: (_ for _ in ()).throw(PermissionError(13, "en uso"))
got = []
aw = AdjustWorker([(T(20, mp3), 2)]); aw.adjusted.connect(lambda *a: got.append(a)); aw.run()
mp3gain.APEv2 = real_ape
check("archivo bloqueado al leer la anotación: no se ajusta (no se supone 0)", got and got[0][1] == 0 and mp3gain.read_applied_steps(mp3) == 2, got)
fin = []
an = AnalyzeWorker([T(21, os.path.join(music, "no-existe.mp3"))])
meas = []
an.measured.connect(lambda *a: meas.append(a)); an.finished.connect(lambda c: fin.append(c)); an.run()
check("Analizar no se cuelga si falta un archivo", fin == [False] and meas and "no se encuentra" in meas[0][3], meas)
m = LoudnessMeter(); y = np.full((48000, 2), 0.1, np.float32); y[500, 0] = np.nan; m.add(y.reshape(-1))
check("un dato inválido (NaN) no da una medición falsa", m.result() == (None, None))
m = LoudnessMeter(); m.add(np.full((48000 // 20, 2), 0.5, np.float32).reshape(-1))
check("menos de 400 ms: sin sonoridad (solo pico)", m.result()[0] is None)

print("[Papelera]")
import winreg
real_q = winreg.QueryValueEx
winreg.QueryValueEx = lambda h, name: (1, 4) if name == "NukeOnDelete" else real_q(h, name)
reason = file_ops.trash_block_reason(r"C:\Windows\win.ini")
winreg.QueryValueEx = real_q
check("con la Papelera configurada para borrar al instante, no se envía", reason and "borrar los archivos al instante" in reason, reason)
check("con la Papelera normal, se permite", file_ops.trash_block_reason(r"C:\Windows\win.ini") is None)
# Carpetas: se mide TODO su contenido (antes se medía la carpeta en sí, 0 bytes, y nunca se bloqueaba).
import tempfile as _tf
big = _tf.mkdtemp(prefix="mp_bin_"); os.makedirs(os.path.join(big, "sub"))
open(os.path.join(big, "sub", "a.bin"), "wb").write(b"\0" * (1536 * 1024))  # 1,5 MB
small = _tf.mkdtemp(prefix="mp_bin_"); open(os.path.join(small, "b.bin"), "wb").write(b"\0" * 1024)
winreg.QueryValueEx = lambda h, name: (1, 4) if name == "MaxCapacity" else real_q(h, name)  # Papelera de 1 MB
r_big, r_small = file_ops.trash_block_reason(big), file_ops.trash_block_reason(small)
winreg.QueryValueEx = real_q
check("carpeta más grande que la Papelera: no se envía (se borraría para siempre)", r_big and "carpeta ocupa más" in r_big, r_big)
check("  carpeta chica: se permite", r_small is None, r_small)
def _no_capacity(h, name):
    if name == "MaxCapacity": raise OSError("no existe")
    return real_q(h, name)
winreg.QueryValueEx = _no_capacity
old_fraction = file_ops._DEFAULT_BIN_FRACTION; file_ops._DEFAULT_BIN_FRACTION = 1e-12  # Papelera «por defecto» diminuta
r_default = file_ops.trash_block_reason(big)
file_ops._DEFAULT_BIN_FRACTION = old_fraction; winreg.QueryValueEx = real_q
check("  sin tamaño configurado se usa el de Windows por defecto (y también bloquea)", r_default and "Papelera del disco" in r_default, r_default)
check("  una unidad normal no se confunde con «subst»", not file_ops._is_subst_drive(r"C:\Windows\win.ini"))
import shutil as _sh; _sh.rmtree(big, ignore_errors=True); _sh.rmtree(small, ignore_errors=True)

print("[Importación]")
rf64 = os.path.join(music, "grande.wav")
with open(rf64, "wb") as f:
    f.write(b"RF64" + b"\xff\xff\xff\xff" + b"WAVE" + b"ds64" + struct.pack("<I", 28) + b"\x00" * 28 + b"fmt " + b"\x00" * 200)
track, failure = scan_file(rf64)
check("un WAV RF64 no se marca como dañado", track is not None or (failure and not failure.corrupt), failure.reason if failure else "importado")
real_read = importer.read_metadata
importer.read_metadata = lambda p: 1 / 0
track, failure = scan_file(wav)
importer.read_metadata = real_read
check("un error raro en un archivo no corta la importación", track is None and failure and not failure.corrupt)
os.makedirs(os.path.join(music, converter.ORIGINALS_FOLDER_NAME)); shutil.copy(wav, os.path.join(music, converter.ORIGINALS_FOLDER_NAME, "x.wav"))
files, _f, _i = collect_folder(music, True)
check("reimportar no mete «_Originales convertidos»", not any(converter.ORIGINALS_FOLDER_NAME in p for p in files))

print("[Respaldos]")
odd = os.path.join(work, "carpeta #1 %20"); os.makedirs(odd)
junk = os.path.join(odd, "basura.db"); open(junk, "wb").write(b"no es sqlite" * 100)
check("una ruta con «#» o «%» se revisa bien", backup.check_database(junk) is not None)

print("[Deshacer]")
from app import review_folder
src = os.path.join(music, "a.wav"); tone_wav(src)
dest = os.path.join(work, "rev", "a.wav"); os.makedirs(os.path.dirname(dest))
os.rename(src, dest)
sess = review_folder.Session(id="t1", destination=os.path.dirname(dest), status=review_folder.STATUS_DONE, created_at="2026-10-23T10:00:00",
                             moves=[review_folder.Move(1, src, dest, True)])
restored, problems = review_folder.undo(sess, on_restored=lambda m: (_ for _ in ()).throw(sqlite3.OperationalError("disco lleno")))
check("si la biblioteca falla al deshacer, el archivo se deja donde estaba", not restored and problems and os.path.exists(dest) and not os.path.exists(src))

print("[Reproductor]")
p = PlaybackController()
a, b = os.path.join(music, "pa.wav"), os.path.join(music, "pb.wav"); tone_wav(a); tone_wav(b)
p.play_queue([T(1, a), T(2, b), T(3, os.path.join(music, "falta.wav"))], 1); spin(100)
p.set_repeat(RepeatMode.OFF)
p._advance(1, user=False); spin(100)
check("sin repetición, saltar la última que falta termina la cola", not p.is_playing and p.current_track.id == 1)
started = []
p.track_started.connect(lambda t: started.append(t.id))
p.play_queue([T(1, a), T(2, b)], 0); spin(300)
p.release_source(); p.toggle_play(); spin(300)
check("tras soltar el archivo, «Reproducir» vuelve a sonar", p.is_playing and p.current_track.id == 1)
check("  y no se cuenta dos veces como reproducida", started.count(1) == 1, started)
p.remove_tracks({1}); spin(200)
check("quitar la que suena pasa a la siguiente (no vacía la cola)", p.current_track is not None and p.current_track.id == 2)
p.stop()

print("[Menús]")
src_ui = open(menu_loader.MENUS_FILE, encoding="utf-8").read()
ui = src_ui.replace("<string>Ctrl+N</string>", "<string>Del</string>").replace("<string>Ctrl+R</string>", "<string>Ctrl+O</string>")
ui = ui.replace("""   <addaction name="menu_ayuda"/>""", """   <addaction name="menu_ayuda"/>
   <addaction name="act_about"/>""")
ui = ui.replace("""  <action name="act_stop">""", """  <action name="act_stop">
   <property name="visible">
    <bool>false</bool>
   </property>""")
edited = os.path.join(work, "m.ui"); open(edited, "w", encoding="utf-8").write(ui)
spec, _w = menu_loader.load(edited)
win = QMainWindow()
acts, _m = menu_loader.build(win, win.menuBar(), spec, {n: (lambda: None) for n in spec.actions})
check("atajo reservado (Supr) no se asigna y se avisa", acts["act_new_playlist"].shortcut().isEmpty() and any("Del" in w for w in spec.warnings), spec.warnings)
check("atajo repetido se avisa", any("repetido" in w for w in spec.warnings))
check("opción suelta en la barra aparece", any(a.objectName() == "act_about" for a in win.menuBar().actions()))
check("«visible = falso» se respeta", not acts["act_stop"].isVisible())
broken = os.path.join(work, "roto.ui"); open(broken, "w").write("<roto")
spec2, warn2 = menu_loader.load(broken, broken)
check("si fallan los dos archivos, no se rompe (menú básico)", spec2 is None and "menú básico" in warn2 and menu_loader.basic_spec({"act_quit": None}).menus)

print("[Datos en internet]")
real_search = dict(online_lookup._SEARCHERS)
online_lookup._SEARCHERS["deezer"] = lambda q, n: (_ for _ in ()).throw(AttributeError("formato raro"))
online_lookup._SEARCHERS["itunes"] = lambda q, n: [Candidate("itunes", "T", "A", "B", 0, "")]
res = online_lookup.lookup(online_lookup.Query("T", "A", 0), ["deezer", "itunes"])
online_lookup._SEARCHERS.update(real_search)
check("una fuente que responde raro no borra lo de las otras", len(res.candidates) == 1 and "deezer" in res.failed_sources, res.errors)
check("la carátula no se lee de archivos locales", online_lookup.download("file:///C:/Windows/win.ini") is None)
cw = CoverWorker([(T(1, a), Candidate("itunes", "T", "A", "B", 0, "https://x/1.jpg")), (T(2, b), Candidate("itunes", "T2", "A", "B", 0, ""))], True)
out = []
cw.finished.connect(lambda u: out.append(u)); cw.cancel(); cw.run()
check("detener las carátulas guarda igual los datos elegidos", out and len(out[0]) == 2 and all(c is None for _t, _c, c in out[0]))

print("[Preferencias y textos]")
from app.preferences import Preferences
from app.ui.dialogs import PreferencesDialog
prefs = Preferences(QSettings("ReproductorMusicaTest", "Prefs")); prefs.theme = "light"
d = PreferencesDialog(prefs); d.theme_buttons["dark"].setChecked(True)
for box in d.source_boxes.values(): box.setChecked(False)
import app.ui.dialogs as dlg
dlg.QMessageBox.information = staticmethod(lambda *a, **k: None)
d._save(); d.reject()
check("«Cancelar» en Preferencias no deja guardado el tema", prefs.theme == "light", prefs.theme)
check("títulos con número que es parte del nombre", suggest_from_filename("99 Luftballons.mp3")[0] == "99 Luftballons"
      and suggest_from_filename("50 Cent - In Da Club.mp3") == ("In Da Club", "50 Cent") and suggest_from_filename("01 Intro.mp3")[0] == "Intro")
check("buscar «lodz» encuentra «Łódź»", normalize_text("Łódź") == "lodz")
check("duración absurda no rompe la importación", metadata.read_metadata.__code__ is not None)

shutil.rmtree(work, ignore_errors=True)
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear(); QSettings("ReproductorMusicaTest", "Prefs").clear()
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
