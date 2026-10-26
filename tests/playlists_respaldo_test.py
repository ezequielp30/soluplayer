"""1.12.5: copia de las playlists en archivos M3U8 (a mano y automática en Documentos) y restaurarlas.
Todo en carpetas temporales; la carpeta «Documentos» de las pruebas es otra (MUSICPLAYER_PLAYLISTS_DIR)."""
import math, os, shutil, struct, sys, tempfile, time, wave
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_pl_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_PLAYLISTS_DIR"] = os.path.join(work, "Documentos", "Playlists")
from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app import config
from app.database import Database
from app.importer import scan_file

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def tone(path, secs=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
        f.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 3))) for i in range(8000 * secs)))
    return path

try:
    from app import playlist_files as pf
except ImportError as exc:
    pf = None
    check("existe el módulo de copias de playlists", False, exc)

music = os.path.join(work, "Música Cristiana")
songs = [tone(os.path.join(music, "Alabanza", f"Canción {n} — Señor.wav")) for n in range(1, 6)]
db = Database(config.database_path())
db.add_tracks([scan_file(p)[0] for p in songs])
by_path = {t.path: t for t in db.all_tracks()}
domingo = db.create_playlist("Domingo de Adoración")
db.add_to_playlist(domingo.id, [by_path[songs[i]].id for i in (2, 0, 4)])  # el orden importa
auto = db.create_playlist("Para el auto")
db.add_to_playlist(auto.id, [by_path[songs[1]].id])
vacia = db.create_playlist("Vacía")

