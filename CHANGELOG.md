# Registro de cambios

Formato: versión — fecha. Las versiones siguen `MAYOR.MENOR.CORRECCIÓN`.

## 1.27.1 — 2026-11-02 (corrección del aviso de versiones nuevas)

- **Corregido un fallo de la 1.27.0:** la respuesta de GitHub se atendía fuera del hilo de la ventana, con riesgo de
  que el programa se cerrara al buscar actualizaciones, también en la consulta automática al abrir.
- **Corregido un cierre inesperado al usar *Localizar archivo* varias veces (desde la 1.25.0):** la ventana de búsqueda
  anterior no se liberaba y se destruía en un mal momento.

## 1.27.0 — 2026-11-01 (aviso de versiones nuevas)

- **El programa avisa cuando hay una versión nueva:** aparece «Versión X disponible» en la barra inferior, y al pulsarlo
  se abre la página de descarga. Nunca descarga ni instala nada por su cuenta.
- **También a mano:** *Ayuda → Buscar actualizaciones…*.
- Consulta GitHub como mucho una vez al día, al abrir. Se puede desactivar en *Preferencias → Internet*.

## 1.26.0 — 2026-11-01 (temas modernos)

- **Temas nuevos:** *Ónix*, *Medianoche*, *Esmeralda*, *Rubí*, *Ámbar* y *Alto contraste* (oscuros); *Nieve*, *Perla*,
  *Menta* y *Lavanda* (claros). Superficies neutras y un solo color de acento por tema. Se cambian sin reiniciar.
- **Quien tenía un tema retirado pasa al más parecido:** Grafito → Ámbar, Carmesí → Rubí, Acero → Esmeralda, Aluminio
  y Cromo → Nieve, Cobalto → Lavanda, Arena → Perla. Automático sigue a Windows con Ónix o Nieve.
- **La canción actual va en una tarjeta** en lugar de la pantalla tipo LCD, con tiempos en la letra del programa.
- **Más limpio:** la barra lateral sin píldoras de colores, las listas sin rayas y con resaltado al pasar el cursor,
  y casillas, opciones y pestañas con los colores del tema en todas las ventanas.
- **En Windows 11, la barra de título** de la ventana principal toma el color del tema.

## 1.25.0 — 2026-11-01 (Localizar archivo lo encuentra solo)

- **Clic derecho → *Localizar archivo* muestra el archivo directamente,** en cualquier lista del programa: abre
  el Explorador con el archivo seleccionado. Reemplaza a «Mostrar en el Explorador».
- **Si el archivo ya no está donde se guardó, el programa lo busca solo:** primero en su carpeta y en las de la
  biblioteca, después en las carpetas personales y por último en todos los discos del equipo (no en unidades de red).
  Sirve un archivo con el mismo nombre o título y la misma duración, aunque se haya renombrado o movido. La canción
  conserva playlists y orden. La música sigue sonando mientras busca, y la búsqueda se puede detener.
- Si hay varios posibles, se elige de una lista; si no hay ninguno, se puede buscar a mano.

## 1.24.0 — 2026-11-01 (sin signos ni numeración al inicio)

- **«¿» y «¡» ya no se conservan al inicio del título:** se quitan como los demás signos, en la biblioteca y
  dentro de los archivos. Se hace solo, una vez, al abrir («¿A quién tengo yo?» → «A quién tengo yo?»); se
  puede deshacer en *Historial de cambios en archivos*. El «?» del final se queda.
- **Título y quién la canta quita la numeración del inicio:** «3-4 de 19», «12/19», «06.», «7 -», «4ª». Los
  números que son parte del título se quedan («3 Días», «7 de Mayo», «24/7»).
- **Título y quién la canta usa el nombre del archivo como pista:** si coincide en la canción y en quién canta,
  la propuesta queda Lista; si dice otra cosa, se propone lo del nombre, pero queda por revisar.
- **Canciones renombradas por fuera:** si a un archivo solo se le quitaron signos o numeración del inicio, al
  abrir la canción vuelve a encontrarlo y conserva playlists y orden. Solo con un único archivo posible y de la
  misma duración.

## 1.23.0 — 2026-11-01 (título y quién la canta)

