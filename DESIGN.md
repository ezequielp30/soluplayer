# Diseño visual

Una herramienta de uso diario para tener la música en orden: superficies neutras, un solo acento por tema y nada que compita con la lista de canciones.
Modo: **Operate**: primero la claridad, y la marca se nota en los detalles.

## Temas

Diez temas definidos en `app/ui/theme.py` como roles con nombre. En modo *automático* sigue a Windows con **Ónix** (oscuro) o **Nieve** (claro).

| Tema | Tipo | `bg` | `sidebar` | `elevated` | `accent` |
|---|---|---|---|---|---|
| Ónix | oscuro | `#16181d` | `#101216` | `#20232a` | `#5b9dff` |
| Medianoche | oscuro | `#14162b` | `#0e1022` | `#1e2140` | `#8f8bff` |
| Esmeralda | oscuro | `#121a18` | `#0c1311` | `#1b2623` | `#2fd6a3` |
| Rubí | oscuro | `#1a1518` | `#130f11` | `#251d21` | `#ff5f7e` |
| Ámbar | oscuro | `#18171a` | `#121114` | `#232125` | `#f7b23b` |
| Alto contraste | oscuro | `#000000` | `#000000` | `#161616` | `#ffd60a` |
| Nieve | claro | `#f7f8fa` | `#eef0f4` | `#ffffff` | `#2563eb` |
| Perla | claro | `#faf8f7` | `#f2eeec` | `#fffefd` | `#d42c5c` |
| Menta | claro | `#f6faf8` | `#ebf2ef` | `#fdfefe` | `#0a7d63` |
| Lavanda | claro | `#f8f7fc` | `#efedf7` | `#fefeff` | `#5b45d6` |

Reglas:
- El acento marca solo lo **activo o principal**: reproducir, el progreso, la canción que suena, la selección, la acción principal de cada ventana.
- Los títulos de sección y los menús van en `muted`: nada de colores por sección.
- Las listas no llevan rayas (`row_alt` es igual a `bg`): las filas se distinguen por el aire y por el resaltado al pasar el cursor.
- Salvo en Alto contraste, el texto no es blanco ni negro puro: siempre ≥ 7:1, pero descansado para muchas horas. Los temas claros no usan blanco puro de fondo; solo en tarjetas y campos.
- La elevación se marca con borde o con un cambio de superficie, sin sombras.
- Los colores siempre se toman por rol (`theme.color("muted")`), nunca escritos a mano en los widgets. `tests/theme_contrast_test.py` comprueba el contraste de todos los temas.
- En Windows 11, la barra de título de la ventana principal toma el color de la barra de menús.

## Tipografía

Segoe UI Variable (Text para la interfaz, Display para los títulos de 22 pt en peso 600). Los textos secundarios a 9 pt en `muted`, y los tiempos a 8.5 pt.

## Formas

- Tarjeta de la canción actual y tarjetas de tema: radio de 12 px.
- Botones, campos y listas desplegables: 8 px. Menús: 10 px. Elementos de lista: 8 px. Casillas: 4 px.
- Botón reproducir: círculo de 44 px, el único control relleno de la barra.
- Campo de búsqueda: forma de píldora.
- Carátulas: 40 px en la tabla, 52 px en la barra y 92 px en el encabezado, con esquinas redondeadas del 8 %.

## Iconos

Juego propio en `app/ui/icons.py`: SVG en retícula de 24 px con trazo de 1.8 y extremos redondeados (varias formas siguen a Lucide, licencia ISC).
- Los controles de transporte van **rellenos**; el resto, en trazo.
- El color se pasa por rol y se vuelve a dibujar al cambiar de tema.
- Nunca se usan emojis ni caracteres Unicode como iconos.

## Movimiento

Un único momento animado: el **medidor** de tres barras junto al título de la canción que suena (`LevelMeter`), en el color del acento. Late mientras se reproduce y queda quieto y gris en pausa.
