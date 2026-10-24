@echo off
rem Abre los menus del Reproductor de Musica en Qt Designer (editor grafico de Qt).
rem Al terminar: Archivo > Guardar en Designer, y vuelve a abrir el programa para ver los cambios.
start "" "%~dp0.venv\Scripts\pyside6-designer.exe" "%~dp0assets\menus.ui"
