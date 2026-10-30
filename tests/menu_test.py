"""Prueba exhaustiva de cada opción de menú, menú contextual y botón, con diálogos reales."""
import math, os, shutil, struct, sys, tempfile, time, traceback, wave

sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_menu_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QDialogButtonBox, QFileDialog, QLabel, QMenu, QMessageBox,
                               QTreeWidget)

app = QApplication(sys.argv)
app.setOrganizationName("ReproductorMusicaTest")  # no tocar los ajustes reales del usuario
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw
from app.ui.dialogs import FolderImportDialog, ImportReportDialog, PlaylistNameDialog
from app.ui import theme
from app.ui.track_model import COL_ACTION
theme.apply(app, "auto")

# ---------------------------------------------------------------- archivos de prueba (tonos generados)
music = os.path.join(work, "Música"); sub = os.path.join(music, "Subcarpeta"); os.makedirs(sub)

def tone(path, freq, secs=6):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / 8000))) for i in range(8000 * secs)))

for name, f in (("A tono.wav", 330), ("B tono.wav", 440), ("C tono.wav", 550)):
    tone(os.path.join(music, name), f)
tone(os.path.join(sub, "D sub.wav"), 660)
extra = os.path.join(work, "Sueltos"); os.makedirs(extra)
tagged = os.path.join(extra, "etiquetado.wav"); tone(tagged, 700)
tone(os.path.join(extra, "suelto.wav"), 800)
open(os.path.join(extra, "roto.mp3"), "wb").write(b"no es audio" * 50)
open(os.path.join(extra, "notas.txt"), "w").write("x")

# Etiquetas ID3 + carátula dentro del WAV
from mutagen.id3 import APIC, TALB, TCON, TIT2, TPE1
from mutagen.wave import WAVE
img = QImage(400, 400, QImage.Format.Format_RGB32); img.fill(QColor("#3366cc"))
ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG"); buf.close()
wf = WAVE(tagged); wf.add_tags()
wf.tags.add(TIT2(encoding=3, text="Canción etiquetada")); wf.tags.add(TPE1(encoding=3, text="Artista Prueba"))
wf.tags.add(TALB(encoding=3, text="Álbum Prueba")); wf.tags.add(TCON(encoding=3, text="Rock"))
wf.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=bytes(ba.data()))); wf.save()

# ---------------------------------------------------------------- utilidades
results, errors = [], []
sys.excepthook = lambda t, v, tb: errors.append("".join(traceback.format_exception(t, v, tb)))

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")

def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)

