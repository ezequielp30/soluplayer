"""Organizador, fase 6: la ventana de punta a punta dentro del programa, con AcoustID simulado. Analizar no cambia nada;
normalizar, pendientes y restaurar mantienen la biblioteca y las playlists. Todo en carpetas temporales."""
import hashlib, json, os, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_ventana_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.id3 import ID3, TALB
import audio_sintetico as synth
from app import acoustid_lookup, fingerprint, organizer_db
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.organizer import PENDING_FOLDER
from app.ui import main_window as mw, organizer_dialog as od

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

music = os.path.join(work, "Musica"); os.makedirs(music)
def song(name, title, artist, seed):
    path = synth.mp3(os.path.join(music, name), 5, title=title, artist=artist, seed=seed)
    tags = ID3(path); tags.add(TALB(encoding=3, text=["Disco"])); tags.save(path, v2_version=3)
    return path
safe = song("01 - Santo (Video Oficial).mp3", "Santo (Video Oficial)", "canal1", 1)
doubt = song("Rara.mp3", "Algo Raro", "canal2", 2)
none = song("Ninguna.mp3", "Otra Cosa", "canal3", 3)
outside_folder = os.path.join(work, "Fuera"); os.makedirs(outside_folder)
outside = synth.mp3(os.path.join(outside_folder, "Fuera.mp3"), 5, title="Fuera", artist="canal4", seed=4)
broken = os.path.join(music, "Rota.mp3"); open(broken, "wb").write(b"esto no es audio" * 200)
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in (safe, doubt, none)])
playlist = db.create_playlist("Domingo"); db.add_to_playlist(playlist.id, [db.track_id_for_path(safe), db.track_id_for_path(doubt)])
originals = {p: sha(p) for p in (safe, doubt, none, outside, broken)}

# AcoustID simulado, según la huella real que dé fpcalc a cada archivo.
def answer(title, artist, score=1.0, duration=5):
    return json.dumps({"status": "ok", "results": [{"id": "a", "score": score, "recordings": [{"id": "r", "title": title, "duration": duration, "artists": [{"name": artist}]}]}]})
replies = {}; calls = []
def fake_lookup(key, duration, value):
    calls.append(value)
    return replies.get(value, '{"status": "ok", "results": []}')
acoustid_lookup.lookup_raw = fake_lookup
check("  (fpcalc disponible)", fingerprint.available())
replies[fingerprint.compute(safe).value] = answer("Santo", "New Wine ")
replies[fingerprint.compute(doubt).value] = answer("Otra Cancion Distinta", "Otro Grupo", score=0.6)

# Lo que aparece en pantalla se responde solo.
answers = {"¿Normalizar": "Normalizar", "¿Restaurar": "Restaurar"}; shown = []
def fake_ask(parent, title, text, buttons, *a, **k):
    shown.append(text)
    for start, label in answers.items():
        if text.startswith(start):
            return [b[0] for b in buttons].index(label)
    return -1
od.ask = fake_ask
QMessageBox.information = staticmethod(lambda p, t, text, *a: shown.append(text))
QMessageBox.warning = staticmethod(lambda p, t, text, *a: shown.append(text))
key_dialogs = []
class FakeKeyDialog:
    def __init__(self, prefs, parent=None): self.prefs = prefs; key_dialogs.append(self)
    def exec(self):
        if keys_to_enter: self.prefs.acoustid_key = keys_to_enter.pop(0)
keys_to_enter = []
od.AcoustIdKeyDialog = FakeKeyDialog
win = mw.MainWindow(db); win.show(); spin(200); win._reload_library()
win.prefs.organizer_backup_folder = os.path.join(work, "Respaldos")  # nunca en la raíz del disco de verdad

def open_dialog(roots=None):
    d = od.OrganizerDialog(win.ops, win.prefs, roots if roots is not None else od.default_roots([t.path for t in win.library]), win)
    d.show(); spin(50); return d
idle = lambda d: not d.runner.busy
def wait(d, ms=60000):
    spin(100); spin(ms, lambda: idle(d)); spin(100)
def row_of(d, name):
    return next(r for r in d.model.rows() if os.path.basename(r.path) == name)

print("[Rutas]")
from app.utils import path_key
kept = os.path.join(music, "Clave.mp3"); open(kept, "wb").write(b"x"); key = path_key(kept); os.remove(kept)
check("la clave de una ruta no cambia aunque el archivo ya no exista", path_key(kept) == key, (key, path_key(kept)))

