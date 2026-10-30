import math, os, struct, sys, tempfile, time, traceback, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_fold_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")

from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMenu, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw
from app.ui.dialogs import FolderImportDialog, ImportReportDialog

results, errors = [], []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

def tone(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(5000*math.sin(i/4))) for i in range(8000*2)))
root = os.path.join(work, "Musica")
tone(os.path.join(root, "Música", "Rock", "80s", "a.wav"))
tone(os.path.join(root, "Música", "Rock", "b.wav"))
tone(os.path.join(root, "Música", "Pop", "c.wav"))
tone(os.path.join(root, "Otra", "d.wav"))

pending = []
def expect(pred, handler): pending.append((pred, handler))
def pump():
    QTimer.singleShot(40, pump)
    w = QApplication.activePopupWidget() or QApplication.activeModalWidget()
    if pending and w is not None and w.isVisible() and pending[0][0](w):
        _, h = pending.pop(0)
        try: h(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, pump)
def is_(cls): return lambda w: isinstance(w, cls)
def pick(label, seen=None):
    def h(menu):
        if seen is not None: seen.extend(a.text() for a in menu.actions())
        for a in menu.actions():
            if a.text().startswith(label):
                menu.setActiveAction(a); QTest.keyClick(menu, Qt.Key.Key_Return); return
        menu.close(); raise AssertionError([a.text() for a in menu.actions()])
    return h
def spin(ms):
    end = time.time() + ms/1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def wait_until(cond, timeout=15000):
    end = time.time() + timeout/1000
    while time.time() < end and not cond():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
    return cond()

answers = []
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: answers.pop(0))
explorer = []
mw.subprocess.Popen = lambda args, *a, **k: explorer.append(args)
db = Database(database_path()); win = mw.MainWindow(db); win.show(); win.activateWindow(); spin(200)
sb, c = win.sidebar, win.content

check("Sin música: sección Carpetas con mensaje", sb.folder_tree.topLevelItemCount() == 0 and sb.empty_folders.isVisible())
done = {}
answers.append(root)
expect(is_(FolderImportDialog), lambda d: d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click())
expect(is_(ImportReportDialog), lambda d: (done.setdefault("x", 1), d.accept()))
sb.btn_add_folder.click(); wait_until(lambda: "x" in done)
check("Botón + de «Carpetas» importa una carpeta", len(win.library) == 4)

def tree_snapshot(item, depth=0):
    out = [("  " * depth) + item.text(0) + (" [abierta]" if item.isExpanded() else "")]
    for i in range(item.childCount()): out += tree_snapshot(item.child(i), depth + 1)
    return out
top = sb.folder_tree.topLevelItem(0)
snap = tree_snapshot(top)
print("     árbol:\n       " + "\n       ".join(snap))
check("Árbol compactado: raíz «Musica (4)» (sin C:\\Users\\…)", sb.folder_tree.topLevelItemCount() == 1 and top.text(0) == "Musica  (4)", top.text(0))
check("  subcarpetas con su cantidad", [top.child(i).text(0) for i in range(top.childCount())] == ["Música  (3)", "Otra  (1)"])
check("  la raíz aparece abierta", top.isExpanded())
check("  sección sin mensaje vacío", not sb.empty_folders.isVisible())

def find(name):
    for item in sb._folder_items():
        if item.text(0).startswith(name + "  ("): return item
musica = find("Música"); musica.setExpanded(True); spin(600)
rock = find("Rock")
rect = sb.folder_tree.visualItemRect(rock)
QTest.mouseClick(sb.folder_tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()); spin(150)
check("Clic en «Rock» → muestra sus canciones (con subcarpetas)", c.title.text() == "Rock" and sorted(t.title for t in c.visible_tracks()) == ["a", "b"],
      (c.title.text(), [t.title for t in c.visible_tracks()]))
check("  subtítulo con cantidad y duración", "2 canciones" in c.subtitle.text() and "subcarpetas" in c.subtitle.text(), c.subtitle.text())
check("  ruta de navegación visible", c.breadcrumb.isVisible() and "Musica" in c.breadcrumb.text() and "Música" in c.breadcrumb.text(), c.breadcrumb.text()[:200])
check("  solo la carpeta queda resaltada", rock.isSelected() and sb.library_list.currentRow() == -1 and sb.playlist_list.currentRow() == -1)
check("  current_view = carpeta", sb.current_view() == ("folder", rock.data(0, Qt.ItemDataRole.UserRole)))

c.breadcrumb.linkActivated.emit(musica.data(0, Qt.ItemDataRole.UserRole)); spin(150)
check("Clic en la ruta «Música» → sube a esa carpeta", c.title.text() == "Música" and len(c.visible_tracks()) == 3 and musica.isSelected())

