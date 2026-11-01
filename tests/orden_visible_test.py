"""El orden de cada lista se ve y se controla: selector «Orden:», número de cada fila y aviso de cómo va a sonar.
Cada lista recuerda el suyo al cerrar el programa, y lo que suena lo sigue. Todo en carpetas temporales."""
import math, os, struct, sys, tempfile, time, wave
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
work = tempfile.mkdtemp(prefix="mp_orden_visible_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.importer import scan_file
from app.ui import main_window as mw
from app.ui.track_model import COL_ARTIST, COL_DURATION, COL_TITLE

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 7))) for i in range(int(8000 * secs))))
    return path

music = os.path.join(work, "Musica")
data = [("Zeta", "Ana", 3), ("Alfa", "Carlos", 1), ("Media", "Beto", 2), ("Beta", "Ana", 4)]
db = Database(database_path())
for title, artist, secs in data:
    db.add_tracks([scan_file(tone(os.path.join(music, f"{title}.wav"), secs))[0]])
    tid = db.track_id_for_path(os.path.join(music, f"{title}.wav"))
    db.update_track_info(tid, title, artist, "Disco")
win = mw.MainWindow(db); win.show(); win.player.set_volume(0); spin(300)
c = win.content
titles = lambda: [t.title for t in c.visible_tracks()]
combo = c.order_combo
def choose(mode):
    combo.setCurrentIndex(combo.findData(mode)); c._on_order_chosen(combo.currentIndex()); spin(100)

print("[Se ve en qué orden está]")
win.sidebar.select_library("songs"); spin(150)
check("el selector «Orden:» dice el orden de siempre", combo.currentText().startswith("Alfabético") and combo.isVisible(), combo.currentText())
check("  y la lista está en ese orden (por título)", titles() == ["Alfa", "Beta", "Media", "Zeta"], titles())
check("  el aviso dice cómo suena", c.order_note.text() == "Suena de arriba abajo", c.order_note.text())
check("cada fila muestra su número en la secuencia", c.table.verticalHeader().isVisible()
      and [c.proxy.headerData(i, Qt.Orientation.Vertical) for i in range(3)] == [1, 2, 3])

print("[Se elige desde el selector]")
choose("title_asc")
check("Título (A–Z): la lista queda así", titles() == ["Alfa", "Beta", "Media", "Zeta"], titles())
check("  la flecha del encabezado lo acompaña", c.proxy.sortColumn() == COL_TITLE)
choose("duration_desc")
check("Duración (largas primero)", titles() == ["Beta", "Zeta", "Media", "Alfa"], titles())
win._on_play_requested(c.visible_tracks(), 0); spin(300)
check("  «Reproducir» suena en ese orden", win.player.current_track.title == "Beta")
choose("title_asc")
check("  cambiar el orden con la lista sonando: la que sigue es la del orden nuevo",
      win.player.current_track.title == "Beta" and win.player._queue[win.player._order[win.player._pos + 1]].title == "Media",
      win.player._queue[win.player._order[win.player._pos + 1]].title)
win.player.stop()
choose("random")
check("Aleatorio desde el selector: la lista se ve mezclada", sorted(titles()) == ["Alfa", "Beta", "Media", "Zeta"] and combo.currentData() == "random")
mix = titles()
win._refresh_view(); spin(100)
check("  refrescar la lista (renombrar un archivo, etc.) no la vuelve a mezclar", titles() == mix, titles())
seen = set()
for _ in range(8):
    combo.setCurrentIndex(combo.findData("random")); c._on_order_chosen(combo.currentIndex()); spin(30); seen.add(tuple(titles()))
check("  elegir «Aleatorio» otra vez hace otra mezcla", len(seen) > 1, len(seen))

print("[Clic en un encabezado]")
c.table.horizontalHeader().setSortIndicator(COL_ARTIST, Qt.SortOrder.AscendingOrder); spin(100)
check("ordenar por una columna: el selector lo dice", combo.currentData() == "artist_asc", combo.currentText())
check("  y queda guardado para esa lista", win.prefs.order_mode("songs") == "artist_asc")

print("[El aleatorio de la barra]")
win.player.set_shuffle(True); spin(50)
check("con el aleatorio de la barra encendido, el aviso dice que suena al azar", "suena al azar" in c.order_note.text(), c.order_note.text())
choose("title_desc")
check("  al elegir un orden se apaga (manda el orden elegido)", not win.player.shuffle and c.order_note.text() == "Suena de arriba abajo")

