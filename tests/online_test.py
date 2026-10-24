"""Prueba de «Buscar datos en internet» contra MusicBrainz/Deezer/iTunes reales (archivos de silencio)."""
import os, sys, tempfile, time, traceback, urllib.error, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_online_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")

from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE
from app import online_lookup
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import theme
from app.ui import main_window as mw
from app.ui.dialogs import PreferencesDialog
from app.ui.online_dialog import COL_PROPOSAL, COL_SCORE, COL_USE, OnlineLookupDialog
theme.apply(app, "auto")

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

def silence(path, secs, title=None, artist=None):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(2000); w.writeframes(b"\x80" * (2000 * secs))
    if title:
        f = WAVE(path); f.add_tags(); f.tags.add(TIT2(encoding=3, text=title)); f.tags.add(TPE1(encoding=3, text=artist)); f.save()

music = os.path.join(work, "m"); os.makedirs(music)
silence(os.path.join(music, "03 - Queen - Bohemian Rhapsody.wav"), 355)          # sin etiquetas
silence(os.path.join(music, "musica.wav"), 213, "De música ligera", "Soda Stereo")   # sin álbum
silence(os.path.join(music, "zzqx_pista_inexistente_8812.wav"), 60)                # no existe
silence(os.path.join(music, "lamento.wav"), 223, "Lamento boliviano", "Los Enanitos Verdes")
db = Database(database_path())
db.add_tracks([scan_file(os.path.join(music, n))[0] for n in sorted(os.listdir(music))])

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
def is_(cls): return lambda w: isinstance(w, cls)
def wait_until(cond, timeout=120000):
    end = time.time() + timeout/1000
    while time.time() < end and not cond():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.01)
    return cond()

win = mw.MainWindow(db); win.show(); app.processEvents()
by_file = lambda name: next(t for t in win.library if os.path.basename(t.path) == name)

def action(text):
    for top in win.menuBar().actions():
        for a in top.menu().actions():
            if a.text().replace("&", "") == text: return a

# ---------- búsqueda en todas
state = {}
def batch(d):
    try:
        state["sources"] = {k: b.isChecked() for k, b in d.source_boxes.items()}
        state["incomplete"] = d.only_incomplete.text()
        state["btn"] = d.btn_search.text()
        t0 = time.time(); d.btn_search.click()
        wait_until(lambda: not d.runner.busy and len(d._results) == len(d._rows))
        state["secs"] = round(time.time() - t0, 1)
        state["status"] = d.status.text()
        rows = {}
        for r, track in enumerate(d._rows):
            combo = d.table.cellWidget(r, COL_PROPOSAL)
            rows[os.path.basename(track.path)] = (
                d.table.item(r, COL_USE).checkState() == Qt.CheckState.Checked,
                combo.currentText() if isinstance(combo, QComboBox) else d.table.item(r, COL_PROPOSAL).text(),
                d.table.item(r, COL_SCORE).text(),
                combo.count() if isinstance(combo, QComboBox) else 0,
            )
        state["rows"] = rows
        # Elegir «(No cambiar)» en Lamento: debe desmarcarse
        r_lam = next(r for r, t in enumerate(d._rows) if t.path.endswith("lamento.wav"))
        d.table.cellWidget(r_lam, COL_PROPOSAL).setCurrentIndex(0)
        state["lam_unchecked"] = d.table.item(r_lam, COL_USE).checkState() == Qt.CheckState.Unchecked
        state["apply_btn"] = d.btn_apply.text()
        d.btn_apply.click()
        wait_until(lambda: not d.runner.busy, 60000)
        state["after_apply"] = d.banner.text()
        state["scores_after"] = [d.table.item(r, COL_SCORE).text() for r in range(d.table.rowCount())]
        state["hidden_after"] = sum(d.table.isRowHidden(r) for r in range(d.table.rowCount()))
    finally:
        d.reject(); state["done"] = True
expect(is_(OnlineLookupDialog), batch)
action("Buscar datos en internet…").trigger(); wait_until(lambda: "done" in state, 240000)

check("Herramientas → Buscar datos en internet…", "rows" in state)
check("  fuentes por defecto: MusicBrainz y Deezer (iTunes opcional)", state.get("sources") == {"musicbrainz": True, "deezer": True, "itunes": False}, state.get("sources"))
check("  opción «Solo incompletas»", "de 4" in state.get("incomplete", ""), state.get("incomplete"))
check("  botón «Buscar en todas (4)»", state.get("btn") == "Buscar en todas (4)", state.get("btn"))
rows = state.get("rows", {})
for name, row in rows.items():
    print(f"       {name:40s} marcada={row[0]!s:5s} {row[2]:>14s}  opciones={row[3]}  → {row[1][:90]}")
