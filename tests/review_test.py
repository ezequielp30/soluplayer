"""Prueba de «Reunir repetidas en una carpeta» y «Devolver a su lugar». Todo en carpetas temporales."""
import math, os, sqlite3, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_review_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QProgressDialog
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE
from app import backup, file_ops, review_folder
from app.config import database_path
from app.database import Database
from app.duplicates import find_duplicates
from app.importer import scan_file
from app.ui import main_window as mw
mw.MainWindow._choose_scope = lambda self, tool: ((lambda: self.library), None)  # primer paso «¿qué analizar?»: toda la biblioteca (se prueba en herramientas_carpeta_test)
from app.ui.duplicates_dialog import DuplicatesDialog
from app.ui.history_dialog import HistoryDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def tone(path, title, artist, secs=3, freq=440):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * freq * i / 8000))) for i in range(8000 * secs)))
    f = WAVE(path); f.add_tags(); f.tags.add(TIT2(encoding=3, text=title)); f.tags.add(TPE1(encoding=3, text=artist)); f.save()
    return path
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)

pending = []
def expect(pred, handler): pending.append((pred, handler))
def pump():
    QTimer.singleShot(40, pump)
    w = QApplication.activeModalWidget()
    if pending and w is not None and w.isVisible() and pending[0][0](w):
        _, h = pending.pop(0)
        try: h(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, pump)
def msg(text): return lambda w: isinstance(w, QMessageBox) and text in (w.text() + w.informativeText())
def click(label):
    def h(box):
        for b in box.buttons():
            if b.text().replace("&", "") == label: b.click(); return
        raise AssertionError(f"{label!r} no está en {[b.text() for b in box.buttons()]}")
    return h

music = os.path.join(work, "Musica")
originals = {
    "a1": tone(os.path.join(music, "Albunes completos", "06. Dios manda lluvia.wav"), "Dios manda lluvia", "Marcos Witt"),
    "a2": tone(os.path.join(music, "Variado", "06. Dios manda lluvia.wav"), "Dios manda lluvia", "Marcos Witt", 3, 445),
    "b1": tone(os.path.join(music, "Raros", "x.wav"), 'Hola: ¿qué? "tal"', "A/B*C"),
    "b2": tone(os.path.join(music, "Raros", "y.wav"), 'Hola: ¿qué? "tal"', "A/B*C", 3, 450),
    "c1": tone(os.path.join(music, "Larga", "l1.wav"), "T" * 200, "Artista"),
    "c2": tone(os.path.join(music, "Larga2", "l2.wav"), "T" * 200, "Artista", 3, 455),
    "solo": tone(os.path.join(music, "Variado", "unica.wav"), "Única", "Nadie"),
}
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in originals.values()])
win = mw.MainWindow(db); win.show(); spin(200)
lib = {os.path.basename(os.path.dirname(t.path)) + "/" + os.path.basename(t.path): t for t in win.library}
pl = db.create_playlist("Favoritas")
db.add_to_playlist(pl.id, [lib["Albunes completos/06. Dios manda lluvia.wav"].id, lib["Variado/unica.wav"].id])
dest_root = os.path.join(music, review_folder.REVIEW_FOLDER_NAME)

print("\n[1. Ventana de repetidas: calidad y botón]")
dd = {}
def dialog(d):
    try:
        dd["quality"] = d.tree.topLevelItem(0).child(0).toolTip(4)  # columna Calidad: el detalle va en el tooltip
        dd["btn"] = d.btn_gather.isVisible() and d.btn_gather.isEnabled()
        dd["groups"] = len(d._groups)
        # Reproducir una copia para comprobar que se suelta antes de moverla
        playing = next(t for g in d._groups for t in g.tracks if t.path == originals["a1"])
        win._on_play_requested([playing], 0); spin(400); dd["playing_before"] = win.player.is_playing
        expect(msg("Se moverán las copias"), click("Continuar"))
        expect(msg("¿Mover"), click("Mover"))
        expect(msg("Se movieron"), lambda b: (dd.setdefault("summary", b.text() + " | " + b.informativeText()), click("Cerrar")(b)))
        d.btn_gather.click(); spin(300)
        dd["after"] = d.summary.text()
    finally:
        d.accept(); dd["done"] = True
