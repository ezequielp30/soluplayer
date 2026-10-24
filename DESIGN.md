# Diseño visual — «Hi-Fi»

Referencia: el frontal de un equipo de música. Grafito o aluminio, con la luz ámbar de un vúmetro como único acento.
Modo: **Operate** (herramienta de uso diario): primero la claridad, y la marca se nota en los detalles.

## Temas

Hay dos temas, **Grafito** (oscuro) y **Aluminio** (claro), definidos en `app/ui/theme.py` como roles con nombre.
En modo *automático* sigue a Windows; la barra de título acompaña al tema.

| Rol | Grafito | Aluminio | Uso |
|---|---|---|---|
| `bg` | `#17181c` | `#fbfbfc` | panel principal |
| `sidebar` | `#111215` | `#f0f1f4` | barra lateral |
| `bar` | `#1c1d22` | `#f6f7f9` | barra del reproductor, menús, estado |
| `elevated` | `#23252b` | `#ffffff` | tarjeta «sonando», campos, menús |
| `border` | `#2e3038` | `#e1e3e8` | única forma de elevación (sin sombras) |
| `text` / `muted` | `#eceef1` / `#a3a7b1` | `#16171b` / `#5c606b` | texto principal / secundario (≥ 4.5:1) |
| `accent` | `#f5a524` | `#eda21b` | rellenos: botón reproducir, progreso, volumen |
| `accent_text` | `#f7b548` | `#9a5a00` | ámbar como texto o icono (canción actual, enlaces) |
| `accent_soft` | `#3a2f1a` | `#fcecc9` | selección |
| `on_accent` | `#1c1404` | `#2a1a00` | texto o icono sobre el relleno ámbar |

Reglas:
- El ámbar marca solo lo **activo**: reproducir, la canción que suena, la selección, los modos encendidos.
- No hay sombras ni brillos: la elevación se marca con borde o con un cambio de superficie.
- Los colores siempre se toman por rol (`theme.color("muted")`), nunca escritos a mano en los widgets.

## Tipografía

Segoe UI Variable (Text para la interfaz, Display para los títulos de 24 pt en peso 700, algo compactados).
Los textos secundarios a 9 pt en `muted`, y los tiempos a 8.5 pt.

## Formas

- Tarjeta «sonando»: radio de 14 px.
- Botones: 9 px. Menús: 10 px. Elementos de lista: 8 px.
- Botón reproducir: círculo de 44 px, el único control relleno de la barra.
- Campo de búsqueda: forma de píldora.
- Carátulas: 40 px en la tabla, 52 px en la barra y 92 px en el encabezado, con esquinas redondeadas del 8 %.

## Iconos

Juego propio en `app/ui/icons.py`: SVG en retícula de 24 px con trazo de 1.8 y extremos redondeados (varias formas siguen a Lucide, licencia ISC).
- Los controles de transporte van **rellenos**; el resto, en trazo.
- El color se pasa por rol y se vuelve a dibujar al cambiar de tema.
- Nunca se usan emojis ni caracteres Unicode como iconos.

## Movimiento

Un único momento animado: el **vúmetro** de tres barras junto al título de la canción que suena (`LevelMeter`). Late mientras se reproduce y queda quieto y gris en pausa.
