"""1.12.4: detalles menores de la revisión completa, cada uno reproducido antes de corregirlo.
Todo en carpetas temporales (y una temporal en otro disco, que se borra al final)."""
import ctypes, math, os, shutil, struct, sys, tempfile, time, wave
from datetime import datetime, timedelta
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_1124_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import backup, file_history, file_manager
from app.config import database_path
from app.database import Database
from app.file_operations import KIND_FILES, FileOperations
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def wait_until(cond, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond(): return True
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
    return cond()
def tone(path, secs=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))
    return path
def short_name(path):
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value if 0 < n < len(buf) else path

music = os.path.join(work, "Musica")
db = Database(database_path())
ops = FileOperations(db, lambda *_: None, lambda *_: None, lambda: None, lambda: True)
by_id = lambda i: next(t for t in db.all_tracks() if t.id == i)
by_path = lambda p: next(t for t in db.all_tracks() if os.path.normcase(t.path) == os.path.normcase(p))
other = tempfile.mkdtemp(prefix="_mp_1124_", dir="D:\\") if os.path.splitdrive(work)[0].upper() != "D:" else tempfile.mkdtemp(prefix="_mp_1124_", dir="C:\\Users\\Public")

try:
    print("[Historial: deshacer un cambio solo de mayúsculas]")
    low = tone(os.path.join(music, "Mayus", "cancion.wav"))
    db.add_tracks([scan_file(low)[0]])
    up = ops.rename_track_file(by_path(low), "CANCION")
    entry = next((e for e in ops.history(db.all_tracks()) if e.kind == KIND_FILES and e.title == "Renombrar archivo"), None)
    check("un renombre que solo cambia mayúsculas se puede deshacer", entry is not None and entry.can_undo, entry and entry.status)

    print("[Historial: deshacer un movimiento a otro disco cuando ya no existe la carpeta original]")
    gone_dir = os.path.join(music, "SeBorra")
    away = tone(os.path.join(gone_dir, "viaje.wav"))
    db.add_tracks([scan_file(away)[0]])
    away_id = by_path(away).id
    ops.move_tracks([by_path(away)], other)
    shutil.rmtree(gone_dir)
    entry = next((e for e in ops.history(db.all_tracks()) if e.kind == KIND_FILES and e.title == "Mover a otra carpeta" and e.can_undo), None)
    out = ops.undo(entry) if entry is not None else None
    check("vuelve a su carpeta (se vuelve a crear) y la biblioteca con ella", out is not None and os.path.exists(away) and by_id(away_id).path == away,
          out and out.message)

    print("[Rutas largas: el temporal de la copia entre discos también tiene que caber]")
    deep = other
    while len(deep) < 225:
        deep = os.path.join(deep, "carpeta")
    os.makedirs(deep)
    name = "c" * (250 - len(deep) - 5) + ".wav"  # destino de 250 caracteres: cabe; con «.moviendo.tmp» no
    src = tone(os.path.join(music, "Larga", name))
    r = file_manager.move_files([src], deep)
    check("se mueve a otro disco aunque el temporal con su terminación no hubiera cabido",
          r.moved and os.path.exists(os.path.join(deep, name)) and not os.path.exists(src), r.failed)

    print("[Temporales sobrantes en la carpeta de destino de un movimiento cortado]")
    dest = os.path.join(music, "DestinoSinBiblioteca"); os.makedirs(dest)
    planned = tone(os.path.join(music, "Corte", "a-medias.wav"))
    db.add_tracks([scan_file(planned)[0]])
    target = os.path.join(dest, "a-medias.wav")
    file_history.begin(file_history.KIND_MOVE, [file_history.Change(planned, target, [by_path(planned).id])])
    leftover = target + ".moviendo.tmp"
    open(leftover, "wb").write(b"copia a medias")  # se cortó la luz copiando
    ops.reconcile_interrupted_moves()
    check("al abrir se borra el temporal a medias del destino (el original sigue en su sitio)",
          not os.path.exists(leftover) and os.path.exists(planned))

    print("[Respaldos: los de antes de una operación duran al menos una semana]")
    bdir = backup.backup_dir()
    for f in bdir.glob("*.db"):
        f.unlink()
    now = datetime(2026, 10, 25, 12, 0, 0)
    def fake(when, reason):
        p = bdir / f"biblioteca-{when.strftime('%Y%m%d-%H%M%S')}-{reason}.db"; p.write_bytes(b"x"); return p
    important = fake(now - timedelta(days=2), "antes-de-quitar-faltantes")
    for n in range(12):
        fake(now - timedelta(hours=n), "antes-de-renombrar")  # una tarde de renombrar canciones
    backup.prune(now)
    check("el respaldo de antes de quitar faltantes sigue después de 12 operaciones más", important.exists())
    old = fake(now - timedelta(days=40), "antes-de-mover")
    backup.prune(now)
    check("  los de hace más de un mes sí se borran", not old.exists())
    for f in bdir.glob("*.db"):
        f.unlink()
    important = fake(now - timedelta(days=2), "antes-de-quitar-faltantes")
    for n in range(300):
        fake(now - timedelta(minutes=n + 1), "antes-de-renombrar")  # renombrar 300 canciones en una tarde
    backup.prune(now)
    kept = len(list(bdir.glob("*.db")))
    check("  renombrar 300 canciones no deja 300 copias de la biblioteca guardadas una semana", kept <= 20 and important.exists(), kept)

    print("[Renombrar una carpeta con canciones guardadas con su nombre corto (8.3)]")
    longdir = os.path.join(music, "Carpeta con nombre largo de verdad")
    song = tone(os.path.join(longdir, "Tema numero uno.wav"))
    short = short_name(song)
    if short == song:
        print("  (se omite: este disco no tiene nombres cortos 8.3)")
        short = None
    db.add_tracks([scan_file(song)[0]])
    sid = by_path(song).id
    db.update_track_paths([(sid, short or song)])  # importada desde una ruta escrita con nombres cortos
    lib = db.all_tracks()
    ops.rename_folder(longdir, "Renombrada", lib)
    moved_to = by_id(sid).path
    if short is not None:
        check("la canción guardada con nombre corto pasa a la carpeta nueva", os.path.exists(moved_to)
              and os.path.basename(os.path.dirname(moved_to)) == "Renombrada", moved_to)
    print("[Historial: un movimiento interrumpido no figura como «Hecho» con los archivos planeados]")
    plan_dir = os.path.join(music, "Plan"); dest2 = os.path.join(music, "Destino2"); os.makedirs(dest2)
    p1, p2, p3 = (tone(os.path.join(plan_dir, f"p{n}.wav")) for n in (1, 2, 3))
    db.add_tracks([scan_file(p)[0] for p in (p1, p2, p3)])
    running = file_history.begin(file_history.KIND_MOVE, [file_history.Change(p, os.path.join(dest2, os.path.basename(p)), [by_path(p).id]) for p in (p1, p2, p3)])
    os.rename(p1, os.path.join(dest2, "p1.wav"))  # solo llegó a mover la primera
    entry = next(e for e in ops.history(db.all_tracks()) if e.kind == KIND_FILES and e.session is not None and e.session.id == running.id)
    check("figura «Interrumpida» y cuenta solo lo que se movió", entry.status == "Interrumpida" and entry.detail.startswith("1 archivo"),
          (entry.status, entry.detail))
    file_history.finish(running, [])
    os.rename(os.path.join(dest2, "p1.wav"), p1)

    print("[Mover: un archivo que no se pudo mover sale del plan en el momento]")
    class Corte(BaseException):
        pass
    dest3 = os.path.join(music, "Destino3"); os.makedirs(dest3)
    stale = tone(os.path.join(music, "Plan3", "igual.wav")); ok_song = tone(os.path.join(music, "Plan3", "bien.wav"))
    db.add_tracks([scan_file(p)[0] for p in (stale, ok_song)])
    stale_id, lib3 = by_path(stale).id, db.all_tracks()
    os.remove(stale)  # se borró por fuera (la lista aún la muestra)…
    tone(os.path.join(dest3, "igual.wav"))  # …y en el destino ya hay OTRO archivo con ese nombre
    real_update = db.update_track_paths
    db.update_track_paths = lambda changes: (_ for _ in ()).throw(Corte())  # se corta la luz al guardar la 2.ª
    try:
        ops.move_tracks([t for t in lib3 if t.id in (stale_id, by_path(ok_song).id)], dest3)
    except Corte:
        pass
    db.update_track_paths = real_update
    ops.reconcile_interrupted_moves()
    check("al abrir, la canción que no se movió no pasa a apuntar al archivo ajeno del destino",
          os.path.normcase(by_id(stale_id).path) == os.path.normcase(stale), by_id(stale_id).path)
    print("[Reproducción: saltos de posición y orden aleatorio]")
    from app.models import Track
    from app.player import PlaybackController
    def tr(i, path): return Track(id=i, path=path, title=os.path.basename(path), artist="", album="", genre="", duration_ms=8000, added_at="")
    long1 = tr(301, tone(os.path.join(music, "Larga", "ocho1.wav"), secs=8))
    long2 = tr(302, tone(os.path.join(music, "Larga", "ocho2.wav"), secs=8))
    player = PlaybackController()
    player.play_queue([long1], 0)
    wait_until(lambda: player.is_playing and player.duration() > 0, 5000)
    player._pending_seek = 5000  # un salto que quedó esperando (p. ej. al apagar el ecualizador)
    player.play_queue([long2], 0)
    wait_until(lambda: player.is_playing and player.position() > 0, 5000); spin(200)
    check("un salto pendiente no pasa a la canción siguiente", player.position() < 2500, player.position())
    player.play_queue([long1], 0)
    player.seek(4000)  # enseguida, antes de que termine de cargar (disco lento)
    wait_until(lambda: player.is_playing and player.position() > 0, 5000); spin(300)
    check("saltar antes de que cargue no se pierde", player.position() >= 3500, player.position())
    player.release_source()
    many = [tr(310 + n, long1.path) for n in range(8)]
    player.set_shuffle(True); player.set_repeat(1)
    player.play_queue(many, 0); spin(100)
    first_lap = list(player._order)
    last = first_lap[-1]
    player._pos = len(first_lap) - 1
    player._advance(1, user=False)  # terminó la última: vuelta nueva
    check("al dar la vuelta con aleatorio se vuelve a mezclar", player._order != first_lap, (first_lap, player._order))
    check("  y no empieza por la que acaba de sonar", player._order[player._pos] != last)
    player.set_shuffle(False); player.set_repeat(0); player.release_source(); spin(100)

    print("[Registro de errores]")
    import logging
    from logging.handlers import RotatingFileHandler
    from app import config, error_log
    crash_log = config.data_dir() / "cierres-inesperados.log"
    crash_log.write_bytes(b"x" * 1_500_000)  # años de cierres anotados
    made = []
    real_handler = error_log.RotatingFileHandler
    class Counting(real_handler):
        def __init__(self, *a, **k):
            made.append(1); super().__init__(*a, **k)
    error_log.RotatingFileHandler = Counting
    error_log.setup(); error_log.setup()
    error_log.RotatingFileHandler = real_handler
    in_root = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    check("llamar dos veces a setup no abre el archivo de registro de más", len(made) <= 1 and len(in_root) == 1, (len(made), len(in_root)))
    check("  el archivo de cierres inesperados no crece sin límite", crash_log.stat().st_size < 1_000_000, crash_log.stat().st_size)
    logged = []
    class Catch(logging.Handler):
        def emit(self, record): logged.append(record.getMessage())
    catcher = Catch(); logging.getLogger("errores").addHandler(catcher)
    old_hook = sys.excepthook
    error_log.install_excepthook(); error_log.install_excepthook(lambda m: None)
    try:
        raise ValueError("prueba")
    except ValueError:
        import io
        stderr, sys.stderr = sys.stderr, io.StringIO()  # con consola (p. ej. al correrlo desde la terminal)
        sys.excepthook(*sys.exc_info())
        shown, sys.stderr = sys.stderr.getvalue(), stderr
    sys.excepthook = old_hook; logging.getLogger("errores").removeHandler(catcher)
    check("un error se anota una sola vez aunque el aviso se instale dos veces", len(logged) == 1, len(logged))
    check("  y en la consola se muestra una vez", shown.count("ValueError: prueba") == 1, shown.count("ValueError: prueba"))

    print("[Instancia única: un mensaje enorme no llena la memoria]")
    from PySide6.QtNetwork import QLocalSocket
    from app import single_instance
    server = single_instance.InstanceServer()
    got = []
    server.set_handler(lambda paths: got.append(len(paths)))
    sock = QLocalSocket(); sock.connectToServer(single_instance._server_name())
    sock.waitForConnected(2000)
    chunk = b"C:\\x.mp3\n" * 20000
    for _ in range(40):  # unos 7 MB sin terminar nunca el mensaje
        sock.write(chunk); sock.waitForBytesWritten(2000); spin(5)
    spin(300)
    states = [st for st in getattr(server, "_states", [])]
    closed = sock.state() == QLocalSocket.LocalSocketState.UnconnectedState
    check("la conexión que manda demasiado se corta", closed, sock.state())
    sock.abort(); server.deleteLater(); spin(100)

    print("[Internet: una redirección a http no se sigue]")
    import urllib.request
    from app import online_lookup
    handler = getattr(online_lookup, "_HttpsOnlyRedirect", None)
    req = urllib.request.Request("https://coverartarchive.org/release/x/front")
    refused = handler is not None and handler().redirect_request(req, None, 302, "Found", {}, "http://ejemplo.invalid/tapa.jpg") is None
    check("se rechaza antes de hacer la petición en texto plano", refused)
    followed = handler is not None and handler().redirect_request(req, None, 302, "Found", {}, "https://ejemplo.invalid/tapa.jpg") is not None
    check("  una redirección a https sí se sigue", followed)

    print("[Instancia única: al cerrar se deja de recibir archivos]")
    server2 = single_instance.InstanceServer()
    closer = getattr(server2, "close", None)
    if closer is not None:
        closer()
    check("después de cerrar, otra copia no le entrega archivos (los abre ella)", closer is not None and not single_instance.send_to_running(["C:\\x.mp3"]))
    server2.deleteLater(); spin(50)

    print("[Barra de avance con el teclado]")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from app.ui import main_window as mw
    win = mw.MainWindow(Database(os.path.join(work, "data", "teclado.db"))); win.show(); spin(200)
    bar = win.player_bar
    bar.progress.setEnabled(True); bar.progress.setRange(0, 200000); bar.progress.setValue(60000)
    seeks = []
    bar.seek_requested.connect(seeks.append)
    bar.progress.setFocus(); spin(50)
    QTest.keyClick(bar.progress, Qt.Key.Key_Right); spin(50)
    QTest.keyClick(bar.progress, Qt.Key.Key_PageUp); spin(50)  # en Qt, Re Pág avanza
    check("las flechas y Re Pág saltan en la canción (no solo mueven la barra)", len(seeks) == 2 and seeks[0] >= 63000 and seeks[1] >= seeks[0] + 20000, seeks)

    print("[Teclas multimedia con la ventana minimizada]")
    keys = getattr(win, "_media_keys", None)
    toggled = []
    win.act_play.triggered.connect(lambda *_: toggled.append("play"))
    win.showMinimized(); spin(200)
    if keys is not None:
        WM_HOTKEY = 0x0312
        ctypes.windll.user32.PostMessageW(int(win.winId()), WM_HOTKEY, keys.PLAY_PAUSE_ID, 0)  # como la tecla Reproducir/Pausa
    spin(300)
    check("la tecla Reproducir/Pausa funciona aunque la ventana esté minimizada", toggled == ["play"], toggled)
    win.showNormal(); spin(100)
    from PySide6.QtWidgets import QDialog
    modal = QDialog(win); modal.setModal(True); modal.open(); spin(150)  # p. ej. «Convertir a MP3» trabajando
    toggled.clear()
    if keys is not None:
        ctypes.windll.user32.PostMessageW(int(win.winId()), WM_HOTKEY, keys.PLAY_PAUSE_ID, 0)
    spin(300)
    check("  con una ventana de herramientas abierta la tecla no hace nada (no vuelve a abrir el archivo)", toggled == [], toggled)
    modal.reject(); spin(50)
    win.close(); spin(100)
finally:
    shutil.rmtree(other, ignore_errors=True)

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
db.close()
sys.exit(0 if all(results) else 1)