print("[Abrir]")
check("carpetas de partida: las de la biblioteca", od.default_roots([os.path.join("D:\\a", "1.mp3"), os.path.join("D:\\a", "b", "2.mp3"), os.path.join("D:\\c", "3.mp3")]) == ["D:\\a", "D:\\c"])
d = open_dialog()
check("sin analizar no hay nada que normalizar", not d.btn_normalize_selected.isEnabled() and not d.btn_normalize_all.isEnabled())
check("el menú abre el organizador", od.OrganizerDialog.__name__ == "OrganizerDialog" and d.windowTitle() == "Título y quién la canta")

print("[Sin clave]")
check("  (sin clave)", not win.prefs.acoustid_key)
d.btn_analyze.click(); wait(d)
check("pide la clave", len(key_dialogs) == 1)
check("analiza igual, con propuestas por el título", row_of(d, "Rara.mp3").decision == "sin_huella" and row_of(d, "Rara.mp3").title, d.status.text())
check("sin clave no consulta nada", not calls)
check("  y ninguna se da por segura", not d.btn_normalize_all.isEnabled() and "Sin clave" in d.status.text(), d.status.text())
check("analizar no cambia ningún archivo", all(sha(p) == h for p, h in originals.items()))
check("los archivos dañados se ven, y no se pueden marcar", row_of(d, "Rota.mp3").damaged and "dañad" in row_of(d, "Rota.mp3").reason, row_of(d, "Rota.mp3").reason)

print("[Con clave]")
keys_to_enter.append("clave-buena"); win.prefs.acoustid_key = "clave-buena"
d.btn_analyze.click(); wait(d)
check("identifica por huella", row_of(d, "01 - Santo (Video Oficial).mp3").decision == "automatica" and row_of(d, "01 - Santo (Video Oficial).mp3").title == "Santo", d.status.text())
check("una coincidencia floja queda dudosa, y sin título inventado", row_of(d, "Rara.mp3").decision == "revisar" and not row_of(d, "Rara.mp3").title and "60%" in row_of(d, "Rara.mp3").reason)
check("sin coincidencia, también", row_of(d, "Ninguna.mp3").decision == "revisar")
check("analizar sigue sin cambiar nada", all(sha(p) == h for p, h in originals.items()))
check("resumen en pantalla", "4 canciones" in d.summary.text() and "1 seguras" in d.summary.text() and "2 dudosas" in d.summary.text(), d.summary.text())
count_before = len(calls); d.btn_analyze.click(); wait(d)
check("analizar otra vez no repite nada", len(calls) == count_before)

print("[Tabla]")
m = d.model
d.filter_combo.setCurrentIndex(1); check("filtrar seguras", [r.decision for r in m.visible()] == ["automatica"])
d.filter_combo.setCurrentIndex(4); check("filtrar dañadas", [os.path.basename(r.path) for r in m.visible()] == ["Rota.mp3"])
check("  una dañada no se puede marcar ni editar", not (m.flags(m.index(0, od.COL_NOW)) & Qt.ItemFlag.ItemIsUserCheckable) and not (m.flags(m.index(0, od.COL_TITLE)) & Qt.ItemFlag.ItemIsEditable))
d.filter_combo.setCurrentIndex(0)
check("muestra confianza y estado", m.data(m.index(next(i for i, r in enumerate(m.visible()) if r.decision == "automatica"), od.COL_SCORE)) == "100%")
m.check_visible(True); check("marcar las visibles, sin las dañadas", not row_of(d, "Rota.mp3").checked and row_of(d, "Rara.mp3").checked)
m.check_visible(False); check("desmarcar", not any(r.checked for r in m.rows()))
index = next(i for i, r in enumerate(m.visible()) if os.path.basename(r.path) == "Ninguna.mp3")
m.setData(m.index(index, od.COL_TITLE), " Escrita A Mano "); m.setData(m.index(index, od.COL_ARTIST), "Quien Sea"); m.setData(m.index(index, od.COL_NOW), Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)
check("se puede corregir y marcar a mano", row_of(d, "Ninguna.mp3").title == "Escrita A Mano" and row_of(d, "Ninguna.mp3").checked and d.btn_normalize_selected.isEnabled())

print("[Normalizar selección]")
shown.clear(); d.btn_normalize_selected.click(); wait(d)
final = os.path.join(music, "Escrita A Mano - Quien Sea.mp3")
check("avisa antes qué va a pasar", shown and shown[0].startswith("¿Normalizar 1"), shown[:1])
check("queda normalizada", os.path.isfile(final) and not os.path.exists(none) and str(ID3(final)["TIT2"]) == "Escrita A Mano", d.status.text())
tracks = {t.path: t for t in db.all_tracks()}
check("la biblioteca se entera", final in tracks and none not in tracks and tracks[final].title == "Escrita A Mano" and tracks[final].artist == "Quien Sea", list(tracks)[:3])
check("no toca las demás", sha(safe) == originals[safe] and sha(doubt) == originals[doubt])
check("aparece en Historial", d.history_model.rowCount() == 1)

