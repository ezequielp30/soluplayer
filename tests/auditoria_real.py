"""Auditoría de SOLO LECTURA de la biblioteca real del usuario: no modifica nada (la base se abre en modo
solo lectura y los archivos de música solo se leen)."""
import glob, json, os, sqlite3, sys
from collections import Counter

sys.path.insert(0, r"D:\soluplayer")
from app import backup, mp3gain
from app.duplicates import find_duplicates
from app.library_cleanup import plan_missing, relocate_folder
from app.models import Track

data = os.path.join(os.environ["LOCALAPPDATA"], "ReproductorMusica")
db_file = os.path.join(data, "biblioteca.db")
uri = "file:" + __import__("urllib.request").request.pathname2url(db_file) + "?mode=ro"
c = sqlite3.connect(uri, uri=True)

print("== Base de datos")
print("  integridad completa:", c.execute("PRAGMA integrity_check").fetchone()[0])
print("  claves foráneas rotas:", len(c.execute("PRAGMA foreign_key_check").fetchall()))
print("  versión del esquema:", c.execute("PRAGMA user_version").fetchone()[0])
tracks_n = c.execute("select count(*) from tracks").fetchone()[0]
print("  canciones:", tracks_n, "| playlists:", c.execute("select count(*) from playlists").fetchone()[0],
      "| entradas de playlists:", c.execute("select count(*) from playlist_tracks").fetchone()[0])
print("  entradas de playlist sin canción:", c.execute("select count(*) from playlist_tracks where track_id not in (select id from tracks)").fetchone()[0])
print("  carátulas huérfanas:", c.execute("select count(*) from covers where hash not in (select cover_hash from tracks where cover_hash is not null)").fetchone()[0])
print("  rutas repetidas:", c.execute("select count(*) from (select path_key from tracks group by path_key having count(*)>1)").fetchone()[0])

rows = c.execute("select id,path,title,artist,album,genre,duration_ms,added_at,norm_gain_db,loudness_lufs from tracks").fetchall()
tracks = [Track(id=r[0], path=r[1], title=r[2], artist=r[3], album=r[4], genre=r[5], duration_ms=r[6] or 0, added_at=r[7],
                norm_gain_db=r[8] or 0.0, loudness_lufs=r[9]) for r in rows]

print("== Archivos")
exist = [t for t in tracks if os.path.isfile(t.path)]
print("  existen en el disco:", len(exist), "de", len(tracks))
print("  por formato:", dict(Counter(os.path.splitext(t.path)[1].lower() for t in tracks).most_common()))
plan = plan_missing(tracks, set())
print("  limpieza al abrir → se quitarían solas:", len(plan.remove), "| carpetas que preguntaría:",
      {k: len(v) for k, v in plan.missing_folders.items()}, "| discos desconectados:", plan.disconnected)
for folder, ts in plan.missing_folders.items():
    guess = os.path.join(os.path.splitdrive(folder)[0] + os.sep, os.path.basename(folder))
    if os.path.isdir(guess):
        print(f"    «{folder}» está en «{guess}»: se reubicarían {len(relocate_folder(ts, folder, guess))} de {len(ts)}")
for t in plan.remove[:10]:
    print("    se quitaría:", t.path)

print("== Volumen")
adjusted = [t for t in tracks if t.norm_gain_db > 0]
ok = mismatch = unreadable = absent = 0
for t in adjusted:
    if not os.path.isfile(t.path):
        absent += 1
        continue
    try:
        steps = mp3gain.read_applied_steps(t.path)
    except Exception:
        unreadable += 1
        continue
    if steps == round(t.norm_gain_db / mp3gain.STEP_DB):
        ok += 1
    else:
        mismatch += 1
print(f"  ajustadas según la biblioteca: {len(adjusted)} | anotación correcta en el MP3: {ok} | "
      f"sin anotar o distinta: {mismatch} | ilegibles: {unreadable} | archivo ausente: {absent}")
print("  analizadas:", sum(1 for t in tracks if t.loudness_lufs is not None), "de", len(tracks))
print("  más de +12 dB:", sum(1 for t in adjusted if t.norm_gain_db > 12.01))

print("== Repetidas (criterio título y artista)")
groups = find_duplicates(exist)
print("  grupos:", len(groups), "| copias:", sum(len(g.tracks) for g in groups))

print("== Registros de operaciones")
for kind in ("reuniones", "conversiones"):
    files = glob.glob(os.path.join(data, kind, "*.json"))
    states = Counter(json.load(open(f, encoding="utf-8")).get("status") for f in files)
    print(f"  {kind}: {len(files)} {dict(states)}")
    leftovers = glob.glob(os.path.join(data, kind, "*.tmp"))
    if leftovers:
        print("    temporales sueltos:", leftovers)

print("== Respaldos")
bks = backup.list_backups()
print("  cantidad:", len(bks), "| más reciente:", bks[0].name if bks else "—")
bad = [b.name for b in bks if backup.check_database(b) is not None]
print("  respaldos dañados:", bad or "ninguno")
print("  último respaldo válido:", (backup.latest_valid_backup() or "—"))

print("== Registro de errores")
log_file = os.path.join(data, "registro.log")
if os.path.exists(log_file):
    lines = open(log_file, encoding="utf-8", errors="replace").read().splitlines()
    errors = [l for l in lines if " ERROR " in l or "Traceback" in l]
    print("  líneas:", len(lines), "| errores:", len(errors))
    for l in errors[-5:]:
        print("   ", l[:160])
crash = os.path.join(data, "cierres-inesperados.log")
print("  cierres inesperados registrados (bytes):", os.path.getsize(crash) if os.path.exists(crash) else 0)
