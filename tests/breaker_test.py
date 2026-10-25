import sys, time; sys.path.insert(0, r"D:\reproductor-musica")
from PySide6.QtCore import QCoreApplication
app = QCoreApplication(sys.argv)
from app import online_lookup as ol
from app.ui.online_dialog import LookupWorker
calls = {"musicbrainz": 0, "deezer": 0}
def dead(q, limit=8):
    calls["musicbrainz"] += 1; raise ol.LookupError_("No se pudo conectar con MusicBrainz. Revisa tu conexión a internet.")
def ok(q, limit=8):
    calls["deezer"] += 1; return [ol.Candidate("deezer", q.title, "X", "Y", 1000)]
ol._SEARCHERS["musicbrainz"] = dead; ol._SEARCHERS["deezer"] = ok
w = LookupWorker([ol.Query(f"t{i}", "a") for i in range(6)], ["musicbrainz", "deezer"])
found = []; w.found.connect(lambda i, r: found.append(r))
w.run()
print("consultas a MusicBrainz caído:", calls["musicbrainz"], "(debe ser 2) | a Deezer:", calls["deezer"], "(debe ser 6)")
print("resultados con datos:", sum(1 for r in found if r.candidates), "de 6")
print("aviso:", [e for r in found for e in r.errors if "se omite" in e])
ok = calls == {"musicbrainz": 2, "deezer": 6}
print("RESULTADO:", "OK" if ok else "FALLA")
sys.exit(0 if ok else 1)
