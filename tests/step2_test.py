"""Pruebas de los pasos 1 y 2 del arquitecto: registro común, cierre inesperado, anotación en el MP3,
fallo inesperado del trabajador, respaldo fallido, liberación de diálogos y aviso de repetición."""
import math
import os
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace

ROOT = tempfile.mkdtemp(prefix="mp_step2_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(ROOT, "datos")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\reproductor-musica")

import lameenc  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication(sys.argv)

from app import backup, converter, journal, mp3gain  # noqa: E402
from app.loudness_job import AdjustWorker  # noqa: E402
from app.models import Track  # noqa: E402
from app.ui import dialogs  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")


def make_mp3(path, seconds=3, amp=0.1):
    enc = lameenc.Encoder()
    enc.set_bit_rate(128); enc.set_in_sample_rate(44100); enc.set_channels(2); enc.set_quality(2)
    frames = bytearray()
    for i in range(44100 * seconds):
        v = int(amp * 32767 * math.sin(2 * math.pi * 440 * i / 44100))
        frames += struct.pack("<hh", v, v)
    data = enc.encode(bytes(frames)) + enc.flush()
    open(path, "wb").write(data)


def track(tid, path, **kw):
    return Track(id=tid, path=path, title=os.path.basename(path), artist="Prueba", album="", genre="", duration_ms=3000, added_at="2026-10-23", **kw)


music = os.path.join(ROOT, "Musica")
os.makedirs(music)


def program_mp3(item):
    """MP3 como lo deja el programa: con su marca de «creado a partir de este original»."""
    from mutagen.id3 import ID3, TXXX
    open(item.mp3, "wb").write(b"mp3 creado")
    tags = ID3(); tags.add(TXXX(encoding=3, desc=converter._CREATED_MARK, text=[converter._origin_id(item.original)]))
    tags.save(item.mp3)

# ---------------------------------------------------------------- 1. cierre inesperado en la conversión
print("1. Conversión: cierre inesperado justo después de mover el original")
src = os.path.join(music, "cancion.wma")
open(src, "wb").write(b"original-wma" * 100)
t1 = track(1, src)
session = converter.new_session([t1])
session.save()
item = session.items[0]
program_mp3(item)  # el MP3 ya se había creado
# Simula el cierre: se anota la intención y se mueve, pero el registro no llega a guardar nada más.
target = converter.original_target(item, session.originals_root)
item.moved_to = target
session.save()
os.makedirs(os.path.dirname(target), exist_ok=True)
os.rename(src, target)
reloaded = converter.interrupted_sessions()
check("al abrir se detecta la conversión interrumpida", len(reloaded) == 1)
again = reloaded[0]
check("el registro sabe dónde quedó el original", again.items[0].moved_to == target)
check("queda pendiente de deshacer aunque no se marcara como hecha", len(converter.pending_items(again)) == 1)
restored, problems = converter.undo(again)
check("deshacer devuelve el original a su sitio", os.path.exists(src) and not os.path.exists(target), problems)
check("el MP3 creado se quita", not os.path.exists(item.mp3))
check("la sesión queda deshecha", converter.list_sessions()[0].status == converter.STATUS_UNDONE)

print("2. Conversión: cierre ANTES de mover (solo la intención anotada)")
session = converter.new_session([t1])
item = session.items[0]
program_mp3(item)
item.moved_to = converter.original_target(item, session.originals_root)
session.save()  # se cierra aquí: el original nunca se movió
again = [s for s in converter.interrupted_sessions() if s.id == session.id][0]
restored, problems = converter.undo(again)
check("el original sigue intacto en su sitio", open(src, "rb").read() == b"original-wma" * 100, problems)
check("el MP3 a medias se quita", not os.path.exists(item.mp3))

print("3. Conversión: el MP3 nunca se borra si el original no aparece")
session = converter.new_session([t1])
item = session.items[0]
open(item.mp3, "wb").write(b"mp3 unico")
item.done = True
item.moved_to = os.path.join(session.originals_root, "no-existe.wma")
session.save()
os.rename(src, src + ".perdido")  # el original desapareció por fuera del programa
restored, problems = converter.undo(session)
check("el MP3 se conserva", os.path.exists(item.mp3), problems)
check("se informa el problema", len(problems) == 1)
os.rename(src + ".perdido", src)
os.remove(item.mp3)

print("4. Registro: un archivo de registro dañado no impide leer los demás")
bad = converter.sessions_dir() / "conversion-99999999-999999.json"
bad.write_text("{ roto", encoding="utf-8")
check("los registros sanos se siguen leyendo", len(converter.list_sessions()) >= 3)
bad.unlink()
check("la escritura atómica no deja temporales", not list(converter.sessions_dir().glob("*.tmp")))
check("was_moved distingue origen/destino",
      journal.was_moved(os.path.join(ROOT, "nada"), src) and not journal.was_moved(src, src))

# ---------------------------------------------------------------- anotación en el MP3
print("5. Anotación del ajuste de volumen dentro del MP3")
mp3 = os.path.join(music, "baja.mp3")
make_mp3(mp3)
untouched = open(mp3, "rb").read()
worker = AdjustWorker([(track(10, mp3), 2)])
emitted = []
worker.adjusted.connect(lambda *a: emitted.append(a))
finished = []
worker.finished.connect(lambda: finished.append(True))
worker.run()
check("se ajustó 2 pasos y se anotó el total", emitted == [(10, 2, 2, "")], emitted)
check("la anotación dice 2 pasos", mp3gain.read_applied_steps(mp3) == 2)
worker = AdjustWorker([(track(10, mp3), -99)])  # revertir: manda lo que diga el archivo
emitted.clear()
worker.adjusted.connect(lambda *a: emitted.append(a))
worker.run()
check("revertir usa la anotación del archivo", emitted == [(10, -2, 0, "")], emitted)
check("tras revertir el archivo queda idéntico al original", open(mp3, "rb").read() == untouched)

