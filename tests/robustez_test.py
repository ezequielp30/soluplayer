"""Correcciones de la revisión de producción (control de calidad de los agentes), cada una reproducida:
Papelera de carpetas, mover entre discos sin copias sobrantes, nombres y rutas largas, biblioteca vacía,
preferencias dañadas, deshacer solo MP3 creados por el programa, ecualizador con disco lleno, carátulas
solo JPEG/PNG, importar sin las carpetas del programa, temas retirados y Repetidas sin copia conservada.
Todo en carpetas temporales (y una temporal en D: para probar entre discos, que se borra al final)."""
import ctypes, math, os, shutil, sqlite3, stat, struct, sys, tempfile, time, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_rob_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
import numpy as np
from PySide6.QtCore import QEventLoop, QSettings, QUrl
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import artwork, backup, converter, file_manager
from app.file_manager import FileManagerError
from app.importer import ImportWorker, in_skipped_folder

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs=2):
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(22050)
        f.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(i / 5))) for i in range(22050 * secs)))
    return path

print("[Mover a otro disco]")
other = tempfile.mkdtemp(prefix="_mp_rob_", dir="D:\\") if os.path.splitdrive(work)[0].upper() != "D:" else tempfile.mkdtemp(prefix="_mp_rob_", dir="C:\\Users\\Public")
src_dir = os.path.join(work, "origen"); os.makedirs(src_dir)
ok_file = tone(os.path.join(src_dir, "normal.wav"))
data = open(ok_file, "rb").read()
r = file_manager.move_files([ok_file], other)
target = os.path.join(other, "normal.wav")
check("mueve a otro disco: original quitado, copia idéntica, sin temporales", r.moved and not os.path.exists(ok_file)
      and open(target, "rb").read() == data and not [f for f in os.listdir(other) if f.endswith(".tmp")], (r.moved, r.failed))
ro = tone(os.path.join(src_dir, "solo-lectura.wav")); os.chmod(ro, stat.S_IREAD)
r = file_manager.move_files([ro], other)
check("archivo de solo lectura: no se mueve y NO queda copia en el destino", r.failed and os.path.exists(ro)
      and not os.path.exists(os.path.join(other, "solo-lectura.wav")) and not os.listdir(other) == ["x"], (r.failed, os.listdir(other)))
os.chmod(ro, stat.S_IWRITE | stat.S_IREAD)
locked = tone(os.path.join(src_dir, "bloqueado.wav"))
k32 = ctypes.windll.kernel32; k32.CreateFileW.restype = ctypes.c_void_p
handle = k32.CreateFileW(locked, 0x80000000, 0x1, None, 3, 0x80, None)  # lectura compartida, sin permiso de borrar
r = file_manager.move_files([locked], other)
k32.CloseHandle(ctypes.c_void_p(handle))
check("archivo abierto en otro programa: no se mueve y NO queda copia", r.failed and os.path.exists(locked)
      and not os.path.exists(os.path.join(other, "bloqueado.wav")), (r.failed, sorted(os.listdir(other))))
shutil.rmtree(other, ignore_errors=True)

print("[Nombres y rutas largas]")
def rejected(name):
    try:
        file_manager.check_name(name); return False
    except FileManagerError:
        return True
check("200 emoji (400 unidades en Windows) se rechazan", rejected("😀" * 150))
check("espacio invisible U+200B y U+202E se rechazan", rejected("\u200b") and rejected("abc\u202emp3.exe"))
check("«CON .mp3», CONIN$ y COM¹ se rechazan", rejected("CON .mp3") and rejected("CONIN$") and rejected("COM¹.mp3"))
check("nombres normales con acentos, ñ y emoji se aceptan", not rejected("Canción ñandú 🎵.mp3"))
deep = os.path.join(work, "d" * 60, "e" * 60); os.makedirs(deep)
song = tone(os.path.join(deep, "s.wav"), 1)
try:
    file_manager.rename_file(song, "x" * 150); msg = ""
except FileManagerError as exc:
    msg = str(exc)
check("ruta de más de 260 caracteres: mensaje claro (no «ya no existe»)", "demasiado larga" in msg and os.path.exists(song), msg)

print("[Biblioteca vacía]")
empty = os.path.join(work, "vacia.db"); open(empty, "wb").close()
check("una biblioteca de 0 bytes se detecta como dañada", backup.check_database(empty) is not None, backup.check_database(empty))
noschema = os.path.join(work, "sin-tablas.db"); sqlite3.connect(noschema).execute("create table x(a)").connection.commit()
check("una base sin las tablas de la biblioteca se detecta", backup.check_database(noschema) is not None)

