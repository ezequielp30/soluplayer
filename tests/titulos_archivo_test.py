"""El título limpio se graba dentro de los archivos: solo cambia esa etiqueta (sonido, nombre, fecha y demás
etiquetas siguen iguales), se puede deshacer y un fallo deja el archivo intacto. Todo en carpetas temporales."""
import os, shutil, struct, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_titulos_archivo_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.flac import FLAC
from mutagen.id3 import APIC, ID3, TIT2
from mutagen.wave import WAVE
import audio_sintetico as synth
from app import title_tags
from app.config import database_path
from app.database import Database
from app.file_operations import KIND_TITLES
from app.importer import scan_file
from app.metadata import read_metadata
from app.ui import main_window as mw

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def audio_bytes(path):
    """El MP3 sin su cabecera ID3: lo que suena."""
    data = open(path, "rb").read()
    if data[:3] != b"ID3":
        return data
    b = data[6:10]
    return data[10 + ((b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]):]
def title_tag(path):
    meta = read_metadata(path)
    return meta.title if meta.has_title_tag else None
def leftovers(folder):
    return [f for f in os.listdir(folder) if "limpiando-titulo" in f]

music = os.path.join(work, "Musica"); os.makedirs(music)
MESSY = "►►cuando mi pueblo ora (original)"; CLEAN = "cuando mi pueblo ora (original)"

print("[Solo cambia la etiqueta del título]")
v23 = synth.mp3(os.path.join(music, "v23.mp3"), 3, title=MESSY, artist="Jose Luis")
tags = ID3(v23); tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=b"\x89PNG\r\n\x1a\nfake")); tags.save(v23, v2_version=3)
os.utime(v23, (1500000000, 1500000000))
sound, stamp = audio_bytes(v23), os.stat(v23).st_mtime_ns
title_tags.write_title(v23, CLEAN)
after = ID3(v23)
check("el título queda limpio", title_tag(v23) == CLEAN, title_tag(v23))
check("  el sonido es idéntico, byte a byte", audio_bytes(v23) == sound)
check("  el nombre y la fecha del archivo no cambian", os.path.exists(v23) and os.stat(v23).st_mtime_ns == stamp)
check("  las demás etiquetas y la carátula siguen", read_metadata(v23).artist == "Jose Luis" and after.getall("APIC"))
check("  sigue en ID3v2.3, la que entienden todos", after.version[:2] == (2, 3), after.version)
check("  y no deja temporales", not leftovers(music))

v24 = synth.mp3(os.path.join(music, "v24.mp3"), 2, title=MESSY)
ID3(v24).save(v24, v2_version=4); sound = audio_bytes(v24)
title_tags.write_title(v24, CLEAN)
check("ID3v2.4 sigue en 2.4", ID3(v24).version[:2] == (2, 4) and title_tag(v24) == CLEAN and audio_bytes(v24) == sound)

wav = synth.wav(os.path.join(music, "►►con wav.wav"), 1)
title_tags.write_title(wav, "con wav")
check("WAV: se graba y no se pierde el sonido", title_tag(wav) == "con wav" and abs(WAVE(wav).info.length - 1) < 0.05)

flac = os.path.join(music, "f.flac")
info = struct.pack(">HH3s3s", 4096, 4096, b"\0\0\0", b"\0\0\0") + ((44100 << 44 | 1 << 41 | 15 << 36 | 44100).to_bytes(8, "big")) + b"\0" * 16
with open(flac, "wb") as f: f.write(b"fLaC" + b"\x80\x00\x00\x22" + info)
tagged = FLAC(flac); tagged["title"] = [MESSY]; tagged.save()
title_tags.write_title(flac, CLEAN)
check("FLAC: se graba", FLAC(flac)["title"] == [CLEAN])

print("[Qué se graba y qué no]")
check("un título sin signos no se toca", title_tags.clean_title_for(synth.mp3(os.path.join(music, "normal.mp3"), 1, title="Normal")) is None)
check("«¿» y «¡» también se quitan", title_tags.clean_title_for(synth.mp3(os.path.join(music, "preg.mp3"), 1, title="¿A quién tengo yo?")) == ("¿A quién tengo yo?", "A quién tengo yo?"))
check("los números tampoco", title_tags.clean_title_for(synth.mp3(os.path.join(music, "num.mp3"), 1, title="06. Con tu Sangre")) is None)
broken = os.path.join(music, "roto.mp3"); open(broken, "wb").write(b"no es audio")
check("un archivo dañado se deja como está", title_tags.clean_title_for(broken) is None)
aac = os.path.join(music, "►x.aac"); open(aac, "wb").write(b"\xff\xf1\x50\x80\x01\x7f\xfc" + b"\0" * 40)
worker = title_tags.CleanTitleTagsWorker([(1, aac)]); got = []
worker.finished.connect(lambda n, p: got.append((n, p))); worker.run()
check("un formato sin etiquetas que escribir no es un fallo", got == [(0, [])] and not leftovers(music), got)

print("[Un fallo deja el archivo intacto]")
locked = synth.mp3(os.path.join(music, "enuso.mp3"), 1, title=MESSY); before = open(locked, "rb").read()
holder = open(locked, "rb")
try:
    title_tags.write_title(locked, CLEAN); failed = False