print("6. Relleno al arrancar: canciones ajustadas según la biblioteca pero sin anotación")
mp3b = os.path.join(music, "ajustada-antes.mp3")
make_mp3(mp3b)
mp3gain.apply_steps(mp3b, 3)  # como las 172 canciones ajustadas antes de existir la anotación
playing = os.path.join(music, "sonando.mp3")
make_mp3(playing)
mp3gain.apply_steps(playing, 1)
lib = [
    track(20, mp3b, norm_gain_db=4.5),
    track(21, playing, norm_gain_db=1.5),
    track(22, mp3, norm_gain_db=0.0),
    track(23, os.path.join(music, "no-esta.mp3"), norm_gain_db=3.0, available=False),
]
from app.file_operations import FileOperations
fake = SimpleNamespace(library=lib, player=SimpleNamespace(current_track=lib[1]), ops=FileOperations)
before_audio = open(mp3b, "rb").read()
MainWindow.sync_volume_annotations(fake)
check("se anota la ajustada (3 pasos)", mp3gain.read_applied_steps(mp3b) == 3)
check("la que está sonando se deja para el próximo arranque", mp3gain.read_applied_steps(playing) == 0)
check("la no ajustada no recibe anotación", mp3gain.read_applied_steps(mp3) == 0)
frames_before = mp3gain.inspect.__wrapped__ if hasattr(mp3gain.inspect, "__wrapped__") else None
check("el audio no cambia al anotar", open(mp3b, "rb").read()[:len(before_audio) - 200] == before_audio[:len(before_audio) - 200]
      and mp3gain.inspect(mp3b).frames == mp3gain.inspect(mp3).frames)
MainWindow.sync_volume_annotations(fake)
check("repetirlo no duplica ni cambia la anotación", mp3gain.read_applied_steps(mp3b) == 3)
worker = AdjustWorker([(track(20, mp3b), -2)])
emitted.clear()
worker.adjusted.connect(lambda *a: emitted.append(a))
worker.run()
check("una canción rellenada se revierte completa (3 pasos)", emitted == [(20, -3, 0, "")], emitted)

# ---------------------------------------------------------------- fallo inesperado del trabajador
print("7. Un error inesperado en el trabajador no deja el diálogo colgado")
real = mp3gain.read_applied_steps
mp3gain.read_applied_steps = lambda p: 1 / 0
worker = AdjustWorker([(track(30, mp3), 2), (track(31, mp3), 2)])
emitted.clear(); finished.clear()
worker.adjusted.connect(lambda *a: emitted.append(a))
worker.finished.connect(lambda: finished.append(True))
worker.run()
mp3gain.read_applied_steps = real
check("cada canción informa el error", len(emitted) == 2 and all("Error inesperado" in e[3] for e in emitted), emitted)
check("el trabajador termina (la ventana se puede cerrar)", finished == [True])
check("el archivo no se tocó", open(mp3, "rb").read() == untouched)

# ---------------------------------------------------------------- respaldo previo fallido
print("8. Si el respaldo previo falla, se pregunta antes de seguir")
real_backup, real_ask = backup.create_backup, dialogs.ask
backup.create_backup = lambda conn, reason: None
asked = []
dialogs.ask = lambda *a, **k: (asked.append(a[2]), 0)[1]
check("«Cancelar» detiene la operación", dialogs.backup_before(None, None, "x") is False)
dialogs.ask = lambda *a, **k: 1
check("«Continuar sin respaldo» sigue", dialogs.backup_before(None, None, "x") is True)
backup.create_backup = lambda conn, reason: "ok.db"
dialogs.ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía preguntar"))
check("con respaldo correcto no pregunta", dialogs.backup_before(None, None, "x") is True)
backup.create_backup, dialogs.ask = real_backup, real_ask
check("el aviso explica el problema", asked and "respaldo" in asked[0])

# ---------------------------------------------------------------- diálogos liberados y aviso de repetición
print("9. Los diálogos se liberan al cerrarse")
dialog = QDialog()
gone = []
dialog.destroyed.connect(lambda: gone.append(True))
QTimer.singleShot(50, dialog.accept)
check("devuelve el resultado del diálogo", MainWindow._run_dialog(dialog) == 1)
from PySide6.QtCore import QEvent
app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)  # procesa deleteLater
app.processEvents()
check("el diálogo se destruyó", gone == [True])

print("10. Restaurar los ajustes no muestra «Repetición: …»")
shown = []
bar = SimpleNamespace(showMessage=lambda *a: shown.append(a))
fake = SimpleNamespace(player_bar=SimpleNamespace(set_repeat=lambda m: None), statusBar=lambda: bar, _restoring=True)
MainWindow._on_repeat_changed(fake, 1)
check("al restaurar no hay aviso", shown == [])
fake._restoring = False
MainWindow._on_repeat_changed(fake, 1)
check("al cambiarla el usuario sí hay aviso", len(shown) == 1 and "toda la lista" in shown[0][0])

shutil.rmtree(ROOT, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush()
os._exit(0 if all(results) else 1)
