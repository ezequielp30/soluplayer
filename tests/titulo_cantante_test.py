"""Herramientas → Título y quién la canta: propone bien, deja el título, el nombre y las etiquetas como
«Canción - Quién la canta», borra los demás datos sin tocar el sonido ni las marcas del programa y se deshace
por completo. Todo en carpetas temporales."""
import os, shutil, sqlite3, sys, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="mp_titulo_cantante_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from mutagen.apev2 import APEv2
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TXXX
import audio_sintetico as synth
from app import converter, journal, song_format
from app.config import database_path
from app.database import Database
from app.file_operations import KIND_FORMAT
from app.importer import scan_file
from app.metadata import UNKNOWN_ALBUM, UNKNOWN_GENRE
from app.title_format import known_singers, propose, strip_noise
from app.ui import dialogs, main_window as mw, song_format_dialog as sfd

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def spin(ms, until=None):
    end = time.time() + ms / 1000
    while time.time() < end and not (until and until()):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10); time.sleep(0.003)
def audio_bytes(path):
    data = open(path, "rb").read()
    if data[:3] != b"ID3":
        return data
    b = data[6:10]
    return data[10 + ((b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]):]

print("[La propuesta]")
library = [
    ("Jesús Adrián Romero - Es Por Tu Gracia (Video Oficial)", "Jesus Adrian Romero"),
    ("Ingrid Rosario - Eres Mi Respirar", "Ingrid Rosario Music"),
    ("Ven, Manifiéstate - Montesanto (Video Oficial)", "Montesanto Oficial"),
    ("Caminare Por Fe | Concierto En Vivo | New Wine", "New Wine"),
    ("El Himno de victoria- VÍDEOCLIP- Danny Berrios . Con letra", "jason81022"),
    ("Sólo En Ti", "Danny Berrios"),
    ("isabelle valdez Una oracion", "isabelle valdez"),
    ("Digno De Adorar I MISSION MUSICA", "MISSION MUSICA"),
    ("Tu amor no tiene fin (Generación 12) - Joel Rocco", "Factor de Cambio"),
    ("Generación 12 - Quiero Conocer", "Generación 12"),
    ("TU PELEAS POR MI (Glorea - En Vivo) | New Wine", "New Wine"),
    ("Hector Lavoe - El Todopoderoso", "Fania Records"),
    ("DIOS MANDA LLUVIA", "zaupagabi"),
    ("Buen Cristiano", "Benjamin Grullón, Benjamin Grullón"),
    ("Encontrarte", "Lilly Goodman"),
    ("Encontrarte (otra)", "Lilly Goodman"),
]
singers = known_singers(library)
want = {
    0: ("Es Por Tu Gracia - Jesús Adrián Romero", True),
    1: ("Eres Mi Respirar - Ingrid Rosario", True),
    2: ("Ven, Manifiéstate - Montesanto", True),
    3: ("Caminare Por Fe - New Wine", True),
    4: ("El Himno de victoria - Danny Berrios", True),
    5: ("Sólo En Ti - Danny Berrios", True),
    6: ("Una oracion - isabelle valdez", True),
    7: ("Digno De Adorar - MISSION MUSICA", True),
    10: ("TU PELEAS POR MI (Glorea - En Vivo) - New Wine", True),
    12: ("DIOS MANDA LLUVIA - zaupagabi", False),
    13: ("Buen Cristiano - Benjamin Grullón", True),
    14: ("Encontrarte - Lilly Goodman", True),
}
for index, (title, sure) in want.items():
    got = propose(*library[index], singers)
    check(f"«{library[index][0][:44]}»", got.title == title and got.sure == sure, (got.title, got.sure))
got = propose(*library[8], singers)
check("lo que está entre paréntesis no es quien canta", got.song.startswith("Tu amor no tiene fin") and got.singer == "Joel Rocco", got)
got = propose(*library[11], singers)
check("si no se sabe quién canta, queda por revisar", not got.sure, got)
check("«(En vivo)» se conserva", "(En vivo)" in strip_noise("Santo (En vivo) [Video Oficial]") and "Oficial" not in strip_noise("Santo (En vivo) [Video Oficial]"))