def wait_until(cond, timeout=10000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        if cond(): return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
    return cond()

pending = []  # cola de (predicado, manejador) para diálogos y menús emergentes
def expect(pred, handler): pending.append((pred, handler))
def _pump():
    QTimer.singleShot(40, _pump)
    if not pending: return
    w = QApplication.activePopupWidget() or QApplication.activeModalWidget()
    pred, handler = pending[0]
    if w is not None and w.isVisible() and pred(w):
        pending.pop(0)
        try: handler(w)
        except Exception: errors.append(traceback.format_exc())
QTimer.singleShot(40, _pump)

def is_(cls): return lambda w: isinstance(w, cls)
def msgbox_with(text): return lambda w: isinstance(w, QMessageBox) and text in (w.text() + w.informativeText())

def click_msg(label):
    def h(box):
        for b in box.buttons():
            if b.text().replace("&", "") == label: b.click(); return
        raise AssertionError(f"botón {label!r} no está en {[b.text() for b in box.buttons()]}")
    return h

def pick_menu(label, seen=None):
    def h(menu):
        texts = [a.text() for a in menu.actions()]
        if seen is not None: seen.extend(texts)
        for a in menu.actions():
            if a.text().replace("&", "").startswith(label) and a.isEnabled():
                menu.setActiveAction(a); QTest.keyClick(menu, Qt.Key.Key_Return); return
        menu.close(); raise AssertionError(f"opción {label!r} no está en {texts}")
    return h

def name_dialog(text, expect_error=None, then_cancel=False):
    def h(d):
        d.edit.setText(text)
        d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        if expect_error is not None:
            check(f"  diálogo nombre «{text}» rechazado", d.isVisible() and expect_error in d.error.text(), d.error.text())
            if then_cancel: d.reject()
    return h

def menu_action(menu_title, text):
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == menu_title:
            m = top.menu(); m.aboutToShow.emit()
            for a in m.actions():
                if a.text().replace("&", "") == text: return a
    raise KeyError(f"{menu_title} → {text}")

def titles(): return [t.title for t in win.content.visible_tracks()]

# Selectores de archivo de Windows: se simulan (no se pueden automatizar); el resto es real.
file_answers = []
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: (file_answers.pop(0), ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (file_answers.pop(0), ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: file_answers.pop(0))
explorer_calls = []
mw.subprocess.Popen = lambda args, *a, **k: explorer_calls.append(args)

db = Database(database_path())
win = mw.MainWindow(db); win.show(); win.raise_(); win.activateWindow(); spin(300)
c, bar, sb = win.content, win.player_bar, win.sidebar

def run(title, fn):
    print(f"\n[{title}]")
    try: fn()
    except Exception as e:
        check(title + " (excepción)", False, repr(e)); errors.append(traceback.format_exc())

# ================================================================ ARCHIVO
def t_import_files():
    file_answers.append([tagged, os.path.join(extra, "suelto.wav"), os.path.join(extra, "roto.mp3"), os.path.join(extra, "notas.txt")])
    report = {}
    def on_report(d):
        report["text"] = d.findChild(QLabel).text()
        tree = d.findChild(QTreeWidget)
        report["rows"] = [(tree.topLevelItem(i).text(0), tree.topLevelItem(i).text(1)) for i in range(tree.topLevelItemCount())] if tree else []
        d.accept()
    expect(is_(ImportReportDialog), on_report)
    menu_action("Archivo", "Importar archivos…").trigger()
    wait_until(lambda: "text" in report)
    check("Importar archivos… → informe mostrado", "text" in report)
    check("  importó 2 válidos", "2 canciones" in report.get("text", ""), report.get("text", "")[:90])
    check("  2 rechazados con motivo", len(report.get("rows", [])) == 2, report.get("rows"))
    t = next((x for x in win.library if x.title == "Canción etiquetada"), None)
    check("  metadatos leídos (título/artista/álbum/género)", t and (t.artist, t.album, t.genre) == ("Artista Prueba", "Álbum Prueba", "Rock"),
          t and (t.title, t.artist, t.album, t.genre))
    check("  carátula guardada", t is not None and t.cover_hash is not None)
    check("  duración leída (6 s)", t is not None and t.duration_ms == 6000, t and t.duration_ms)

def t_import_folder():
    for recursive, expected_new in ((False, 3), (True, 1)):
        file_answers.append(music)
        report = {}
        def on_folder(d, recursive=recursive):
            d.recursive.setChecked(recursive)
            d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        def on_report(d):
            report["text"] = d.findChild(QLabel).text(); d.accept()
        expect(is_(FolderImportDialog), on_folder)
        expect(is_(ImportReportDialog), on_report)
        before = len(win.library)
        menu_action("Archivo", "Importar carpeta…").trigger()
        wait_until(lambda: "text" in report)
        label = "con subcarpetas" if recursive else "sin subcarpetas"
        check(f"Importar carpeta… {label} → {expected_new} nuevas", len(win.library) - before == expected_new,
              f"{len(win.library) - before} nuevas; {report.get('text', '')[:80]}")
        if recursive:
            check("  sin duplicados al reimportar (3 omitidas)", "3 archivos ya estaban" in report.get("text", ""), report.get("text", "")[:160])
    check("  total biblioteca = 6", len(win.library) == 6, len(win.library))

def t_search():
    win.activateWindow(); spin(100); menu_action("Archivo", "Buscar").trigger(); spin(50)
    check("Buscar (Ctrl+F) → foco en el campo de búsqueda", QApplication.focusWidget() is bar.search)
    QTest.keyClicks(bar.search, "etiquetada"); spin(400)
    check("  resultados mientras se escribe", c.mode == "search" and titles() == ["Canción etiquetada"], titles())
    bar.search.setText("ALBUM PRUEBA"); spin(400)
    check("  busca por álbum, sin mayúsculas ni tildes", titles() == ["Canción etiquetada"], titles())
    bar.search.setText("tono"); spin(400)
    check("  busca por título (3)", len(titles()) == 3, titles())
    bar.search.setText("xyz123"); spin(400)
    check("  sin resultados → mensaje claro", c.stack.currentWidget() is c.empty and "Sin resultados" in c.empty.title.text())
    btn = [b for b in c.empty.findChildren(type(c.btn_play)) if "Limpiar" in b.text()]
    btn[0].click(); spin(100)
    check("  botón «Limpiar búsqueda»", bar.search.text() == "" and c.mode != "search")

# ================================================================ REPRODUCCIÓN
def t_playback():
    sb.select_library("songs"); spin(100)
    c.table.clearSelection()
    order = titles()
    menu_action("Reproducción", "Reproducir / Pausar").trigger(); spin(600)
    check("Reproducir / Pausar sin cola → empieza la lista", win.player.is_playing and win.player.current_track.title == order[0],
          win.player.current_track and win.player.current_track.title)
    check("  barra superior sincronizada", bar.title.text() == order[0] and bar.progress.maximum() == 6000, (bar.title.text(), bar.progress.maximum()))
    menu_action("Reproducción", "Reproducir / Pausar").trigger(); spin(300)
    check("  segunda vez → pausa", not win.player.is_playing)
    menu_action("Reproducción", "Reproducir / Pausar").trigger(); spin(300)
    check("  tercera vez → reanuda", win.player.is_playing)
    menu_action("Reproducción", "Siguiente").trigger(); spin(400)
    check("Siguiente", win.player.current_track.title == order[1], win.player.current_track.title)
    menu_action("Reproducción", "Anterior").trigger(); spin(400)
    check("Anterior (antes de 3 s → canción previa)", win.player.current_track.title == order[0], win.player.current_track.title)
    win.player.seek(4000); spin(400)
    menu_action("Reproducción", "Anterior").trigger(); spin(300)
    check("Anterior (después de 3 s → reinicia la misma)", win.player.current_track.title == order[0] and win.player.position() < 2500,
          (win.player.current_track.title, win.player.position()))
    bar.progress.released_at.emit(3000); spin(300)
    check("Barra de progreso → cambia la posición", 2900 <= win.player.position() <= 4000, win.player.position())
    menu_action("Reproducción", "Detener").trigger(); spin(300)
    check("Detener → parado y posición 0", not win.player.is_playing and win.player.position() == 0, win.player.position())
    dpos=c.table.visualRect(c.proxy.index(2, 1)).center(); QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=dpos); QTest.mouseDClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=dpos); spin(500)
    check("Doble clic en una canción la reproduce", win.player.current_track.title == order[2] and win.player.is_playing)