sb.select_library("songs"); spin(100)
check("Elegir «Canciones» quita el resaltado de carpetas", sb.current_folder() is None and c.title.text() == "Canciones")

dpos = sb.folder_tree.visualItemRect(find("Otra")).center()
QTest.mouseClick(sb.folder_tree.viewport(), Qt.MouseButton.LeftButton, pos=dpos); QTest.mouseDClick(sb.folder_tree.viewport(), Qt.MouseButton.LeftButton, pos=dpos); spin(500)
check("Doble clic en carpeta → la reproduce", win.player.is_playing and win.player.current_track.title == "d",
      win.player.current_track and win.player.current_track.title)

pos_m = sb.folder_tree.visualItemRect(find("Música")).center()
seen = []
expect(is_(QMenu), pick("Reproducir en aleatorio", seen))
sb._folder_menu(pos_m); spin(400)
check("Menú carpeta → Reproducir en aleatorio (la muestra mezclada y suena la primera de la vista)",
      c.title.text() == "Música" and win.player.current_track.title in ("a", "b", "c")
      and win.player.current_track.id == c.visible_tracks()[0].id)
check("  opciones del menú", all(any(s.startswith(x) for s in seen) for x in
      ["Reproducir carpeta", "Reproducir en aleatorio", "Agregar carpeta a playlist", "Mostrar en el Explorador",
       "Buscar música nueva", "Expandir todo", "Contraer todo", "Quitar carpeta de la biblioteca", "Agregar otra carpeta"]), seen)
win.player.set_shuffle(False)

expect(is_(QMenu), pick("Reproducir carpeta"))
sb._folder_menu(pos_m); spin(400)
check("Menú carpeta → Reproducir carpeta (orden de carpetas: Pop antes que Rock)", win.player.current_track.title == "c", win.player.current_track.title)

p = db.create_playlist("Desde carpeta"); sb.set_playlists(db.playlists())
expect(is_(QMenu), pick("Agregar carpeta a playlist"))
expect(is_(QMenu), pick("Desde carpeta"))
sb._folder_menu(pos_m); spin(300)
check("Menú carpeta → Agregar carpeta a playlist", db.playlist(p.id).track_count == 3)

expect(is_(QMenu), pick("Mostrar en el Explorador"))
sb._folder_menu(pos_m); spin(100)
check("Menú carpeta → Mostrar en el Explorador", explorer and os.path.basename(explorer[-1][0]).lower() == "explorer.exe" and os.path.isabs(explorer[-1][0]) and explorer[-1][1].endswith("Música"), explorer[-1:])

sb.select_folder(musica.data(0, Qt.ItemDataRole.UserRole)); spin(100)
expect(is_(QMenu), pick("Contraer todo"))
sb._folder_menu(pos_m); spin(100)
check("Menú carpeta → Contraer todo", not find("Música").isExpanded())
expect(is_(QMenu), pick("Expandir todo"))
sb._folder_menu(sb.folder_tree.visualItemRect(find("Música")).center()); spin(100)
check("Menú carpeta → Expandir todo", find("Música").isExpanded() and find("Rock").isExpanded())

tone(os.path.join(root, "Música", "Rock", "nueva.wav"))
done = {}
expect(is_(QMenu), pick("Buscar música nueva"))
expect(is_(ImportReportDialog), lambda d: (done.setdefault("x", 1), d.accept()))
sb._folder_menu(sb.folder_tree.visualItemRect(find("Música")).center()); wait_until(lambda: "x" in done)
spin(200)
check("Menú carpeta → Buscar música nueva (solo agrega la nueva)", len(win.library) == 5 and find("Rock").text(0) == "Rock  (3)", find("Rock").text(0))
check("  el árbol conserva carpetas abiertas y la selección", find("Rock").isExpanded() and find("Música").isSelected() and c.title.text() == "Música")

# Quitar todas las canciones de la carpeta que se está viendo → vuelve a Canciones
otra = find("Otra"); sb.folder_tree.setCurrentItem(otra); spin(100)
win.player.stop()
win._remove_from_library_confirmed = None
mw.ask = lambda *a, **k: 0
win._remove_from_library(c.visible_tracks()); spin(150)
check("Si la carpeta se queda sin canciones desaparece y se vuelve a Canciones",
      find("Otra") is None and sb.current_view() == ("songs", None) and c.title.text() == "Canciones", (sb.current_view(), c.title.text()))

win.grab().save(os.path.join(os.path.dirname(__file__), "folders.png"))
check("todos los diálogos/menús esperados aparecieron", not pending, pending)
win.close(); QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
if errors: print("\n".join(errors))
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas, {len(errors)} errores")
sys.exit(0 if all(results) and not errors else 1)
