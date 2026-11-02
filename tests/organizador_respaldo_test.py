"""Organizador, fase 4: ninguna canción se pierde. Copia verificada antes de tocar nada, audio idéntico byte a byte, solo
TITLE y ARTIST, nombre sin pisar otros archivos, cortes en cada paso y restauración exacta. Todo en carpetas temporales."""
import hashlib, json, os, shutil, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_respaldo_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QCoreApplication
app = QCoreApplication(sys.argv)
from mutagen.apev2 import APEv2
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TXXX
from mutagen.mp3 import MP3
import audio_sintetico as synth
from app import converter, normalizer, song_backup, title_tags
from app.normalizer import NormalizeError, SongJob
from app.organizer import DECISION_AUTO, DECISION_REVIEW, Identification
from app.organizer_db import (ITEM_BACKED_UP, ITEM_DONE, ITEM_FAILED, ITEM_PLANNED, ITEM_RENAMING, ITEM_RESTORED, ITEM_TAGGED, OrganizerDb)
from app.organizer_job import NormalizeWorker, RestoreWorker

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
music = os.path.join(work, "Coleccion"); os.makedirs(music)
backups = os.path.join(work, "Respaldos")
db_file = os.path.join(work, "org.db"); db = OrganizerDb(db_file)
counter = [0]
def song(name="Pista 01.mp3", title="Canal de YouTube - Santo (Video Oficial)", artist="canal123", rich=True, folder=music):
    counter[0] += 1
    path = synth.mp3(os.path.join(folder, name), 3, title=title, artist=artist, seed=counter[0])
    if rich:
        tags = ID3(path)
        tags.add(TALB(encoding=3, text=["Disco"])); tags.add(TCON(encoding=3, text=["Cristiana"]))
        tags.add(COMM(encoding=3, lang="spa", desc="", text=["De YouTube"]))
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=b"\x89PNG\r\n\x1a\nfake"))
        tags.save(path, v2_version=3)
    os.utime(path, (1500000000, 1500000000))
    info = os.stat(path); db.register([(path, info.st_size, info.st_mtime_ns)])
    return path, db.file(path).id
op = db.begin_operation()
def run(file_id, title="Santo", artist="New Wine"):
    return normalizer.normalize(db, op, SongJob(file_id, title, artist), backups)

print("[Audio]")
path, fid = song("Comparar.mp3")
digest = song_backup.audio_digest(path); start, end = song_backup.audio_range(path)
check("excluye la etiqueta del principio", start > 10 and end == os.path.getsize(path), (start, end))
copy = path + ".copia.mp3"; shutil.copy2(path, copy)
ID3(copy).save(copy, v2_version=4); tags = ID3(copy); tags.add(TALB(encoding=3, text=["Otro disco " * 50])); tags.save(copy)
check("otras etiquetas: el mismo audio", song_backup.audio_digest(copy) == digest and sha(copy) != sha(path))
ape = APEv2(); ape["MP3GAIN_UNDO"] = "-002,-002,N"; ape.save(copy)
check("con APEv2: el mismo audio", song_backup.audio_digest(copy) == digest)
with open(copy, "r+b") as f:
    f.seek(start + 2000); byte = f.read(1); f.seek(start + 2000); f.write(bytes([byte[0] ^ 1]))
check("un solo byte de audio distinto se detecta", song_backup.audio_digest(copy) != digest)
os.remove(copy)
bad_edit = path + ".mal.mp3"; shutil.copy2(path, bad_edit)
def corrupt(temp):
    a, b = song_backup.audio_range(temp)
    with open(temp, "r+b") as f:
        f.seek(a + 500); f.write(b"\x00\x01\x02")
before = sha(bad_edit)
try:
    title_tags.edit_safely(bad_edit, corrupt, None); check("una edición que daña el audio se rechaza", False)
except ValueError:
    check("una edición que daña el audio se rechaza y el archivo queda igual", sha(bad_edit) == before)
os.remove(bad_edit)

print("[Respaldo]")
backup = os.path.join(backups, "x", "copia.mp3")
got = song_backup.make_backup(path, backup)
check("copia idéntica y verificada", got == sha(path) == sha(backup))
try:
    song_backup.make_backup(path, backup); check("no pisa un respaldo", False)