def t_shuffle_repeat():
    a = menu_action("Reproducción", "Orden aleatorio")
    a.trigger(); spin(50)
    check("Orden aleatorio → activado y botón sincronizado", win.player.shuffle and bar.btn_shuffle.isChecked() and a.isChecked())
    a.trigger(); spin(50)
    check("  otra vez → desactivado", not win.player.shuffle and not bar.btn_shuffle.isChecked())
    bar.btn_shuffle.click(); spin(50)
    check("  botón de la barra sincroniza el menú", win.player.shuffle and a.isChecked())
    bar.btn_shuffle.click()
    seen = []
    r = menu_action("Reproducción", "Cambiar repetición")
    for _ in range(3):
        r.trigger(); spin(30); seen.append((int(win.player.repeat), bar.btn_repeat.toolTip().split(":")[1].split("(")[0].strip()))
    check("Cambiar repetición → toda la lista → una → desactivada", [s[0] for s in seen] == [1, 2, 0], seen)
    # Repetir una: al terminar vuelve a sonar la misma
    win.player.set_repeat(2); cur = win.player.current_track.title
    win.player.seek(5700); spin(1200)
    check("  repetir una canción al terminar", win.player.current_track.title == cur and win.player.is_playing, win.player.current_track.title)
    # Repetir todo: tras la última pasa a la primera
    win.player.set_repeat(1); tracks = c.visible_tracks()
    win.player.play_queue(tracks, len(tracks) - 1)
    # Esperas por condición: con la batería completa la máquina va cargada y 300 ms fijos no alcanzaban.
    wait_until(lambda: win.player.is_playing and win.player.duration() > 0, 5000); win.player.seek(5700)
    wait_until(lambda: win.player.current_track.title == tracks[0].title, 6000)
    check("  repetir toda la lista: tras la última → la primera", win.player.current_track.title == tracks[0].title, win.player.current_track.title)
    win.player.set_repeat(0)
    win.player.play_queue(tracks, len(tracks) - 1); spin(300); win.player.seek(5700); spin(1200)
    check("  sin repetición: al final se detiene", not win.player.is_playing)

