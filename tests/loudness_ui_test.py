"""Prueba de «Analizar y ajustar volumen» de punta a punta, sobre COPIAS de canciones reales."""
import hashlib, math, os, shutil, sqlite3, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_loud_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import main_window as mw
from app.ui.loudness_dialog import COL_DIAG, COL_GAIN, COL_SONG, COL_USE, LoudnessDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def wait_until(cond, timeout=180000):
    end = time.time() + timeout / 1000
    while time.time() < end and not cond(): app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.01)
    return cond()
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
        raise AssertionError([b.text() for b in box.buttons()])
    return h

real = {
    "track1": r"D:\Musica Cristiana\Padre Celestial (Variado)\01 - Track 1.mp3",
}
con = sqlite3.connect("file:" + os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db") + "?mode=ro", uri=True)
for key, like in (("belen", "%Tu amor me hace fuerte%"), ("vasijas", "%Vasijas Rotas%"), ("hossana", "%Hossana - Marcela%"), ("wma", "%.wma")):
    rows = con.execute("select path from tracks where path like ?", (like,)).fetchall()
    found = next((r[0] for r in rows if os.path.isfile(r[0])), None)  # solo archivos que existen
    if found: real[key] = found
real_hashes = {k: sha(p) for k, p in real.items()}
lib = os.path.join(work, "musica"); os.makedirs(lib)
copies = {}
for k, p in real.items():
    copies[k] = os.path.join(lib, f"{k}{os.path.splitext(p)[1]}"); shutil.copy2(p, copies[k])
# MP3 bajo propio (generado con LAME), para no depender de archivos reales que el usuario ya pudo ajustar
import lameenc, numpy as np
enc = lameenc.Encoder(); enc.set_bit_rate(192); enc.set_in_sample_rate(44100); enc.set_channels(2); enc.set_quality(2)
t = np.arange(44100 * 20) / 44100
music = (0.06 * np.sin(2 * np.pi * 220 * t) + 0.04 * np.sin(2 * np.pi * 330 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t))
pcm = (np.repeat(music[:, None], 2, axis=1) * 32767).astype("<i2").tobytes()
quiet = os.path.join(lib, "track1.mp3")
open(quiet, "wb").write(enc.encode(pcm) + enc.flush())
copies["track1"] = quiet
# WAV muy bajo (-30 dBFS): formato no ajustable
w = os.path.join(lib, "bajo.wav")
with wave.open(w, "wb") as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(44100)
    f.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(1000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100 * 8))))
copies["wav"] = w
copy_hashes = {k: sha(p) for k, p in copies.items()}

db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in copies.values()])
win = mw.MainWindow(db); win.show(); spin(200)
by_name = lambda key: next(t for t in win.library if os.path.basename(t.path).startswith(key + "."))
win._on_play_requested([by_name("track1")], 0); spin(500)
check("Canción sonando antes de ajustar", win.player.is_playing)

state = {}
def dialog(d):
    try:
        state["btn"] = d.btn_analyze_new.text()
        d.btn_analyze_new.click()
        wait_until(lambda: not d.runner.busy, 240000)
        state["summary"] = d.summary.text()
        rows = {}
        for r in range(d.table.rowCount()):
            track, steps = d.table.item(r, COL_USE).data(Qt.ItemDataRole.UserRole)
            rows[os.path.basename(track.path)] = (d.table.item(r, COL_USE).checkState() == Qt.CheckState.Checked, d.table.item(r, COL_GAIN).text(), d.table.item(r, COL_DIAG).text())
        state["rows"] = rows
        state["apply_text"] = d.btn_apply.text()
        expect(msg("¿Subir el volumen"), click("Subir volumen"))
        expect(msg("Se subió el volumen"), lambda b: (state.setdefault("result", b.text()), b.accept()))
        d.btn_apply.click()
        wait_until(lambda: not d.runner.busy and "result" in state, 120000)
        spin(300)
        # Revertir: filtro «ya ajustadas», seleccionar todo
        d.filter.setCurrentIndex(1); spin(100)
        state["done_rows"] = d.table.rowCount()
        d.table.selectAll()
        expect(msg("¿Devolver"), click("Revertir"))
        expect(msg("Se revirti"), lambda b: (state.setdefault("revert", b.text()), b.accept()))
        state["hashes_after_apply"] = {k: sha(p) for k, p in copies.items()}
        state["gains_after_apply"] = {os.path.basename(t.path): t.norm_gain_db for t in win.library}
        d.btn_revert.click()
        wait_until(lambda: not d.runner.busy and "revert" in state, 120000)
    finally:
        d.reject(); state["done"] = True
expect(lambda w: isinstance(w, LoudnessDialog), dialog)
win._open_loudness(); wait_until(lambda: "done" in state, 400000)

print("     resumen:", state.get("summary", "").replace("<b>", "").replace("</b>", "").replace("<br>", " | "))
for name, row in state.get("rows", {}).items(): print(f"       {name:12s} marcada={row[0]!s:5s} {row[1]:>8s}  {row[2][:95]}")
rows = state.get("rows", {})
check("Herramientas → Analizar y ajustar volumen: analiza todas", f"Analizadas: {len(copies)} de {len(copies)}" in state.get("summary", "").replace("<b>", "").replace("</b>", ""), state.get("summary", "")[:80])
check("  propone subir la canción baja «Track 1»", rows.get("track1.mp3", (False,))[0] and rows["track1.mp3"][1].startswith("+"), rows.get("track1.mp3"))
check("  no toca una canción fuerte (Hossana)", "hossana.mp3" not in rows or not rows["hossana.mp3"][0], rows.get("hossana.mp3"))
check("  WAV muy bajo: se indica, pero no se ajusta (no MP3)", "bajo.wav" in rows and not rows["bajo.wav"][0] and "no se puede ajustar" in rows["bajo.wav"][2], rows.get("bajo.wav"))
changed = [k for k in copies if state.get("hashes_after_apply", {}).get(k) != copy_hashes[k]]
check("  aplicar modifica solo los MP3 marcados", set(changed) == {os.path.splitext(n)[0] for n, r in rows.items() if r[0]}, changed)
check("  guarda la ganancia aplicada", any(g > 0 for g in state.get("gains_after_apply", {}).values()), state.get("gains_after_apply"))
check("  respaldo de la biblioteca antes de ajustar", any("antes-de-ajustar-volumen" in f.name for f in backup.list_backups()))
check("  la canción que sonaba se soltó y se ajustó", "track1" in changed)
check("Revertir: vuelven byte a byte a como estaban", all(sha(p) == copy_hashes[k] for k, p in copies.items()), state.get("revert"))
check("  y la biblioteca queda sin ajustes", all(t.norm_gain_db == 0 for t in win.library))
check("Tus archivos originales no se tocaron", all(sha(p) == real_hashes[k] for k, p in real.items()))
check("todos los diálogos esperados aparecieron", not pending, pending)
win.player.stop(); win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
os._exit(0 if all(results) and not errors else 1)
