# Reproductor de Música

Reproductor de archivos de audio locales para Windows, hecho con **Python**, **PySide6** y **Qt Multimedia**.
La biblioteca y las playlists se guardan en **SQLite** y se conservan al cerrar el programa.

> El programa no incluye ni descarga música: solo reproduce los archivos que tú eliges. Por sí solo **no mueve,
> renombra, modifica ni elimina** tus archivos. Solo lo hace cuando tú lo pides y lo confirmas: *Reunir
> repetidas* (mueve, se puede deshacer), *Ajustar volumen* (modifica MP3 sin pérdida, se puede revertir),
> *Convertir a MP3* (guarda los originales aparte, se puede deshacer), *Renombrar / Mover / Nueva carpeta*
> (gestión de archivos) y *Enviar a la Papelera* (se recupera desde la Papelera). Nunca se borra nada de
> forma definitiva. El ecualizador cambia el sonido al reproducir, no los archivos.

## Requisitos

- Windows 10 u 11
- Python 3.10 o superior (probado con 3.12). Descárgalo de <https://www.python.org/downloads/> y marca
  **«Add python.exe to PATH»** durante la instalación.
- Visual Studio Code con la extensión **Python** (Microsoft).

Dependencias (`requirements.txt`):

| Paquete  | Uso |
|----------|-----|
| PySide6  | Interfaz gráfica y reproducción (Qt Multimedia, backend FFmpeg incluido) |
| mutagen  | Lectura de metadatos: título, artista, álbum, género, duración y carátula |

## Instalación y ejecución desde VS Code (PowerShell)

1. Abre la carpeta del proyecto: **Archivo → Abrir carpeta…** y elige `reproductor-musica`.
2. Abre la terminal integrada: **Terminal → Nueva terminal** (PowerShell).
3. Ejecuta estos comandos, en orden:

```powershell
# 1. Crear el entorno virtual
python -m venv .venv

# 2. Activarlo
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Ejecutar el programa
python main.py
```

Si PowerShell bloquea la activación con un error de *«la ejecución de scripts está deshabilitada»*,
ejecuta una vez lo siguiente y vuelve a activar el entorno:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

También puedes ejecutar sin activar el entorno: `.\.venv\Scripts\python.exe main.py`.

### Ejecutar con F5 (depurador)

El proyecto incluye `.vscode/launch.json` y `.vscode/settings.json`. Tras crear el entorno virtual:

1. `Ctrl+Mayús+P` → **Python: Select Interpreter** → elige `.\.venv\Scripts\python.exe`.
2. Pulsa **F5** (configuración «Reproductor de Música»).

## Estructura del proyecto