except OSError:
    failed = True
holder.close()
check("en uso: da error, sin tocar el archivo ni dejar temporales", failed and open(locked, "rb").read() == before and not leftovers(music))
readonly = synth.mp3(os.path.join(music, "solo.mp3"), 1, title=MESSY); os.chmod(readonly, 0o444); before = open(readonly, "rb").read()
try:
    title_tags.write_title(readonly, CLEAN); failed = False
except OSError:
    failed = True
os.chmod(readonly, 0o666)
check("solo lectura: se respeta", failed and open(readonly, "rb").read() == before and not leftovers(music))
changing = synth.mp3(os.path.join(music, "cambia.mp3"), 1, title=MESSY)
real_verify = title_tags._verify
def touched(source, temp, title):
    real_verify(source, temp, title); os.utime(source, (1400000000, 1400000000))
title_tags._verify = touched
try:
    title_tags.write_title(changing, CLEAN); failed = False
except OSError:
    failed = True
title_tags._verify = real_verify
check("si otro lo cambia a mitad (ajuste de volumen), no se pisa", failed and title_tag(changing) == MESSY and not leftovers(music))
for path in (locked, readonly, changing, broken, aac, v23, v24, wav, flac):
    os.remove(path)

print("[En el programa: solo, en segundo plano y reversible]")
files = {
    "uno": synth.mp3(os.path.join(music, "uno.mp3"), 1, title="🔥El Infierno Tiembla"),
    "dos": synth.mp3(os.path.join(music, "dos.mp3"), 1, title="| EL PODEROSO"),
    "bloqueado": synth.mp3(os.path.join(music, "bloqueado.mp3"), 1, title="[Oficial] Santo"),
}
db = Database(database_path())
for path in files.values():
    db.add_tracks([scan_file(path)[0]])
mw.FILE_TITLES_DELAY_MS = 0
holder = open(files["bloqueado"], "rb")
win = mw.MainWindow(db); win.show(); win.player.set_volume(0)
idle = lambda: win._tags_thread is None and win.settings.contains("library/file_titles_cleaned_2")
spin(15000, idle)
check("al abrir, los títulos quedan grabados en los archivos", title_tag(files["uno"]) == "El Infierno Tiembla" and title_tag(files["dos"]) == "EL PODEROSO",
      (title_tag(files["uno"]), title_tag(files["dos"])))
check("el que está en uso queda como estaba", title_tag(files["bloqueado"]) == "[Oficial] Santo")
check("  y queda pendiente para la próxima vez", not win.settings.value("library/file_titles_cleaned_2", type=bool))
holder.close()
win._clean_file_titles_once(); spin(15000, lambda: win._tags_thread is None)
check("al reintentar se graba, y ya no vuelve a revisar", title_tag(files["bloqueado"]) == "Oficial Santo" and win.settings.value("library/file_titles_cleaned_2", type=bool))

imported = synth.mp3(os.path.join(music, "nueva.mp3"), 1, title="►Nueva")
db_item = scan_file(imported)[0]
added, _ = db.add_tracks([db_item]); win._reload_library()
win._start_cleaning_tags([(db.track_id_for_path(imported), imported)]); spin(15000, lambda: win._tags_thread is None)
check("lo importado también", title_tag(imported) == "Nueva" and db.conn.execute("select title from tracks where id=?", (db.track_id_for_path(imported),)).fetchone()[0] == "Nueva")

entries = [e for e in win.ops.history(win.library) if e.kind == KIND_TITLES]
check("en el Historial se ve y se puede deshacer", len(entries) == 3 and all(e.can_undo for e in entries), [(e.detail, e.status) for e in entries])
first = next(e for e in entries if e.count == 2)
title_tags.write_title(files["dos"], "Puesto a mano")
first = next(e for e in win.ops.history(win.library) if e.kind == KIND_TITLES and e.session.id == first.session.id)
outcome = win.ops.undo(first)
check("deshacer: vuelve el título original", title_tag(files["uno"]) == "🔥El Infierno Tiembla", outcome.message)
check("  lo cambiado después a mano no se toca", title_tag(files["dos"]) == "Puesto a mano" and outcome.problems, outcome.problems)
check("  en la biblioteca el título sigue limpio", db.conn.execute("select title from tracks where id=?", (db.track_id_for_path(files["uno"]),)).fetchone()[0] == "El Infierno Tiembla")

print("[Cerrar mientras graba]")
extra = [synth.mp3(os.path.join(music, f"lote{i}.mp3"), 1, title=f"►Lote {i}") for i in range(6)]
win.settings.setValue("library/file_titles_cleaned_2", True)
win._start_cleaning_tags([(1000 + i, p) for i, p in enumerate(extra)])
win.close(); spin(100)
sane = all(title_tag(p) in (f"►Lote {i}", f"Lote {i}") for i, p in enumerate(extra))
check("cierra sin dañar nada y sin temporales", sane and not leftovers(music))
check("  lo que faltó queda para la próxima vez", not QSettings("ReproductorMusicaTest", "ReproductorMusica").value("library/file_titles_cleaned_2", type=bool))

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