if pf is not None:
    print("[Guardar copia a mano]")
    out = os.path.join(work, "Pendrive")
    written = pf.export_all(db, out)
    files = sorted(os.listdir(out))
    check("un archivo .m3u8 por playlist, con su nombre", files == ["Domingo de Adoración.m3u8", "Para el auto.m3u8", "Vacía.m3u8"], files)
    text = open(os.path.join(out, "Domingo de Adoración.m3u8"), encoding="utf-8").read()
    lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    check("  formato M3U8 estándar, con acentos, rutas completas y en el mismo orden", text.startswith("#EXTM3U")
          and lines == [songs[2], songs[0], songs[4]] and "#EXTINF:" in text, lines)
    again = pf.export_all(db, out)
    check("  volver a guardar sin cambios no reescribe nada", again == [], again)

    print("[Restaurar en una biblioteca vacía (como si se hubiera borrado la carpeta del programa)]")
    db.close()
    shutil.rmtree(os.path.join(work, "data"))
    db = Database(config.database_path())
    found = pf.read_folder(out)
    check("se encuentran las 3 playlists de la copia", sorted(p.name for p in found) == ["Domingo de Adoración", "Para el auto", "Vacía"],
          [p.name for p in found])
    plans = pf.plan_restore(found, db.all_tracks())
    dom = next(p for p in plans if p.name == "Domingo de Adoración")
    check("  antes de restaurar dice cuántas canciones encontró en el disco", dom.found == 3 and dom.missing == 0, (dom.found, dom.missing))
    outcome = pf.apply_restore(db, plans)
    restored = {p.name: [t.path for t in db.playlist_tracks(p.id)] for p in db.playlists()}
    check("las playlists vuelven, con sus canciones en el mismo orden", restored.get("Domingo de Adoración") == [songs[2], songs[0], songs[4]]
          and restored.get("Para el auto") == [songs[1]] and "Vacía" in restored, restored)
    check("  las canciones que faltaban en la biblioteca se agregan", len(db.all_tracks()) == 4, len(db.all_tracks()))

    print("[Restaurar otra vez no duplica nada]")
    plans = pf.plan_restore(pf.read_folder(out), db.all_tracks())
    pf.apply_restore(db, plans)
    names = sorted(p.name for p in db.playlists())
    check("una playlist igual que la que ya existe no se duplica", names == ["Domingo de Adoración", "Para el auto", "Vacía"], names)
    db.add_to_playlist(next(p.id for p in db.playlists() if p.name == "Para el auto"), [by_path_now.id for by_path_now in db.all_tracks()
                                                                                       if by_path_now.path == songs[0]])
    pf.apply_restore(db, pf.plan_restore(pf.read_folder(out), db.all_tracks()))
    names = sorted(p.name for p in db.playlists())
    check("  una con el mismo nombre pero distinta entra como «(restaurada)»", "Para el auto (restaurada)" in names, names)

    print("[La música cambió de carpeta]")
    moved = os.path.join(work, "Música nueva")
    shutil.copytree(music, moved)
    shutil.rmtree(music)
    db.close(); shutil.rmtree(os.path.join(work, "data")); db = Database(config.database_path())
    db.add_tracks([scan_file(os.path.join(moved, "Alabanza", os.path.basename(p)))[0] for p in songs])
    plans = pf.plan_restore(pf.read_folder(out), db.all_tracks())
    dom = next(p for p in plans if p.name == "Domingo de Adoración")
    check("se encuentran por título, artista y duración aunque la ruta ya no exista", dom.found == 3 and dom.missing == 0, (dom.found, dom.missing))
    pf.apply_restore(db, [dom])
    pl = next(p for p in db.playlists() if p.name == "Domingo de Adoración")
    check("  y la playlist usa las canciones de la carpeta nueva", [os.path.dirname(os.path.dirname(t.path)) for t in db.playlist_tracks(pl.id)] == [moved] * 3)
    gone = [p for p in plans if p.name == "Para el auto"][0]
    check("  lo que no se encuentra se cuenta (no se inventa)", gone.found + gone.missing == 1)

    print("[Las pruebas nunca escriben en los Documentos del usuario]")
    saved = os.environ.pop("MUSICPLAYER_PLAYLISTS_DIR")
    inside = config.playlists_backup_dir()
    os.environ["MUSICPLAYER_PLAYLISTS_DIR"] = saved
    check("con una carpeta de datos de prueba, la copia automática va dentro de ella", str(inside).startswith(os.path.join(work, "data")), inside)

    print("[Copia automática en Documentos]")
    target = config.playlists_backup_dir()
    check("la carpeta automática está en Documentos (en las pruebas, la temporal)", str(target).startswith(work), target)
    pf.export_all(db, target)
    check("  se guarda allí", os.path.exists(os.path.join(target, "Domingo de Adoración.m3u8")))
    db.delete_playlist(pl.id)
    pf.export_all(db, target)
    check("  borrar una playlist en el programa NO borra su copia (se puede restaurar)", os.path.exists(os.path.join(target, "Domingo de Adoración.m3u8")))
    open(os.path.join(target, "mía.txt"), "w").write("archivo del usuario")
    pf.export_all(db, target)
    check("  nunca se tocan otros archivos de esa carpeta", os.path.exists(os.path.join(target, "mía.txt")))

    print("[Nombres de playlist que Windows no acepta como archivo]")
    rara = db.create_playlist('Culto: "Noche" / Vigilia?')
    db.add_to_playlist(rara.id, [db.all_tracks()[0].id])
    pf.export_all(db, out)
    back = [p for p in pf.read_folder(out) if p.name == 'Culto: "Noche" / Vigilia?']
    check("el nombre se guarda dentro del archivo y vuelve tal cual", len(back) == 1, [p.name for p in pf.read_folder(out)])

    print("[Revisión: nombres, restaurar varias veces, archivos bloqueados, versión anterior]")
    from app.database import MAX_PLAYLIST_NAME
    rev = os.path.join(work, "Revision"); os.makedirs(rev)
    a_song, b_song = (t for t in db.all_tracks()[:2])
    largo = "L" * (MAX_PLAYLIST_NAME - 5)
    pl_largo = db.create_playlist(largo); db.add_to_playlist(pl_largo.id, [a_song.id])
    open(os.path.join(rev, "largo.m3u8"), "w", encoding="utf-8").write(f"#EXTM3U\n#PLAYLIST:{largo}\n{b_song.path}\n")
    pl_rock = db.create_playlist("Rock Nacional"); db.add_to_playlist(pl_rock.id, [a_song.id])
    open(os.path.join(rev, "rock.m3u8"), "w", encoding="utf-8").write(f"#EXTM3U\n#PLAYLIST:Rock  Nacional\n{b_song.path}\n")
    open(os.path.join(rev, "z-ultima.m3u8"), "w", encoding="utf-8").write(f"#EXTM3U\n#PLAYLIST:Zeta\n{b_song.path}\n")
    try:
        result = pf.apply_restore(db, pf.plan_restore(pf.read_folder(rev), db.all_tracks()))
        error = ""
    except Exception as exc:
        result, error = None, repr(exc)
    names = [p.name for p in db.playlists()]
    check("un nombre largo o con espacios dobles no corta la restauración de las demás", not error and "Zeta" in names, error or names)
    before = len(db.playlists())
    pf.apply_restore(db, pf.plan_restore(pf.read_folder(rev), db.all_tracks()))
    pf.apply_restore(db, pf.plan_restore(pf.read_folder(rev), db.all_tracks()))
    check("  restaurar la misma copia otra vez no amontona «(restaurada 2)», «(restaurada 3)»…", len(db.playlists()) == before,
          [p.name for p in db.playlists()])
    lock_dir = os.path.join(work, "Bloqueo")
    pf.export_all(db, lock_dir)
    first_file = sorted(f for f in os.listdir(lock_dir) if f.endswith(".m3u8"))[0]
    for p in db.playlists():
        db.add_to_playlist(p.id, [b_song.id], allow_duplicates=True)  # todas cambian
    import ctypes
    k32 = ctypes.windll.kernel32; k32.CreateFileW.restype = ctypes.c_void_p
    handle = k32.CreateFileW(os.path.join(lock_dir, first_file), 0x80000000, 0, None, 3, 0x80, None)  # abierto sin compartir
    try:
        pf.export_all(db, lock_dir)
    except Exception as exc:
        print("  (export_all lanzó)", exc)
    k32.CloseHandle(ctypes.c_void_p(handle))
    leftovers = [f for f in os.listdir(lock_dir) if f.endswith(".tmp")]
    zeta = open(os.path.join(lock_dir, "Zeta.m3u8"), encoding="utf-8-sig").read()
    check("un archivo abierto en otro programa no frena el resto ni deja temporales", not leftovers and zeta.count(b_song.path) == 2,
          (leftovers, zeta.count(b_song.path)))
    zeta_id = next(p.id for p in db.playlists() if p.name == "Zeta")
    db.remove_playlist_entries([t.entry_id for t in db.playlist_tracks(zeta_id)][:1])  # p. ej. «quitar faltantes»
    pf.export_all(db, lock_dir)
    previous = os.path.join(lock_dir, "Anteriores", "Zeta.m3u8")
    check("si una playlist pierde canciones, la versión anterior queda en «Anteriores»", os.path.exists(previous)
          and open(previous, encoding="utf-8-sig").read().count(b_song.path) == 2)
    exact = tone(os.path.join(work, "Exacta", "Canción 1 — Señor.wav"))  # mismo título que otra de la biblioteca
    open(os.path.join(rev, "exacta.m3u8"), "w", encoding="utf-8").write(f"#EXTM3U\n#PLAYLIST:Exacta\n#EXTINF:1,Canción 1 — Señor\n{exact}\n")
    pf.apply_restore(db, pf.plan_restore([pf.read_file(os.path.join(rev, "exacta.m3u8"))], db.all_tracks()))
    ex = next(p for p in db.playlists() if p.name == "Exacta")
    check("si la canción está en el disco en su ruta exacta, se usa esa (no otra con el mismo título)",
          [t.path for t in db.playlist_tracks(ex.id)] == [exact], [t.path for t in db.playlist_tracks(ex.id)])

    print("[En la ventana: copia automática, Guardar copia… y Restaurar…]")
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
    from app.ui import main_window as mw
    auto_dir = str(config.playlists_backup_dir())
    shutil.rmtree(auto_dir, ignore_errors=True)
    win = mw.MainWindow(db); win.show(); spin(200)
    def wait_file(path, ms):
        end = time.time() + ms / 1000
        while time.time() < end and not os.path.exists(path):
            spin(50)
        return os.path.exists(path)
    first = os.path.join(auto_dir, pf.safe_name(db.playlists()[0].name) + ".m3u8")  # las que hay ahora en la biblioteca
    check("al abrir el programa se hace la copia automática de las playlists que ya hay",
          wait_file(first, 8000), os.listdir(auto_dir) if os.path.isdir(auto_dir) else "sin carpeta")
    nueva = db.create_playlist("Ensayo del jueves")
    db.add_to_playlist(nueva.id, [db.all_tracks()[0].id])
    changed = getattr(win, "_playlists_changed", None)
    if changed is not None:
        changed()
    check("  y al cambiar una playlist, unos segundos después", wait_file(os.path.join(auto_dir, "Ensayo del jueves.m3u8"), 8000))
    actions = {a.objectName(): a for a in win.findChildren(mw.QAction)}
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    manual = os.path.join(work, "Pendrive2")
    os.makedirs(manual)
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: manual)
    if "act_save_playlists" in actions:
        actions["act_save_playlists"].trigger(); spin(200)
    check("Playlists → «Guardar copia de las playlists…» las guarda en la carpeta elegida",
          os.path.exists(os.path.join(manual, "Ensayo del jueves.m3u8")), os.listdir(manual))
    db.delete_playlist(nueva.id); win._playlists_changed() if changed else None
    seen = []
    def answer():
        d = next((w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()), None)
        if d is None:
            QTimer.singleShot(100, answer); return
        seen.append(type(d).__name__)
        d.accept()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(300, answer)
    if "act_restore_playlists" in actions:
        actions["act_restore_playlists"].trigger(); spin(500)
    check("Playlists → «Restaurar playlists…» muestra cuáles hay y las restaura", seen == ["PlaylistRestoreDialog"]
          and "Ensayo del jueves" in [p.name for p in db.playlists()], (seen, [p.name for p in db.playlists()]))
    win._playlist_backup.stop()
    win._reload_library()  # p. ej. «Localizar archivo…» o datos de internet: cambian rutas o títulos
    check("  cambiar rutas o títulos de canciones también actualiza la copia automática", win._playlist_backup.isActive())
    win.close(); spin(100)
    db = Database(config.database_path())

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
db.close()
sys.exit(0 if all(results) else 1)
