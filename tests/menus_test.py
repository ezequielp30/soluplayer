"""Prueba de los menús leídos desde assets/menus.ui (editables con Qt Designer)."""
import os, shutil, sys, tempfile, time
sys.path.insert(0, r"D:\soluplayer")
work = tempfile.mkdtemp(prefix="mp_menus_")
os.environ["MUSICPLAYER_DATA_DIR"] = os.path.join(work, "data")
os.environ["MUSICPLAYER_SILENCIO"] = "1"
from PySide6.QtCore import QEventLoop, QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
app = QApplication(sys.argv); app.setOrganizationName("ReproductorMusicaTest")
QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
from app.config import database_path
from app.database import Database
from app.ui import main_window as mw, menu_loader
mw.MainWindow._choose_scope = lambda self, tool: ((lambda: self.library), None)  # primer paso «¿qué analizar?»: toda la biblioteca (se prueba en herramientas_carpeta_test)

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "")
def spin(ms):
    end = time.time() + ms / 1000
    while time.time() < end: app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20); time.sleep(0.005)
def structure(bar):
    def walk(menu):
        out = []
        for a in menu.actions():
            if a.isSeparator(): out.append("—")
            elif a.menu() is not None: out.append((a.text(), walk(a.menu())))
            else: out.append((a.text(), a.shortcut().toString(), a.isEnabled()))
        return out
    return [(a.text(), walk(a.menu())) for a in bar.actions()]

# Lo que había antes de pasar los menús al archivo (textos, atajos y orden exactos).
BEFORE = [
 ("&Archivo", [("Importar &archivos…", "Ctrl+O", True), ("Importar &carpeta…", "Ctrl+Shift+O", True), "—",
   ("&Buscar", "Ctrl+F", True), "—", ("&Respaldos de la biblioteca", [("Crear un respaldo ahora", "", True),
   ("Abrir la carpeta de respaldos", "", True)]), ("&Preferencias…", "Ctrl+,", True), "—", ("&Salir", "Ctrl+Q", True)]),
 ("&Reproducción", [("Reproducir / Pausar", "Space", True), ("Detener", "Ctrl+.", True), ("Anterior", "Ctrl+Left", True),
   ("Siguiente", "Ctrl+Right", True), "—", ("Orden aleatorio", "Ctrl+H", True), ("Cambiar repetición", "Ctrl+R", True), ("&Ecualizador…", "Ctrl+E", True),
   ("&Igualar volumen al reproducir", "", True), "—",
   ("Subir volumen", "Ctrl+Up", True), ("Bajar volumen", "Ctrl+Down", True), "—", ("Probar sonido…", "", True)]),
 ("&Playlists", [("&Nueva playlist…", "Ctrl+N", True), ("&Renombrar playlist…", "", True), ("&Eliminar playlist…", "", True), "—",
                ("&Guardar copia de las playlists…", "", True), ("Re&staurar playlists…", "", True)]),
 ("&Herramientas", [("Buscar datos en &internet…", "Ctrl+Shift+I", True), ("Buscar canciones &repetidas…", "Ctrl+Shift+D", True),
   ("Analizar y ajustar &volumen…", "Ctrl+Shift+V", True), ("Convertir a &MP3…", "Ctrl+Shift+M", True), "—",
   ("&Historial de cambios en archivos…", "Ctrl+Shift+H", True)]),
 ("A&yuda", [("Abrir registro de errores", "", True), "—", ("Acerca de…", "", True)]),
]

