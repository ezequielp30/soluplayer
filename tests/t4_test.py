import os as _os, tempfile as _tf  # datos y ajustes de prueba aparte: nunca los del usuario
_os.environ["MUSICPLAYER_DATA_DIR"] = _tf.mkdtemp(prefix="mp_t_"); _os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"
import os, sys
sys.path.insert(0, r"D:\soluplayer")
from app import backup
D = sys.argv[1]
for sub in ["normal", "con#alm"]:
    dd = os.path.join(D, sub); os.makedirs(dd, exist_ok=True)
    db = os.path.join(dd, "b.db"); open(db, "wb").write(b"esto no es sqlite" * 200)
    print(sub, "check_database(archivo basura) ->", backup.check_database(db))