def t_volume():
    bar.volume.setValue(90)
    up, down = menu_action("Reproducción", "Subir volumen"), menu_action("Reproducción", "Bajar volumen")
    up.trigger(); check("Subir volumen (+5)", bar.volume.value() == 95)
    up.trigger(); up.trigger(); check("  límite en 100", bar.volume.value() == 100)
    down.trigger(); check("Bajar volumen (−5)", bar.volume.value() == 95)
    check("  volumen aplicado al audio", abs(win.player._audio.volume() - 0.95) < 0.01, win.player._audio.volume())
    bar.btn_mute.click(); check("Silenciar", win.player._audio.isMuted()); bar.btn_mute.click()
    check("  quitar silencio", not win.player._audio.isMuted())

def t_shortcuts():
    win.activateWindow(); c.table.setFocus(); spin(50)
    playing = win.player.is_playing
    QTest.keyClick(c.table, Qt.Key.Key_Space); spin(300)
    check("Atajo Espacio → reproducir/pausar", win.player.is_playing != playing)
    bar.search.setFocus(); QTest.keyClick(bar.search, Qt.Key.Key_Space)
    check("  Espacio dentro de la búsqueda escribe un espacio", bar.search.text() == " ", repr(bar.search.text()))
    win.player_bar.clear_search(); c.table.setFocus()
    sb.select_library("songs"); spin(100)

