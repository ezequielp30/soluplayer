"""Prueba de las reparaciones de integridad (todo en carpetas temporales; nunca toca la biblioteca real)."""
import logging, os, shutil, sqlite3, sys, tempfile, time, traceback, wave
from datetime import datetime, timedelta
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_repair_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")

from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup, error_log, file_ops
from app import database as dbmod
from app.config import data_dir, database_path
from app.database import Database
from app.importer import ImportFailure, scan_file
from app.metadata import read_metadata

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def wav(path, secs=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(2000); w.writeframes(b"\x80" * 2000 * secs)
    return path
def spin(ms):
    end = time.time() + ms/1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)

check("Datos de prueba fuera de la biblioteca real", "mp_repair_" in str(data_dir()), data_dir())
log_file = error_log.setup()

print("\n[1. Respaldos]")
db = Database(database_path())
m = os.path.join(work, "m")
db.add_tracks([scan_file(wav(os.path.join(m, f"t{i}.wav")))[0] for i in range(3)])
p = backup.create_backup(db.conn, "manual")
check("Crear respaldo", p is not None and p.exists(), p)
check("  el respaldo pasa la verificación y tiene los datos", backup.check_database(p) is None
      and sqlite3.connect(p).execute("select count(*) from tracks").fetchone()[0] == 3)
check("  respaldo diario no se repite antes de 24 h", backup.backup_if_due(db.conn) is None)
for f in backup.list_backups(): f.unlink()
check("  sin respaldos previos → se crea el diario", backup.backup_if_due(db.conn) is not None)
# Retención: 30 respaldos falsos a lo largo de 60 días
for f in backup.list_backups(): f.unlink()
now = datetime.now()
for d in range(30):
    t = now - timedelta(days=d * 2)
    shutil.copy(database_path(), backup.backup_dir() / f"biblioteca-{t.strftime('%Y%m%d-%H%M%S')}-diario.db")
src = backup.create_backup(db.conn, "manual")
removed = backup.prune()
kept = backup.list_backups()
check("  retención: 10 recientes + 1 por semana (≤ 15)", 10 < len(kept) <= 15, f"quedan {len(kept)}, borrados {len(removed)}")
oldest = min(backup._taken_at(k) for k in kept if backup._taken_at(k))
check("  no guarda más de ~5 semanas", (now - oldest).days <= 36, f"{(now - oldest).days} días")

print("\n[2. Revisión al arrancar y restauración]")
broken_dir = os.path.join(work, "roto"); os.makedirs(broken_dir)
broken = os.path.join(broken_dir, "biblioteca.db")
c = sqlite3.connect(broken); c.execute("create table t(x)"); c.executemany("insert into t values (?)", [("x" * 500,)] * 400); c.commit(); c.close()
with open(broken, "r+b") as fh:
    fh.seek(4096 * 2); fh.write(b"\xff" * 4096)
problem = backup.check_database(broken)
check("Detecta una base dañada", problem is not None, problem)
check("  y una sana como sana", backup.check_database(database_path()) is None)
good = backup.latest_valid_backup()
from pathlib import Path
aside = backup.restore(good, Path(broken))
check("  restaurar: la dañada se aparta (no se borra)", aside.exists() and "danada" in aside.name, aside.name)
check("  la restaurada está sana", backup.check_database(broken) is None)

print("\n[3. Migración atómica + respaldo previo]")
mig = os.path.join(work, "mig.db")
orig_schema, orig_ver = dbmod._SCHEMA, dbmod.SCHEMA_VERSION
dbmod._SCHEMA = orig_schema + ";\nCREATE TABLE tracks_roto (x INT REFERENCES; "  # sentencia inválida al final
try:
    Database(mig); check("Migración con error debe fallar", False)
except sqlite3.Error:
    c = sqlite3.connect(mig)
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    ver = c.execute("pragma user_version").fetchone()[0]; c.close()
    check("Migración que falla a mitad: no deja nada a medias", tables == [] and ver == 0, (tables, ver))
dbmod._SCHEMA = orig_schema
d2 = Database(mig); d2.close()
before = len(backup.list_backups())
dbmod.SCHEMA_VERSION = orig_ver + 1
dbmod._MIGRATIONS[orig_ver + 1] = ["CREATE TABLE IF NOT EXISTS extra (x)"]
d2 = Database(mig)
check("Actualizar una base existente crea respaldo antes", any(f"antes-de-actualizar-v{orig_ver}" in f.name for f in backup.list_backups()))
check("  y queda en la versión nueva", d2.conn.execute("pragma user_version").fetchone()[0] == orig_ver + 1)
d2.close(); dbmod._SCHEMA, dbmod.SCHEMA_VERSION = orig_schema, orig_ver; del dbmod._MIGRATIONS[orig_ver + 1]

print("\n[4. Operaciones de una sola vez]")
tracks = db.all_tracks()
pl = db.create_playlist("P"); db.add_to_playlist(pl.id, [tracks[1].id, tracks[2].id])
orig_delete = Database._delete_tracks
Database._delete_tracks = lambda self, ids: (_ for _ in ()).throw(sqlite3.OperationalError("disco lleno (simulado)"))
try:
    db.merge_duplicate_groups([(tracks[0].id, [tracks[1].id, tracks[2].id])])
except sqlite3.OperationalError:
    pass