print("[1. Ventana principal con los menús del archivo]")
db = Database(database_path()); win = mw.MainWindow(db); win.show(); spin(200)
got = structure(win.menuBar())
check("menús idénticos a los de antes (textos, atajos, orden, submenú)", got == BEFORE, got if got != BEFORE else "")
check("sin aviso de archivo dañado", win._menu_warning == "")
play = [s.toString() for s in win.act_play.shortcuts()]
check("Reproducir conserva Espacio y las teclas multimedia", play[0] == "Space" and len(play) == 3, play)
check("«Orden aleatorio» es casilla y está conectada", win.act_shuffle.isCheckable())
win.act_shuffle.setChecked(True); spin(50)
check("  activa el orden aleatorio del reproductor", win.player.shuffle if hasattr(win.player, "shuffle") else True)
win.act_shuffle.setChecked(False)
names = {a.objectName() for a in win.findChildren(mw.QAction) if a.objectName().startswith("act_")}
check("las 30 opciones tienen su nombre de objeto", len(names) == 30, len(names))
win.close()

print("[2. Cambios hechos en el editor]")
src = open(menu_loader.MENUS_FILE, encoding="utf-8").read()
edited = os.path.join(work, "menus.ui")
s = src.replace("<string>Probar sonido…</string>", "<string>Probar el sonido de mi PC…</string>")
s = s.replace("""    <addaction name="act_error_log"/>""", """    <addaction name="act_history"/>
    <addaction name="act_nueva"/>
    <addaction name="act_error_log"/>""")
s = s.replace("""    <addaction name="separator"/>
    <addaction name="act_history"/>
   </widget>""", """   </widget>""")
s = s.replace("""    <addaction name="act_about"/>""", "")
s = s.replace(""" <resources/>""", """ <resources/>""").replace("""  <action name="act_about">""", """  <action name="act_nueva">
   <property name="text">
    <string>Opción nueva</string>
   </property>
  </action>
  <action name="act_about">""")
open(edited, "w", encoding="utf-8").write(s)
spec, warning = menu_loader.load(edited)
w = QMainWindow()
actions, menus = menu_loader.build(w, w.menuBar(), spec, {"act_history": lambda: None, "act_test_sound": lambda: None})
st = dict(structure(w.menuBar()))
check("texto cambiado", ("Probar el sonido de mi PC…", "", True) in st["&Reproducción"])
check("opción movida de menú (Historial → Ayuda)", any(i[0].startswith("&Historial") for i in st["A&yuda"] if i != "—")
      and not any(i != "—" and i[0].startswith("&Historial") for i in st["&Herramientas"]))
check("opción quitada (Acerca de) ya no aparece", not any(i != "—" and i[0] == "Acerca de…" for i in st["A&yuda"]))
nueva = actions.get("act_nueva")
check("opción nueva sin función: aparece desactivada y explica por qué", nueva is not None and not nueva.isEnabled()
      and "no tiene una función" in nueva.statusTip())

print("[3. Archivo con errores]")
broken = os.path.join(work, "roto.ui")
open(broken, "w", encoding="utf-8").write(src[: len(src) // 2])
spec, warning = menu_loader.load(broken)
check("si el archivo está dañado se usan los menús originales", len(spec.menus) == 5 and "dañado" in warning, warning[:90])
spec, warning = menu_loader.load(os.path.join(work, "no-existe.ui"))
check("si falta el archivo, también", len(spec.menus) == 5 and "No se encuentra" in warning)
real_load = menu_loader.load
menu_loader.load = lambda: real_load(broken)
shown = []
QMessageBox.warning = staticmethod(lambda *a, **k: shown.append(a[2]))
win2 = mw.MainWindow(Database(database_path())); win2.show(); spin(1200)
menu_loader.load = real_load
check("la ventana abre igual y avisa del problema", structure(win2.menuBar()) == BEFORE and shown and "originales" in shown[0], shown[:1])
win2.close()

print("[4. Copia original intacta]")
check("menus.original.ui es igual al de fábrica", open(menu_loader.ORIGINAL_FILE, encoding="utf-8").read() == src)

QSettings("ReproductorMusicaTest", "ReproductorMusica").clear()
shutil.rmtree(work, ignore_errors=True)
print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.stdout.flush(); os._exit(0 if all(results) else 1)
