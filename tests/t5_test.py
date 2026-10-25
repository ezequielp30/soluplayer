import os as _os, tempfile as _tf  # datos y ajustes de prueba aparte: nunca los del usuario
_os.environ["MUSICPLAYER_DATA_DIR"] = _tf.mkdtemp(prefix="mp_t_"); _os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"
import os, sys
sys.path.insert(0, r"D:\reproductor-musica")
from app import converter
from app.database import Database
from app.file_operations import FileOperations
from app.utils import path_key
D = sys.argv[1]
lib = os.path.join(D, "Musica", "Album"); os.makedirs(lib, exist_ok=True)
db = Database(os.path.join(D, "lib.db"))
paths = [os.path.join(lib, "Cancion.wav"), os.path.join(lib, "Cancion.flac")]
for p in paths:
    open(p, "wb").write(b"ORIG-" + os.path.basename(p).encode())
    db.conn.execute("INSERT INTO tracks(path, path_key, title, artist, album, genre, added_at) VALUES (?,?,?,?,?,?,?)",
                    (p, path_key(p), os.path.basename(p), "a", "b", "c", "now"))
db.conn.commit()
class T:  # Track mínimo
    def __init__(self, i, p): self.id, self.path = i, p
tracks = [T(1, paths[0]), T(2, paths[1])]
s = converter.new_session(tracks)
print("mp3 previstos:", [os.path.basename(i.mp3) for i in s.items])
ops = FileOperations(db, lambda ids: None, lambda ids: None, lambda: None, lambda: True)
s.save()
for item in s.items:
    tmp = item.mp3 + ".convirtiendo.tmp"; open(tmp, "wb").write(b"MP3 de " + os.path.basename(item.original).encode())
    os.replace(tmp, item.mp3)  # lo que hace el trabajador
    try:
        ops.record_converted(item, s)
        print("record_converted ok", item.track_id)
    except Exception as e:
        print("record_converted", item.track_id, "->", type(e).__name__, e)
print("contenido Cancion.mp3:", open(s.items[0].mp3, "rb").read())
for r in db.conn.execute("select id, path from tracks"): print("BD:", r[0], os.path.relpath(r[1], D), "existe:", os.path.exists(r[1]))
for item in s.items: print("item", item.track_id, "done", item.done, "moved_to", os.path.relpath(item.moved_to, D) if item.moved_to else "")
