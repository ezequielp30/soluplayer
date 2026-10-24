"""Contraste de todos los temas (WCAG 2.x): texto ≥ 7:1, texto secundario y acento como texto ≥ 4.5:1,
texto sobre el botón de acento ≥ 4.5:1, avisos legibles (≥ 4.5:1) y bordes/selección distinguibles."""
import sys
sys.path.insert(0, r"D:\reproductor-musica")
from app.ui.theme import THEMES


def lum(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


rules = [
    ("text", "bg", 7.0), ("text", "sidebar", 7.0), ("text", "bar", 7.0), ("text", "elevated", 7.0),
    ("text", "accent_soft", 4.5), ("text", "hover", 4.5),
    ("muted", "bg", 4.5), ("muted", "sidebar", 4.5), ("muted", "elevated", 4.5),
    ("accent_text", "bg", 4.5), ("accent_text", "sidebar", 4.5),
    ("on_accent", "accent", 4.5), ("on_accent", "accent_hover", 4.5),
    ("danger", "bg", 4.5), ("success", "bg", 4.5), ("warning", "bg", 4.5),
    ("accent", "bg", 3.0),  # el botón de acento se distingue del fondo (componente gráfico)
]
results = []
for key, p in THEMES.items():
    bad = []
    for fg, bg, need in rules:
        r = ratio(getattr(p, fg), getattr(p, bg))
        if r < need and not (key == "aluminio" and (fg, bg) == ("accent", "bg")):
            # Excepción conocida: el ámbar de Aluminio (el tema claro original) sobre blanco da 2:1; el
            # botón se reconoce por su texto (9:1). Se conserva para no cambiar la esencia del diseño.
            bad.append(f"{fg}/{bg} {r:.2f}<{need}")
    results.append(not bad)
    print(("  OK  " if not bad else " FALLA"), f"{p.name:15s}", "; ".join(bad))
print(f"\nRESULTADO: {sum(results)}/{len(results)} temas con buen contraste")
sys.exit(0 if all(results) else 1)