except song_backup.BackupError:
    check("no pisa un respaldo", True)
real_digest = song_backup.file_digest; calls = [0]
def lying(p):
    calls[0] += 1
    return "otro" if calls[0] == 2 else real_digest(p)
song_backup.file_digest = lying; other = os.path.join(backups, "x", "mala.mp3")
try:
    song_backup.make_backup(path, other); check("copia que no sale idéntica", False)
except song_backup.BackupError:
    check("copia que no sale idéntica: se rechaza y no queda a medias", not os.path.exists(other) and not os.path.exists(other + ".copiando.tmp"))
song_backup.file_digest = real_digest
check("mira si hay espacio", song_backup.enough_space(work, 1) and not song_backup.enough_space(work, 10**16))

print("[Normalizar]")
path, fid = song("01 - Santo (Video Oficial).mp3")
original = open(path, "rb").read(); audio_before = song_backup.audio_digest(path); length_before = MP3(path).info
item = run(fid, "01 - Santo (feat. Alguien)", "New Wine ft. Otro")
target = os.path.join(music, "Santo - New Wine.mp3")
check("nombre TITULO - ARTISTA.mp3", item.state == ITEM_DONE and os.path.isfile(target) and not os.path.exists(path), item.new_path)
tags = ID3(target)
check("solo TITLE y ARTIST", set(tags.keys()) == {"TIT2", "TPE1"} and str(tags["TIT2"]) == "Santo" and str(tags["TPE1"]) == "New Wine", dict((k, str(v)) for k, v in tags.items()))
check("el audio es idéntico byte a byte", song_backup.audio_digest(target) == audio_before)
after = MP3(target).info
check("duración, calidad y frecuencia iguales", (after.length, after.bitrate, after.sample_rate, after.channels) == (length_before.length, length_before.bitrate, length_before.sample_rate, length_before.channels))
check("conserva la fecha del archivo", int(os.path.getmtime(target)) == 1500000000)
check("el respaldo es el original exacto", open(item.backup_path, "rb").read() == original and song_backup.file_digest(item.backup_path) == item.backup_sha)
check("registra metadatos, ubicación y cambios", item.old_path == path and "De YouTube" in item.old_tags and "Disco" in item.old_tags and item.new_title == "Santo" and item.new_artist == "New Wine", item.old_tags[:120])
check("los metadatos anotados se pueden leer", isinstance(json.loads(item.old_tags), dict))
check("la huella sigue valiendo tras el cambio", db.file(target).id == fid and db.file_by_id(fid).path == target)
accent, afid = song("Señor.mp3"); item2 = run(afid, "Canción del Señor", "José Ñáñez")
check("  etiquetas con tildes, nombre sin ellas", os.path.basename(item2.new_path) == "Cancion del Senor - Jose Nanez.mp3" and str(ID3(item2.new_path)["TIT2"]) == "Canción del Señor" and str(ID3(item2.new_path)["TPE1"]) == "José Ñáñez", item2.new_path)
number, nfid = song("03 - Siete.mp3"); item3 = run(nfid, "7 Dias", "A")
check("  un número del título se conserva", os.path.basename(item3.new_path) == "7 Dias - A.mp3", item3.new_path)
check("otra vez lo mismo: no hace nada ni crea otro respaldo", run(fid, "Santo", "New Wine") is None)

print("[Marcas del programa]")
marked, mfid = song("Marcada.mp3")
tags = ID3(marked); tags.add(TXXX(encoding=3, desc=converter._CREATED_MARK, text=["origen"])); tags.save(marked, v2_version=3)
ape = APEv2(); ape["MP3GAIN_UNDO"] = "-002,-002,N"; ape.save(marked)
info = os.stat(marked); db.register([(marked, info.st_size, info.st_mtime_ns)])
done = run(db.file(marked).id, "Marcada", "A")
check("conserva la marca de conversión", f"TXXX:{converter._CREATED_MARK}" in ID3(done.new_path))
check("conserva el ajuste de volumen", "MP3GAIN_UNDO" in APEv2(done.new_path))

