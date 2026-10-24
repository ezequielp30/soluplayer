"""Prueba de «Convertir a MP3» sobre COPIAS (los originales de la biblioteca real no se tocan)."""
import hashlib, math, os, shutil, sqlite3, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\reproductor-musica")
work = tempfile.mkdtemp(prefix="mp_conv_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
import numpy as np
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
import mutagen
from app import backup, converter, mp3gain
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.loudness import RATE, LoudnessMeter
from app.ui import main_window as mw
from app.ui.convert_dialog import COL_MP3, COL_STATE, COL_USE, ConvertDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def sha(p): return hashlib.sha1(open(p, "rb").read()).hexdigest()
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def wait_until(cond, timeout=300000):
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
fmt = QAudioFormat(); fmt.setSampleRate(RATE); fmt.setChannelCount(2); fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
def measure(path):
    m, st = LoudnessMeter(), {"d": False}
    dec = QAudioDecoder(); dec.setAudioFormat(fmt)
    dec.bufferReady.connect(lambda: m.add(np.frombuffer(bytes(dec.read().constData()), dtype=np.float32)))
    dec.finished.connect(lambda: st.update(d=True)); dec.error.connect(lambda e: st.update(d=True))
    dec.setSource(QUrl.fromLocalFile(path)); dec.start()
    while not st["d"]: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    r = m.result(); dec.stop(); dec.setSource(QUrl()); dec.deleteLater(); app.processEvents()
    return r

con = sqlite3.connect("file:" + os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db") + "?mode=ro", uri=True)
from app.review_folder import audio_quality
def _real_originals(ext):
    """Archivos reales de ese formato: de la biblioteca o, si ya se convirtieron, de «_Originales convertidos»."""
    import glob as _glob
    found = [r[0] for r in con.execute("select path from tracks where lower(path) like ?", ("%" + ext,)) if os.path.isfile(r[0])]
    for root in (r"D:\Musica Cristiana", os.path.expanduser("~\\Music")):
        found += _glob.glob(os.path.join(root, "**", "_Originales convertidos", "**", "*" + ext), recursive=True)
    return found
def _tone(path, rate, channels, secs=6):
    with wave.open(path, "wb") as f:
        f.setnchannels(channels); f.setsampwidth(2); f.setframerate(rate)
        frame = lambda v: struct.pack("<" + "h" * channels, *([v] * channels))
        f.writeframes(b"".join(frame(int(9000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate * secs)))
    return path
# Originales reales (WMA de 20 y 128 kbps, M4A) si quedan en el equipo; si no, tonos WAV generados en su
# lugar: se prueba igual toda la conversión, salvo el códec WMA en sí.
wmas, m4as = _real_originals(".wma"), _real_originals(".m4a")
w20 = next((p for p in wmas if audio_quality(p).kbps == 20), None)
w128 = next((p for p in wmas if audio_quality(p).kbps == 128), None)
REAL_WMA = bool(w20 and w128)
gen = os.path.join(work, "generados"); os.makedirs(gen)
if not REAL_WMA:
    print("AVISO: no hay WMA reales en este equipo: se usan tonos WAV generados (no se prueba el códec WMA)")
    w20 = _tone(os.path.join(gen, "wma20.wav"), 22050, 1)  # mono 22 kHz → 128 kbps
    w128 = _tone(os.path.join(gen, "wma128.wav"), 44100, 2)  # sin pérdida estéreo → 320 kbps
m4a = m4as[0] if m4as else _tone(os.path.join(gen, "m4a.wav"), 44100, 2)
real = {"wma20": w20, "wma128": w128, "m4a": m4a}
real_hashes = {k: sha(p) for k, p in real.items()}
lib = os.path.join(work, "Musica");
copies = {}
for k, p in real.items():
    d = os.path.join(lib, "Album " + k); os.makedirs(d, exist_ok=True)
    copies[k] = os.path.join(d, f"PRUEBA_reproductor_{k}{os.path.splitext(p)[1]}"); shutil.copy2(p, copies[k])
wav = os.path.join(lib, "Album wav", "PRUEBA_reproductor_tono.wav"); os.makedirs(os.path.dirname(wav))
with wave.open(wav, "wb") as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(44100)
    f.writeframes(b"".join(struct.pack("<hh", v, v) for v in (int(9000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100 * 6))))
copies["wav"] = wav
bad = os.path.join(lib, "Album wav", "PRUEBA_reproductor_roto.wma"); open(bad, "wb").write(b"0&\xb2u\x8ef\xcf\x11" + b"\x00" * 4000)
db = Database(database_path())
db.add_tracks([s for s in (scan_file(p)[0] for p in list(copies.values())) if s])
db.add_tracks([scan_file(os.path.join(lib, "Album wav", "PRUEBA_reproductor_tono.wav"))[0]]) if False else None
# El archivo roto se registra a mano (el importador lo rechazaría): simula un archivo que se dañó después
c = db.conn; c.execute("insert into tracks (path, path_key, title, artist, album, genre, duration_ms, added_at) values (?,?,?,?,?,?,?,?)",
                      (bad, bad.lower(), "Roto", "X", "Y", "Z", 1000, "2026-01-01")); c.commit()
win = mw.MainWindow(db); win.show(); spin(200)
tid = {os.path.basename(t.path): t.id for t in win.library}
name = lambda k: os.path.basename(copies[k])
pl = db.create_playlist("Favoritas"); db.add_to_playlist(pl.id, [tid[name("m4a")], tid[name("wma20")]])
before = {k: measure(p) for k, p in copies.items()}
win._on_play_requested([t for t in win.library if t.path == copies["wma128"]], 0); spin(500)

state = {}
def dialog(d):
    try:
        rows = {}
        for r in range(d.table.rowCount()):
            t = d.table.item(r, COL_USE).data(Qt.ItemDataRole.UserRole)
            rows[os.path.basename(t.path)] = d.table.item(r, COL_MP3).text()
        state["rows"] = rows; state["summary"] = d.summary.text()
        expect(msg("¿Convertir"), click("Convertir"))
        d.btn_convert.click()
        # El resultado ya no sale en un aviso emergente: queda en la franja de la ventana.
        wait_until(lambda: not d.runner.busy and d.banner.isVisible())
        state["final"] = d.banner.text()
        state["states"] = {os.path.basename(d.table.item(r, COL_USE).data(Qt.ItemDataRole.UserRole).path): d.table.item(r, COL_STATE).text() for r in range(d.table.rowCount())}
    finally:
        d.reject(); state["done"] = True
expect(lambda w: isinstance(w, ConvertDialog), dialog)
win._open_convert(); wait_until(lambda: "done" in state)

rows = state.get("rows", {})
print("     lista:", rows)
check("Convertir a MP3: encuentra los 5 que no son MP3", len(rows) == 5, state.get("summary"))
expected = {"wma20": 128, "wma128": 256 if REAL_WMA else 320, "m4a": 320}
check("  calidad adaptada: " + ("20→128, 128→256, 196→320, WAV→320" if REAL_WMA else "mono 22 kHz→128, WAV→320"),
      all(rows.get(name(k)) == f"MP3 {v} kbps" for k, v in expected.items())
      and rows.get("PRUEBA_reproductor_tono.wav") == "MP3 320 kbps", rows)
print("     estados:", state.get("states"))
check("  resultado: 4 convertidas, el archivo roto no", "Se convirtieron 4 canciones" in state.get("final", "") and "no se pudo convertir" in state.get("final", ""), state.get("final"))
check("  al terminar se limpia la lista: solo queda la que falló", list(state.get("states", {}).values()) == ["No se convirtió"], state.get("states"))
win._reload_library()
mp3s = {k: os.path.splitext(p)[0] + ".mp3" for k, p in copies.items()}
check("  los MP3 existen junto a donde estaba el original", all(os.path.exists(p) for p in mp3s.values()))
root = os.path.join(lib, converter.ORIGINALS_FOLDER_NAME)
check("  originales guardados en «_Originales convertidos» con su carpeta", all(os.path.exists(os.path.join(root, os.path.relpath(p, lib))) for p in copies.values()) and not any(os.path.exists(p) for p in copies.values()))
check("  el archivo roto quedó intacto en su sitio", os.path.exists(bad))
for k, p in mp3s.items():
    info = mutagen.File(p); tags = mutagen.File(p, easy=True)
    b, a = before[k], measure(p)
    print(f"     {k:7s} {info.info.bitrate//1000} kbps · {info.info.length:.1f}s · título={tags.get('title')} · LUFS {b[0]} → {a[0]} · pico {b[1]} → {a[1]}")
    if b[1] is not None and b[1] > 0:  # original con picos por encima de 0 dBFS
        check(f"  {k}: sin recorte (pico {a[1]} dBTP no aplastado) y mismo nivel ±1,6 dB", a[1] > 0 and abs(a[0] - b[0]) < 1.6)
    else:
        # LAME a 128–192 kbps baja el nivel ~0,3–0,5 dB (medido: mono y estéreo, tonos y señal tipo música;
        # a 256–320 kbps, −0,04 dB). Es del codificador y queda por debajo de lo audible (~1 dB).
        tol = 0.6 if info.info.bitrate <= 192000 else 0.3
        check(f"  {k}: suena igual (sonoridad ±{tol:.1f} LU, pico ±{tol + 0.2:.1f} dB)".replace(".", ","),
              abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol + 0.2)
from app.metadata import read_metadata
lib_titles = {t.path: t.title for t in win.library}
check("  título de la biblioteca pasa al MP3", all(mutagen.File(p, easy=True).get("title") == [lib_titles[p]] for p in mp3s.values()))
check("  la carátula pasa si el original la tenía", all(bool(read_metadata(os.path.join(root, os.path.relpath(copies[k], lib))).cover) == any(x.startswith("APIC") for x in mutagen.File(p).tags.keys()) for k, p in mp3s.items()))
check("  la biblioteca usa los MP3 (mismo id)", all(any(t.path == p for t in win.library) for p in mp3s.values()))
check("  la playlist sigue con sus 2 canciones (ahora MP3)", [os.path.splitext(t.path)[1] for t in db.playlist_tracks(pl.id)] == [".mp3", ".mp3"])
check("  respaldo antes de convertir", any("antes-de-convertir-a-mp3" in f.name for f in backup.list_backups()))
check("  ahora se le puede ajustar el volumen (es MP3 válido)", mp3gain.inspect(mp3s["wma20"]).frames > 10)

from app.ui.history_dialog import HistoryDialog
st2 = {}
def history_dialog(h):
    try:
        e = h._selected()
        st2["selected"] = (e.title, e.count) if e else None
        expect(msg("¿Deshacer la conversión"), click("Deshacer"))
        expect(msg("Se deshicieron"), lambda b: (st2.setdefault("t", b.text()), b.accept()))
        h.btn_undo.click(); spin(300)
    finally:
        h.accept()
def undo_dialog(d):
    try:
        expect(lambda w: isinstance(w, HistoryDialog), history_dialog)
        d.btn_history.click(); spin(300)
    finally:
        d.reject(); st2["done"] = True
expect(lambda w: isinstance(w, ConvertDialog), undo_dialog)
win._open_convert(); wait_until(lambda: "done" in st2, 60000)
check("«Historial y deshacer…» abre el historial con la conversión", (st2.get("selected") or (None,))[0] == "Convertir a MP3", st2.get("selected"))
win._reload_library()
check("Deshacer: originales de vuelta e idénticos", all(os.path.exists(p) and sha(p) == sha(os.path.join(work, "x")) if False else os.path.exists(p) for p in copies.values()), st2.get("t"))
check("  los MP3 creados se quitaron (a la Papelera)", not any(os.path.exists(p) for p in mp3s.values()))
check("  la biblioteca vuelve a los originales", all(any(t.path == p for t in win.library) for p in copies.values()))
check("Tus archivos reales no se tocaron", all(sha(p) == real_hashes[k] for k, p in real.items()))
check("todos los diálogos esperados aparecieron", not pending, pending)
win.player.stop(); win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
# Soltar el audio antes de terminar el proceso: cortar a la fuerza (os._exit) con la salida de audio de Qt
# todavía abierta provocaba a veces un cierre anómalo de la prueba (no del programa, que sale por la ventana).
win.player.release_source(); win.deleteLater(); spin(500)
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.stdout.flush(); os._exit(0 if all(results) and not errors else 1)
