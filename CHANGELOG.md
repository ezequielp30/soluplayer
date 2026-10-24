# Registro de cambios

Formato: versión — fecha. Las versiones siguen `MAYOR.MENOR.CORRECCIÓN`.

## 1.11.1 — 2026-10-24

- **Licencia:** el programa es software libre bajo la GNU GPL versión 3 o posterior (`LICENSE`); «Acerca
  de…» lo indica. `crear-instalador.ps1` deja también `ReproductorMusica-<versión>-codigo-fuente.zip` para
  entregar junto con el instalador, como exige la GPL.
- **Canciones que faltan al abrir:** ahora siempre se pregunta antes de quitarlas de la lista y de las
  playlists (muestra cuáles); antes las pocas se quitaban solas.

## 1.11.0 — 2026-10-24 (revisión de producción)

Correcciones de la revisión de control de calidad (QA, código, seguridad, integridad de datos y
auditoría de producción). Cada una tiene su prueba en `tests/robustez_test.py`.

- **Papelera:** una carpeta más grande que la Papelera ya no se borra para siempre (se mide su contenido;
  si la Papelera no tiene tamaño configurado se usa el de Windows). Se detectan unidades `subst`, discos
  montados en carpetas, accesos directos de carpeta y la directiva del equipo.
- **Mover a otro disco:** nunca deja copias de más ni archivos a medias (copia a un temporal, fuerza al
  disco, verifica y recién entonces borra el original; si no puede borrarlo, quita la copia).
- **Deshacer una conversión** solo envía a la Papelera MP3 que creó el programa (marca propia en el MP3).
- **Biblioteca vacía o sin tablas** (p. ej. tras un corte de luz): se avisa y se ofrece el respaldo.
- **Ecualizador:** con el disco lleno ya no se cuelga; memoria limitada en bytes (≈ 14 min) y a tramos.
- **Errores:** el aviso de error se muestra siempre desde la ventana (antes podía cerrar el programa si
  el fallo ocurría en una tarea en segundo plano); se registran también los errores al arrancar.
- **Preferencias dañadas** en el registro ya no impiden abrir el programa.
- **Importar** miles de canciones usa mucha menos memoria (no se guardan las carátulas originales).
- **Nombres y rutas:** se rechazan caracteres invisibles, más nombres reservados y nombres demasiado
  largos para Windows; rutas de más de 260 caracteres con un mensaje claro.
- **Repetidas:** no se envía la única copia real si la «conservada» no está en el disco; «Reunir para
  revisar» avisa que mueve todas las copias; los originales convertidos no se pueden reimportar.
- **Historial:** ya no ofrece deshacer operaciones cuyos archivos ya no existen.
- **Windows 10/11:** la ventana entra en pantallas chicas y no queda bajo la barra de tareas; el
  Explorador se abre con su ruta completa; carátulas solo JPEG/PNG por https.
- **Ventanas de herramientas:** con el ecualizador activo se puede renombrar o mover la canción que suena;
  sin internet la búsqueda se detiene en vez de esperar canción por canción; errores al guardar se
  muestran en la franja.
- **Distribución:** carpeta `licencias` con los textos de licencia de los componentes de terceros; el nombre
  del programa ya no sale como «MÃºsica» en Windows; al actualizar se borran los archivos de la versión
  anterior; versiones exactas de las dependencias.
- **Pruebas:** ya no dependen de tu música ni de tus ajustes; una prueba que termina con un cierre
  anómalo cuenta como falla.

## 1.10.0 — 2026-10-24 (no se publicó por separado: incluida en 1.11.0)

- **Ventanas de herramientas más compactas** (Buscar datos en internet, Canciones repetidas, Analizar y
  ajustar volumen, Convertir a MP3), siguiendo cómo lo hacen foobar2000, MusicBrainz Picard, dupeGuru y
  dBpoweramp: una sola línea de explicación con el detalle en «?», menos columnas (el resto en el tooltip),
  textos de botones más cortos, ventanas más chicas y la línea de estado solo cuando hay algo que decir.
- **Al terminar una operación se limpia la lista:** las canciones convertidas, ajustadas, actualizadas o
  resueltas salen de la vista, y el resultado se muestra en una franja dentro de la ventana en lugar de un
  aviso emergente.

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
