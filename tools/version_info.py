"""Pone la versión de app/__init__.py en packaging/version_info.txt (datos del .exe).

Se hace en Python y no en PowerShell: Windows PowerShell 5.1 leía el archivo UTF-8 como ANSI y lo volvía a
guardar, y «Música» terminaba como «MÃºsica» en el Administrador de tareas y en el Mezclador de volumen.
Falla si el resultado no tiene el nombre bien escrito.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import __version__  # noqa: E402

path = ROOT / "packaging" / "version_info.txt"
text = path.read_text(encoding="utf-8-sig")
for _ in range(3):  # repara una doble codificación previa («MÃºsica» → «Música»)
    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        break
    if fixed == text:
        break
    text = fixed
parts = ", ".join((__version__.split(".") + ["0"] * 4)[:4])
text = re.sub(r"filevers=\([^)]*\)", f"filevers=({parts})", text)
text = re.sub(r"prodvers=\([^)]*\)", f"prodvers=({parts})", text)
text = re.sub(r"'(FileVersion|ProductVersion)', '[^']*'", rf"'\1', '{__version__}'", text)
text = text.rstrip() + "\n"
if "Reproductor de Música" not in text or "Ã" in text:
    raise SystemExit("version_info.txt: el nombre del programa quedó mal escrito")
path.write_text(text, encoding="utf-8")
print(f"version_info.txt: {__version__}")
