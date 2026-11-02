"""Organizador, fase 1: reglas para el título, el artista principal y el nombre del archivo. Sin ventanas ni archivos."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.title_format import clean_song_title, file_stem, main_artist, strip_noise

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("  OK  " if ok else " FALLA"), name, ("— " + str(detail)) if detail else "", flush=True)
def table(name, function, cases):
    bad = {k: function(*k) if isinstance(k, tuple) else function(k) for k in cases}
    bad = {k: got for k, got in bad.items() if got != cases[k]}
    check(name, not bad, bad)

print("[Numeración inicial]")
table("se quita la numeración de pista", strip_noise, {
    "01 - Cancion": "Cancion", "02. Cancion": "Cancion", "001_Cancion": "Cancion", "01-Cancion": "Cancion",
    "02.Cancion": "Cancion", "2.Cancion": "Cancion", "12_Cancion": "Cancion", "003 - Cancion": "Cancion",
    "01 Cancion": "Cancion", "7) Cancion": "Cancion", "3-4 de 19 Cancion": "Cancion", "4ª Cancion": "Cancion",
})
table("se conservan los números del título", strip_noise, {
    "7 Dias": "7 Dias", "1999": "1999", "1999 - Prince": "1999 - Prince", "3 Dias": "3 Dias", "7 de Mayo": "7 de Mayo",
    "1º de Mayo": "1º de Mayo", "24/7 Adoracion": "24/7 Adoracion", "40 de Fe": "40 de Fe", "100 Razones": "100 Razones",
    "4.40 Musica": "4.40 Musica", "7-Eleven": "7-Eleven", "007 Agente": "007 Agente", "06.": "06.",
})

print("[Título]")
table("sin YouTube ni colaboradores, con tildes y versión", clean_song_title, {
    "Ángel (Video Oficial)": "Ángel",
    "Santo (En Vivo) [Video Oficial]": "Santo (En Vivo)",
    "Mi Tesoro (feat. Daniela Barrientos)": "Mi Tesoro",
    "Tú Estás Aquí ft. Marcela Gándara": "Tú Estás Aquí",
    "Dios Remix (Ft. Otro) (Live)": "Dios Remix (Live)",
    "01 - ¿Quién Como Tú?": "Quién Como Tú?",
    "Walk With Me": "Walk With Me",
    "Soft Rock": "Soft Rock",
})

print("[Artista principal]")
table("uno solo", main_artist, {
    "Marcos Brunet ft. abbiegamboa": "Marcos Brunet",
    "Generación 12 feat. Marcos Barrientos": "Generación 12",
    "Grupo Grace Feat OASISMINISTRY": "Grupo Grace",
    "Abel Zavala, Marcela Gandara": "Abel Zavala",
    "Israel Houghton (feat. New Breed)": "Israel Houghton",
    "Jesus Worship Center (Live)": "Jesus Worship Center",
    "Montesanto Oficial": "Montesanto",
    "Lilly Goodman - Topic": "Lilly Goodman",
    "Marcela Gándara.": "Marcela Gándara",
})
table("«&» e «y» no se cortan sin confirmación", main_artist, {
    "Ana y Ricky": "Ana y Ricky", "Israel & New Breed": "Israel & New Breed", "En Espíritu Y En Verdad": "En Espíritu Y En Verdad",
})
check("el dato confirmado manda", main_artist("Bethel Music & Steffany Gretzinger", "Bethel Music") == "Bethel Music")

print("[Nombre del archivo]")
table("formato TITULO - ARTISTA", file_stem, {
    ("Es Por Tu Gracia", "Jesús Adrián Romero"): "Es Por Tu Gracia - Jesus Adrian Romero",
    ("Un Año Más", "Peña"): "Un Ano Mas - Pena",
    ("¿Quién Como Tú?", "Ñandú"): "Quien Como Tu - Nandu",
    ("Santo (En Vivo)", "New Wine"): "Santo En Vivo - New Wine",
    ("It's a New Day", "Bethel Music"): "Its a New Day - Bethel Music",
    ("Hay un Rey / Que Ruja el León", "Marcos"): "Hay un Rey Que Ruja el Leon - Marcos",
    ("Campfire Coritos", "Israel & New Breed"): "Campfire Coritos - Israel y New Breed",
    ("►► Cancion", "A"): "Cancion - A",
    ("01 - Cancion", "A"): "Cancion - A",
    ("001_Cancion", "A"): "Cancion - A",
    ("7 Dias", "A"): "7 Dias - A",
    ("1999", "Prince"): "1999 - Prince",
    ("Sin Artista", ""): "Sin Artista",
})
check("si el título no deja nada, no inventa", file_stem("日本語", "A") == "" and file_stem("♪♪♪", "A") == "")
samples = ["01 - ¡Señor!", "¿Qué?", "(En Vivo) Santo", "#1 Fan", "...Cancion", "_Cancion", "[Oficial] Cancion", "—Cancion"]
bad = [s for s in samples if not file_stem(s, "A")[:1].isalnum()]
check("nunca empieza con un signo", not bad, bad)
bad = [s for s in samples + ["Cañón: «Ñu»", "Olé & Más"] if not file_stem(s, "Peña").isascii()]
check("solo letras sin tildes, números y espacios", not bad, bad)
check("no le quedan caracteres prohibidos en Windows", not set('<>:"/\\|?*') & set(file_stem('a<b>c:d"e/f\\g|h?i*j', "x")))

print(f"\nRESULTADO: {sum(results)}/{len(results)} correctas")
sys.exit(0 if all(results) else 1)
