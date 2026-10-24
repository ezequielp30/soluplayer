import os, sys
sys.path.insert(0, r"D:\reproductor-musica")
from app import backup
D = sys.argv[1]
for sub in ["normal", "con#alm"]:
    dd = os.path.join(D, sub); os.makedirs(dd, exist_ok=True)
    db = os.path.join(dd, "b.db"); open(db, "wb").write(b"esto no es sqlite" * 200)
    print(sub, "check_database(archivo basura) ->", backup.check_database(db))
