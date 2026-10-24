import os, sys, sqlite3, shutil
sys.path.insert(0, r"D:\reproductor-musica")
import numpy as np, lameenc
from app import mp3gain, converter, backup
D = sys.argv[1]
src = os.path.join(D, "..", "t2", "m1s.mp3")
p = os.path.join(D, "v1.mp3"); shutil.copy(src, p)
with open(p, "ab") as f: f.write(b"TAG" + b"titulo".ljust(125, b"\0"))
raw = open(p, "rb").read()
n0 = len(mp3gain._frames(raw))
mp3gain.write_applied_steps(p, 3)
d = open(p, "rb").read()
print("ID3v1 at end after APE save?", d[-128:-125] == b"TAG", "| APE before TAG?", b"APETAGEX" in d[-160:-128])
print("frames before/after annot:", n0, len(mp3gain._frames(d)), "read:", mp3gain.read_applied_steps(p))
mp3gain.apply_steps(p, 3)
mp3gain.write_applied_steps(p, 0)
mp3gain.apply_steps(p, -3)
print("identical after annotate/delete roundtrip:", open(p, "rb").read() == raw)
# check_database con caracteres raros en la ruta
for sub in ["con espacio", "con#almohadilla", "con%20porcentaje", "con?interrog"[:3]+"_x"]:
    dd = os.path.join(D, sub); os.makedirs(dd, exist_ok=True)
    db = os.path.join(dd, "b.db"); c = sqlite3.connect(db); c.execute("create table t(x)"); c.commit(); c.close()
    print(repr(sub), "check_database ->", backup.check_database(db))
# colisión del nombre de MP3 en un mismo plan
from app.models import Track
for n in ("Cancion.wav", "Cancion.flac"): open(os.path.join(D, n), "wb").close()
print("mp3 previstos:", [converter.mp3_path_for(os.path.join(D, n)) for n in ("Cancion.wav", "Cancion.flac")])