Database._delete_tracks = orig_delete
pt = [t.id for t in db.playlist_tracks(pl.id)]
check("Fusionar repetidas que falla a mitad: playlists y biblioteca intactas", pt == [tracks[1].id, tracks[2].id] and len(db.all_tracks()) == 3, pt)
n = db.merge_duplicate_groups([(tracks[0].id, [tracks[1].id]), (tracks[0].id, [tracks[2].id])])
pt = [t.id for t in db.playlist_tracks(pl.id)]
check("  varios grupos juntos: quita 2 y la playlist usa la conservada una vez", n == 2 and pt == [tracks[0].id], (n, pt))

t0 = db.all_tracks()[0]
orig_store = Database._store_cover
calls = {"n": 0}
def flaky(self, d, data):
    calls["n"] += 1
    if calls["n"] == 2: raise sqlite3.OperationalError("fallo simulado")
Database._store_cover = flaky
db.add_tracks([scan_file(wav(os.path.join(m, "t9.wav")))[0]]) if False else None
two = db.all_tracks()
try:
    db.update_tracks_info([(two[0].id, "A1", "B", "C", None, None), (two[0].id, "A2", "B", "C", None, None)])
except sqlite3.OperationalError:
    pass
Database._store_cover = orig_store
check("«Datos en internet» en lote que falla: no queda la mitad aplicada", db.all_tracks()[0].title == two[0].title, db.all_tracks()[0].title)

print("\n[5. Relocalizar conserva tus correcciones]")
tr = db.all_tracks()[0]
db.update_track_info(tr.id, "Título corregido", "Artista corregido", "Álbum corregido")
newp = wav(os.path.join(work, "movida", "otro.wav"), 5)
scanned, _ = scan_file(newp)
db.relocate_track(tr.id, scanned.path, scanned.metadata, scanned.cover_hash, scanned.cover_bytes)
after = next(t for t in db.all_tracks() if t.id == tr.id)
check("Relocalizar conserva título/artista/álbum corregidos", (after.title, after.artist, after.album) == ("Título corregido", "Artista corregido", "Álbum corregido"))
check("  y toma la nueva ruta y duración", after.path == scanned.path and after.duration_ms == 5000, (after.path, after.duration_ms))

print("\n[6. Papelera segura]")
check("Disco local D: permitido", file_ops.trash_block_reason(r"D:\soluplayer\main.py") is None)
check("Carpeta de red bloqueada", "red" in (file_ops.trash_block_reason(r"\\servidor\musica\a.mp3") or ""))
orig_type = file_ops._drive_type
for code, word in ((4, "red"), (2, "extraíble"), (5, "CD")):
    file_ops._drive_type = lambda _p, c=code: c
    check(f"  tipo de unidad {code} bloqueado", word in (file_ops.trash_block_reason(r"Y:\a.mp3") or ""))
victim = wav(os.path.join(work, "victima.wav"))
file_ops._drive_type = lambda _p: 4
moved, failed = file_ops.move_to_trash([victim])
file_ops._drive_type = orig_type
check("  en unidad de red NO se manda a la Papelera y el archivo sigue", not moved and os.path.exists(victim) and "para siempre" in failed[0][1])

from app.ui import main_window as mw
from app.ui.dialogs import ImportReportDialog
win = mw.MainWindow(db); win.show(); spin(150)
real = wav(os.path.join(work, "dup", "original.wav"))
alias = os.path.join(work, "dup", "enlace_al_mismo.wav"); os.link(real, alias)  # mismo archivo, otra ruta
db.add_tracks([scan_file(real)[0], scan_file(alias)[0]]); win._reload_library()
keep = next(t for t in win.library if t.path.endswith("original.wav")); other = next(t for t in win.library if t.path.endswith("enlace_al_mismo.wav"))
msg = win._apply_duplicates_plan([(keep.id, [other])], trash=True)
check("Mismo archivo con dos rutas: no se manda a la Papelera la única copia", os.path.exists(real) and os.path.exists(alias), msg[:80])
check("  pero la entrada repetida sí se quita de la biblioteca", all(t.id != other.id for t in win.library))
check("  y se hizo respaldo antes de fusionar", any("antes-de-repetidas" in f.name for f in backup.list_backups()))

dlg = ImportReportDialog(0, [], [ImportFailure("x.mp3", "dañado", corrupt=True)], 0, False, win)
check("Informe: archivos dañados SIN marcar por defecto", dlg._corrupt_items[0].checkState(0) == Qt.CheckState.Unchecked and not dlg.trash_button.isEnabled(), dlg.trash_button.text())
dlg.close()

print("\n[7. Registro de errores]")
notes = []
error_log.install_excepthook(lambda s: notes.append(s))
QTimer.singleShot(0, lambda: 1 / 0)  # error dentro de un slot de Qt
spin(300)
for h in logging.getLogger().handlers: h.flush()
text = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
check("Error en un slot de Qt queda en registro.log", "ZeroDivisionError" in text and "Traceback" in text, log_file)
check("  y se avisa al usuario", notes and "ZeroDivisionError" in notes[0], notes)
check("  los respaldos también se registran", "Respaldo creado" in text)
sys.excepthook = sys.__excepthook__

win.close(); db.close()
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
os._exit(0 if all(results) and not errors else 1)
