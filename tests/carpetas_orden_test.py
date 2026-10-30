"""1.13.0: quitar una carpeta de la biblioteca sin tocar sus archivos, y ordenar a mano «Canciones» y las playlists
(se guarda y la reproducción lo sigue). Todo en carpetas temporales."""
import math, os, sqlite3, struct, sys, tempfile, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_carpetas_orden_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import file_manager
from app.config import database_path
from app.database import SCHEMA_VERSION, Database
from app.importer import scan_file
from app.ui.track_model import move_rows

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs=4):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 7))) for i in range(8000 * secs)))
    return path

print("[Mover filas]")
check("bajar una al final", move_rows(list("abcd"), [0], 4) == list("bcda"))
check("subir una al principio", move_rows(list("abcd"), [3], 0) == list("dabc"))
check("varias separadas quedan juntas, en su orden", move_rows(list("abcdef"), [1, 4], 3) == list("acbedf"), move_rows(list("abcdef"), [1, 4], 3))
check("soltar en su mismo lugar no cambia nada", move_rows(list("abcd"), [1], 2) == list("abcd"))
check("filas fuera de rango se ignoran", move_rows(list("abc"), [7], 0) == list("abc"))

print("[Base de datos]")
rock = os.path.join(work, "Musica", "Rock")
pop = os.path.join(work, "Musica", "Pop")
otra = os.path.join(work, "Otra")
files = ([tone(os.path.join(rock, f"r{n}.wav")) for n in range(4)] + [tone(os.path.join(rock, "80s", "r80.wav"))]
         + [tone(os.path.join(pop, f"p{n}.wav")) for n in range(3)] + [tone(os.path.join(otra, "o.wav"))])
os.makedirs(os.path.dirname(database_path()), exist_ok=True)
db = Database(database_path())
db.add_tracks([scan_file(p)[0] for p in files])
# Simula una base de la versión anterior (sin orden manual) y la vuelve a abrir.
db.conn.execute("ALTER TABLE tracks DROP COLUMN sort_pos"); db.conn.execute("DROP TABLE view_order"); db.conn.execute("PRAGMA user_version = 2"); db.conn.commit(); db.close()
db = Database(database_path())
check("una base anterior se actualiza sin perder canciones", len(db.all_tracks()) == len(files)
      and db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 4
      and db.view_order("recent") == {})
before = [t.id for t in db.all_tracks()]
check("sin orden manual, «Canciones» queda como siempre", not db.has_library_order())
custom = list(reversed(before))
db.set_library_order(custom)
check("el orden manual se guarda y se lee", [t.id for t in db.all_tracks()] == custom)
nuevo = tone(os.path.join(otra, "nueva.wav"))
db.add_tracks([scan_file(nuevo)[0]])
after = [t.id for t in db.all_tracks()]
check("una canción importada después va al final", after[:-1] == custom and after[-1] == db.track_id_for_path(nuevo))
db.clear_library_order()
check("«Volver al orden de siempre» lo borra", not db.has_library_order())

pl = db.create_playlist("Mezcla")
rid = db.track_id_for_path(files[0]); pid_ = db.track_id_for_path(files[5]); oid = db.track_id_for_path(files[-1])
db.add_to_playlist(pl.id, [rid, pid_, oid, rid], allow_duplicates=True)
entries = [t.entry_id for t in db.playlist_tracks(pl.id)]
db.reorder_playlist(pl.id, [entries[3], entries[2], entries[0], entries[1]])
check("una playlist se reordena por entrada (la repetida se mueve sola)",
      [t.entry_id for t in db.playlist_tracks(pl.id)] == [entries[3], entries[2], entries[0], entries[1]])
try:
    db.reorder_playlist(pl.id, entries[:3]); bad = False
except ValueError:
    bad = True
check("  si no nombra todas las entradas, no toca nada", bad and len(db.playlist_tracks(pl.id)) == 4)
check("cuenta las entradas de playlists de unas canciones", db.playlist_entries_of([rid]) == 2 and db.playlist_entries_of([oid, pid_]) == 2)

print("[Ventana: orden manual]")
from app.ui import main_window as mw
asked = []
def answer_with(index):
    def fake(parent, title, text, buttons, icon=None, informative=""):
        asked.append((title, text, informative, [b[0] for b in buttons])); return index
    mw.ask = fake