expect(lambda w: isinstance(w, DuplicatesDialog), dialog)
win._open_duplicates(); spin(300)
check("Columna «Calidad» con kbps y frecuencia", "kbps" in dd.get("quality", "") and "kHz" in dd.get("quality", ""), dd.get("quality"))
check("  botón «Reunir en una carpeta para revisar…»", dd.get("btn"))
check("  3 canciones repetidas detectadas", dd.get("groups") == 3, dd.get("groups"))

print("\n[2. Reunir]")
check("Mensaje final con lo hecho", "Se movieron 6 archivos a 3 carpetas" in dd.get("summary", ""), dd.get("summary", "")[:120])
check("  los originales ya no están en su sitio", not any(os.path.exists(originals[k]) for k in ("a1", "a2", "b1", "b2", "c1", "c2")))
check("  la canción única no se tocó", os.path.exists(originals["solo"]))
sub = os.path.join(dest_root, "Dios manda lluvia - Marcos Witt")
files = sorted(os.listdir(sub)) if os.path.isdir(sub) else []
check("  subcarpeta con el nombre de la canción", os.path.isdir(sub), files)
check("  cada copia numerada y con su carpeta de origen", files[:2] == ["1 - 06. Dios manda lluvia (de «Albunes completos»).wav", "2 - 06. Dios manda lluvia (de «Variado»).wav"], files)
readme = open(os.path.join(sub, "LEEME.txt"), encoding="utf-8-sig").read() if "LEEME.txt" in files else ""
check("  LEEME.txt con origen, tamaño y calidad", "Origen:" in readme and "kbps" in readme and "sugerida para conservar" in readme, readme[:160].replace("\n", " | "))
raw = open(os.path.join(sub, "LEEME.txt"), "rb").read(3) if readme else b""
check("  LEEME.txt legible en el Bloc de notas (UTF-8 con BOM)", raw == b"\xef\xbb\xbf")
odd = [d for d in os.listdir(dest_root) if d.startswith("Hola")]
check("  nombres con caracteres prohibidos se limpian", odd and not any(c in odd[0] for c in ':?"/*'), odd)
longest = max(len(os.path.join(r, f)) for r, _, fs in os.walk(dest_root) for f in fs)
check("  rutas largas recortadas (≤ 260)", longest <= 260, longest)
win._reload_library()
paths = {t.path for t in win.library}
check("  la biblioteca apunta a las rutas nuevas", all(os.path.exists(p) for p in paths) and any(review_folder.REVIEW_FOLDER_NAME in p for p in paths))
pt = db.playlist_tracks(pl.id)
check("  la playlist conserva sus 2 canciones (con la ruta nueva)", len(pt) == 2 and any(review_folder.REVIEW_FOLDER_NAME in t.path for t in pt) and all(t.available for t in pt))
check("  la canción que sonaba se soltó y se movió", dd.get("playing_before") and not win.player.is_playing)
check("  respaldo antes de reunir", any("antes-de-reunir-repetidas" in f.name for f in backup.list_backups()))
check("  la carpeta aparece en la barra lateral", any(i.text(0).startswith(review_folder.REVIEW_FOLDER_NAME) for i in win.sidebar._folder_items()))
s = review_folder.list_sessions()
check("  registro de la reunión «completada» con 6 movimientos", s and s[0].status == "completada" and len(s[0].moves) == 6)

print("\n[3. Devolver a su lugar desde el Historial]")
hist = {}
def history_handler(d):
    try:
        e = d._selected()
        hist["selected"] = (e.title, e.status, e.count) if e else None
        hist["button"] = d.btn_undo.text()
        expect(msg("¿Devolver 6 archivos"), click("Deshacer"))
        expect(msg("Se devolvieron"), lambda b: (dd.setdefault("undo", b.text()), b.accept()))
        d.btn_undo.click(); spin(200)
        hist["after"] = [(e.title, e.status) for e in d._entries]
        hist["enabled_after"] = d.btn_undo.isEnabled()
    finally:
        d.accept(); hist["done"] = True