print("[Normalizar todas las seguras]")
track_id = db.track_id_for_path(safe); shown.clear(); d.btn_normalize_all.click(); wait(d); spin(100, lambda: False); wait(d)
final_safe = os.path.join(music, "Santo - New Wine.mp3")
check("normaliza las seguras", os.path.isfile(final_safe) and str(ID3(final_safe)["TPE1"]) == "New Wine", d.status.text())
check("no cuenta otra vez la que ya se normalizó", shown[0].startswith("¿Normalizar 1 "), shown[:1])
pending_path = os.path.join(music, PENDING_FOLDER, "Rara.mp3")
check("las dudosas van a pendientes, sin cambios", os.path.isfile(pending_path) and sha(pending_path) == originals[doubt] and not os.path.exists(doubt), d.status.text())
check("no toca otras carpetas", db.track_id_for_path(outside) is None and sha(outside) == originals[outside])
check("la dañada se queda donde está", sha(broken) == originals[broken])
tracks = {t.path: t for t in db.all_tracks()}
check("la biblioteca sigue a las movidas", pending_path in tracks and final_safe in tracks)
check("  conserva el id y las playlists", tracks[final_safe].id == track_id and len(db.playlist_tracks(playlist.id)) == 2)
check("  la canción movida sigue sonando desde su lugar nuevo", tracks[pending_path].check_available())
check("la pestaña Pendientes la muestra con su motivo", d.pending_model.rowCount() == 1 and "60%" in d.pending_model.data(d.pending_model.index(0, 2)) and "Pendientes (1)" == d.tabs.tabText(1), d.tabs.tabText(1))
check("  y las posibles coincidencias", "Otra Cancion Distinta" in d.pending_model.data(d.pending_model.index(0, 3)))
check("ya no sale en Resultados", not any(os.path.basename(r.path) == "Rara.mp3" for r in d.model.rows()))

print("[Pendientes]")
replies[fingerprint.compute(pending_path).value] = answer("Ahora Si", "Grupo Bueno")
d.pending.selectRow(0); d.btn_retry_selected.click(); wait(d)
check_db = organizer_db.OrganizerDb(); check("reintentar: vuelve a preguntar", check_db.identification(d._pending_rows[0].file_id).title == "Ahora Si", d.status.text()); check_db.close()
check("  el motivo se actualiza", "100%" in d.pending_model.data(d.pending_model.index(0, 2)), d.pending_model.data(d.pending_model.index(0, 2)))
d.btn_resolve.click(); wait(d)
back = os.path.join(music, "Ahora Si - Grupo Bueno.mp3")
check("procesar: normalizada y de vuelta en su carpeta", os.path.isfile(back) and not os.path.exists(pending_path), d.status.text())
check("la carpeta de pendientes vacía se quita", not os.path.exists(os.path.join(music, PENDING_FOLDER)))
tracks = {t.path: t for t in db.all_tracks()}
check("la biblioteca lo sigue", back in tracks and tracks[back].title == "Ahora Si", list(tracks))
check("Pendientes queda vacía", d.pending_model.rowCount() == 0 and d.tabs.tabText(1) == "Pendientes (0)")

print("[Restaurar]")
history = d.history_model.rowCount(); d.history.selectRow(0); restored_name = d._history_rows[0].old_path; d.btn_restore_selected.click(); wait(d)
check("restaurar selección", d.history_model.rowCount() == history - 1 and os.path.isfile(restored_name), d.status.text())
d.btn_restore_all.click(); wait(d)
check("restaurar todo: cada archivo exacto y con su nombre", all(os.path.isfile(p) and sha(p) == originals[p] for p in (safe, doubt, none)), d.status.text())
check("no quedan los nombres nuevos", not os.path.exists(final) and not os.path.exists(final_safe) and not os.path.exists(back))
tracks = {t.path: t for t in db.all_tracks()}
check("la biblioteca vuelve a sus datos", safe in tracks and tracks[safe].album == "Disco" and tracks[safe].artist == "canal1" and tracks[safe].id == track_id, tracks.get(safe))
check("las playlists siguen intactas", len(db.playlist_tracks(playlist.id)) == 2)