print("[Numeración y signos del inicio]")
numbered = {
    "3-4 de 19 Marco Barrientos - El Señor": "Marco Barrientos - El Señor",
    "3 de 19 - Santo": "Santo",
    "12/19 Santo": "Santo",
    "7 of 12 - Holy": "Holy",
    "06. Con tu Sangre": "Con tu Sangre",
    "7 - Santo": "Santo",
    "4ª EN EL MISMO SITIO": "EN EL MISMO SITIO",
    "¿A quién tengo yo?": "A quién tengo yo?",
    "► 06. ¡Santo!": "Santo!",
    "3 Días": "3 Días",
    "7 de Mayo": "7 de Mayo",
    "1º de Mayo": "1º de Mayo",
    "1ª del Rey": "1ª del Rey",
    "24/7 Adoración": "24/7 Adoración",
    "40 de Fe": "40 de Fe",
    "2019 - Santo": "2019 - Santo",
    "06.": "06.",
}
bad = {k: strip_noise(k) for k, v in numbered.items() if strip_noise(k) != v}
check("se quita la numeración, no los números que son parte del título", not bad, bad)

print("[El nombre del archivo como pista]")
named = known_singers([("x", "Marco Barrientos"), ("y", "Nancy Amancio"), ("z", "Benjamin Grullón")])
got = propose("3-4 de 19 Marco Barrientos - El SEÑOR está en este lugar / El camino del SEÑOR", "ifernand2011", named,
              r"D:\M\El Señor esta en este lugar - Marco Barrientos.mp3")
check("el nombre confirma: queda Lista y con el título completo",
      got.title == "El SEÑOR está en este lugar / El camino del SEÑOR - Marco Barrientos" and got.sure, got)
got = propose("Benjamin - Ser o No Ser (Audio)", "Twisted Symmetry", named, r"D:\M\Benjamin Grullón - Ser o no Ser.mp3")
check("si el título no alcanza, se propone el nombre, pero por revisar", got.title == "Ser o no Ser - Benjamin Grullón" and not got.sure, got)
got = propose("PISTA  NANCY AMANCIO  AMÁNDOME ASÍ", "ADM Claude", named, r"D:\M\Nancy Amancio - Pista 01.mp3")
check("«Pista 01» no confirma nada", not got.sure and "Pista 01" not in got.title, got)
got = propose("Algo Raro", "canal123", named, r"D:\M\no dice nada.mp3")
check("un nombre sin «Canción - Cantante» no cambia la propuesta", got == propose("Algo Raro", "canal123", named), got)

print("[En el archivo]")
music = os.path.join(work, "Musica"); os.makedirs(music)
path = synth.mp3(os.path.join(music, "Eres mi Respirar - Ingrid Rosario Música Cristiana.mp3"), 2,
                 title="Ingrid Rosario - Eres Mi Respirar (Video Oficial)", artist="Canal de alguien")
tags = ID3(path)
tags.add(TALB(encoding=3, text=["Disco"])); tags.add(TCON(encoding=3, text=["Cristiana"])); tags.add(TDRC(encoding=3, text=["2010"]))
tags.add(COMM(encoding=3, lang="spa", desc="", text=["De YouTube"]))
tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=b"\x89PNG\r\n\x1a\nfake"))
tags.add(TXXX(encoding=3, desc=converter._CREATED_MARK, text=["origen"]))
tags.save(path, v2_version=3)
ape = APEv2(); ape["MP3GAIN_UNDO"] = "-002,-002,N"; ape.save(path)
os.utime(path, (1500000000, 1500000000))
sound, stamp, before_tags = audio_bytes(path), os.stat(path).st_mtime_ns, sorted(ID3(path).keys())
playlist_song = synth.mp3(os.path.join(music, "otra.mp3"), 1, title="Otra - Lilly Goodman", artist="Lilly Goodman")
same_name = synth.mp3(os.path.join(music, "repetida.mp3"), 1, title="Eres Mi Respirar - Ingrid Rosario", artist="Ingrid Rosario")
open(os.path.join(music, "Eres Mi Respirar - Ingrid Rosario.mp3"), "wb").close()  # un archivo ajeno con ese nombre

