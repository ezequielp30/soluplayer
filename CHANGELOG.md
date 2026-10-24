# Registro de cambios

Formato: versión — fecha. Las versiones siguen `MAYOR.MENOR.CORRECCIÓN`.

## 1.9.0 — 2026-10-24

- **Temas inspirados en reproductores clásicos** (referencias del usuario: Winamp, jetAudio, AIMP, XMPlay,
  UltraPlayer, MusicMatch): *Grafito*, *Carmesí*, *Acero*, *Medianoche*, *Alto contraste*, *Aluminio*,
  *Cromo*, *Cobalto* y *Arena*. Se toman como referencia de color, sin copiar sus diseños.
- **Pantalla de la canción actual** al estilo del visor LCD de esos reproductores: fondo y texto propios de
  cada tema, tiempos con dígitos de ancho fijo y el medidor de nivel en el color de la pantalla.
- Temas retirados → el más parecido: Aurora y Vúmetro → Acero, Vino → Carmesí, Océano → Cromo,
  Lavanda → Cobalto, Neón → Medianoche.

## 1.8.1 — 2026-10-24

- **Temas más suaves a la vista** (a pedido del usuario): texto menos brillante (≈ 10:1 en lugar de ≈ 15:1,
  sigue por encima del 7:1 recomendado), oscuros un poco menos negros, claros sin blanco puro, acentos y
  colores de sección menos saturados y píldoras más tenues. *Alto contraste* no cambia (es el de accesibilidad).

## 1.8.0 — 2026-10-24

- **Temas rediseñados:** 9 temas (5 oscuros, 4 claros) con fondos casi neutros, un acento propio y mejor
  jerarquía entre barra lateral, paneles y selección. *Vino* pasa a llamarse *Burdeos*; *Neón* y *Vúmetro
  verde* se retiran (quien los usaba pasa a *Medianoche* y *Aurora*). Aluminio cumple ahora el contraste
  sin excepciones.
- **Barra lateral:** Biblioteca, Playlists y Carpetas tienen cada una su color e icono, adaptados a cada
  tema; la fila elegida lleva una marca del color del acento.

## 1.7.1 — 2026-10-24

- **Ecualizador sin límite de duración:** los archivos de más de 30 minutos ya no suenan sin ecualizar. Su
  audio pasa a un archivo temporal en disco (la memoria no crece) que se borra al cambiar de canción.

## 1.7.0 — 2026-10-24 (versión para producción)

- **Diseño:** la barra lateral ocupa toda la altura de la ventana y la barra del reproductor queda solo
  sobre el panel principal (según el diseño del usuario). Siempre se ven al menos 5 playlists.
- **Buscador** más grande y legible; la zona de la canción actual es más compacta.
- **Artistas y Álbumes:** sin barra horizontal; el elegido se ve en la lista al volver.
- **Carpetas:** el resaltado al pasar el mouse ya no se parte en dos bloques.
- **Acerca de** muestra el número de versión.
- Prueba nueva que activa cada opción del menú (`tests/menu_all_test.py`).

## 1.6.0 — 2026-10-23

- **Ecualizador** de 10 bandas que cambia el sonido real: presets por género, presets propios, nivel
  general, evitar saturación, activar/desactivar sin cortar la canción (`Ctrl+E`).
- **11 temas** con vista previa y cambio sin reiniciar; Preferencias en pestañas.
- **Gestión de archivos y carpetas:** renombrar, crear subcarpeta, mover y enviar a la Papelera, con
  confirmación y mensajes claros.
- **Control de versiones** con git.

## 1.5.1 — 2026-10-23

- Limpieza automática al abrir: quita de la lista las canciones y carpetas que ya no existen, con
  protecciones (discos desconectados, carpetas movidas → «Buscar dónde está…», respaldo previo).

## 1.5.0 — 2026-10-23

- Corrección de ~45 fallos encontrados por la revisión de 4 agentes: conversión a MP3 (nombres repetidos,
  orden de pasos), repetidas que agrupaban canciones distintas, una sola copia del programa, Papelera
  desactivada, ajuste de volumen atómico, importación robusta, reproducción y editor de menús.

## 1.4.x — 2026-10-23

- Historial de cambios en archivos, tareas en segundo plano unificadas, menús reorganizados.
- Menús editables con Qt Designer (`assets/menus.ui`).

## 1.3.x y anteriores

- Reproductor, biblioteca SQLite, playlists, importación, repetidas, datos en internet, ajuste de volumen
  sin pérdida, conversión a MP3, respaldos e instalador de Windows.