print("[No pisa nada]")
first, f1 = song("uno.mp3"); second, f2 = song("dos.mp3")
a = run(f1, "Repetida", "A"); kept = sha(a.new_path); b = run(f2, "Repetida", "A")
check("mismo nombre: «(2)», sin pisar", os.path.basename(b.new_path) == "Repetida - A (2).mp3" and sha(a.new_path) == kept and os.path.isfile(b.new_path), b.new_path)
files_before = sorted(os.listdir(music))
check("no quedan temporales", not [f for f in files_before if "tmp" in f or "limpiando" in f], files_before)

print("[Si algo falla, la canción queda como estaba]")
blocked, bfid = song("bloqueada.mp3"); before = sha(blocked)
real_backup = song_backup.make_backup
def no_backup(*a): raise song_backup.BackupError("disco lleno")
song_backup.make_backup = no_backup
try:
    run(bfid, "Bloqueada", "A"); check("sin respaldo", False)
except NormalizeError as exc:
    check("sin respaldo confirmado no se toca", sha(blocked) == before and os.path.exists(blocked), exc)
song_backup.make_backup = real_backup
real_space = song_backup.enough_space; song_backup.enough_space = lambda *a: False
try:
    run(bfid, "Bloqueada", "A"); check("sin espacio", False)
except NormalizeError as exc:
    check("sin espacio no se toca", sha(blocked) == before, exc)
song_backup.enough_space = real_space
holder = open(blocked, "rb")
try:
    run(bfid, "Bloqueada", "A"); check("archivo en uso", False)
except NormalizeError as exc:
    check("archivo en uso: avisa y queda intacto", sha(blocked) == before and os.path.exists(blocked), exc)
holder.close()
retry = run(bfid, "Bloqueada", "A")
check("al liberarse se retoma con el mismo respaldo", retry.state == ITEM_DONE and sha(retry.backup_path) == before and len([i for i in db.items() if i.file_id == bfid and i.backup_path]) == 1)
changed, cfid = song("cambiada.mp3"); open(changed, "ab").write(b"\x00" * 10)
try:
    run(cfid, "Cambiada", "A"); check("archivo cambiado", False)
except NormalizeError as exc:
    check("si cambió desde el análisis, no se toca", "cambió" in str(exc), exc)
retouched, rfid = song("retocada.mp3"); kept_item = db.add_item(op, rfid, retouched, "{}", "Retocada", "A"); kept_item = normalizer._back_up(db, kept_item, backups)
open(retouched, "ab").write(b"\x01" * 10); before = sha(retouched)
try:
    run(rfid, "Retocada", "A"); check("cambiado tras el respaldo", False)
except NormalizeError as exc:
    check("si cambió después del respaldo, no se pisa lo nuevo", sha(retouched) == before and "cambió" in str(exc), exc)
gone, gfid = song("borrada.mp3"); os.remove(gone)
try:
    run(gfid, "Borrada", "A"); check("archivo que ya no está", False)
except NormalizeError as exc:
    check("si ya no está, lo dice", "ya no está" in str(exc), exc)
empty, efid = song("sinnada.mp3")
for title, artist in (("", "A"), ("Santo", ""), ("♪♪♪", "A")):
    try:
        run(efid, title, artist); check(f"sin datos «{title}» «{artist}»", False)
    except NormalizeError:
        check(f"sin datos «{title}» «{artist}»: no inventa ni toca", os.path.exists(empty))
damaged = os.path.join(music, "danada.mp3"); open(damaged, "wb").write(b"esto no es audio" * 200)
info = os.stat(damaged); db.register([(damaged, info.st_size, info.st_mtime_ns)]); before = sha(damaged)
try:
    run(db.file(damaged).id, "Danada", "A"); check("archivo dañado", False)
except NormalizeError as exc:
    check("archivo dañado: queda intacto", sha(damaged) == before, str(exc)[:80])

print("[Corte de luz en cada paso]")
def interrupted(state):
    """Deja una canción como si se hubiera cortado la luz justo tras llegar a `state`."""
    path, fid = song(f"corte {state}.mp3")
    item = db.add_item(op, fid, path, normalizer.tags_snapshot(path), f"Corte {state}", "A")
    original = sha(path)
    if state != ITEM_PLANNED:
        item = normalizer._back_up(db, item, backups)
    if state in (ITEM_TAGGED, ITEM_RENAMING):
        item = normalizer._write_tags(db, item)
    if state == ITEM_RENAMING:
        item = normalizer._rename(db, item)
    return path, fid, item, original
