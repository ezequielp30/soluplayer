"""Un MP3 real para las pruebas que necesitan audio de verdad (siempre se trabaja sobre copias).

Se prefiere la canción de siempre; si ya no está (se movió la música), cualquier MP3 que exista de la
biblioteca del usuario, que se abre solo para leer."""
import os
import sqlite3

PREFERIDA = r"D:\Musica Cristiana\Padre Celestial (Variado)\01 - Track 1.mp3"
BIBLIOTECA = os.path.expandvars(r"%LOCALAPPDATA%\ReproductorMusica\biblioteca.db")


def mp3_existentes(limite: int = 1) -> list[str]:
    """Hasta `limite` MP3 de la biblioteca que existen en el disco (menos de 15 minutos)."""
    found = [PREFERIDA] if os.path.isfile(PREFERIDA) else []
    if len(found) < limite and os.path.isfile(BIBLIOTECA):
        con = sqlite3.connect(f"file:{BIBLIOTECA}?mode=ro", uri=True)
        try:
            rows = con.execute("select path from tracks where lower(path) like '%.mp3' and duration_ms between 1 and 900000 "
                               "order by random() limit 200").fetchall()
        finally:
            con.close()
        for (path,) in rows:
            if path not in found and os.path.isfile(path):
                found.append(path)
            if len(found) >= limite:
                break
    if not found:
        raise SystemExit("No hay ningún MP3 de la biblioteca en el disco para esta prueba.")
    return found


def mp3_real() -> str:
    return mp3_existentes(1)[0]