print("[Clave mala]")
win.prefs.acoustid_key = "mala"; odb = organizer_db.OrganizerDb(); odb.forget_identifications(); odb.conn.execute("DELETE FROM api_cache"); odb.conn.commit(); odb.close()
def reject(*a): raise acoustid_lookup.InvalidKey
acoustid_lookup.lookup_raw = reject; dialogs_before = len(key_dialogs); d._refresh(); d.btn_analyze.click(); wait(d)
check("vuelve a pedirla, y nada se marca como dudoso", len(key_dialogs) == dialogs_before + 1 and "clave" in d.status.text() and not any(r.decision == "revisar" for r in d.model.rows()), d.status.text())
def down(*a): raise acoustid_lookup.ServiceError("No se pudo conectar con AcoustID.")
acoustid_lookup.lookup_raw = down; d.btn_analyze.click(); wait(d)
check("sin internet: lo explica y no marca nada", "conectar" in d.status.text() and "conectar" in d.errors.toPlainText() and not any(r.decision == "revisar" for r in d.model.rows()), d.status.text())
acoustid_lookup.lookup_raw = fake_lookup

print("[Carpetas]")
d.reject(); spin(50); d = open_dialog([])
d.btn_analyze.click(); spin(50)
check("sin carpetas lo pide", any("carpeta" in s for s in shown))
od.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: outside_folder)
d.btn_add_folder.click(); check("agregar carpeta", d.roots.count() == 1 and d.roots.item(0).text() == os.path.normpath(outside_folder))
d.btn_add_folder.click(); check("  sin repetirla", d.roots.count() == 1)
od.QInputDialog.getItem = staticmethod(lambda *a, **k: ("D:\\", True)); d.btn_add_drive.click()
check("agregar unidad completa", d.roots.count() == 2 and d.roots.item(1).text() == "D:\\")
d.roots.item(1).setSelected(True); d.btn_remove_root.click(); check("quitar", d.roots.count() == 1)
win.prefs.acoustid_key = "clave-buena"; d.btn_analyze.click(); wait(d)
check("analiza una carpeta fuera de la biblioteca, sin agregarla", [os.path.basename(r.path) for r in d.model.rows()] == ["Fuera.mp3"] and db.track_id_for_path(outside) is None)

print("[Ajustes]")
settings = od.OrganizerSettingsDialog(win.prefs, d); settings.auto_score.setValue(75); settings.max_diff.setValue(9); settings.backup.setText(os.path.join(work, "MisRespaldos")); settings._save()
check("guarda niveles y carpeta", abs(win.prefs.confidence.auto_score - 0.75) < 1e-6 and win.prefs.confidence.max_duration_diff_s == 9 and win.prefs.organizer_backup_folder.endswith("MisRespaldos"))
one = row_of(d, "Fuera.mp3"); one.title, one.artist, one.checked = "Fuera", "Alguien", True; d._update_buttons(); d.btn_normalize_selected.click(); wait(d)
check("usa esa carpeta de respaldos", os.path.isdir(os.path.join(work, "MisRespaldos")) and os.listdir(os.path.join(work, "MisRespaldos")), d.status.text())
check("una fuera de la biblioteca se normaliza sin agregarla", os.path.isfile(os.path.join(outside_folder, "Fuera - Alguien.mp3")) and not [t for t in db.all_tracks() if "Fuera" in t.path])

print("[Progreso y cierre]")
d._started = time.monotonic() - 3725; d._counts = (31, 50); d._show_progress()
check("porcentaje, hechas, restantes y tiempo", d.status.text().startswith("62 %") and "31 de 50" in d.status.text() and "faltan 19" in d.status.text() and "01:02:05" in d.status.text(), d.status.text())
d.reject(); spin(50); check("se cierra", not d.isVisible())

print("[Corte de luz: la biblioteca se pone al día]")
odb = organizer_db.OrganizerDb(); odb.conn.execute("UPDATE operation_items SET library_synced = 1"); odb.conn.commit()
p2 = synth.mp3(os.path.join(music, "CorteVentana.mp3"), 5, title="Corte", artist="x", seed=9); db.add_tracks([scan_file(p2)[0]]); info = os.stat(p2)
odb.register([(p2, info.st_size, info.st_mtime_ns)]); fid = odb.file(p2).id; op = odb.begin_operation()
new_p2 = os.path.join(music, "Corte - Grupo.mp3"); os.rename(p2, new_p2)
it = odb.add_item(op, fid, p2, "{}", "Corte", "Grupo"); odb.mark_renaming(it.id, new_p2); odb.set_item_state(it.id, organizer_db.ITEM_DONE); odb.close()
check("al abrir, la biblioteca alcanza al disco", win.ops.reconcile_organizer() >= 1 and db.track_id_for_path(new_p2) is not None and db.track_id_for_path(p2) is None)
check("  una segunda vez no hace nada", win.ops.reconcile_organizer() == 0)

win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