for state in (ITEM_PLANNED, ITEM_BACKED_UP, ITEM_TAGGED, ITEM_RENAMING):
    path, fid, item, original = interrupted(state)
    check(f"«{state}»: se detecta a medias", any(i.id == item.id for i in db.unfinished_items()) and item.state == state, item.state)
    copies = len(os.listdir(os.path.dirname(item.backup_path))) if item.backup_path else None
    done = normalizer.normalize(db, op, SongJob(fid, f"Corte {state}", "A"), backups)
    check(f"«{state}»: se retoma y termina", done.id == item.id and done.state == ITEM_DONE and os.path.isfile(done.new_path) and not os.path.exists(path), done.state)
    check(f"«{state}»: el respaldo es el original", sha(done.backup_path) == original)
    if copies is not None:
        check(f"«{state}»: no duplica el respaldo", len(os.listdir(os.path.dirname(done.backup_path))) == copies)
path, fid, item, original = interrupted(ITEM_RENAMING); os.rename(item.old_path, item.new_path)
done = normalizer.normalize(db, op, SongJob(fid, f"Corte {ITEM_RENAMING}", "A"), backups)
check("corte justo después de renombrar: lo reconoce", done.state == ITEM_DONE and os.path.isfile(done.new_path))
path, fid, item, original = interrupted(ITEM_BACKED_UP)
edited = path + ".t.mp3"; shutil.copy2(path, edited); normalizer.write_song_tags(edited, f"Corte {ITEM_BACKED_UP}", "A"); os.replace(edited, path)
done = normalizer.normalize(db, op, SongJob(fid, f"Corte {ITEM_BACKED_UP}", "A"), backups)
check("corte justo tras escribir las etiquetas: lo reconoce y sigue", done.state == ITEM_DONE and sha(done.backup_path) == original)
renaming, rnfid = song("no se renombra.mp3"); real_rename = os.rename
def locked_rename(a, b):
    if a.endswith(".copiando.tmp"): return real_rename(a, b)  # el respaldo sí se puede
    raise PermissionError(13, "En uso")
os.rename = locked_rename
try:
    run(rnfid, "Renombrar", "A"); check("nombre bloqueado", False)
except NormalizeError as exc:
    os.rename = real_rename; open_one = db.open_item(rnfid)
    check("no se puede renombrar: queda para retomar", open_one is not None and "nombre" in open_one.error, exc)
os.rename = real_rename
done = run(rnfid, "Renombrar", "A")
check("  al retomar termina, sin otro respaldo", done.state == ITEM_DONE and os.path.isfile(done.new_path) and len([i for i in db.items() if i.file_id == rnfid]) == 1)
check("  y se puede restaurar", normalizer.restore(db, done).state == ITEM_RESTORED and os.path.isfile(renaming))
path, fid, item, original = interrupted(ITEM_BACKED_UP); os.remove(item.backup_path)
try:
    normalizer.normalize(db, op, SongJob(fid, "X", "A"), backups); check("respaldo perdido", False)
except NormalizeError:
    check("si el respaldo se perdió antes de seguir, no toca la canción", sha(path) == original)

print("[Restaurar]")
path, fid = song("Restaurar (Video Oficial).mp3"); original = open(path, "rb").read(); name = os.path.basename(path)
item = run(fid, "Restaurada", "A"); new = item.new_path
restored = normalizer.restore(db, item)
check("vuelve byte a byte, con su nombre", open(path, "rb").read() == original and restored.state == ITEM_RESTORED and not os.path.exists(new))
check("  con su fecha", int(os.path.getmtime(path)) == 1500000000)
check("  el respaldo se conserva", os.path.isfile(item.backup_path) and sha(item.backup_path) == item.backup_sha)
check("  y el análisis apunta a su lugar", db.file_by_id(fid).path == path)
check("restaurar dos veces no rompe nada", normalizer.restore(db, restored).state == ITEM_RESTORED and open(path, "rb").read() == original)
item = run(fid, "Restaurada", "A")
check("se puede normalizar otra vez", item.state == ITEM_DONE and os.path.isfile(item.new_path))
os.remove(item.backup_path)
try:
    normalizer.restore(db, item); check("sin respaldo", False)