win = mw.MainWindow(db); win.show(); spin(300)
c = win.content
win.sidebar.select_library("songs"); spin(150)
check("en «Canciones» se puede arrastrar", c.table.reorderable() and c.table.dragEnabled())
shown = [t.id for t in c.visible_tracks()]
c.table.selectRow(0); c.table.setFocus(); spin(50)
QTest.keyClick(c.table, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier); spin(100)
expected = [shown[1], shown[0]] + shown[2:]
check("Alt+↓ baja la canción seleccionada", [t.id for t in c.visible_tracks()] == expected)
check("  y queda guardado", [t.id for t in db.all_tracks()] == expected and db.has_library_order())
check("  el resumen dice «orden personalizado»", "orden personalizado" in c.subtitle.text(), c.subtitle.text())
check("  la canción movida sigue seleccionada", [t.id for t in c.selected_tracks()] == [shown[0]])
c.table.sortByColumn(0, Qt.SortOrder.AscendingOrder); spin(50)
visible = [t.id for t in c.visible_tracks()]
c.table.rows_dropped.emit([len(visible) - 1], 0); spin(100)
check("arrastrar con la tabla ordenada por columna toma ese orden visible como el manual",
      [t.id for t in db.all_tracks()] == [visible[-1]] + visible[:-1])
check("  y vuelve al orden manual (sin columna marcada)", c.proxy.sortColumn() == -1)

win._on_play_requested(c.visible_tracks(), 0); spin(300)
playing = win.player.current_track
c.table.clearSelection(); c.table.selectRow(len(c.visible_tracks()) - 1)
c.table.rows_dropped.emit([len(c.visible_tracks()) - 1], 1); spin(100)
moved = c.visible_tracks()[1]
check("si la lista es la que suena, sigue la misma canción", win.player.current_track.id == playing.id)
win.player.next(); spin(300)
check("  y la siguiente es la que se puso detrás", win.player.current_track and win.player.current_track.id == moved.id,
      win.player.current_track and win.player.current_track.title)
win.player.stop()

win.sidebar.select_playlist(pl.id); spin(150)
check("en una playlist también se puede arrastrar", c.table.reorderable())
first = c.visible_tracks()[0].entry_id
c.table.clearSelection(); c.table.selectRow(0)
QTest.keyClick(c.table, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier); spin(100)
check("Alt+↓ en la playlist queda guardado", [t.entry_id for t in db.playlist_tracks(pl.id)][1] == first)

win.sidebar.select_library("songs"); spin(150)
answer_with(0); win._reset_order(); spin(150)
check("«Volver al orden de siempre» pregunta y lo restablece", not db.has_library_order() and "orden" in asked[-1][1])

print("[Ventana: cada vista con su propio orden]")
def nudge_down_first():
    c.table.clearSelection(); c.table.selectRow(0)
    c._nudge_selected(1); spin(100)  # lo mismo que «Bajar» del clic derecho (Alt+↓ ya se prueba en «Canciones»)

win.sidebar.select_folder(rock); spin(150)
check("en una carpeta se puede ordenar", c.table.reorderable())
shown = [t.id for t in c.visible_tracks()]
nudge_down_first()
want = [shown[1], shown[0]] + shown[2:]
check("Alt+↓ en la carpeta queda guardado para esa carpeta",
      [t.id for t in win._folder_tracks(rock)] == want and "orden personalizado" in c.subtitle.text())
check("  «Canciones» no cambia", not db.has_library_order())
win.sidebar.select_folder(os.path.join(rock, "80s")); spin(100)
win.sidebar.select_folder(rock); spin(150)
check("  al volver a la carpeta sigue igual", [t.id for t in c.visible_tracks()] == want)
win._on_play_requested(c.visible_tracks(), 0); spin(300)
check("  «Reproducir» sigue ese orden", win.player.current_track.id == want[0]); win.player.stop()
win._play_folder(rock, False); spin(300)
check("  y también el doble clic / menú de la carpeta", win.player.current_track.id == want[0]); win.player.stop()