# ================================================================ PLAYLISTS
def t_playlists():
    a_new = menu_action("Playlists", "Nueva playlist…")
    expect(is_(PlaylistNameDialog), name_dialog("   ", expect_error="Escribe un nombre", then_cancel=False))
    expect(is_(PlaylistNameDialog), name_dialog("Rock"))
    a_new.trigger(); spin(100)
    pls = db.playlists()
    check("Nueva playlist… (nombre vacío rechazado, luego «Rock»)", [p.name for p in pls] == ["Rock"], [p.name for p in pls])
    expect(is_(PlaylistNameDialog), name_dialog("  rock ", expect_error="Ya existe", then_cancel=True))
    a_new.trigger(); spin(100)
    check("  nombre repetido rechazado", len(db.playlists()) == 1)

    sb.select_library("songs"); spin(50)
    check("Renombrar/Eliminar desactivados sin playlist seleccionada",
          not menu_action("Playlists", "Renombrar playlist…").isEnabled() and not menu_action("Playlists", "Eliminar playlist…").isEnabled())
    pid = db.playlists()[0].id
    sb.select_playlist(pid); spin(100)
    check("Seleccionar playlist → resaltada y panel actualizado",
          sb.playlist_list.currentItem().isSelected() and c.title.text() == "Rock" and c.mode == "playlist"
          and sb.library_list.currentRow() == -1)
    check("  playlist vacía → mensaje y botón «Ir a Canciones»", c.stack.currentWidget() is c.empty, c.empty.title.text())
    expect(is_(PlaylistNameDialog), name_dialog("Rock clásico"))
    menu_action("Playlists", "Renombrar playlist…").trigger(); spin(100)
    check("Renombrar playlist…", db.playlist(pid).name == "Rock clásico" and c.title.text() == "Rock clásico"
          and sb.playlist_list.currentItem().text() == "Rock clásico")
    expect(msgbox_with("¿Eliminar la playlist"), click_msg("Cancelar"))
    menu_action("Playlists", "Eliminar playlist…").trigger(); spin(100)
    check("Eliminar playlist… → Cancelar la conserva", db.playlist(pid) is not None)
    expect(msgbox_with("¿Eliminar la playlist"), click_msg("Eliminar"))
    menu_action("Playlists", "Eliminar playlist…").trigger(); spin(100)
    check("Eliminar playlist… → Eliminar la borra y vuelve a Canciones",
          db.playlist(pid) is None and sb.current_view() == ("songs", None) and c.title.text() == "Canciones")

def t_add_to_playlist():
    db.create_playlist("Favoritas"); sb.set_playlists(db.playlists())
    fav = db.playlists()[0].id
    sb.select_library("songs"); spin(100)
    row = titles().index("A tono")
    plus = c.table.visualRect(c.proxy.index(row, COL_ACTION)).center()
    seen = []
    expect(is_(QMenu), pick_menu("Favoritas", seen))
    QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=plus); spin(200)
    check("Botón + de la fila → menú con playlists y «Nueva playlist…»", any("Favoritas" in s for s in seen) and any("Nueva playlist" in s for s in seen), seen)
    check("  canción agregada a Favoritas", db.playlist(fav).track_count == 1)
    seen.clear()
    expect(is_(QMenu), pick_menu("Favoritas", seen))
    expect(msgbox_with("ya está en"), click_msg("No agregar"))
    QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=plus); spin(200)
    check("  menú marca «ya incluida»", any("ya incluida" in s for s in seen), seen)
    check("  repetida → «No agregar» no duplica", db.playlist(fav).track_count == 1)
    expect(is_(QMenu), pick_menu("Favoritas"))
    expect(msgbox_with("ya está en"), click_msg("Agregar repetida"))
    QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=plus); spin(200)
    check("  repetida → «Agregar repetida» sí la repite", db.playlist(fav).track_count == 2)

    # Desde la búsqueda, crear una playlist nueva desde el menú
    bar.search.setText("etiquetada"); spin(400)
    expect(is_(QMenu), pick_menu("Nueva playlist"))
    expect(is_(PlaylistNameDialog), name_dialog("Desde búsqueda"))
    QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=c.table.visualRect(c.proxy.index(0, COL_ACTION)).center()); spin(200)
    new = next((p for p in db.playlists() if p.name == "Desde búsqueda"), None)
    check("Desde resultados de búsqueda → «Nueva playlist…» crea y agrega", new is not None and new.track_count == 1)
    bar.search.setText(""); spin(300)

    # Botón del encabezado con varias seleccionadas (algunas ya están)
    sb.select_library("songs"); spin(100)
    c.table.selectAll(); spin(50)
    expect(is_(QMenu), pick_menu("Favoritas"))
    expect(msgbox_with("ya están en"), click_msg("Agregar solo las nuevas"))
    c.btn_add.click(); spin(200)
    check("Botón «Agregar a playlist» con selección múltiple → solo nuevas", db.playlist(fav).track_count == 2 + 5, db.playlist(fav).track_count)

    # Clic derecho → Agregar a playlist…
    c.table.clearSelection()
    pos = c.table.visualRect(c.proxy.index(0, 1)).center()
    expect(is_(QMenu), pick_menu("Agregar a playlist"))
    expect(is_(QMenu), pick_menu("Desde búsqueda"))
    c._table_menu(pos); spin(200)
    check("Clic derecho → «Agregar a playlist…»", db.playlist(new.id).track_count == 2, db.playlist(new.id).track_count)

