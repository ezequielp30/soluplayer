import sys, threading, time, faulthandler
faulthandler.enable()
sys.path.insert(0, r"D:\reproductor-musica")
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication, QWidget, QProgressBar, QLabel, QPushButton
app = QApplication(sys.argv)
from app.ui.worker_runner import WorkerRunner, _orphans
main = threading.get_ident()

class W(QObject):
    progress = Signal(int, int, str); finished = Signal(bool)
    def __init__(s, delay=0.05): super().__init__(); s.c = False; s.d = delay
    def cancel(s): s.c = True
    @Slot()
    def run(s):
        for i in range(3): s.progress.emit(i, 3, 't%d' % i); time.sleep(s.d)
        s.finished.emit(s.c)

class W0(QObject):
    finished = Signal()
    @Slot()
    def run(s): s.finished.emit()

w = QWidget(); p = QProgressBar(); l = QLabel(); b = QPushButton()
r = WorkerRunner(w, p, l, b); got = []
def cb(*a): got.append((a, threading.get_ident() == main))
r.start(W(), 3, 'x', cb, label='Haciendo')
while r.busy: app.processEvents()
print('1 args', got, 'status', l.text(), flush=True)
got.clear(); r.start(W0(), 0, 'y', cb)
while r.busy: app.processEvents()
print('2 noargs', got, flush=True)

class Slow(QObject):
    finished = Signal()
    @Slot()
    def run(s): time.sleep(1.5); s.finished.emit()

got.clear(); r.start(Slow(), 0, 'z', cb)
t0 = time.time(); ok = r.request_close(wait_ms=200)
print('3 close', ok, round(time.time() - t0, 1), 'orphans', len(_orphans), 'busy', r.busy, flush=True)
t0 = time.time()
while _orphans and time.time() - t0 < 5: app.processEvents()
for _ in range(20): app.processEvents(); time.sleep(0.02)
print('  orphan finished', len(_orphans) == 0, 'callback not called', got == [], flush=True)

got.clear(); r.start(W(0.01), 3, 'w', cb)
ok = r.request_close(); print('4 close-ok', ok, got, 'busy', r.busy, flush=True)

got.clear(); r.start(W(0.2), 3, 'm', cb, modifies_files=True)
from PySide6.QtWidgets import QMessageBox
QMessageBox.information = lambda *a, **k: got.append('aviso')
print('5 modifies blocks', r.request_close() is False, got, flush=True)
while r.busy: app.processEvents()
w.deleteLater(); app.processEvents()
print('6 fin', flush=True)