print(f"       tiempo: {state.get('secs')} s · {state.get('status')}")
bo = rows.get("03 - Queen - Bohemian Rhapsody.wav", (False, "", "", 0))
check("  sin etiquetas: reconoce «Bohemian Rhapsody — Queen» y la marca", bo[0] and "Bohemian Rhapsody — Queen" in bo[1], bo)
so = rows.get("musica.wav", (False, "", "", 0))
check("  Soda Stereo: propone álbum y la marca", so[0] and "Soda Stereo" in so[1], so)
zz = rows.get("zzqx_pista_inexistente_8812.wav", (True, "", "", 0))
check("  canción inexistente: no se marca", not zz[0], zz)
check("  varias opciones para elegir por canción", bo[3] >= 3, bo[3])
check("  elegir «(No cambiar)» desmarca la fila", state.get("lam_unchecked"))
check("  «Aplicar (2)»", state.get("apply_btn") == "Aplicar (2)", state.get("apply_btn"))
check("  mensaje tras aplicar", "Se actualizaron 2 canciones" in state.get("after_apply", ""), state.get("after_apply"))
check("  al terminar se limpia la lista: las 2 actualizadas salen de la vista", state.get("hidden_after") == 2, state.get("hidden_after"))
bo_t = by_file("03 - Queen - Bohemian Rhapsody.wav"); so_t = by_file("musica.wav")
check("  biblioteca actualizada (título/artista/álbum)", bo_t.title == "Bohemian Rhapsody" and bo_t.artist == "Queen" and bo_t.album not in ("", "Álbum desconocido"),
      (bo_t.title, bo_t.artist, bo_t.album))
check("  carátula descargada", bo_t.cover_hash is not None or so_t.cover_hash is not None, (bo_t.cover_hash, so_t.cover_hash))
check("  el archivo de audio no se modificó", WAVE(bo_t.path).tags is None)
check("  la fila «(No cambiar)» quedó igual", by_file("lamento.wav").album == "Álbum desconocido")

# ---------- una sola canción (clic derecho), con iTunes y búsqueda corregida a mano
single = {}
def one(d):
    try:
        wait_until(lambda: not d.runner.busy and d._results, 60000)
        single["auto"] = d.table.rowCount() == 1 and bool(d._results)
        d.source_boxes["itunes"].setChecked(True)
        d.query_title.setText("Lamento boliviano"); d.query_artist.setText("Enanitos Verdes")
        d.btn_search.click(); wait_until(lambda: not d.runner.busy and d._results, 60000)
        combo = d.table.cellWidget(0, COL_PROPOSAL)
        texts = [combo.itemText(i) for i in range(combo.count())]
        single["sources"] = sorted({t.split("[")[-1].rstrip("]") for t in texts[1:]})
        single["first"] = texts[1] if len(texts) > 1 else ""
    finally:
        d.reject(); single["done"] = True
expect(is_(OnlineLookupDialog), one)
win.content.online_lookup_requested.emit([by_file("lamento.wav")]); wait_until(lambda: "done" in single, 180000)
check("Clic derecho en una canción: busca sola al abrir", single.get("auto"))
check("  corregir título/artista y repetir búsqueda con iTunes", "iTunes (Apple)" in single.get("sources", []), single.get("sources"))
check("  propuesta coherente", "Lamento" in single.get("first", ""), single.get("first"))

# ---------- sin conexión: mensaje claro, sin colgarse
orig = online_lookup.urllib.request.urlopen
online_lookup.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("sin red"))
off = {}
def offline(d):
    try:
        wait_until(lambda: not d.runner.busy and d._results, 30000)
        off["status"] = d.status.text(); off["cell"] = d.table.item(0, COL_PROPOSAL).text()
    finally:
        d.reject(); off["done"] = True
expect(is_(OnlineLookupDialog), offline)
win.content.online_lookup_requested.emit([by_file("lamento.wav")]); wait_until(lambda: "done" in off, 60000)
online_lookup.urllib.request.urlopen = orig
check("Sin internet: aviso claro", "conexión" in off.get("status", ""), off.get("status"))
check("  la fila indica el error", "error de conexión" in off.get("cell", ""), off.get("cell"))

# ---------- preferencias
def prefs(d):
    d.source_boxes["deezer"].setChecked(False); d.source_boxes["itunes"].setChecked(True)
    d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
expect(is_(PreferencesDialog), prefs)
action("Preferencias…").trigger(); app.processEvents()
check("Preferencias → bases de datos por defecto", win.prefs.online_sources == ["musicbrainz", "itunes"], win.prefs.online_sources)

# ---------- botón del encabezado
win.sidebar.select_library("songs"); app.processEvents()
check("Botón «Datos en internet» visible en la lista", win.content.btn_online.isVisible())
win.content.table.selectRow(0); win.content.table.selectionModel().select(
    win.content.proxy.index(1, 0), win.content.table.selectionModel().SelectionFlag.Select | win.content.table.selectionModel().SelectionFlag.Rows)
app.processEvents()
got = {}
win.content.online_lookup_requested.disconnect()
win.content.online_lookup_requested.connect(lambda tracks: got.setdefault("n", len(tracks)))
win.content.btn_online.click()
check("  usa las canciones seleccionadas", got.get("n") == 2 and "(2)" in win.content.btn_online.text(), (got, win.content.btn_online.text()))

check("todos los diálogos esperados aparecieron", not pending, pending)
win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
os._exit(0 if all(results) and not errors else 1)