db = Database(database_path())
for p in (path, playlist_song, same_name):
    db.add_tracks([scan_file(p)[0]])
tid = db.track_id_for_path(path); other_id = db.track_id_for_path(same_name)
db.conn.execute("update tracks set album='Disco', genre='Cristiana', cover_hash=NULL where id=?", (tid,)); db.conn.commit()
pl = db.create_playlist("Mi lista"); db.add_to_playlist(pl.id if hasattr(pl, "id") else pl, [tid])

mw.FILE_TITLES_DELAY_MS = 10**7  # que no se mezcle con la otra limpieza
win = mw.MainWindow(db); win.show(); win.player.set_volume(0); spin(200)
check("está en Herramientas", win.menuBar().findChild(type(win.menuBar()), "") is None and any(
    a.text().replace("&", "") == "Título y quién la canta…" for top in win.menuBar().actions() if top.menu() for a in top.menu().actions()))

answers = []
real_ask = sfd.ask
sfd.ask = lambda *a, **k: (answers.append(a[2]), 0)[1]
real_info = QMessageBox.information
QMessageBox.information = staticmethod(lambda *a, **k: 0)

dlg = sfd.SongFormatDialog(win.ops, lambda: win.library, win); dlg.show(); spin(100)
row = next(i for i, t in enumerate(dlg._rows) if t.id == tid)
check("la propuesta se ve antes de cambiar nada", dlg.table.item(row, sfd.COL_SONG).text() == "Eres Mi Respirar" and dlg.table.item(row, sfd.COL_SINGER).text() == "Ingrid Rosario",
      (dlg.table.item(row, sfd.COL_SONG).text(), dlg.table.item(row, sfd.COL_SINGER).text()))
check("  el archivo sigue igual hasta aplicar", os.path.exists(path) and ID3(path)["TIT2"].text[0].startswith("Ingrid"))
dlg.table.clearSelection(); dlg.table.selectRow(row); dlg._swap_selected()
check("invertir cambia las dos columnas", dlg.table.item(row, sfd.COL_SONG).text() == "Ingrid Rosario")
dlg._swap_selected()
dlg._check_visible(False); dlg.table.item(row, sfd.COL_NOW).setCheckState(Qt.CheckState.Checked)
other_row = next(i for i, t in enumerate(dlg._rows) if t.id == other_id)
dlg.table.item(other_row, sfd.COL_NOW).setCheckState(Qt.CheckState.Checked)
dlg._apply(); spin(20000, lambda: not dlg.runner.busy)
check("pidió confirmar", len(answers) == 1, answers)
new_path = os.path.join(music, "Eres Mi Respirar - Ingrid Rosario (2).mp3")
found = {t.id: t for t in db.with_raw_text(db.all_tracks())}
# Dos canciones con el mismo resultado y un archivo ajeno: ninguno se pisa.
paths = {found[tid].path, found[other_id].path}
check("no se pisa ningún archivo con el mismo nombre", os.path.exists(os.path.join(music, "Eres Mi Respirar - Ingrid Rosario.mp3")) and
      os.path.getsize(os.path.join(music, "Eres Mi Respirar - Ingrid Rosario.mp3")) == 0 and len(paths) == 2 and all(os.path.exists(p) for p in paths), paths)
now_path = found[tid].path
after = ID3(now_path)
check("título y artista dentro del archivo", after["TIT2"].text == ["Eres Mi Respirar - Ingrid Rosario"] and after["TPE1"].text == ["Ingrid Rosario"])
check("  el nombre del archivo también", os.path.basename(now_path).startswith("Eres Mi Respirar - Ingrid Rosario"), os.path.basename(now_path))
check("  los demás datos se borraron", not any(k[:4] in ("TALB", "TCON", "TDRC", "COMM", "APIC") for k in after.keys()), list(after.keys()))
check("  la marca del programa sigue", after.getall(f"TXXX:{converter._CREATED_MARK}"))
check("  el ajuste de volumen anotado sigue", "MP3GAIN_UNDO" in APEv2(now_path))
check("  el sonido es idéntico, byte a byte", audio_bytes(now_path) == sound)
check("  la fecha del archivo no cambia", os.stat(now_path).st_mtime_ns == stamp)
check("en la biblioteca igual", (found[tid].title, found[tid].artist, found[tid].album, found[tid].genre) == ("Eres Mi Respirar - Ingrid Rosario", "Ingrid Rosario", UNKNOWN_ALBUM, UNKNOWN_GENRE),
      (found[tid].title, found[tid].artist, found[tid].album))