print("[Preferencias dañadas]")
from app.preferences import Preferences
s = QSettings("ReproductorMusicaTest", "ReproductorMusica")
s.setValue("equalizer/state", '{"gains": ["abc", null, 1e999], "preamp": "x", "custom": {"m": {"gains": "no"}}}')
s.setValue("player/volume", "mucho"); s.setValue("preferences/theme", "vino")
eq = Preferences(s).equalizer()
check("ecualizador dañado vuelve a valores válidos", eq["gains"][:3] == [0.0, 0.0, 0.0] and eq["preamp"] == 0.0 and eq["custom"]["m"]["gains"] == [0.0] * 10, eq)
check("tema retirado («vino») se lee como el nuevo («rubi»)", Preferences(s).theme == "rubi", Preferences(s).theme)
from app.database import Database
from app.config import database_path
from app.ui import main_window as mw
db = Database(database_path())
try:
    win = mw.MainWindow(db); opened = True
except Exception as exc:
    opened = False; print(exc)
check("con volumen dañado en el registro el programa abre igual", opened and win.player_bar.volume.value() == 70)
from app.ui.theme_picker import ThemePicker
check("Preferencias marca el tema que reemplaza al retirado", ThemePicker("vino").selected() == "rubi")

print("[Deshacer conversión: solo MP3 creados por el programa]")
conv = os.path.join(work, "conv"); os.makedirs(conv)
orig = tone(os.path.join(conv, "cancion.wav"))
users_mp3 = os.path.join(conv, "cancion.mp3"); open(users_mp3, "wb").write(b"ID3" + b"\0" * 2000)  # MP3 del usuario
item = converter.Conversion(track_id=1, original=orig, mp3=users_mp3, moved_to="", done=False)
session = converter.ConversionSession(id="t1", originals_root=os.path.join(conv, "_Originales convertidos"),
                                      status=converter.STATUS_DONE, created_at="2026-10-24T10:00:00", items=[item])
check("un MP3 que ya estaba (no lo creó el programa) no cuenta para deshacer", converter.pending_items(session) == [])
converter.undo(session)
check("  y deshacer NO lo envía a la Papelera", os.path.exists(users_mp3))

print("[Ecualizador: disco lleno]")
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices
from app.eq_player import EqPlayer
audio = QAudioOutput(QMediaDevices.defaultAudioOutput()); audio.setVolume(0.0)
p = EqPlayer(audio)
store = p._store
store._limit = 100; store._step = 100
store.append(np.zeros((50, 2), np.int16))
class Full:
    def write(self, *_): raise OSError(28, "No queda espacio en el disco")
    def close(self): pass
real_fdopen = os.fdopen
import app.eq_player as eqp
eqp.os.fdopen = lambda fd, mode: (os.close(fd), Full())[1]
temps_before = set(os.listdir(tempfile.gettempdir()))  # el reproductor instalado puede estar sonando con los suyos
try:
    store.append(np.zeros((80, 2), np.int16)); spilled = "sin error"
except OSError:
    spilled = "error"
eqp.os.fdopen = real_fdopen
check("si el disco se llena al pasar a temporal: error controlado, sigue en memoria", spilled == "error" and not store.on_disk and store.frames == 50, (spilled, store.frames))
check("  y no deja archivos temporales", not [f for f in set(os.listdir(tempfile.gettempdir())) - temps_before if f.startswith("reproductor-eq-")])

print("[Carátulas]")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage
def encoded(fmt):
    img = QImage(40, 40, QImage.Format.Format_RGB32); img.fill(0x336699)
    ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, fmt); buf.close()
    return bytes(ba.data())
check("carátula JPEG y PNG se aceptan", artwork.make_thumbnail(encoded("JPG")) and artwork.make_thumbnail(encoded("PNG")))
check("carátula en otro formato (BMP, GIF) se ignora", artwork.make_thumbnail(encoded("BMP")) is None and artwork.make_thumbnail(encoded("GIF")) is None)

print("[Importar sin las carpetas del programa]")
lib = os.path.join(work, "lib", "_Originales convertidos", "Album"); os.makedirs(lib)
inside = tone(os.path.join(lib, "original.wav"), 1)
check("se reconoce un archivo dentro de «_Originales convertidos»", in_skipped_folder(inside))
done = {}
w = ImportWorker(set(), files=[inside])
w.finished.connect(lambda res: done.setdefault("r", res)); w.run()
check("importarlo directamente no lo agrega a la biblioteca", not done["r"].tracks and "carpeta del programa" in done["r"].failures[0].reason)

print("[Repetidas: copia conservada que no existe]")
from app.file_operations import FileOperations
from app.models import Track
real_copy = tone(os.path.join(work, "real.wav"), 1)
ids = db.add_tracks([__import__("app.importer", fromlist=["scan_file"]).scan_file(real_copy)[0]])
lib_tracks = db.all_tracks()
present = lib_tracks[0]
ghost = present.copy(); ghost.id = 999999; ghost.path = os.path.join(work, "no-existe.wav")
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
ops._prepare = lambda *a, **k: True
out = ops.remove_duplicates([(ghost.id, [present])], True, [present, ghost])
check("si la copia «conservada» no está en el disco, NO se envía la única real", os.path.exists(real_copy) and out.failed, out.failed if out else None)

win.close(); spin(100)
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