def t_playlist_view_and_remove():
    fav = next(p for p in db.playlists() if p.name == "Favoritas")
    sb.select_playlist(fav.id); spin(150)
    total = sum(t.duration_ms for t in c.visible_tracks())
    check("Vista de playlist: nombre, nº canciones y duración", c.title.text() == "Favoritas" and "7 canciones" in c.subtitle.text()
          and "42 s" in c.subtitle.text(), (c.subtitle.text(), total))
    from app.ui.track_model import COL_DURATION, HEADERS
    check("  cada fila tiene carátula/título/artista/álbum/duración", c.model.columnCount() == len(HEADERS)
          and c.proxy.index(0, COL_DURATION).data() == "0:06")
    pos = c.table.visualRect(c.proxy.index(0, 1)).center()
    expect(is_(QMenu), pick_menu("Quitar de la playlist"))
    c._table_menu(pos); spin(200)
    check("Clic derecho → «Quitar de la playlist»", db.playlist(fav.id).track_count == 6 and len(c.visible_tracks()) == 6)
    win.activateWindow(); c.table.setFocus(); spin(100); c.table.selectRow(0); QTest.keyClick(c.table, Qt.Key.Key_Delete); spin(200)
    check("  tecla Supr quita de la playlist (sin borrar archivo)", db.playlist(fav.id).track_count == 5 and len(win.library) == 6)
    c.btn_shuffle.click(); spin(300)
    check("Botón «Aleatorio» en playlist (mezcla la lista a la vista y suena la primera)",
          win.player.is_playing and win.player.current_track.entry_id == c.visible_tracks()[0].entry_id)
    c.btn_play.click(); spin(300)
    check("Botón «Reproducir» en playlist", win.player.is_playing)
    win.player.set_shuffle(False)

def t_sidebar_menu():
    fav = next(p for p in db.playlists() if p.name == "Favoritas")
    row = [sb.playlist_list.item(i).text() for i in range(sb.playlist_list.count())].index("Favoritas")
    pos = sb.playlist_list.visualItemRect(sb.playlist_list.item(row)).center()
    win.player.stop(); spin(100)
    expect(is_(QMenu), pick_menu("Reproducir"))
    sb._playlist_menu(pos); spin(400)
    check("Menú lateral → Reproducir", win.player.is_playing and win.player.current_track is not None)
    expect(is_(QMenu), pick_menu("Renombrar"))
    expect(is_(PlaylistNameDialog), name_dialog("Favoritas 2"))
    sb._playlist_menu(pos); spin(100)
    check("Menú lateral → Renombrar…", db.playlist(fav.id).name == "Favoritas 2")
    expect(is_(QMenu), pick_menu("Nueva playlist"))
    expect(is_(PlaylistNameDialog), name_dialog("Temporal"))
    sb._playlist_menu(pos); spin(100)
    tmp = next((p for p in db.playlists() if p.name == "Temporal"), None)
    check("Menú lateral → Nueva playlist…", tmp is not None)
    row = [sb.playlist_list.item(i).text() for i in range(sb.playlist_list.count())].index("Temporal")
    pos = sb.playlist_list.visualItemRect(sb.playlist_list.item(row)).center()
    expect(is_(QMenu), pick_menu("Eliminar"))
    expect(msgbox_with("¿Eliminar la playlist"), click_msg("Eliminar"))
    sb._playlist_menu(pos); spin(100)
    check("Menú lateral → Eliminar…", db.playlist(tmp.id) is None)
    sb.btn_new.click if False else None
    expect(is_(PlaylistNameDialog), lambda d: d.reject())
    sb.btn_new.click(); spin(100)
    check("Botón + de «Playlists» abre el diálogo (cancelado)", len(db.playlists()) == 2)

