import math, os, shutil, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_dup_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")

from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw
from app.ui.dialogs import FolderImportDialog, ImportReportDialog
from app.ui.duplicates_dialog import DuplicatesDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

def tone(path, freq, secs, title=None, artist=None):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(5000*math.sin(2*math.pi*freq*i/8000))) for i in range(8000*secs)))
    if title:
        f = WAVE(path); f.add_tags(); f.tags.add(TIT2(encoding=3, text=title)); f.tags.add(TPE1(encoding=3, text=artist)); f.save()

# ---- carpeta con dañados
bad = os.path.join(work, "Con dañados"); os.makedirs(bad)
tone(os.path.join(bad, "PRUEBA_reproductor_bien.wav"), 440, 1)
roto = os.path.join(bad, "PRUEBA_reproductor_roto.mp3"); open(roto, "wb").write(b"basura" * 100)
vacio = os.path.join(bad, "PRUEBA_reproductor_vacio.flac"); open(vacio, "wb").close()
txt = os.path.join(bad, "PRUEBA_reproductor_notas.mp3.txt"); open(txt, "w").write("x")
noaudio = os.path.join(bad, "PRUEBA_reproductor_texto.ogg"); open(noaudio, "w").write("no soy audio" * 30)

# ---- carpeta con repetidas
lib = os.path.join(work, "Biblioteca"); copias = os.path.join(work, "Copias")
os.makedirs(lib); os.makedirs(copias)
tone(os.path.join(lib, "Tema.wav"), 440, 4, "Tema", "Banda")
shutil.copy(os.path.join(lib, "Tema.wav"), os.path.join(copias, "Tema (copia).wav"))       # idéntica
tone(os.path.join(copias, "Tema otra fuente.wav"), 445, 5, "TEMA", "banda")                 # misma canción, otro archivo
tone(os.path.join(copias, "Tema en vivo.wav"), 440, 12, "Tema", "Banda")                     # duración distinta: no es repetida
tone(os.path.join(lib, "Otra.wav"), 600, 3, "Otra", "Banda")

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
def msg(text): return lambda w: isinstance(w, QMessageBox) and text in w.text() + w.informativeText()
def click(label):
    def h(box):
        for b in box.buttons():
            if b.text().replace("&", "") == label: b.click(); return
        raise AssertionError([b.text() for b in box.buttons()])
    return h
def wait_until(cond, timeout=15000):
    end = time.time() + timeout/1000
    while time.time() < end and not cond():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
    return cond()

answers = []
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: answers.pop(0))
db = Database(database_path()); win = mw.MainWindow(db); win.show()
def action(text):
    for top in win.menuBar().actions():
        for a in top.menu().actions():
            if a.text().replace("&", "") == text: return a

# ======================== 1) informe con archivos dañados
state = {}
def report_handler(d):
    items = d._corrupt_items
    state["unchecked_default"] = all(i.checkState(0) == Qt.CheckState.Unchecked for i in items)
    for i in items: i.setCheckState(0, Qt.CheckState.Checked)  # el usuario los marca
    state["corrupt_names"] = sorted(i.text(0) for i in items)
    state["all_rows"] = d.tree.topLevelItemCount()
    state["btn"] = d.trash_button.text(); state["btn_visible"] = d.trash_button.isVisible()
    state["summary"] = d.findChild(type(d.trash_result)).text()
    # desmarcar el vacío: solo se enviará el roto
    next(i for i in items if "vacio" in i.text(0)).setCheckState(0, Qt.CheckState.Unchecked)
    state["btn_after_uncheck"] = d.trash_button.text()
    # primero Cancelar, luego confirmar
    expect(msg("¿Enviar 2 archivos dañados"), click("Cancelar"))
    d.trash_button.click()
    state["exists_after_cancel"] = os.path.exists(roto)
    expect(msg("¿Enviar 2 archivos dañados"), click("Enviar a la papelera"))
    d.trash_button.click()
    state["row_texts"] = {i.text(0): i.text(1) for i in items}
    state["result"] = d.trash_result.text()
    state["btn_final_enabled"] = d.trash_button.isEnabled()
    d.accept(); state["done"] = True
