# Receta de PyInstaller: genera dist\ReproductorMusica\ReproductorMusica.exe (modo carpeta).
# Se ejecuta desde crear-instalador.ps1; las rutas son relativas a la carpeta del proyecto.
# -*- mode: python ; coding: utf-8 -*-
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Módulos de Qt que el programa no usa: excluirlos reduce mucho el tamaño.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DExtras",
    "PySide6.Qt3DAnimation", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtSpatialAudio",
    "PySide6.QtHttpServer", "PySide6.QtUiTools", "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtDBus",
    "PySide6.QtMultimediaWidgets",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "assets", "icono.ico"), "assets"),
        # Menús editables con Qt Designer, y su copia original de respaldo.
        (os.path.join(ROOT, "assets", "menus.ui"), "assets"),
        (os.path.join(ROOT, "assets", "menus.original.ui"), "assets"),
        # Licencias de los componentes de terceros (obligatorio al distribuir el programa).
        (os.path.join(ROOT, "licencias"), "licencias"),
        # Huella digital del audio (Chromaprint): lo descarga con su huella comprobada tools/obtener_fpcalc.py.
        (os.path.join(ROOT, "build", "herramientas", "fpcalc.exe"), "fpcalc"),
    ],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=EXCLUDES,
    noarchive=False,
)
# Complementos que Qt arrastra pero el programa no usa: teclado virtual (con todo Qml/Quick), el lector de
# PDF y decodificadores de imagen que nunca hacen falta (las carátulas solo se aceptan en JPEG o PNG):
# quitarlos ahorra espacio y deja menos código nativo expuesto a imágenes manipuladas. opengl32sw.dll es el
# OpenGL por software (Mesa) que solo usa Qt Quick: la interfaz de Widgets dibuja sin OpenGL.
_UNUSED = (
    "qtvirtualkeyboard", "qt6virtualkeyboard", "qt6quick", "qt6qml", "qpdf", "qt6pdf", "qt6opengl.dll",
    "qtiff.dll", "qwebp.dll", "qicns.dll", "qtga.dll", "qwbmp.dll", "opengl32sw.dll",
)
a.binaries = [b for b in a.binaries if not any(u in b[0].lower().replace("\\", "/").split("/")[-1] for u in _UNUSED)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReproductorMusica",
    console=False,  # programa de ventanas: sin consola negra
    icon=os.path.join(ROOT, "assets", "icono.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
    upx=False,  # UPX dispara falsos positivos en antivirus
)

coll = COLLECT(exe, a.binaries, a.datas, name="ReproductorMusica", upx=False)