expect(lambda w: isinstance(w, HistoryDialog), history_handler)
next(a for a in win.findChildren(mw.QAction) if a.text().startswith("&Historial")).trigger(); spin(300)
check("Herramientas → Historial: la reunión aparece seleccionada", hist.get("selected") == ("Reunir repetidas para revisar", "Hecha", 6), hist.get("selected"))
check("  «Deshacer» devuelve los archivos", "Se devolvieron 6 archivos" in dd.get("undo", ""), dd.get("undo"))
check("  el historial la muestra como deshecha y ya no se puede deshacer otra vez",
      hist.get("after", [None])[0] == ("Reunir repetidas para revisar", "Deshecha") and not hist.get("enabled_after"), hist.get("after"))
check("  todos vuelven a su carpeta original", all(os.path.exists(p) for p in originals.values()))
check("  la carpeta de revisión se eliminó (estaba vacía)", not os.path.exists(dest_root))
check("  la biblioteca vuelve a las rutas originales", {t.path for t in win.library} == {os.path.abspath(p) for p in originals.values()})
check("  la playlist sigue intacta", len(db.playlist_tracks(pl.id)) == 2 and all(t.available for t in db.playlist_tracks(pl.id)))
check("  registro marcado «deshecha»", review_folder.list_sessions()[0].status == "deshecha")
check("  no queda nada pendiente de devolver", not [e for e in win.ops.history(win.library) if e.can_undo and e.kind == "reunion"])

print("\n[4. Situaciones difíciles]")
groups = find_duplicates(win.library)
# Archivo bloqueado por otro programa
real_rename = os.rename
def flaky(src, dst):
    if src.endswith("x.wav"): raise PermissionError(13, "en uso")
    real_rename(src, dst)
review_folder.os.rename = flaky
session, skipped = review_folder.plan_moves(groups, dest_root)
session, failed = review_folder.execute(session, groups)
review_folder.os.rename = real_rename
check("Archivo abierto en otro programa: se omite con motivo y el resto se mueve",
      len(failed) == 1 and "otro programa" in failed[0].reason and len(session.moves) == 5 and os.path.exists(originals["b1"]))
review_folder.undo(session)
check("  y se puede deshacer", all(os.path.exists(p) for p in originals.values()))

# Cierre inesperado a mitad
session, _ = review_folder.plan_moves(groups, dest_root)
session.save()
for m in session.moves[:3]:
    os.makedirs(os.path.dirname(m.target), exist_ok=True); os.rename(m.source, m.target); m.done = True; session.save()
expect(msg("se interrumpió"), click("Deshacerla ahora"))
expect(msg("Se devolvieron"), lambda b: b.accept())
win.check_interrupted_review(); spin(200)
check("Cierre inesperado a mitad: al abrir ofrece devolver y lo hace", all(os.path.exists(p) for p in originals.values()) and not review_folder.interrupted_sessions())

# Unidad de red
orig_type = file_ops._drive_type
file_ops._drive_type = lambda _p: 4
session, skipped = review_folder.plan_moves(groups, dest_root)
file_ops._drive_type = orig_type
check("Destino en unidad de red: no se mueve nada", not session.moves and skipped and "disco local" in skipped[0].reason)

# Otro disco
session, skipped = review_folder.plan_moves(groups, r"D:\_prueba_no_se_crea\Repetidas")
check("Destino en otro disco: no se mueve nada", not session.moves and "mismo disco" in skipped[0].reason, skipped[:1])

# Fallo al actualizar la biblioteca: se devuelve todo
orig_update = Database.update_track_paths
Database.update_track_paths = lambda self, ch: (_ for _ in ()).throw(sqlite3.OperationalError("disco lleno (simulado)"))
expect(msg("Se moverán las copias"), click("Continuar"))
expect(msg("¿Mover"), click("Mover"))
expect(msg("No se pudo actualizar la biblioteca"), lambda b: b.accept())
win._gather_for_review(groups); spin(200)
Database.update_track_paths = orig_update
check("Si falla la biblioteca tras mover, se devuelven los archivos", all(os.path.exists(p) for p in originals.values()) and not os.path.exists(dest_root))

check("todos los diálogos esperados aparecieron", not pending, pending)
win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
os._exit(0 if all(results) and not errors else 1)