```
reproductor-musica/
├── main.py                  Punto de entrada
├── Editar-menus.cmd         Abre los menús en Qt Designer
├── assets/menus.ui          Menús de la ventana principal (editables con Qt Designer)
├── tests/                   Pruebas automáticas (ver tests\LEEME.txt)
├── requirements.txt
├── README.md
├── .vscode/
│   ├── launch.json          Configuración de F5
│   └── settings.json        Intérprete del entorno virtual
└── app/
    ├── application.py       Arranque: una sola copia, estilos, revisión de la biblioteca, ventana
    ├── config.py            Rutas, nombre de la app, extensiones admitidas
    ├── models.py            Dataclasses Track y Playlist
    ├── utils.py             Formato de tiempos, búsqueda sin tildes, claves de ruta
    ├── metadata.py          Metadatos y calidad (kbps, frecuencia, canales) con mutagen
    ├── artwork.py           Miniaturas de carátulas
    ├── importer.py          Búsqueda en carpetas, validación y lectura en segundo plano
    ├── database.py          SQLite: canciones, carátulas, playlists, volumen medido
    ├── backup.py            Respaldos de la biblioteca y revisión al arrancar
    ├── player.py            Qt Multimedia: cola, aleatorio, repetición, salida de audio
    ├── audio_decode.py      Decodificación completa con vigilancia (para medir y convertir)
    ├── folders.py           Árbol de carpetas de la biblioteca
    ├── duplicates.py        Detección de canciones repetidas
    ├── duplicates_job.py    Búsqueda de repetidas en segundo plano
    ├── review_folder.py     Reunir repetidas en una carpeta de revisión y devolverlas
    ├── loudness.py          Medición EBU R128 (LUFS, pico real) y decisión de ajuste
    ├── loudness_job.py      Medir y ajustar el volumen en segundo plano
    ├── mp3gain.py           Ajuste de volumen sin pérdida dentro del MP3, con anotación para deshacer
    ├── converter.py         Conversión a MP3 con LAME y deshacer
    ├── journal.py           Registro común (intención → hecho) de las operaciones sobre archivos
    ├── file_operations.py   Coordinador de todo lo que modifica archivos, e Historial
    ├── file_manager.py      Renombrar, crear carpeta, mover y enviar a la Papelera
    ├── equalizer.py         Ecualizador de 10 bandas (filtro FIR de fase lineal con numpy)
    ├── eq_player.py         Motor de reproducción con ecualizador (decodifica, filtra, envía al audio)
    ├── file_ops.py          Envío a la Papelera de reciclaje (comprueba que la Papelera esté activa)
    ├── library_cleanup.py   Quitar o reubicar canciones y carpetas que ya no existen
    ├── online_lookup.py     MusicBrainz, Deezer e iTunes
    ├── online_job.py        Búsqueda en internet y carátulas en segundo plano
    ├── titles.py            Títulos propuestos desde el nombre del archivo
    ├── preferences.py       Preferencias del usuario
    ├── error_log.py         Registro de errores en archivo
    ├── single_instance.py   Una sola copia abierta del programa
    ├── win_audio.py         Lectura del volumen de Windows (solo lectura)
    └── ui/
        ├── main_window.py   Ventana principal; conecta todos los módulos
        ├── menu_loader.py   Lee los menús de assets/menus.ui
        ├── player_bar.py    Barra superior (controles, progreso, volumen, búsqueda)
        ├── sidebar.py       Barra lateral (Biblioteca, Playlists y Carpetas)
        ├── content_panel.py Panel derecho (encabezado, tabla, grupos, estados vacíos)
        ├── track_model.py   Modelo de tabla de canciones
        ├── dialogs.py       Diálogos comunes y utilidades (preguntas, estados vacíos, tablas)
        ├── worker_runner.py Tareas en segundo plano: progreso, «Detener» y cierre seguro
        ├── online_dialog.py      Buscar datos en internet
        ├── duplicates_dialog.py  Buscar canciones repetidas
        ├── loudness_dialog.py    Analizar y ajustar volumen
        ├── convert_dialog.py     Convertir a MP3
        ├── history_dialog.py     Historial de cambios en archivos
        ├── equalizer_dialog.py   Ventana del ecualizador
        ├── theme_picker.py       Selector de temas con vista previa
        ├── covers.py        Caché de carátulas y carátula de reemplazo
        ├── icons.py         Iconos vectoriales (SVG) que siguen al tema
        ├── theme.py         Temas claro/oscuro y modo automático
        └── styles.py        Hoja de estilos generada desde el tema
```

## Dónde se guardan los datos

La base de datos está en `%LOCALAPPDATA%\ReproductorMusica\biblioteca.db`
(puedes verla en **Ayuda → Acerca de…**). Guarda rutas, metadatos, miniaturas de carátulas y playlists.
Borrar ese archivo reinicia la biblioteca sin tocar tu música.
Para usar otra carpeta, define la variable de entorno `MUSICPLAYER_DATA_DIR`.

## Formatos admitidos

La reproducción usa el **FFmpeg incluido en PySide6** (210 decodificadores de audio), así que funciona
igual en **Windows 10 y 11** sin instalar paquetes de códecs ni extensiones de Microsoft Store.