check("la canción sigue en su playlist", tid in [t.id for t in db.playlist_tracks(pl.id if hasattr(pl, "id") else pl)])
check("lo ya terminado no vuelve a la lista", tid not in [t.id for t in dlg._rows], [t.title for t in dlg._rows])
dlg.reject(); spin(50)

print("[Deshacer]")
entries = [e for e in win.ops.history(win.library) if e.kind == KIND_FORMAT]
check("en el Historial", len(entries) == 1 and entries[0].can_undo and entries[0].count == 2, [(e.detail, e.status) for e in entries])
outcome = win.ops.undo(entries[0]); spin(100)
back = ID3(path) if os.path.exists(path) else None
check("vuelve el nombre del archivo", back is not None and not os.path.exists(now_path), outcome.message)
check("  vuelven todas las etiquetas, carátula incluida", back is not None and sorted(back.keys()) == before_tags and back["TALB"].text == ["Disco"] and back["APIC:Cover"].data.startswith(b"\x89PNG"),
      sorted(back.keys()) if back else None)
check("  sigue en ID3v2.3", back is not None and back.version[:2] == (2, 3))
check("  y el sonido, idéntico", audio_bytes(path) == sound)
row_back = db.with_raw_text([t for t in db.all_tracks() if t.id == tid])[0]
check("  en la biblioteca, como antes", row_back.album == "Disco" and row_back.genre == "Cristiana" and row_back.path == path, row_back)
entries = [e for e in win.ops.history(win.library) if e.kind == KIND_FORMAT]
check("  queda como deshecha", entries[0].status == "Deshecha" and not entries[0].can_undo, entries[0].status)

print("[Conservar la carátula]")
dlg = sfd.SongFormatDialog(win.ops, lambda: win.library, win); dlg.show(); spin(50)
dlg._check_visible(False); row = next(i for i, t in enumerate(dlg._rows) if t.id == tid)
dlg.table.item(row, sfd.COL_NOW).setCheckState(Qt.CheckState.Checked); dlg.keep_cover.setChecked(True)
dlg._apply(); spin(20000, lambda: not dlg.runner.busy)
kept_path = [t for t in db.all_tracks() if t.id == tid][0].path
check("la carátula se queda y lo demás se va", ID3(kept_path).getall("APIC") and not ID3(kept_path).getall("TALB"))
dlg.reject(); spin(50)

print("[Un archivo en uso no se toca]")
locked = synth.mp3(os.path.join(music, "enuso.mp3"), 1, title="Bloqueada - Lilly Goodman", artist="Lilly Goodman")
db.add_tracks([scan_file(locked)[0]]); win._reload_library(); before = open(locked, "rb").read()
holder = open(locked, "rb")
dlg = sfd.SongFormatDialog(win.ops, lambda: win.library, win); dlg.show(); spin(50)
dlg._check_visible(False); row = next(i for i, t in enumerate(dlg._rows) if t.path == locked)
dlg.table.item(row, sfd.COL_NOW).setCheckState(Qt.CheckState.Checked)
dlg._apply(); spin(20000, lambda: not dlg.runner.busy)
holder.close()
check("avisa y deja todo como estaba", dlg._problems and os.path.exists(locked) and open(locked, "rb").read() == before, dlg._problems)
check("  y la biblioteca también", [t for t in db.all_tracks() if t.path == locked])
dlg.reject(); spin(50)