print("[Mi orden]")
choose("default")
check("sin orden a mano todavía, «Mi orden» no aparece", combo.findData("manual") < 0)
before = titles()
c.table.selectRow(0); c._nudge_selected(1); spin(100)
check("mover una canción pasa a «Mi orden» y lo muestra", combo.currentData() == "manual" and combo.currentText() == "Mi orden", combo.currentText())
mine = titles()
check("  y se guarda", mine == [before[1], before[0]] + before[2:] and db.has_library_order(), mine)
choose("title_asc")
check("elegir otro orden no borra «Mi orden»", db.has_library_order() and titles() == ["Alfa", "Beta", "Media", "Zeta"])
choose("manual")
check("  se puede volver a él cuando quieras", titles() == mine, titles())

print("[Cada lista recuerda el suyo]")
folder = music
win.sidebar.select_folder(folder); spin(150)
check("la carpeta tiene su propio orden (no el de «Canciones»)", combo.currentData() == "default" and combo.currentText() == "Por nombre de archivo", combo.currentText())
choose("duration_asc")
check("  se elige uno para ella", titles() == ["Alfa", "Media", "Zeta", "Beta"], titles())
win.sidebar.select_library("songs"); spin(150)
check("  «Canciones» sigue con el suyo", combo.currentData() == "manual" and titles() == mine)
pl = db.create_playlist("Lista"); db.add_to_playlist(pl.id, [t.id for t in c.visible_tracks()]); win.sidebar.set_playlists(db.playlists())
win.sidebar.select_playlist(pl.id); spin(150)
check("una playlist está en «Mi orden» (no ofrece otro predeterminado)", combo.currentData() == "manual" and combo.findData("default") < 0)
win._play_playlist(pl.id); spin(200)
check("  reproducirla desde el panel izquierdo sigue lo que se ve", win.player.current_track.title == c.visible_tracks()[0].title); win.player.stop()

win.close(); spin(100); db.close()
db = Database(database_path()); win = mw.MainWindow(db); win.show(); win.player.set_volume(0); spin(300); c = win.content; combo = c.order_combo
win.sidebar.select_folder(folder); spin(150)
check("después de cerrar y abrir, la carpeta sigue en su orden", combo.currentData() == "duration_asc" and titles() == ["Alfa", "Media", "Zeta", "Beta"], titles())
win.sidebar.select_library("songs"); spin(150)
check("  y «Canciones» en «Mi orden»", combo.currentData() == "manual" and titles() == mine, titles())

print("[Mover a una posición exacta]")
win.sidebar.select_library("songs"); spin(100)
start = titles()
c.table.clearSelection(); c.table.selectRow(3); c._move_to_position(1); spin(50)
check("«Mover al principio»: la última pasa a ser la 1", titles() == [start[3]] + start[:3] and combo.currentData() == "manual", titles())
now = titles()
c.table.clearSelection(); c.table.selectRow(0); c._move_to_position(len(now)); spin(50)
check("«Mover al final»", titles() == now[1:] + now[:1], titles())
now = titles()
c.table.clearSelection(); c.table.selectRow(0); c._move_to_position(3); spin(50)
check("«Mover a la posición 3»: queda en el número 3", titles()[2] == now[0] and sorted(titles()) == sorted(now), titles())

print("[Ordenar como espera una persona]")
from app.utils import natural_key
messy = ["Zeta", "¡Aleluya!", "10 Mandamientos", "2 Corazones", "Ángel", "(En vivo) Bendito", "eco", "Ñandú", "1 Alabanza"]
check("signos, tildes y números no desordenan los títulos", sorted(messy, key=natural_key) ==
      ["1 Alabanza", "2 Corazones", "10 Mandamientos", "¡Aleluya!", "Ángel", "eco", "(En vivo) Bendito", "Ñandú", "Zeta"], sorted(messy, key=natural_key))

