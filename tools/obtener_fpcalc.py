"""Deja `fpcalc.exe` (Chromaprint) en build/herramientas, comprobando su huella. Lo usan las pruebas y el instalador; no
se guarda en el repositorio. Uso: python tools/obtener_fpcalc.py"""

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.6.2"
URL = f"https://github.com/acoustid/chromaprint/releases/download/v{VERSION}/chromaprint-fpcalc-{VERSION}-windows-x86_64.zip"
SHA256 = "b74369726676670af3ab0eadff45f960cf969fdf4a87a971ba37eaf8d530e874"
TARGET = Path(__file__).resolve().parent.parent / "build" / "herramientas" / "fpcalc.exe"


def main() -> int:
    if TARGET.is_file():
        print(f"Ya está: {TARGET}")
        return 0
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        print("La huella de la descarga no coincide: no se instala.", file=sys.stderr)
        return 1
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        member = next(n for n in archive.namelist() if n.endswith("/fpcalc.exe") or n == "fpcalc.exe")
        content = archive.read(member)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(content)
    print(f"Listo: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