print("[Corte de luz a mitad]")
cut = synth.mp3(os.path.join(music, "cortada.mp3"), 1, title="Cortada - Lilly Goodman", artist="Lilly Goodman")
db.add_tracks([scan_file(cut)[0]]); cut_id = db.track_id_for_path(cut)
cut_track = db.with_raw_text([t for t in db.all_tracks() if t.id == cut_id])[0]
session = song_format.new_session(); change = song_format.plan(cut_track, "Cortada", "Lilly Goodman", False)
song_format.apply(session, change)  # el archivo cambió, pero la biblioteca no llegó a enterarse
check("  (el corte: la biblioteca apunta al archivo viejo)", db.conn.execute("select path from tracks where id=?", (cut_id,)).fetchone()[0] == cut and not os.path.exists(cut))
win.ops.reconcile_interrupted_format(); spin(50)
check("al abrir, la canción apunta al archivo nuevo y no se pierde", db.conn.execute("select path from tracks where id=?", (cut_id,)).fetchone()[0] == change.new_path)
check("  y se puede deshacer", any(e.kind == KIND_FORMAT and e.session.id == session.id and e.can_undo for e in win.ops.history(win.library)))

print("[Renombrada por fuera]")
loose = synth.mp3(os.path.join(music, "¿Cómo no - Lilly Goodman.mp3"), 2, title="Cómo no - Lilly Goodman", artist="Lilly Goodman")
db.add_tracks([scan_file(loose)[0]]); loose_id = db.track_id_for_path(loose)
loose_track = db.with_raw_text([t for t in db.all_tracks() if t.id == loose_id])[0]
session = song_format.new_session(); change = song_format.plan(loose_track, "Cómo no", "Lilly Goodman", False)
song_format.apply(session, change); change.done = True; song_format.set_in_library(db, change); session.status = journal.STATUS_DONE; session.save()
applied_path = change.new_path; win._reload_library()
outside = os.path.join(music, "4ª " + os.path.basename(applied_path))
os.rename(applied_path, outside)
win._reload_library()
check("  (el archivo tiene otro nombre: la biblioteca no lo encuentra)", not os.path.exists(applied_path))
before_paths = {t.id: t.path for t in db.all_tracks() if t.id != loose_id}
check("al abrir vuelve a apuntar a su archivo", win.ops.reconnect_renamed(win.library) == 1
      and db.conn.execute("select path from tracks where id=?", (loose_id,)).fetchone()[0] == outside)
check("  sin tocar las demás", before_paths == {t.id: t.path for t in db.all_tracks() if t.id != loose_id})
reloaded = next(s for s in song_format.list_sessions() if s.id == session.id)
check("  y el Historial lo sigue encontrando", reloaded.changes[-1].new_path == outside and reloaded.pending())
win._reload_library()
check("  la segunda vez no hay nada que hacer", win.ops.reconnect_renamed(win.library) == 0)
twin_a = synth.mp3(os.path.join(music, "Gemela.mp3"), 2, title="Gemela", artist="A")
db.add_tracks([scan_file(twin_a)[0]]); twin_id = db.track_id_for_path(twin_a)
shutil.move(twin_a, os.path.join(music, "1. Gemela.mp3")); shutil.copy(os.path.join(music, "1. Gemela.mp3"), os.path.join(music, "2. Gemela.mp3"))
win._reload_library()
check("con dos archivos posibles no adivina", win.ops.reconnect_renamed(win.library) == 0
      and db.conn.execute("select path from tracks where id=?", (twin_id,)).fetchone()[0] == twin_a)
other_length = synth.mp3(os.path.join(music, "Larga.mp3"), 2, title="Larga", artist="A")
db.add_tracks([scan_file(other_length)[0]]); long_id = db.track_id_for_path(other_length)
os.remove(other_length); synth.mp3(os.path.join(music, "1. Larga.mp3"), 6, title="Larga", artist="A")
win._reload_library()
check("si dura otra cosa, no es la misma canción", win.ops.reconnect_renamed(win.library) == 0
      and db.conn.execute("select path from tracks where id=?", (long_id,)).fetchone()[0] == other_length)

sfd.ask = real_ask; QMessageBox.information = real_info
win.close(); spin(100)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