print("[Caracteres especiales al inicio del título]")
from app.utils import clean_title
cases = {
    "►►cuando mi pueblo ora": "cuando mi pueblo ora",
    "🔥El Infierno Tiembla": "El Infierno Tiembla",
    "| EL PODEROSO DE ISRAEL": "EL PODEROSO DE ISRAEL",
    "[Vídeo Oficial] Cuando A": "Vídeo Oficial Cuando A",
    "(PISTA) CRYSTAL LEWIS": "PISTA CRYSTAL LEWIS",
    "¿A quién tengo yo?": "¿A quién tengo yo?",
    "¡Aleluya!": "¡Aleluya!",
    "►► ¿Quién como Tú?": "¿Quién como Tú?",
    "(¡En vivo!) Santo": "¡En vivo! Santo",
    "06. Con tu Sangre": "06. Con tu Sangre",
    "A Dios (en vivo)": "A Dios (en vivo)",
    "♪♪♪": "♪♪♪",
}
bad = {k: clean_title(k) for k, v in cases.items() if clean_title(k) != v}
check("se quitan del principio; los números y el resto del título quedan; solo signos, igual", not bad, bad)
marked = tone(os.path.join(music, "marcada.wav"), 1)
item = scan_file(marked)[0]; item.metadata.title = "►►Nueva Marcada"; db.add_tracks([item])
tid = db.track_id_for_path(marked)
check("una canción importada entra limpia", db.conn.execute("select title from tracks where id=?", (tid,)).fetchone()[0] == "Nueva Marcada")
db.conn.execute("update tracks set title='🔥Vieja Marcada' where id=?", (tid,)); db.conn.commit()
win.settings.remove("library/titles_cleaned"); bytes_before = open(marked, "rb").read()
win._clean_saved_titles(); win._reload_library()
check("las ya guardadas se limpian una vez, sin tocar el archivo",
      db.conn.execute("select title from tracks where id=?", (tid,)).fetchone()[0] == "Vieja Marcada"
      and open(marked, "rb").read() == bytes_before and win.settings.value("library/titles_cleaned", type=bool))
db.conn.execute("update tracks set title='¡Elegido a mano!' where id=?", (tid,)); db.conn.commit()
win._clean_saved_titles()
check("  no se repite: lo que cambies después a mano se respeta",
      db.conn.execute("select title from tracks where id=?", (tid,)).fetchone()[0] == "¡Elegido a mano!")

print("[Los signos «¿» y «¡» se conservan y se recuperan]")
import sqlite3
from app import backup
check("  y ordenan por la primera letra", sorted(["Beta", "¿Alfa?", "Zeta"], key=natural_key) == ["¿Alfa?", "Beta", "Zeta"])
db.conn.execute("update tracks set title='¿Quién sabe?' where id=?", (tid,)); db.conn.commit()
other = db.track_id_for_path(tracks_paths[0]) if (tracks_paths := [t.path for t in db.all_tracks() if t.id != tid]) else None
db.conn.execute("update tracks set title='¡Santo!' where id=?", (other,)); db.conn.commit()
saved = backup.create_backup(db.conn, "antes-de-limpiar-titulos")
db.conn.execute("update tracks set title='Quién sabe?' where id=?", (tid,))
db.conn.execute("update tracks set title='Lo cambié a mano' where id=?", (other,)); db.conn.commit()
win.settings.remove("library/opening_marks_restored")
win._restore_opening_marks()
title_of = lambda i: db.conn.execute("select title from tracks where id=?", (i,)).fetchone()[0]
check("la versión anterior los quitó: el signo vuelve desde el respaldo", title_of(tid) == "¿Quién sabe?", title_of(tid))
check("  lo cambiado a mano después no se toca", title_of(other) == "Lo cambié a mano", title_of(other))
db.conn.execute("update tracks set title='Quién sabe?' where id=?", (tid,)); db.conn.commit()
win._restore_opening_marks()
check("  se recupera una sola vez", title_of(tid) == "Quién sabe?" and win.settings.value("library/opening_marks_restored", type=bool))
db.conn.execute("update tracks set title='¿Sigue?' where id=?", (tid,)); db.conn.commit()
win.settings.remove("library/titles_cleaned"); win._clean_saved_titles()
check("  la limpieza ya no se los lleva", title_of(tid) == "¿Sigue?", title_of(tid))

print("[Preferencias]")
c._toggle_column("number", False); spin(50)
check("el número de las filas se puede ocultar", not c.table.verticalHeader().isVisible() and "number" not in win.prefs.song_columns)
win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