def t_library_views():
    for kind, title in (("recent", "Recientes"), ("artists", "Artistas"), ("albums", "Álbumes"), ("songs", "Canciones")):
        sb.select_library(kind); spin(100)
        groups = c.group_list.count() if c.group_list.isVisible() else None
        check(f"Vista {title}", c.title.text() == title and sb.library_list.currentItem().text() == title and len(c.visible_tracks()) > 0,
              f"filas={len(c.visible_tracks())} grupos={groups}")
    sb.select_library("artists"); spin(100)
    labels = [c.group_list.item(i).text() for i in range(c.group_list.count())]
    c.group_list.setCurrentRow(labels.index("Artista Prueba")); spin(50)
    check("  Artistas → elegir artista filtra sus canciones", titles() == ["Canción etiquetada"], (labels, titles()))
    check("  «Géneros» ya no aparece en la barra lateral", all(sb.library_list.item(i).text() != "Géneros" for i in range(sb.library_list.count())))

def t_missing_and_explorer():
    sb.select_library("songs"); spin(100)
    row = titles().index("B tono")
    c.table.selectRow(row)
    expect(is_(QMenu), pick_menu("Mostrar en el Explorador"))
    c._table_menu(c.table.visualRect(c.proxy.index(row, 1)).center()); spin(100)
    check("Clic derecho → «Mostrar en el Explorador»", explorer_calls and isinstance(explorer_calls[-1], str) and explorer_calls[-1].lower().startswith('"' + os.environ.get("SystemRoot", r"C:\Windows").lower()) and '/select,"' in explorer_calls[-1],  # ruta completa del Explorador
          explorer_calls[-1:] )
    win.player.stop(); win.player._player.setSource(__import__('PySide6.QtCore',fromlist=['QUrl']).QUrl()); spin(300)
    target = os.path.join(music, "B tono.wav")
    moved = os.path.join(work, "Movidos"); os.makedirs(moved)
    shutil.move(target, os.path.join(moved, "B tono.wav")); shutil.move(os.path.join(music, "C tono.wav"), os.path.join(moved, "C tono.wav"))
    win._reload_library(); win._refresh_view(); spin(100)
    check("Archivos movidos → aviso visible y filas marcadas", c.missing_banner.isVisible() and "2 canciones" in c.missing_text.text(), c.missing_text.text()[:60])
    row = titles().index("B tono")
    expect(msgbox_with("No se encuentra el archivo"), click_msg("Cancelar"))
    dpos = c.table.visualRect(c.proxy.index(row, 1)).center()
    QTest.mouseClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=dpos)
    QTest.mouseDClick(c.table.viewport(), Qt.MouseButton.LeftButton, pos=dpos); spin(300)
    check("  el diálogo de archivo faltante apareció", not pending, len(pending))
    check("Doble clic en canción faltante → mensaje útil, no se reproduce", not win.player.is_playing)
    file_answers.append(os.path.join(moved, "B tono.wav"))
    expect(msgbox_with("No se encuentra el archivo"), click_msg("Localizar archivo…"))
    expect(msgbox_with("otras"), click_msg("Actualizar también"))
    c.btn_missing.click(); spin(300)
    check("Botón «Localizar el primero…» → relocaliza y ofrece las de la misma carpeta",
          all(t.available for t in win.library) and not c.missing_banner.isVisible())
    fav = next(p for p in db.playlists() if p.name == "Favoritas 2")
    check("  las playlists conservan las canciones relocalizadas", db.playlist(fav.id).track_count == 5)