win.sidebar.select_library("artists"); spin(150)
check("en Artistas se puede ordenar cada artista", c.table.reorderable() and c.current_group_label() is not None)
group = c.current_group_label(); shown = [t.id for t in c.visible_tracks()]
nudge_down_first()
from app.utils import normalize_text
saved = db.view_order(f"artist:{normalize_text(group)}")
check("  se guarda el orden de ese artista", sorted(saved, key=saved.get) == [shown[1], shown[0]] + shown[2:])
win.sidebar.select_library("albums"); spin(100); win.sidebar.select_library("artists"); spin(150)
check("  y se ve igual al volver", [t.id for t in c.visible_tracks()] == [shown[1], shown[0]] + shown[2:])

win.sidebar.select_library("recent"); spin(150)
check("en Recientes se puede ordenar", c.table.reorderable())
shown = [t.id for t in c.visible_tracks()]
nudge_down_first()
check("  se guarda", [t.id for t in c.visible_tracks()] == [shown[1], shown[0]] + shown[2:] and db.view_order("recent"))

print("[Reabrir el programa]")
folder_before = [t.id for t in win._folder_tracks(rock)]
win.close(); spin(100); db.close()
db = Database(database_path())
win = mw.MainWindow(db); win.show(); spin(300); c = win.content
win.sidebar.select_folder(rock); spin(150)
check("el orden de la carpeta sigue después de cerrar y abrir", [t.id for t in c.visible_tracks()] == folder_before)
win.sidebar.select_library("recent"); spin(150)
check("  y el de Recientes", [t.id for t in c.visible_tracks()][:2] == [shown[1], shown[0]])

print("[Aleatorio]")
win.sidebar.select_library("songs"); spin(150)
before = [t.id for t in c.visible_tracks()]
import random as _random
_random.seed(7)
c.btn_shuffle.click(); spin(300)
after = [t.id for t in c.visible_tracks()]
check("«Aleatorio» mezcla a la vista las canciones mostradas", sorted(after) == sorted(before) and after != before)
check("  suena la primera de la lista mezclada", win.player.current_track and win.player.current_track.id == after[0])
win.player.next(); spin(300)
check("  y después la segunda (sigue lo que se ve)", win.player.current_track.id == after[1])
check("  el resumen lo dice", "mezcladas al azar" in c.subtitle.text())
check("  no pisa el orden guardado", not db.has_library_order())
win.player.stop()

print("[Ventana: quitar una carpeta]")
seen = []
def record_menu():
    menu = QApplication.activePopupWidget()
    if not isinstance(menu, QMenu) or not any(a.text() == "Reproducir carpeta" for a in menu.actions()):
        if isinstance(menu, QMenu): menu.close()  # otro menú que quedó abierto: no es el de la carpeta
        QTimer.singleShot(50, record_menu); return
    seen.extend(a.text() for a in menu.actions()); menu.close()
QTimer.singleShot(100, record_menu)
item = next(i for i in win.sidebar._folder_items() if i.data(0, Qt.ItemDataRole.UserRole).endswith("Rock"))
win.sidebar._folder_menu(win.sidebar.folder_tree.visualItemRect(item).center()); spin(100)
check("el menú de la carpeta tiene «Quitar carpeta de la biblioteca…» aparte de la Papelera",
      "Quitar carpeta de la biblioteca…" in seen and "Enviar carpeta a la Papelera…" in seen, seen)
win.sidebar.select_library("songs"); spin(100)
check("el botón «−» se apaga sin carpeta elegida", not win.sidebar.btn_unlink_folder.isEnabled())
win.sidebar.select_folder(item.data(0, Qt.ItemDataRole.UserRole)); spin(100)
check("  y se enciende al elegir una", win.sidebar.btn_unlink_folder.isEnabled())

trash_calls = []
file_manager.trash_folder = lambda *a, **k: trash_calls.append(a)
win.ops.trash_folder = lambda *a, **k: trash_calls.append(a)
win.ops.trash_files = lambda *a, **k: trash_calls.append(a)
total = len(db.all_tracks())
answer_with(1)  # Cancelar
win.sidebar.btn_unlink_folder.click(); spin(150)
check("Cancelar no quita nada", len(db.all_tracks()) == total)
q = asked[-1]
check("la pregunta dice cuántas, las playlists y que los archivos no se borran",
      "5 canciones" in q[2] and "playlists" in q[2] and "NO se borran" in q[2], q[2])