| Tipo | Extensiones |
|---|---|
| Con pérdida | MP3, MP2, AAC, M4A/M4B (AAC), OGG/OGA (Vorbis), OPUS, WMA (incluye WMA Pro y Voice), AC3, E-AC3, DTS, AMR |
| Sin pérdida | FLAC, M4A (ALAC), WAV, AIFF/AIFC, APE (Monkey's Audio), WV (WavPack), TTA, WMA Lossless |
| Alta resolución | DSF/DFF (DSD) |
| Contenedores | MKA, WEBM, CAF |

En MKA, WEBM, CAF, DTS, E-AC3 y AMR no se leen etiquetas: se importan con el nombre del archivo como
título y la duración se completa al reproducirlos. No está disponible Musepack (.mpc).

## Guía rápida

### Importar una carpeta con subcarpetas

1. **Archivo → Importar carpeta…** (`Ctrl+Mayús+O`), o el botón **Importar música → Importar carpeta…**.
2. Elige la carpeta.
3. En el diálogo, deja marcada **«Incluir también todas las subcarpetas»** y pulsa **Importar**.
4. Al terminar verás un informe: cuántas canciones se importaron, cuáles ya estaban (no se duplican) y
   cuáles no se pudieron agregar con el motivo (formato no compatible, archivo dañado, vacío, sin permiso…).

Para archivos sueltos usa **Archivo → Importar archivos…** (`Ctrl+O`); puedes seleccionar varios a la vez.

### Analizar y ajustar el volumen (canciones muy bajas)

**Herramientas → Analizar y ajustar volumen…** (`Ctrl+Mayús+V`). Hay que pedirlo: nada se hace solo.

1. **Analizar** mide cada canción con el estándar profesional **EBU R128 / ITU-R BS.1770-4**: sonoridad
   integrada en **LUFS** (cómo percibe el oído el volumen) y **pico real** en **dBTP**. Los resultados se
   guardan; después solo se analizan las canciones nuevas.
2. La referencia es la sonoridad típica de **tu** biblioteca (la mediana, acotada entre −16 y −9 LUFS).
   Una canción es **muy baja** si está 3 LU o más por debajo. Las demás no se tocan, ni las fuertes.
3. La subida es la que falta para llegar a la referencia, **limitada para que el pico real no pase de
   −1 dBTP**, así que **no distorsiona**. Si los picos no dejan subir lo suficiente, se sube lo posible y se
   indica.
4. **Subir volumen de las marcadas** modifica los **MP3 de forma permanente y sin pérdida de calidad**
   (técnica MP3Gain: cambia la ganancia guardada en cada trama, sin recomprimir, en pasos de 1,5 dB). El
   cambio se oye en cualquier reproductor y en el celular. Antes se hace un respaldo de la biblioteca, y la
   canción que esté sonando se suelta antes de modificarla.
5. **Revertir:** filtro «ya ajustadas», selecciona las canciones y pulsa *Revertir ajuste…*. El archivo
   vuelve a quedar idéntico, byte a byte, al original.

WMA, M4A y los demás formatos no se pueden subir sin recomprimir (con pérdida). Se indican en la lista,
pero no se modifican.

### Convertir a MP3

**Herramientas → Convertir a MP3…** (`Ctrl+Mayús+M`). Busca en la biblioteca las canciones que **no son MP3**
(WMA, M4A, FLAC, WAV, OGG…) y las convierte con **LAME**, el codificador MP3 de referencia.

- **Calidad:** el MP3 usa el **doble de kbps que el original** (entre 128 y 320). Los formatos sin pérdida
  (FLAC, WAV…) van a 320 kbps. Así la conversión no añade pérdida audible. Ojo: convertir **no puede mejorar**
  la calidad que ya tiene un archivo (un WMA de 20 kbps no sonará mejor).
- **Sin distorsión:** algunos archivos (sobre todo WMA) tienen picos por encima de 0 dBFS. Antes de codificar
  se baja lo justo para no recortarlos, y después se devuelve el nivel dentro del MP3 sin pérdida (con la misma
  técnica del ajuste de volumen).
- Título, artista, álbum, género, número de pista, año y carátula pasan al MP3 (con tus correcciones). La
  biblioteca y las **playlists pasan a usar el MP3** automáticamente.
- Cada MP3 se **comprueba** (que sea válido y dure lo mismo) antes de darlo por bueno. Un archivo dañado se
  omite y el original queda intacto.
- Los **originales no se borran:** se guardan en `…\_Originales convertidos\`, con su misma estructura de
  carpetas. Antes de empezar se hace un respaldo de la biblioteca.
- **Deshacer:** Herramientas → *Historial de cambios en archivos…* (o el botón *Historial y deshacer…* de
  esta ventana) devuelve los originales a su sitio y manda los MP3 creados a la Papelera.

Después de convertir, también puedes subir el volumen de las que queden bajas con *Analizar y ajustar volumen*.

### Buscar títulos y datos en internet

Busca el título, artista, álbum y carátula correctos en bases de datos de música gratuitas, sin cuenta ni clave:

| Base de datos | Ventaja | Límite |
|---|---|---|
| **MusicBrainz** | Base abierta y muy completa; propone el álbum original | 1 consulta por segundo |
| **Deezer** | Rápida, buena para música popular, carátulas grandes | — |
| **iTunes (Apple)** | Muy precisa | ≈20 consultas por minuto (lenta en bibliotecas grandes) |

- **Todas las canciones:** Herramientas → *Buscar datos en internet…* (`Ctrl+Mayús+I`) y pulsa
  **«Buscar en todas»**. Puedes limitarlo a las canciones con datos incompletos.
- **Solo algunas:** selecciónalas y pulsa el botón **«Datos en internet»** del encabezado (sin selección usa
  toda la lista visible), o clic derecho → *Buscar datos en internet…*. Con una sola canción puedes corregir
  el título y el artista de la búsqueda.
- En cada canción, la lista **«Propuesta»** muestra varias opciones de las distintas bases de datos
  (título — artista · álbum · duración [fuente]) y el porcentaje de **coincidencia**. Las coincidencias
  seguras (≥ 85 %) se marcan solas; elige otra opción o «(No cambiar)» cuando haga falta.
- Pulsa **«Aplicar marcadas»**. Con «Actualizar también la carátula» se descarga la portada.

Solo se envían el título y el artista de cada canción. Los cambios se guardan en la biblioteca:
**los archivos de audio no se modifican**. Las bases de datos por defecto se eligen en
Archivo → Preferencias → *Datos en internet*. Se necesita conexión a internet.

### Navegar por carpetas

En la barra lateral, la sección **Carpetas** muestra las carpetas donde está tu música importada, con la
cantidad de canciones de cada una. Haz clic en una carpeta para ver sus canciones (incluye subcarpetas);
la ruta de arriba del título es clicable para subir de nivel. Doble clic reproduce la carpeta.
Clic derecho: reproducir (normal o aleatorio), agregar la carpeta a una playlist, mostrarla en el Explorador,
buscar música nueva en ella, expandir/contraer. El botón de la sección importa otra carpeta.

### Temas

**Archivo → Preferencias… → pestaña Tema**: 9 temas con una miniatura de la ventana en sus colores —
inspirados en reproductores clásicos de Windows: oscuros *Grafito* (biblioteca de Winamp, pantalla de
fósforo verde), *Carmesí* (Winamp en rojo), *Acero* (UltraPlayer), *Medianoche* y *Alto contraste*; claros
*Aluminio* (AIMP, dígitos naranjas), *Cromo* (jetAudio, LCD celeste), *Cobalto* (XMPlay, pantalla azul) y
*Arena* — más *Automático* (Grafito o Aluminio según el modo claro/oscuro de Windows). Colores suaves a la
vista; la canción actual se muestra en una «pantalla» como el visor de esos reproductores. En la barra
lateral, *Biblioteca*, *Playlists* y *Carpetas* tienen cada una su color e icono. (Quien usaba un tema de
versiones anteriores que ya no está pasa al más parecido: Aurora y Vúmetro → Acero, Vino → Carmesí,
Océano → Cromo, Lavanda → Cobalto, Neón → Medianoche.) Al
elegir uno se aplica al instante, sin reiniciar; *Guardar* lo deja para las próximas veces y *Cancelar*
vuelve al anterior. La disposición de la ventana es la misma en todos: solo cambian los colores. Todos
cumplen el contraste recomendado (WCAG) para texto; lo comprueba `tests\theme_contrast_test.py`.

### Ecualizador

**Reproducción → Ecualizador…** (`Ctrl+E`) o el botón de barras junto a *Repetir*. La ventana se puede dejar
abierta mientras suena la música y cada cambio se oye en el acto.

- **10 bandas** (31 Hz a 16 kHz, ±12 dB) y **nivel general**.
- **Presets:** Normal, Pop, Rock, Clásica, Jazz, Electrónica, Hip-Hop, Vocal, Más graves y Más agudos.
- **Presets propios:** *Guardar como preset…* y *Eliminar preset*. *Restablecer* vuelve todo a 0 dB.
- **Evitar saturación** (activado): baja el nivel general lo que sube la banda más alta; además un
  limitador suave evita la distorsión por picos.
- **Activar/desactivar** sin cortar la canción: sigue en el mismo segundo. El estado y los presets se
  recuerdan al volver a abrir el programa; el botón de la barra se ve en color mientras está activado.

Cómo funciona y límites: el reproductor de Qt no permite procesar el audio, así que con el ecualizador
activado el programa usa un motor propio (decodifica con el mismo FFmpeg de Qt, aplica un filtro de fase
lineal de 8192 coeficientes y envía el audio a la tarjeta de sonido). Con el ecualizador desactivado se usa
el motor de siempre. El audio de la canción se guarda en memoria (unos 11 MB por minuto); **no hay límite de
duración**: si un archivo dura más de unos 14 minutos (por ejemplo un CD completo en un solo archivo), el audio
pasa a un archivo temporal en disco, que se borra al cambiar de canción o al cerrar el programa (y, si el
programa se cerró de golpe, la próxima vez que se usa el ecualizador). Un archivo de 2 horas ocupa
temporalmente unos 1,3 GB.

### Gestión de archivos y carpetas

Desde el programa se pueden administrar los archivos de música (clic derecho):

- **Canciones:** *Renombrar archivo…* (si no escribes la extensión, se conserva), *Mover a otra carpeta…*
  (en el diálogo puedes crear una carpeta nueva) y *Enviar a la Papelera…*.
- **Carpetas** (barra lateral → Carpetas): *Renombrar carpeta…*, *Nueva subcarpeta…* y *Enviar carpeta a la
  Papelera…*.
- Antes de borrar se muestra el nombre y la ubicación; si es una carpeta, cuántos archivos contiene y cuántos
  se borrarán. **Borrar = enviar a la Papelera de reciclaje**: se puede recuperar desde allí.
- La biblioteca, las playlists y la canción que suena se actualizan solas. Si renombras o mueves la que está
  sonando, sigue sonando en el mismo punto.
- Nombres repetidos, caracteres no válidos o reservados de Windows, archivos abiertos en otro programa,
  falta de permisos o rutas que ya no existen se explican con un mensaje; nunca se sobrescribe ni se borra
  nada sin avisar. Antes de cada cambio se hace un respaldo de la biblioteca.

### Archivos dañados

Si el informe de importación encuentra archivos de audio **dañados o vacíos**, aparecen marcados en la lista y se
muestra el botón **«Enviar a la papelera los dañados (N)…»**. Puedes desmarcar los que quieras conservar.
Tras confirmar, se envían a la **Papelera de reciclaje** (nunca se borran de forma definitiva).
Los archivos con formato no compatible o sin permiso de lectura no se ofrecen para borrar.

### Canciones repetidas

**Herramientas → Buscar canciones repetidas…** (`Ctrl+Mayús+D`). Dos criterios:

- **Mismo título y artista (duración parecida)**: detecta la misma canción aunque venga de archivos distintos.
  No mezcla versiones de duración muy diferente (por ejemplo, una versión en vivo).
- **Archivos idénticos**: compara el contenido byte a byte (más lento).

En cada grupo se propone **conservar** una copia (la disponible de mayor tamaño) y las demás quedan marcadas
para **quitar**; puedes cambiar las marcas. Luego elige:

- **Quitar marcadas de la biblioteca**: los archivos se quedan en el disco.
- **Enviar marcadas a la papelera…**: además envía los archivos a la Papelera de reciclaje.

En ambos casos, las playlists que usaban una copia quitada pasan a usar la copia conservada.
No se permite quitar todas las copias de una canción.

La columna **Calidad** muestra el formato, los kbps, la frecuencia y si es mono o estéreo de cada copia.

#### Reunir las repetidas en una carpeta para revisarlas

El botón **«Reunir en una carpeta para revisar…»** **mueve** todas las copias de cada canción repetida (según
el criterio elegido) a `…\_Repetidas para revisar\<Título - Artista>\`. Cada copia lleva un número y su carpeta
de origen en el nombre, por ejemplo `1 - Autoridad (de «El Poder está en Ti»).mp3`. Cada subcarpeta incluye un
`LEEME.txt` con la ruta original, el tamaño, la duración y la calidad de cada copia. La carpeta aparece en la
barra lateral, en **Carpetas**, para escucharlas y compararlas.

Es la única función que mueve archivos, y lo hace con estas garantías:

- **Solo dentro del mismo disco** y en discos fijos locales: mover es un renombrado instantáneo, sin copiar
  datos. Lo que está en otro disco, en red o en USB se omite con su motivo.
- **Respaldo de la biblioteca** antes de empezar. La biblioteca y las **playlists se actualizan solas**.
- **Registro de cada movimiento.** Si el programa se cierra a mitad, al abrirlo ofrece devolver todo.
- **Deshacer:** Herramientas → *Historial de cambios en archivos…* devuelve cada archivo a su carpeta original y
  borra la carpeta de revisión si quedó vacía (solo los `LEEME.txt`; nunca música).

Después de revisar, puedes conservar la mejor copia y quitar o enviar a la Papelera las demás desde la misma
ventana. Si devuelves las demás a su lugar, la conservada vuelve también a su carpeta original.

### Historial de cambios en archivos

**Herramientas → Historial de cambios en archivos…** (`Ctrl+Mayús+H`). Reúne en un solo lugar todo lo que el
programa hizo con tus archivos de música, con su fecha y su estado:

- **Reunir repetidas para revisar:** *Deshacer* devuelve cada archivo a su carpeta original.
- **Convertir a MP3:** *Deshacer* devuelve los originales a su sitio y manda los MP3 creados a la Papelera
  (solo si el original está de vuelta en su lugar).
- **Ajustar volumen:** *Revertir volumen…* abre la ventana de volumen con las canciones ya ajustadas, para
  elegir cuáles devolver a su volumen original.

Si el programa se cerró a mitad de una operación, al abrirlo ofrece deshacerla; si eliges «Más tarde», la
encuentras aquí marcada como *Interrumpida*.

### Completar títulos de canciones sin título (opcional)

Actívalo en **Archivo → Preferencias…** (`Ctrl+,`) marcando
**«Al importar, preguntar si quiero completar los títulos de las canciones que no tienen título»**
(desactivado por defecto).

Con la opción activa, si al importar se detectan canciones sin título en sus etiquetas, aparece una lista con un
título propuesto a partir del nombre del archivo (por ejemplo `03 - Queen - Bohemian Rhapsody.mp3` →
título «Bohemian Rhapsody», artista «Queen»). Puedes editar cada título (doble clic), desmarcar las que no quieras
cambiar, y pulsar **Agregar con estos títulos**, u **Omitir** para usar el nombre del archivo.
La sub-opción «Proponer también el artista…» controla si se detecta el artista en el nombre.
Los títulos se guardan solo en la biblioteca: **los archivos no se modifican**.

### Buscar una canción y agregarla a una playlist

1. Escribe en el campo **Buscar** de la barra superior (`Ctrl+F`). Los resultados se actualizan mientras
   escribes y la búsqueda no distingue mayúsculas ni tildes (título, artista o álbum).
2. En la canción encontrada, pulsa el **+** de la derecha (o clic derecho → **Agregar a playlist…**).
3. Elige la playlist del menú. Si aún no existe, elige **Nueva playlist…**, escribe el nombre y la canción
   se agregará a ella directamente.
4. Si la canción ya estaba en esa playlist, el programa pregunta antes de agregarla repetida.

Para agregar varias canciones a la vez, selecciónalas (`Ctrl`/`Mayús` + clic) y usa el botón
**Agregar a playlist** del encabezado.

### Playlists

- Crear: botón **+** junto a «Playlists», o **Playlists → Nueva playlist…** (`Ctrl+N`).
- Renombrar / eliminar: clic derecho sobre la playlist (o `F2` / `Supr`). Eliminar una playlist no borra
  canciones ni archivos.
- Quitar una canción de la playlist: clic derecho → **Quitar de la playlist** (o `Supr`). El archivo no se toca.
- Doble clic sobre una playlist de la barra lateral la reproduce.

### Archivos movidos o eliminados

Las canciones cuyo archivo ya no existe aparecen en gris con un icono de aviso, y el panel muestra un mensaje.
Usa clic derecho → **Localizar archivo…** para elegir la nueva ubicación: la canción conserva sus playlists.
Si otras canciones de la misma carpeta también faltan y están en la nueva carpeta, el programa ofrece
actualizarlas todas de una vez.

**Limpieza automática al abrir** (Archivo → Preferencias → Biblioteca; viene activada): las canciones
cuyo archivo ya no existe se quitan de la lista y de las playlists (no se borra ningún archivo; se hace un
respaldo antes y la lista queda en el registro). Las carpetas que se quedan sin canciones desaparecen de
«Carpetas». Protecciones:

- Si el disco donde estaban (USB, externo o de red) **no está conectado**, se conservan hasta que vuelva.
- Si falta **una carpeta entera** con 10 canciones o más, pregunta: *Buscar dónde está…* (si la moviste
  o renombraste, eliges la nueva y se reubican todas), *Quitarlas de la lista* o *Conservarlas*.
- Si falta **más de la mitad** de las canciones de un disco (¿cambió de letra?), pregunta antes.
- No se quitan las de una conversión a MP3 que todavía se puede deshacer en el Historial.

## Atajos de teclado

| Acción | Atajo |
|--------|-------|
| Reproducir / pausar | `Espacio` o tecla multimedia |
| Anterior / siguiente | `Ctrl+←` / `Ctrl+→` |
| Detener | `Ctrl+.` |
| Orden aleatorio | `Ctrl+H` |
| Cambiar repetición (no / todo / una) | `Ctrl+R` |
| Ecualizador | `Ctrl+E` |
| Volumen | `Ctrl+↑` / `Ctrl+↓` |
| Buscar | `Ctrl+F` |
| Reproducir la canción seleccionada | `Enter` o doble clic |
| Historial de cambios en archivos | `Ctrl+Mayús+H` |

## Editar los menús con Qt Designer (editor gráfico)

Los menús de la ventana principal están en **`assets\menus.ui`**, un archivo de **Qt Designer**, el editor
gráfico oficial de Qt (viene gratis con PySide6; no hay que instalar nada más).

1. Haz doble clic en **`Editar-menus.cmd`** (en la carpeta del proyecto). Se abre Qt Designer con los menús.
2. Edita con el mouse:
   - **Cambiar un texto:** doble clic sobre la opción. El `&` marca la letra subrayada (Alt+letra).
   - **Mover una opción** o cambiar el orden: arrástrala dentro del menú o a otro menú.
   - **Separador:** en el menú, «Agregar separador» (Add Separator).
   - **Submenú:** escribe un texto nuevo en «Escribe aquí» y agrega opciones dentro.
   - **Atajo de teclado:** selecciona la opción en el «Editor de acciones» (Action Editor) y cambia
     `shortcut` en el «Editor de propiedades».
   - **Quitar una opción:** selecciónala en el menú y pulsa Supr.
3. **Archivo → Guardar** en Designer y vuelve a abrir el programa (`python main.py`) para ver los cambios.

Reglas para no romper nada:

- **No cambies el nombre de objeto** (`objectName`, p. ej. `act_history`): así el programa sabe qué hace cada
  opción. El texto visible sí puedes cambiarlo libremente.
- Una **opción nueva** aparece desactivada hasta que se le asigne una función en el código
  (`_build_menus` en `app/ui/main_window.py`).
- Si el archivo queda con un error, el programa **avisa y usa la copia original** `assets\menus.original.ui`
  (no la edites: es el respaldo).
- Para que el programa instalado tenga los menús nuevos, vuelve a crear el instalador (ver abajo).

En el Escritorio también tienes un acceso directo **Qt Designer**, para diseñar ventanas de tus otros
programas (se guardan como archivos `.ui`).

## Crear el instalador de Windows

```powershell
.\crear-instalador.ps1
```

Genera `build\instalador\Instalar-ReproductorMusica-<versión>.exe` (unos 42 MB). La versión se toma de
`app/__init__.py`. Requisitos (una sola vez): `pip install -r requirements.txt` dentro de `.venv` (versiones
exactas probadas; el script instala la versión fijada de PyInstaller) y
`winget install --id JRSoftware.InnoSetup -e --scope user`. Para publicar, créalo desde una versión
guardada en git (el script avisa si hay cambios sin guardar).

Qué hace el instalador:

- Instala solo para el usuario actual, **sin permisos de administrador**, en
  `%LOCALAPPDATA%\Programs\ReproductorMusica`. Funciona en Windows 10 (1809 o posterior) y 11, de 64 bits,
  y no necesita Python.
- Crea el acceso del menú Inicio; el del Escritorio es opcional.
- Opción **«Abrir con»** para los formatos de música (marcada por defecto). No cambia tu programa
  predeterminado. Si el reproductor ya está abierto, la canción se reproduce en esa ventana.
- El desinstalador pregunta si borrar la biblioteca (por defecto **no**). Los archivos de música nunca se
  borran.
- Al actualizar, borra los archivos internos de la versión anterior (tu biblioteca y tus ajustes se
  conservan).
- El instalador no está firmado: la primera vez Windows puede mostrar «Windows protegió su PC» →
  *Más información* → *Ejecutar de todas formas*.

### Licencias de terceros

El programa incluye Qt/PySide6 y FFmpeg (LGPL), LAME/lameenc (LGPL), mutagen (GPL-2.0 o posterior), NumPy
(BSD) y Python (PSF). La carpeta `licencias` (copiada al instalar) tiene `TERCEROS.txt` con el detalle y
los textos completos. Al distribuir el programa hay que incluirla. Como mutagen es GPL, distribuir el
programa con el código cerrado no es compatible con su licencia: hay que publicarlo bajo GPL o reemplazar
mutagen por una biblioteca de licencia compatible.

Archivos: `packaging/ReproductorMusica.spec` (PyInstaller), `packaging/instalador.iss` (Inno Setup),
`packaging/version_info.txt` y `tools/make_icon.py` (genera `assets/icono.ico`).

## Respaldos y registro de errores

- **Respaldo automático diario** de la biblioteca en `%LOCALAPPDATA%\ReproductorMusica\respaldos`.
  Cada copia se verifica. Se conservan las 10 más recientes y una por semana de las últimas 4 semanas.
- También se hace un respaldo **antes** de fusionar repetidas, de quitar 10 canciones o más, de eliminar
  una playlist con canciones, de aplicar «Datos en internet» a 10 canciones o más y de actualizar el
  formato de la base.
- Al abrir, el programa **revisa la biblioteca**. Si está dañada, ofrece restaurar el último respaldo
  válido; la dañada no se borra, se guarda como `biblioteca-danada-…`.
- Archivo → *Respaldos de la biblioteca* → *Crear un respaldo ahora* / *Abrir la carpeta de respaldos*.
- Si el respaldo previo a una operación sobre archivos falla, el programa pregunta antes de seguir sin él.
- Los errores se guardan en `registro.log` (Ayuda → *Abrir registro de errores*).

## Solución de problemas

- **No se escucha nada**: usa **Reproducción → Probar sonido…**. Toca un tono por el mismo camino que las canciones
  y muestra la salida de audio que se está usando, el volumen de Windows y el del programa. El programa avisa
  si Windows está silenciado o al 0 %, y cambia solo de salida cuando Windows cambia la predeterminada
  (auriculares, Bluetooth, HDMI).

- **«No module named PySide6»**: el entorno virtual no está activo o VS Code usa otro intérprete.
  Activa `.venv` o selecciona el intérprete como se indica arriba.
- **Un archivo no suena o da error**: el programa muestra el motivo (dañado, formato no compatible, sin
  permiso, unidad desconectada). Prueba a abrirlo con otro reproductor para confirmar que está bien.
- **WMA protegidos con DRM** no se pueden reproducir.