answers.append(bad)
expect(is_(FolderImportDialog), lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
expect(is_(ImportReportDialog), report_handler)
action("Importar carpeta…").trigger(); wait_until(lambda: "done" in state)
check("Informe: solo dañados/vacíos se ofrecen (no .txt)", state.get("corrupt_names") == ["PRUEBA_reproductor_roto.mp3", "PRUEBA_reproductor_texto.ogg", "PRUEBA_reproductor_vacio.flac"], state.get("corrupt_names"))
check("  dañados sin marcar por defecto (seguridad)", state.get("unchecked_default") is True)
check("  aviso en el resumen", "dañados o vacíos" in state.get("summary", ""), state.get("summary", "")[-160:])
check("  botón visible con cantidad", state.get("btn_visible") and "(3)" in state.get("btn", ""), state.get("btn"))
check("  desmarcar actualiza la cantidad", "(2)" in state.get("btn_after_uncheck", ""), state.get("btn_after_uncheck"))
check("  Cancelar no borra nada", state.get("exists_after_cancel") is True)
check("  confirmar envía a la papelera los marcados", not os.path.exists(roto) and not os.path.exists(noaudio))
check("  el desmarcado se conserva", os.path.exists(vacio))
check("  el .txt nunca se toca", os.path.exists(txt))
check("  la lista indica el resultado", state.get("row_texts", {}).get("PRUEBA_reproductor_roto.mp3") == "Enviado a la Papelera de reciclaje.", state.get("row_texts"))
check("  mensaje de resultado", "2 archivos enviados" in state.get("result", ""), state.get("result"))
check("  la canción válida se importó", len(win.library) == 1)

# ======================== 2) repetidas
for folder in (lib, copias):
    done = {}
    answers.append(folder)
    expect(is_(FolderImportDialog), lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
    expect(is_(ImportReportDialog), lambda d: (done.setdefault("x", 1), d.accept()))
    action("Importar carpeta…").trigger(); wait_until(lambda: "x" in done)
check("Biblioteca con 6 canciones", len(win.library) == 6, [t.title for t in win.library])
by_path = {os.path.basename(t.path): t for t in win.library}
p1 = db.create_playlist("Solo copia"); p2 = db.create_playlist("Original y copia")
db.add_to_playlist(p1.id, [by_path["Tema (copia).wav"].id])
db.add_to_playlist(p2.id, [by_path["Tema.wav"].id, by_path["Tema otra fuente.wav"].id, by_path["Otra.wav"].id])

dd = {}
def idle(d): wait_until(lambda: not d.runner.busy)
def dup_handler(d):
    try:
        idle(d)
        dd["groups"] = [[os.path.basename(t.path) for t in g.tracks] for g in d._groups]
        dd["keep"] = os.path.basename(d._groups[0].keep.path)
        dd["summary"] = d.banner.text() + " " + d.summary.text()
        # modo contenido
        d.mode.setCurrentIndex(1); d.btn_search.click(); idle(d)
        dd["content_groups"] = [[os.path.basename(t.path) for t in g.tracks] for g in d._groups]
        d.mode.setCurrentIndex(0); d.btn_search.click(); idle(d)
        parent = d.tree.topLevelItem(0)
        # marcar todas → debe avisar y no cambiar nada
        for i in range(parent.childCount()): parent.child(i).setCheckState(0, Qt.CheckState.Checked)
        expect(msg("marcaste todas"), lambda b: b.accept())
        d.btn_remove.click()
        dd["after_all_checked"] = len(win.library)
        d.btn_suggested.click()
        dd["actions"] = [parent.child(i).text(0) for i in range(parent.childCount())]
        # quitar de la biblioteca (sin borrar archivos)
        expect(msg("¿Quitar 2 copias"), click("Quitar"))
        d.btn_remove.click(); idle(d)
        dd["after_remove"] = len(win.library)
        dd["summary_after"] = d.banner.text() + " " + d.summary.text()
        dd["groups_after"] = len(d._groups)
    finally:
        d.accept(); dd["done"] = True
expect(is_(DuplicatesDialog), dup_handler)
action("Buscar canciones repetidas…").trigger(); wait_until(lambda: "done" in dd)
check("Herramientas → Buscar canciones repetidas…", "groups" in dd)
check("  por título/artista: agrupa 3 copias (sin la versión en vivo)",
      dd.get("groups") and sorted(dd["groups"][0]) == ["Tema (copia).wav", "Tema otra fuente.wav", "Tema.wav"] and len(dd["groups"]) == 1, dd.get("groups"))
check("  propone conservar la de mayor tamaño", dd.get("keep") == "Tema otra fuente.wav", dd.get("keep"))
check("  por contenido idéntico: solo las 2 copias exactas", dd.get("content_groups") == [["Tema.wav", "Tema (copia).wav"]], dd.get("content_groups"))
check("  no permite quitar todas las copias", dd.get("after_all_checked") == 6)
check("  «Restaurar sugerencia»", sorted(dd.get("actions", [])) == ["Conservar", "Quitar", "Quitar"], dd.get("actions"))
check("  quitar de la biblioteca: 6 → 4", dd.get("after_remove") == 4, dd.get("after_remove"))
check("  los archivos siguen en el disco", all(os.path.exists(os.path.join(f, n)) for f, n in [(lib, "Tema.wav"), (copias, "Tema (copia).wav")]))
check("  tras quitar ya no quedan repetidas", dd.get("groups_after") == 0 and "Se quitaron 2 copias" in dd.get("summary_after", ""), dd.get("summary_after", "")[:120])
keep_id = by_path["Tema otra fuente.wav"].id
t1 = [t.id for t in db.playlist_tracks(p1.id)]; t2 = [t.id for t in db.playlist_tracks(p2.id)]
check("  playlist que solo tenía la copia → ahora usa la conservada", t1 == [keep_id], t1)
check("  playlist con original y copia → la conservada una sola vez, sin perder las demás", t2 == [keep_id, by_path["Otra.wav"].id], t2)

# ======================== 3) papelera con la copia sonando
copy2 = os.path.join(copias, "PRUEBA_reproductor_dup.wav"); shutil.copy(os.path.join(lib, "Otra.wav"), copy2)
done = {}
answers.append(copias)
expect(is_(FolderImportDialog), lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
expect(is_(ImportReportDialog), lambda d: (done.setdefault("x", 1), d.accept()))
action("Importar carpeta…").trigger(); wait_until(lambda: "x" in done)
dup_track = next(t for t in win.library if t.path == copy2)
win.player.play_queue([dup_track], 0); wait_until(lambda: win.player.is_playing, 3000)
dd2 = {}
def trash_handler(d):
    try:
        idle(d)
        dd2["groups"] = [[os.path.basename(t.path) for t in g.tracks] for g in d._groups]
        parent = d.tree.topLevelItem(0)
        for i in range(parent.childCount()):
            c = parent.child(i)
            c.setCheckState(0, Qt.CheckState.Checked if c.data(0, Qt.ItemDataRole.UserRole).path == copy2 else Qt.CheckState.Unchecked)
        expect(msg("Papelera"), click("Enviar a la papelera"))
        d.btn_trash.click(); idle(d)
        dd2["summary"] = d.banner.text() + " " + d.summary.text()
    finally:
        d.accept(); dd2["done"] = True
expect(is_(DuplicatesDialog), trash_handler)
action("Buscar canciones repetidas…").trigger(); wait_until(lambda: "done" in dd2)
check("Enviar a la papelera una copia que estaba sonando", not os.path.exists(copy2) and all(t.path != copy2 for t in win.library), dd2.get("summary", "")[:140])
check("  el reproductor la soltó (detenido)", not win.player.is_playing)
check("  el original sigue en el disco y en la biblioteca", os.path.exists(os.path.join(lib, "Otra.wav")) and any(t.title == "Otra" for t in win.library))

check("todos los diálogos esperados aparecieron", not pending, pending)
win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.exit(0 if all(results) and not errors else 1)