- **Nueva herramienta: *Herramientas → Título y quién la canta*.** Deja cada canción como «Canción - Quién la
  canta» en el título, en el nombre del archivo y dentro del archivo (etiquetas de título y artista), y quita
  lo que agrega YouTube («(Video Oficial)», «LETRA», «#hashtag»…).
- **Primero se ve qué va a pasar:** una lista con la propuesta de cada canción, que se puede corregir a mano
  o invertir. Las que no son seguras quedan sin marcar para revisarlas.
- **Los demás datos se borran** del archivo y de la biblioteca: álbum, género, año, comentarios y carátula (se
  puede conservar la carátula). En formatos que no son MP3, WAV ni AIFF solo cambian título y artista.
- Se conservan las playlists y el orden, y las marcas internas del programa (volumen ajustado, MP3 convertidos).
- Se deshace todo, carátula incluida, desde *Historial de cambios en archivos*.

## 1.22.0 — 2026-11-01 (títulos limpios también dentro de los archivos; se conservan «¿» y «¡»)

- **El título limpio queda grabado en los archivos,** en la etiqueta del título, así se ve igual en otros
  programas y en el teléfono. Se hace solo: una vez para la biblioteca, en segundo plano al abrir, y con cada
  canción importada. Cambia únicamente esa etiqueta: el sonido, el nombre y la fecha del archivo siguen iguales.
- **Seguro y reversible:** se trabaja sobre una copia que se verifica antes de reemplazar al archivo, y el
  título original queda anotado; se deshace en *Herramientas → Historial de cambios en archivos*. Si un archivo
  no se puede grabar (por ejemplo, está en uso), se intenta de nuevo al volver a abrir.
- **Los signos de apertura «¿» y «¡» ya no se quitan del inicio del título,** porque son parte de la
  escritura en español. Los demás caracteres especiales se siguen quitando («►► ¿Quién como Tú?» → «¿Quién
  como Tú?»). Al ordenar no cuentan: «¿A quién…» va con la A.
- **Los títulos que los perdieron en la 1.21.0 los recuperan solos,** una sola vez, desde el respaldo de
  antes de esa limpieza. Un título cambiado después no se toca.

## 1.21.0 — 2026-11-01 (títulos bien ordenados, mover a una posición)

- **El orden alfabético de «Canciones» ahora es por título** (antes iba por artista y, con muchos artistas
  distintos, la columna Título se veía desordenada). Sigue disponible ordenar por *Artista* o *Álbum*. Los
  artistas y los álbumes ordenan sus canciones por álbum y título.
- **Orden como espera una persona,** en títulos, artistas, álbumes, carpetas y nombres de archivo: no
  distingue mayúsculas ni tildes, no cuenta los signos del principio («¿A quién…», «(En vivo)…», «►…») y
  los números van como números (2 antes que 10).
- **Mover a una posición exacta:** clic derecho → *Mover al principio*, *Mover al final* o *Mover a la
  posición…* (se escribe el número de la lista), además de *Subir*/*Bajar* y arrastrar. Práctico en listas
  largas; pasa a *Mi orden*.
- **Primero los números, después las letras,** como en otros programas (en orden A–Z).
- **Títulos sin caracteres especiales al inicio:** se quitan solos («►►cuando mi pueblo ora» → «cuando mi
  pueblo ora», «[Vídeo Oficial] Cuando A» → «Vídeo Oficial Cuando A»). Solo cambia el título en la
  biblioteca: los archivos, sus nombres y sus etiquetas no se tocan. Se aplica al importar y, una sola vez,
  a los títulos ya guardados (con respaldo antes). Los números no cuentan como especiales, y lo que cambies
  después a mano se respeta.
- Pruebas en `tests/orden_visible_test.py`.

## 1.20.0 — 2026-11-01 (el orden se ve y se controla)

- **Selector «Orden:»** en cada lista, junto al resumen: dice en qué orden está y permite cambiarlo: *Mi
  orden*, el predeterminado de esa lista (por ejemplo *Alfabético* en «Canciones», *Por nombre de archivo* en
  una carpeta), *Título*, *Artista*, *Álbum* (A–Z y Z–A), *Duración* o *Aleatorio*. Cada lista recuerda el
  suyo, también al cerrar el programa. Si la lista está sonando, la siguiente canción ya sigue el orden nuevo.
- **Número en cada fila** (1, 2, 3…): la secuencia que va a sonar. Se puede ocultar en Preferencias → Canciones.
- **Aviso de cómo suena:** «Suena de arriba abajo» o, si el botón aleatorio de la barra está encendido, que
  suena al azar y no en ese orden. Al elegir un orden, ese botón se apaga.
- Mover una canción pasa a *Mi orden*; elegir otro orden no lo borra (se puede volver a él). Hacer clic en un
  encabezado también queda reflejado en el selector.
- Reproducir una carpeta o playlist desde el panel izquierdo sigue el orden que se ve.
- En *Aleatorio*, la mezcla se conserva mientras la lista sea la misma (refrescarla no cambia el orden);
  elegir *Aleatorio* otra vez hace otra mezcla. «Reproducir carpeta» sale de la mezcla.
- Pruebas en `tests/orden_visible_test.py` (29).

## 1.19.0 — 2026-10-31 (saltar el silencio grabado entre canciones)

- **Sin silencios largos entre canciones:** muchas canciones traen segundos de silencio grabado al
  principio y sobre todo al final (en tu biblioteca, en promedio 0,7 s al empezar y 3,3 s al terminar;
  entre dos canciones seguidas se oían 4 s, hasta 9). Ahora la reproducción salta ese silencio: empieza en
  el primer sonido y pasa a la siguiente apenas termina el último (deja 0,15 s para la cola de la nota).
  Por ejemplo, de «12 Visitanos» a «13 La Venida Del Rey» pasa de 8,8 s de silencio a 0,35 s.
- Un silencio a mitad de canción (o antes de una pista «oculta») se respeta; si saltas a un punto, empieza
  ahí. «Desde el principio» vuelve a saltar el silencio inicial.
- Los archivos no se modifican. Se apaga en **Preferencias → Reproducción** («Saltar el silencio grabado
  al principio y al final de cada canción», encendido de fábrica). Funciona con «Pasar a la siguiente
  canción sin silencio» encendido (de fábrica).
- Pruebas en `tests/saltar_silencio_test.py` (10).

## 1.18.0 — 2026-10-30 (graves precisos, dither, cambio de salida)

Etapa 3 de la auditoría de calidad de sonido.

- **Ecualizador con graves precisos:** las bandas de 31 y 62 Hz dan lo que marcan (±0,5 dB a 44,1/48 kHz,
  ±1 dB a 96 kHz; antes hasta 2 y 4 dB menos). Responde igual de rápido (bloques de ~90 ms) y usa poco
  procesador (6–7 % de un núcleo).
- **Por debajo de 20 Hz no refuerza:** subir los graves ya no empuja frecuencias que no se oyen (antes
  +12 dB a 10 Hz, que solo gastaban parlante). Bajarlos sigue funcionando.
- **Dither al pasar a 16 bits** (salidas que no aceptan float y la conversión a MP3): los pasajes muy suaves
  (fundidos, colas de reverberación) ya no salen con distorsión; queda un ruido de fondo parejo e inaudible.
  La conversión da siempre el mismo MP3 para el mismo original.
- **Cambiar de parlantes o auriculares:** si la salida nueva trabaja a otra frecuencia, la canción se vuelve
  a preparar a esa frecuencia y sigue en el mismo punto. Si la música se pausó porque la salida se cayó
  (Bluetooth), sigue sola cuando vuelve; si la pausaste vos, no.
- **Convertir a MP3 algo ya comprimido** (WMA, AAC, OGG…): la ventana lo marca y lo avisa antes de
  convertir (es una segunda compresión, no mejora y puede perder algo). Los M4A en ALAC (sin pérdida) no
  se marcan.
- **Pico real:** se verificó que la medición es exacta (0,0 dBTP con entrada suave); el «exceso» en agudos
  que se había reportado es el sobrepico real de un comienzo brusco, que también produce el conversor. Se
  dejó una prueba que lo fija.
- **Pruebas:** ya no usan tu música (audio generado, mismo resultado en cualquier PC); `codec_test` prueba
  cada formato con los dos motores, variantes (24 bits, 96 kHz, mono, 5.1) y archivos dañados; nueva
  `tests/audio_etapa3_test.py` (19).

## 1.17.0 — 2026-10-30 (sin silencio entre canciones, volumen en dB)

Etapa 2 de la auditoría de calidad de sonido.

- **Sin silencio entre canciones:** la siguiente canción se prepara mientras suena la actual y se pasa a
  ella sin cerrar la salida de audio (antes había ~¼ s de silencio). Funciona también sin ecualizador: la
  reproducción usa el motor propio, que con la curva plana deja el sonido idéntico al original. Si un
  archivo no se puede leer así, ese archivo suena con el motor de siempre. Se puede apagar en
  **Preferencias → Reproducción**.
- **Volumen en decibeles:** cada paso del deslizador cambia lo mismo (0,5 dB), también a volumen bajo
  (antes del 1 % al 2 % subía 6 dB). Al actualizar, tu volumen se convierte una vez para que suene igual
  (por ejemplo, 30 % pasa a verse como 79 %).
- **«Igualar volumen al reproducir» también sube:** una canción baja puede sonar más fuerte aunque el
  volumen esté al 100 % (la salida de Windows queda al máximo y el resto lo pone el motor, sin saturar).
- **Más margen contra cortes:** la salida tiene ¾ s de audio por delante (antes ¼ s), así que aguanta
  más si la ventana está ocupada. Pausar, saltar y cambiar de canción siguen siendo inmediatos.
- **Comienzo limpio:** la salida se abre cuando ya hay audio para llenarla (sin trozos de silencio al
  empezar una canción).
- **Correcciones:** un archivo dañado ya no cuenta como escuchado ni corta la cuenta de fallos seguidos;
  reanudar después de soltar un archivo no cuenta la canción dos veces; un volumen dañado en el registro
  abre con el de fábrica.
- Pruebas en `tests/audio_etapa2_test.py` (22). Batería completa: 46 de 47 (la restante depende de
  canciones de la biblioteca ya ajustadas de volumen).

## 1.16.1 — 2026-10-30 (corrección: herramientas con carpetas que aún no estaban en la biblioteca)

- **Elegir una carpeta lee todo su contenido:** en Herramientas, al seleccionar una carpeta principal (por
  ejemplo `D:\Audiolibro`, con todo en subcarpetas) se cuentan los archivos de audio de esa carpeta y de
  TODAS sus subcarpetas. Antes solo contaba lo que ya estaba en la biblioteca: si la carpeta no se había
  importado decía «no tiene canciones» y no dejaba continuar hasta elegir una subcarpeta.
- Lo que todavía no está en la biblioteca se agrega primero (los archivos no se modifican; se ve la barra
  de importación) y después la herramienta analiza todo. Vale para las cuatro herramientas.
- Pruebas en `tests/herramientas_carpeta_test.py` (24).

## 1.16.0 — 2026-10-30 (herramientas: carpeta origen y destino)

- **Elegir qué analizar:** Datos en internet, Canciones repetidas, Analizar y ajustar volumen y Convertir
  a MP3 preguntan primero «¿Qué canciones quieres analizar?»: toda la biblioteca o una carpeta (con sus
  subcarpetas), con **«Seleccionar carpeta…»**. Si estás viendo una carpeta, la propone. El título de la
  herramienta dice qué carpeta analiza.
- **Elegir la carpeta destino** donde la herramienta crea o mueve archivos: la carpeta de revisión de
  repetidas (ahora se propone dentro de la carpeta analizada), dónde guardar los originales al convertir a
  MP3 y dónde crear «_Volumen sin igualar» al apartar. Se cambia con «Elegir otra carpeta…» antes de
  confirmar.
- Pruebas en `tests/herramientas_carpeta_test.py`.

## 1.15.0 — 2026-10-30 (sonido más fiel con el ecualizador)

Etapa 1 de la auditoría de calidad de sonido. Todo es al reproducir: los archivos no se tocan.

- **El ecualizador ya no altera lo que no debe:** con la curva plana el sonido sale idéntico al original.
  El limitador solo actúa si algo pasaría de 0 dBFS (antes redondeaba todo lo que superaba 0,95 y la
  música masterizada cerca de 0 dBFS salía con distorsión).
- **«Evitar saturación» cuenta también el nivel general:** subir el nivel general ya no satura
  (antes, con +6 dB, la distorsión era clara).
- **Sin perder resolución:** el audio se decodifica en float. Los archivos de 24 bits no se truncan a 16
  y los picos por encima de 0 dBFS ya no se recortan antes del ecualizador.
- **Sin clics:** cambiar el ecualizador mientras suena hace un fundido cruzado; saltar a otra posición y
  reanudar entran con un fundido corto; pausar baja el volumen en unos milisegundos antes de detenerse.
  Detener sigue siendo inmediato (suelta el archivo en el acto).
- Pruebas en `tests/audio_transparencia_test.py` (señales sintéticas; no usa tu música). Las pruebas que
  usaban una canción de una carpeta que ya no existe ahora toman otro MP3 real de la biblioteca.

## 1.14.1 — 2026-10-30 (barra de reproducción reordenada)

- **Aleatorio y Repetir junto a los controles**, como en Spotify o Apple Music:
  aleatorio · anterior · reproducir · siguiente · repetir · detener.
- **El ecualizador va junto al volumen** (los dos ajustan cómo suena).
- **Panel de la canción más ancho:** el título y el texto se leen completos y la barra de progreso es
  casi el doble de larga, sin agregar una segunda fila.
- En ventanas angostas se achica primero el buscador: la barra de progreso y los botones siguen a la vista
  (antes el panel podía taparlos).

## 1.14.0 — 2026-10-30 (orden propio en cada lista, qué ver de cada canción, Preferencias nuevas)

- **Cada lista tiene su propio orden, y se conserva al cerrar el programa:** además de «Canciones» y las
  playlists, ahora también cada **carpeta**, cada **artista**, cada **álbum** y **Recientes** (arrastrar,
  Alt+↑/↓ o «Subir»/«Bajar»). El orden de una carpeta no cambia el de «Canciones» ni el de otra carpeta.
  «Reproducir», el doble clic y el menú de la carpeta lo siguen. Al renombrar una carpeta desde el programa
  su orden la acompaña. En Recientes, las que se escuchen después aparecen arriba. Clic derecho → «Volver
  al orden de siempre» deshace el orden de esa lista. (La búsqueda no se ordena: sus resultados cambian con
  lo que se escribe.)
- **«Aleatorio» mezcla la lista a la vista** y suena en ese orden, de arriba abajo (antes mezclaba sin
  mostrarlo). No reemplaza tu orden guardado; si después mueves una canción, se guarda lo que ves.
  «Reproducir en aleatorio» de una carpeta hace lo mismo.
- **Qué ver de cada canción:** Preferencias → Canciones (o clic derecho sobre los encabezados de la lista):
  Artista, Álbum, Género, Nombre del archivo, Duración y Carátula; el título se ve siempre. Vale para todas
  las listas y se recuerda.
- **Preferencias más simple:** secciones a la izquierda (Apariencia, Canciones, Importación, Internet,
  Biblioteca, Teclado), una página a la vista y sin marcos. Se abre **centrada en la pantalla**, igual que
  las ventanas de Herramientas.
- La base de datos pasa a la versión 4 (respaldo automático antes de actualizar).

## 1.13.0 — 2026-10-29 (carpetas de música y orden manual)

- **Quitar una carpeta de la biblioteca** (clic derecho en la carpeta, o el botón **−** junto al **+** de
  «Carpetas»): olvida sus canciones (con las subcarpetas) sin tocar el disco; nada va a la Papelera y se
  puede volver a agregar con «Importar carpeta…». Antes de quitar dice cuántas canciones son y cuántas
  entradas de playlists se van con ellas (como «Quitar de la biblioteca»). Con 10 o más, o si hay
  playlists afectadas, se hace un respaldo antes.
- **Ordenar a mano «Canciones» y las playlists:** arrastra las canciones, o usa **Alt+↑ / Alt+↓** (también
  «Subir»/«Bajar» en el clic derecho). El orden se guarda, «Reproducir» lo sigue y, si esa lista es la que
  está sonando, la canción siguiente ya respeta el orden nuevo. Las importadas después van al final.
  Ordenar por una columna sigue funcionando; al arrastrar, lo que se ve pasa a ser el orden manual.
  «Volver al orden de siempre» (clic derecho en «Canciones») lo deshace. En una playlist, una canción
  repetida se mueve por separado.
- La base de datos pasa a la versión 3 (respaldo automático antes de actualizar).
- Pruebas en `tests/carpetas_orden_test.py`.

## 1.12.10 — 2026-10-28 (confirmaciones)

- **Detener una tarea pregunta antes** (análisis y ajuste de volumen, conversión a MP3, canciones repetidas,
  datos de internet, descarga de carátulas, importación), con el tema, el avance y qué se conserva:
  «¿Detener el análisis de volumen? Van 312 de 905. Lo medido hasta ahora se conserva…». El botón marcado
  es el de seguir: un Enter de más no detiene nada.
- **Cerrar una ventana que está trabajando** (X, «Cerrar» o Esc) ya no la detiene en silencio: pregunta
  «¿Cerrar y detener…?». Si está modificando archivos, ofrece detener al terminar el archivo en curso.
- **Salir del programa pregunta** «¿Salir del Reproductor de Música?» (con «No volver a preguntar»; se
  vuelve a activar en Preferencias). Con una importación en curso pregunta siempre y dice qué se pierde.
  Al apagar Windows no pregunta.
- Corrige un cierre del programa al usar la casilla «No volver a preguntar» (se liberaba antes de tiempo).

## 1.12.9 — 2026-10-28 (apartar las que no se pueden igualar)

- **Analizar y ajustar volumen → Apartar:** mueve a la carpeta **«_Volumen sin igualar»**, en la carpeta
  principal de tu música, las canciones que no se pueden igualar: bajas con picos altos (ya subidas hasta
  donde se puede sin distorsionar), las que no se pudieron medir (dañadas o sin audio) y las de otro
  formato (no MP3) que necesitan ajuste. Con un LEEME.txt que explica cada una. La carpeta principal es la
  que contiene a la mayoría de tus canciones (nunca la raíz de un disco ni una carpeta del sistema) y se
  muestra antes de confirmar; las ya apartadas no se vuelven a ofrecer. Mover seguro: respaldo previo, nunca pisa nada
  (si dos se llaman igual, la segunda no se mueve y se avisa), las playlists se conservan y se deshace
  desde el Historial.
- Las canciones que no se pudieron medir (dañadas o sin audio) quedan marcadas; las que no estaban en el
  disco durante el análisis (USB desconectado) siguen pendientes. «Revertir» nunca convierte esa marca en
  una medición.

## 1.12.8 — 2026-10-28 (volumen parejo en cualquier reproductor)

Auditoría de «Analizar y ajustar volumen» según EBU R128 / ITU-R BS.1770: ya medía sonoridad integrada
(LUFS) y pico real (×4) y ajustaba de forma lineal y sin pérdida, pero solo SUBÍA las canciones muy bajas.
No se adoptan normalizadores que recomprimen el audio (loudnorm/ffmpeg-normalize, filtros, limitadores):
cambiarían los archivos con pérdida y no se podrían revertir.

- **Igualar todas, dentro de los MP3, a −16 LUFS** (objetivo fijo para escucha general: la mayoría de las
  canciones comerciales vienen entre −9 y −13 LUFS y bajan sin perder dinámica, y el volumen sigue
  alcanzando en celulares y autorradios). Sube las bajas y **baja las fuertes**, sin recomprimir (pasos de
  1,5 dB: queda a menos de ±0,75 LU). La ventana muestra cuántas quedaron parejas y cuántas no pueden subir
  más sin distorsionar (en una biblioteca simulada de 400 canciones: 391 a ±0,75 LU). Queda
  guardado en el archivo, así que suena pareja **en cualquier reproductor** (celular, auto, otros
  programas). Al subir, el pico real nunca pasa de −1 dBTP; tope de ±12 dB por canción. Las bajadas
  también se anotan dentro del MP3 y se revierten exactas, byte a byte.
- Corrige un defecto latente: bajar un MP3 sin ajustes previos no dejaba la nota para revertir.
- **Reproducción → Igualar volumen al reproducir** (apagado de fábrica): complemento que iguala al sonar,
  sin tocar archivos, también otros formatos; el cambio llega con la canción siguiente (sin saltos).
- Pruebas en `tests/igualar_archivos_test.py` y `tests/igualar_volumen_test.py` (con validación de doble
  pasada: −23,7 y −8,1 LUFS quedan en −14,0 y el pico real no pasa de −1 dBTP).

## 1.12.7 — 2026-10-26 (auditoría de seguridad y privacidad)

Correcciones de una auditoría de seguridad y privacidad. Cada una tiene su prueba en
`tests/seguridad_1127_test.py`.

- **Etiquetas preparadas:** el texto de las etiquetas (título, artista, álbum) y de las playlists ajenas
  nunca se dibuja como HTML. Antes, un MP3 con una etiqueta preparada podía hacer que Windows se
  conectara a otro equipo; ahora `<` y `>` se muestran como ‹ ›.
- **Playlists ajenas:** al revisarlas o restaurarlas no se consulta ninguna ruta de red (`\\servidor\…`)
  que no esté ya en la biblioteca, y un archivo de más de 5 MB no se toma como playlist.
- **Carpetas protegidas:** el perfil del usuario, Escritorio, Documentos, Descargas, Música, Imágenes,
  Videos, OneDrive, Windows, Archivos de programa y las raíces de los discos no se pueden enviar a la
  Papelera ni renombrar desde el programa.
- **Avisos que borran:** el botón marcado (Enter) es «Cancelar».
- **Respaldos fuera de la carpeta del programa:** el diario y el manual se copian también a
  `Documentos\Reproductor de Música\Respaldos`, en una subcarpeta de cada PC (los 3 más recientes). Si al
  abrir no está la biblioteca (carpeta del programa borrada), se ofrece recuperarla desde allí, con la
  fecha del respaldo. Si Documentos se sincroniza con OneDrive, esa copia (como la de las playlists) queda
  también en tu nube; cada PC usa su propia subcarpeta.
- **El texto original se respeta al escribir:** convertir a MP3 y aplicar datos de internet guardan los
  títulos tal cual (un «<3» sigue siendo «<3»); solo la pantalla muestra ‹ ›. Los datos que llegan de
  internet y los nombres de playlist guardados antes tampoco pueden dibujarse como HTML.
- **Teclas multimedia globales apagadas de fábrica** (se activan en Preferencias → Teclado).
- **Privacidad:** el registro del programa ya no guarda qué canciones se escuchan.
- **Instalador:** `crear-instalador.ps1` deja la huella SHA-256 en un archivo `.sha256` junto al
  instalador; el README explica cómo comprobarla y ya no aconseja desactivar la protección de Windows 11.

## 1.12.6 — 2026-10-26

- **Desinstalar ya no borra la biblioteca para siempre:** si se elige borrarla, va a la Papelera de
  reciclaje (se puede recuperar); si algo no cabe en la Papelera, Windows pregunta antes de borrarlo para
  siempre. La pregunta es más clara y recuerda que la copia de las playlists en Documentos se conserva.
  (Vale para lo que se instale desde esta versión: un programa instalado con una versión anterior
  conserva el desinstalador de entonces hasta que se actualice.)
- **Si queda otra copia del programa instalada** (p. ej. una «para todos los usuarios» y otra «solo para
  mí»), el desinstalador ni pregunta: esa otra copia usa la misma biblioteca, así que se conserva.
- **Nombres de playlist de 30 caracteres como máximo** al crear o renombrar (el cuadro no deja escribir
  más). Las que ya tenían un nombre más largo no se recortan (al renombrarlas se ven completas); al
  restaurar una copia de otra playlist con nombre largo, el nombre se acorta.

## 1.12.5 — 2026-10-25 (copia de las playlists)

- **Copia automática de las playlists** en `Documentos\Reproductor de Música\Playlists` (fuera de la carpeta
  del programa: sobrevive aunque esa se borre; si Documentos está en OneDrive, queda también en la nube).
  Se actualiza unos segundos después de cada cambio y al abrir el programa. Nunca borra nada en esa
  carpeta: una playlist eliminada en el programa sigue guardada y se puede restaurar, y si una playlist
  pierde canciones (p. ej. al quitar faltantes) su versión anterior queda en la subcarpeta `Anteriores`.
- **Playlists → Guardar copia de las playlists…:** en la carpeta que se elija (por ejemplo, un pendrive),
  un archivo `.m3u8` por playlist (formato estándar: también lo abren VLC, Winamp o foobar2000).
- **Playlists → Restaurar playlists…:** muestra las playlists de una copia para elegir cuáles traer.
  Encuentra cada canción por su ruta, la agrega a la biblioteca si está en el disco, o la busca por título,
  artista y duración si la música cambió de carpeta. No pisa ninguna playlist: si hay una igual se deja, y
  si hay una distinta con el mismo nombre entra como «Nombre (restaurada)».

## 1.12.4 — 2026-10-25 (detalles)

Detalles menores de la revisión completa. Cada uno tiene su prueba en `tests/menores_1124_test.py`.

- **Teclas multimedia con la ventana minimizada** (Reproducir/Pausa, Siguiente, Anterior, Detener); se
  puede apagar en Preferencias → Teclado si se prefiere que manejen otro programa (con el reproductor
  abierto, el navegador u otro reproductor ya no las reciben). No hacen nada mientras hay una ventana de
  herramientas trabajando.
- **Barra de avance con el teclado:** las flechas saltan 5 s y Re Pág / Av Pág 30 s.
- **Aleatorio:** al dar la vuelta a la lista se vuelve a mezclar (y no empieza por la última que sonó).
- **Seguir desde el mismo punto** tras renombrar o mover la canción que suena, aunque el disco sea lento.
- **Historial:**
  - se puede deshacer un renombre que solo cambia mayúsculas;
  - se puede deshacer un movimiento a otro disco aunque se haya borrado la carpeta original;
  - un movimiento interrumpido figura «Interrumpida» con lo que de verdad se movió.
- **Mover entre discos con rutas largas:** el temporal de la copia ya no hace fallar el movimiento.
- **Corte de luz al mover:** se borra el temporal a medias del destino, y nunca se confunde un archivo
  ajeno del destino con uno movido.
- **Renombrar una carpeta** con canciones guardadas con su nombre corto de Windows (8.3).
- **Respaldos:** el más reciente de cada tipo de operación dura al menos una semana (antes, unas pocas
  operaciones seguidas se llevaban el de antes de quitar faltantes).
- **Archivos abiertos mientras el programa se cierra:** ya no se pierden (los abre la copia nueva).
- **Registro de errores:** un error se anota una sola vez; el archivo de cierres inesperados ya no crece
  sin límite.
- **Seguridad:**
  - una redirección de internet a http ya no se sigue;
  - un mensaje enorme de otra copia del programa se descarta.
- **Instalador:**
  - aparece en Configuración → Aplicaciones predeterminadas;
  - se instala siempre para el usuario actual (sin el cuadro «para todos los usuarios»).

## 1.12.3 — 2026-10-25 (licencias y Windows 11)

- **Código fuente dentro del instalador:** el del programa (GPL) y el de FFmpeg 9.0.1 (LGPL, con su firma
  oficial comprobada) se instalan en la carpeta `codigo-fuente`; así lo recibe también quien reciba solo el
  instalador. `crear-instalador.ps1` se niega a armarlo con cambios sin guardar en git, para que el código
  entregado sea exactamente el del programa, y comprueba que PySide6 siga trayendo esa versión de FFmpeg.
- **Licencias completas:** `licencias/TERCEROS.txt` indica la versión exacta de FFmpeg y cómo se compiló, y
  la carpeta trae los avisos de las bibliotecas que Qt lleva dentro (libpng, FreeType, HarfBuzz, PCRE2,
  libjpeg-turbo, libwebp, zlib).
- **Más liviano:** ya no se instala `opengl32sw.dll` (OpenGL por software, que el programa no usa).
- **Windows 11:** el README explica qué pasa con «Control inteligente de aplicaciones», que bloquea los
  programas sin firma sin ofrecer «Ejecutar de todas formas».

## 1.12.2 — 2026-10-25 (revisión completa)

Correcciones de una revisión completa del programa en tres frentes (archivos, reproducción y pruebas).
Cada una tiene su prueba en `tests/revision_1122_test.py`.

- **Corte de luz al mover canciones:** el plan se anota antes de empezar y la biblioteca se actualiza
  canción por canción; al abrir, las ya movidas apuntan a su lugar nuevo (no se ofrece quitarlas de las
  playlists) y el movimiento se puede deshacer desde el Historial.
- **Mover a otro disco:** si la biblioteca no acepta el cambio, el archivo vuelve de verdad a su carpeta
  (antes podía quedar en el otro disco con un mensaje que decía lo contrario).
- **Reunir repetidas interrumpida:** sus canciones ya no se ofrecen para quitar al abrir.
- **Ajuste de volumen:** al abrir ya no se escribe nada en los MP3; si la biblioteca recuerda un ajuste
  que el archivo no tiene, se corrige la biblioteca (antes «Revertir» podía bajar el volumen de más).
- **El programa siempre abre:** un tamaño de ventana guardado dañado en el registro ya no lo impide.
- **Una canción dañada no detiene la música:** si se llega a ella sola, se salta con un aviso en la barra
  de estado; si la elige el usuario, se le avisa como antes.
- **Cerrar durante una importación** ya no da un error inesperado.
- **Disco de red desconectado:** la cola y «Aleatorio» ya no lo consultan canción por canción (la ventana
  podía quedar «No responde» varios minutos).
- **Ecualizador:** si se pierde la salida de audio (auriculares USB o Bluetooth, vuelta de la suspensión)
  pasa a «Pausa» en el mismo punto en vez de figurar sonando sin sonar.
- **Pruebas más estrictas:** un resumen «FALLA» cuenta como falla aunque el código de salida sea 0; la de
  ajuste de volumen compara de verdad el original; las que solo imprimían ahora comprueban; las de
  borrador nunca usan los datos reales.

## 1.12.1 — 2026-10-24

- **Autor y contacto:** Ezequiel Perez · ezequielp30@gmail.com, en Ayuda → Acerca de…, en el instalador, en los
  datos del `.exe` (Compañía y Copyright) y en `licencias/TERCEROS.txt`.
- **Aviso de uso bajo su propia responsabilidad:** en Acerca de… y en una página del instalador antes de instalar.

## 1.12.0 — 2026-10-24

- **Historial de renombres y movimientos:** renombrar un archivo o una carpeta y mover canciones (también a
  otro disco) aparecen en Herramientas → Historial y se pueden deshacer; nunca se pisa nada.
- **Temporales sobrantes:** al abrir se borran los que pudo dejar un corte de luz junto a la música. Mover a
  otro disco ahora da el nombre definitivo a la copia antes de borrar el original, así un temporal que
  quede es siempre una copia a medias.
- **Más rápido con bibliotecas grandes o en red:** se lee cada carpeta una vez (no cada archivo) para saber
  qué canciones existen, y si un disco o servidor no responde no se insiste con el resto; el árbol de
  Carpetas se arma una vez por carpeta. «Convertir a MP3» se abre al instante y lee la calidad por tandas.
- **Textos de Qt en español:** el menú del clic derecho en los campos («Copiar», «Pegar»…) y los botones
  estándar de los cuadros de diálogo.

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
