import os as _os, tempfile as _tf  # datos y ajustes de prueba aparte: nunca los del usuario
_os.environ["MUSICPLAYER_DATA_DIR"] = _tf.mkdtemp(prefix="mp_t_"); _os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"
import os, sys, math, tempfile
sys.path.insert(0, r"D:\soluplayer")
from PySide6.QtCore import QCoreApplication, QFile
app = QCoreApplication([])
from app import mp3gain, converter, backup
from app.loudness_job import AnalyzeWorker
print("crc check 123456789:", hex(mp3gain._crc16(b"123456789")), "(CRC-16/CMS esperado 0xaee7)")
print("moveToTrash nonexistent ->", repr(QFile.moveToTrash(r"C:\no\existe\zz.mp3")))
w = AnalyzeWorker([])
try:
    w.measured.emit(1, None, None, "x")
    print("emit 4 args OK")
except Exception as e:
    print("emit 4 args ->", type(e).__name__, e)