except NormalizeError:
    check("sin respaldo no toca nada", os.path.isfile(item.new_path))
p3, f3 = song("Tres.mp3"); i3 = run(f3, "Tres", "A")
intruder = p3; open(intruder, "wb").write(b"otro archivo de la persona")
try:
    normalizer.restore(db, i3); check("hay otro archivo en su lugar", False)
except NormalizeError:
    check("hay otro archivo en su lugar: no lo pisa", open(intruder, "rb").read() == b"otro archivo de la persona" and os.path.isfile(i3.new_path))
os.remove(intruder)
p4, f4 = song("Cuatro.mp3"); i4 = run(f4, "Cuatro", "A"); open(i4.new_path, "wb").write(b"lo cambiaron por otra cosa")
try:
    normalizer.restore(db, i4); check("reemplazada por otra", False)
except NormalizeError:
    check("si ya no es esta canción, no la borra", open(i4.new_path, "rb").read() == b"lo cambiaron por otra cosa")

print("[Por lotes]")
db.save_identifications([(fid, Identification(DECISION_AUTO, "ok", 1.0, "T", "A")), (f3, Identification(DECISION_REVIEW, "duda", 0.5, "", "", candidates=("X - Y",)))])
jobs = normalizer.jobs_from_identifications(db)
check("automáticamente solo las seguras", {j.file_id for j in jobs} == {fid}, jobs)
db.save_identifications([(f3, Identification(DECISION_REVIEW, "duda", 0.5, "Quizás", "Alguien"))])
check("una dudosa solo si la persona la elige", normalizer.jobs_from_identifications(db, [f3]) == [SongJob(f3, "Quizás", "Alguien")])
batch = []
for i in range(6):
    batch.append(song(f"lote {i}.mp3"))
batch_originals = {f: open(p, "rb").read() for p, f in batch}
locked = open(batch[2][0], "rb")
worker = NormalizeWorker([SongJob(f, f"Lote {n}", "A") for n, (_, f) in enumerate(batch)], backups, db_file); got, applied = [], []
worker.finished.connect(got.append); worker.applied.connect(applied.append); worker.run(); locked.close()
result = got[0]
check("una que falla no detiene a las demás", result.done == 5 and len(result.failed) == 1 and batch[2][0] in result.failed[0][0], result)
check("avisa de cada una, para actualizar la biblioteca", len(applied) == 5 and all(i.state == ITEM_DONE for i in applied))
check("  y queda pendiente hasta que la biblioteca se entere", {i.id for i in applied} <= {i.id for i in db.unsynced_items()})
db.mark_library_synced(applied[0].id); check("  se anota al enterarse", applied[0].id not in {i.id for i in db.unsynced_items()})
worker = NormalizeWorker([SongJob(f, f"Lote {n}", "A") for n, (_, f) in enumerate(batch)], backups, db_file); got = []
worker.finished.connect(got.append); worker.cancel(); worker.run()
check("detener: no toca ninguna más", got[0].cancelled and got[0].done == 0)
worker = RestoreWorker(applied, db_file); back = []; worker.finished.connect(back.append); worker.run()
check("restaurar el lote completo", back[0] == [] and all(open(p, "rb").read() == batch_originals[f] for n, (p, f) in enumerate(batch)), back[0])

print("[Base de la versión anterior]")
import sqlite3
old = os.path.join(work, "vieja.db"); c = sqlite3.connect(old)
c.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, path_key TEXT UNIQUE, size INT, mtime_ns INT, status TEXT, problem TEXT)")
c.execute("INSERT INTO files VALUES (1,'a','a',1,1,'nuevo',NULL)"); c.execute("PRAGMA user_version = 2"); c.commit(); c.close()
m = OrganizerDb(old); check("se actualiza conservando los datos", m.counts() == {"nuevo": 1} and m.items() == []); m.close()
db.close()

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