def t_remove_library():
    sb.select_library("songs"); spin(100)
    row = titles().index("A tono"); c.table.selectRow(row)
    expect(is_(QMenu), pick_menu("Quitar de la biblioteca"))
    expect(msgbox_with("¿Quitar"), click_msg("Cancelar"))
    c._table_menu(c.table.visualRect(c.proxy.index(row, 1)).center()); spin(100)
    check("Quitar de la biblioteca → Cancelar no quita", len(win.library) == 6)
    expect(is_(QMenu), pick_menu("Quitar de la biblioteca"))
    expect(msgbox_with("¿Quitar"), click_msg("Quitar"))
    c._table_menu(c.table.visualRect(c.proxy.index(row, 1)).center()); spin(100)
    check("Quitar de la biblioteca → Quitar", len(win.library) == 5 and "A tono" not in titles())
    check("  el archivo original sigue en el disco", os.path.exists(os.path.join(music, "A tono.wav")))

def t_import_button_and_empty():
    seen = []
    m = c.btn_import.menu(); seen = [a.text() for a in m.actions()]
    file_answers.append("")  # el usuario cancela el selector
    m.actions()[0].trigger(); spin(100)
    check("Botón «Importar música» → menú con carpeta/archivos (cancelar no hace nada)",
          seen == ["Importar carpeta…", "Importar archivos…"] and not any(isinstance(w, FolderImportDialog) for w in app.topLevelWidgets() if w.isVisible()), seen)

def t_about():
    got = {}
    expect(is_(QMessageBox), lambda b: (got.setdefault("t", b.text()), b.accept()))
    menu_action("Ayuda", "Acerca de…").trigger(); spin(100)
    check("Acerca de… muestra ruta de la BD", "biblioteca.db" in got.get("t", ""))

def t_exit():
    bar.volume.setValue(42)
    QSettings("ReproductorMusicaTest", "ReproductorMusica").setValue("preferences/confirm_exit", True)
    expect(msgbox_with("¿Salir del"), click_msg("Salir"))
    menu_action("Archivo", "Salir").trigger(); spin(200)
    check("Salir → pregunta «¿Salir del…?» y cierra la ventana", not win.isVisible())
    s = QSettings("ReproductorMusicaTest", "ReproductorMusica")
    check("  guarda volumen", int(s.value("player/volume", -1)) == 42, s.value("player/volume"))
    db2 = Database(database_path())
    check("  biblioteca y playlists persisten al reabrir", len(db2.all_tracks()) == 5 and {p.name for p in db2.playlists()} == {"Favoritas 2", "Desde búsqueda"},
          [p.name for p in db2.playlists()])
    s.clear()

for title, fn in [
    ("ARCHIVO › Importar archivos…", t_import_files),
    ("ARCHIVO › Importar carpeta…", t_import_folder),
    ("ARCHIVO › Buscar", t_search),
    ("BIBLIOTECA › vistas", t_library_views),
    ("REPRODUCCIÓN › controles", t_playback),
    ("REPRODUCCIÓN › aleatorio / repetición", t_shuffle_repeat),
    ("REPRODUCCIÓN › volumen", t_volume),
    ("ATAJOS", t_shortcuts),
    ("PLAYLISTS › menú", t_playlists),
    ("AGREGAR A PLAYLIST", t_add_to_playlist),
    ("PLAYLIST › vista y quitar", t_playlist_view_and_remove),
    ("BARRA LATERAL › menú contextual", t_sidebar_menu),
    ("ARCHIVOS FALTANTES / EXPLORADOR", t_missing_and_explorer),
    ("QUITAR DE LA BIBLIOTECA", t_remove_library),
    ("BOTÓN IMPORTAR", t_import_button_and_empty),
    ("AYUDA › Acerca de…", t_about),
    ("ARCHIVO › Salir", t_exit),
]:
    run(title, fn)

if pending: check("diálogos esperados que nunca aparecieron", False, len(pending))
if errors: print("\nERRORES DE PYTHON DURANTE LA PRUEBA:\n" + "\n".join(errors))
ok = sum(r[1] for r in results)
print(f"\nRESULTADO: {ok}/{len(results)} comprobaciones correctas, {len(errors)} errores de Python")
sys.exit(0 if ok == len(results) and not errors else 1)
