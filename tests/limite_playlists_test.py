"""1.12.6: nombres de playlist de 30 caracteres como máximo (sin recortar las que ya existían).
Todo en carpetas temporales."""
import os, sys, tempfile
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_lim_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import playlist_files as pf
from app.config import database_path
from app.database import Database, PlaylistNameError
from app.ui.dialogs import PlaylistNameDialog

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)

db = Database(database_path())
treinta = "Alabanza y adoración del domin"  # 30 caracteres
check("(la prueba usa un nombre de 30 caracteres)", len(treinta) == 30, len(treinta))
try:
    db.create_playlist(treinta); ok30 = True
except PlaylistNameError:
    ok30 = False
check("se acepta un nombre de 30 caracteres", ok30)
try:
    db.create_playlist(treinta + "g"); msg = ""
except PlaylistNameError as exc:
    msg = str(exc)
check("uno de 31 se rechaza con un mensaje claro", "30 caracteres" in msg, msg or "se aceptó")

print("[Las playlists que ya tenían un nombre más largo no se tocan]")
long_name = "Canciones para el retiro de jóvenes de verano"
with db.conn:
    from app.utils import normalize_text  # como la guardaba la versión anterior (límite de 80)
    db.conn.execute("INSERT INTO playlists (name, name_key, created_at) VALUES (?, ?, '2026-01-01')", (long_name, normalize_text(long_name)))
check("siguen apareciendo con su nombre completo", long_name in [p.name for p in db.playlists()])

print("[El cuadro de nombre]")
dialog = PlaylistNameDialog("Nueva playlist", "Nombre:", "", lambda t: t)
dialog.edit.setText("x" * 50)
check("no deja escribir más de 30 caracteres", len(dialog.edit.text()) == 30, len(dialog.edit.text()))
rename = PlaylistNameDialog("Renombrar playlist", "Nombre:", long_name, lambda t: t)
check("  al renombrar una que ya tenía un nombre largo, aparece completo (no se recorta sin avisar)",
      rename.edit.text() == long_name and rename.edit.hasSelectedText(), rename.edit.text())

print("[Restaurar una copia con un nombre largo]")
folder = os.path.join(work, "copia"); os.makedirs(folder)
open(os.path.join(folder, "largo.m3u8"), "w", encoding="utf-8").write("#EXTM3U\n#PLAYLIST:Música para la vigilia de oración de los viernes\n")
out = pf.apply_restore(db, pf.plan_restore(pf.read_folder(folder), db.all_tracks()))
check("se restaura con el nombre acortado a 30", out.created and len(out.created[0]) <= 30 and not out.failed, (out.created, out.failed))

print("[Restaurar la copia de una playlist que ya tenía un nombre largo]")
copia = os.path.join(work, "copia-larga")
pf.export_all(db, copia)
before = sorted(p.name for p in db.playlists())
out2 = pf.apply_restore(db, pf.plan_restore(pf.read_folder(copia), db.all_tracks()))
check("no se duplica con el nombre recortado (ya estaba igual)", sorted(p.name for p in db.playlists()) == before and long_name in out2.unchanged,
      (out2.created, out2.unchanged))

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
db.close()
sys.exit(0 if all(results) else 1)