answer_with(0)
win.sidebar.btn_unlink_folder.click(); spin(300)
paths = {os.path.normcase(t.path) for t in db.all_tracks()}
check("quita de la biblioteca las de la carpeta y sus subcarpetas",
      len(db.all_tracks()) == total - 5 and not any(os.path.normcase(rock) in p for p in paths))
check("  las de otras carpetas siguen", os.path.normcase(files[5]) in paths and os.path.normcase(files[-1]) in paths)
check("  los archivos siguen en el disco", all(os.path.isfile(p) for p in files))
check("  no se usó la Papelera", not trash_calls)
check("  la carpeta ya no está en el árbol",
      not any(i.data(0, Qt.ItemDataRole.UserRole).endswith("Rock") for i in win.sidebar._folder_items()))
check("  y se quitó de la playlist (como «Quitar de la biblioteca»)",
      sorted(t.id for t in db.playlist_tracks(pl.id)) == sorted([pid_, oid]))

known = db.known_path_keys()
again = [s for s in (scan_file(p)[0] for p in files[:5]) if s.key not in known]
added, _dups = db.add_tracks(again); win._reload_library()
check("se puede volver a agregar la carpeta (la importación no las da por conocidas)",
      len(again) == 5 and len(added) == 5 and len(db.all_tracks()) == total)

print("[Qué ver de cada canción]")
from app.ui.track_model import COL_ALBUM, COL_ARTIST, COL_DURATION, COL_FILE, COL_GENRE, COL_TITLE
from app.ui.dialogs import PreferencesDialog
win.sidebar.select_library("songs"); spin(100)
hidden = lambda col: c.table.isColumnHidden(col)
check("de fábrica: título, artista, álbum, duración y carátula",
      not hidden(COL_TITLE) and not hidden(COL_ARTIST) and not hidden(COL_ALBUM) and not hidden(COL_DURATION)
      and hidden(COL_GENRE) and hidden(COL_FILE) and "cover" in c.columns())
dialog = PreferencesDialog(win.prefs, win)
check("Preferencias tiene la sección «Canciones» con el título fijo",
      any(dialog.nav.item(i).text() == "Canciones" for i in range(dialog.nav.count())) and "album" in dialog.column_boxes)
win.show(); dialog.show(); spin(150)
screen = win.screen().availableGeometry()
check("Preferencias se abre centrada en la pantalla",
      abs(dialog.frameGeometry().center().x() - screen.center().x()) <= 2
      and abs(dialog.frameGeometry().center().y() - screen.center().y()) <= 2,
      (dialog.frameGeometry().center(), screen.center()))
check("  con secciones a la izquierda (una página a la vista)", dialog.nav.count() >= 5 and dialog.pages.count() == dialog.nav.count())
dialog.hide()
dialog.column_boxes["album"].setChecked(False); dialog.column_boxes["genre"].setChecked(True)
dialog.column_boxes["cover"].setChecked(False)
dialog._save(); win.content.set_columns(win.prefs.song_columns); spin(100)
check("al guardar: se oculta el álbum y se ve el género", hidden(COL_ALBUM) and not hidden(COL_GENRE) and not hidden(COL_TITLE))
check("  sin carátulas las filas son más bajas", c.table.verticalHeader().defaultSectionSize() < 40
      and c.model.index(0, COL_TITLE).data(Qt.ItemDataRole.DecorationRole) is None)
c._toggle_column("file", True); spin(50)
check("clic derecho en los encabezados también lo cambia y se guarda",
      not hidden(COL_FILE) and "file" in win.prefs.song_columns
      and c.model.index(0, COL_FILE).data() == os.path.basename(c.model.track_at(0).path))
win.close(); spin(100); db.close()
db = Database(database_path()); win = mw.MainWindow(db); win.show(); spin(200); c = win.content
check("  y sigue así al abrir de nuevo el programa", hidden(COL_ALBUM) and not hidden(COL_GENRE) and not hidden(COL_FILE))

win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
