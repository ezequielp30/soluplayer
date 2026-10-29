# Carpetas de origen y orden manual

## Contexto

La aplicación importa audio desde una carpeta o archivos elegidos por el usuario. Las pistas y las playlists se guardan en SQLite, pero la aplicación no conserva qué carpetas se eligieron como origen. La sección «Carpetas» se reconstruye a partir de las rutas de las pistas. La tabla permite ordenar temporalmente por columna y la reproducción utiliza el orden de la lista que recibe.

Al quitar una pista de la biblioteca hoy se elimina su fila y, por la clave foránea, sus entradas de playlist. Para poder desvincular una carpeta y conservar sus pistas en playlists, la pertenencia a la biblioteca debe separarse de la fila de pista que necesitan las playlists.

## Objetivos

- Permitir registrar, mostrar y quitar varias carpetas de origen desde el panel izquierdo.
- Al quitar una fuente, desvincular sus pistas de la biblioteca sin modificar, mover ni enviar a la papelera los archivos.
- Mantener en las playlists las pistas desvinculadas que ya estén en ellas.
- Permitir arrastrar pistas para cambiar su orden en «Canciones», en cada carpeta y en cada playlist.
- Persistir cada orden independiente y usarlo al reproducir la lista correspondiente.
- Conservar el comportamiento de importación, las playlists y el orden temporal por columnas que ya existen.

## Fuera de alcance

- Reordenar «Recientes», búsqueda, artistas o álbumes.
- Escanear fuentes automáticamente al iniciar la aplicación o implementar sincronización en segundo plano.
- Cambiar la ubicación o el contenido de los archivos de música al agregar o quitar una fuente.
- Cambiar las acciones explícitas existentes para quitar pistas individuales de la biblioteca.

## Diseño

### Fuentes de música

La base de datos mantendrá las fuentes como rutas normalizadas y una relación entre fuente y pista. La relación será de muchos a muchos: una misma pista puede encontrarse bajo más de una fuente activa. Se guardará también si la importación de esa fuente incluye subcarpetas, reutilizando la opción del diálogo actual.

La sección «Carpetas» conservará el árbol navegable de directorios y presentará las raíces registradas como fuentes, incluso si una fuente todavía no contiene pistas (con contador cero). El botón de agregar abre el selector y el flujo de importación existente. En el menú contextual de una raíz registrada habrá una acción «Quitar de la biblioteca», distinta de «Enviar carpeta a la Papelera». Las subcarpetas seguirán pudiéndose navegar y gestionar con las acciones actuales.

Al agregar una fuente, las pistas encontradas se asocian con ella, incluidas las pistas que ya estaban registradas. La importación individual de archivos mantiene una pertenencia independiente; cuando una fuente reclama una pista heredada, esa pertenencia heredada pasa a ser de la fuente. Al quitar una fuente, una transacción elimina la fuente y sus asociaciones. Una pista sigue visible en la biblioteca si pertenece a otra fuente activa o conserva una pertenencia independiente. Si deja de pertenecer a la biblioteca pero sigue en una playlist, se conserva su fila de pista para que la playlist pueda seguir mostrándola y reproduciéndola. Las pistas sin referencias de biblioteca ni de playlist se pueden retirar de SQLite. Ninguno de estos pasos realiza operaciones sobre el archivo.

La versión actual no registra el origen de las pistas existentes. La migración las conservará visibles como elementos heredados sin fuente; al agregar una fuente, las pistas coincidentes quedarán asociadas con ella. Los archivos que se importen individualmente seguirán siendo independientes de las fuentes.

### Orden manual

El orden se guardará por contexto:

- Un orden global para «Canciones».
- Un orden por ruta de carpeta mostrada, sin mezclar el orden de carpetas diferentes.
- El orden ya existente de cada playlist, actualizado al mover sus entradas.

Las playlists pueden contener entradas repetidas; por eso el movimiento se identificará por el ID de la entrada de playlist, no solo por el ID de la pista. Los órdenes de vistas dinámicas quedan fuera de alcance.

El arrastre modifica el orden de filas, lo persiste y devuelve la tabla al orden manual si antes se había ordenado temporalmente por una columna. La ordenación por encabezado seguirá disponible como vista temporal. Las acciones de reproducir una lista y de iniciar desde una fila usarán la secuencia de esa lista que corresponda; el modo aleatorio mantendrá su comportamiento aleatorio.

Las pistas que aún no tengan posición personalizada conservarán el orden predeterminado actual; las nuevas pistas aparecerán al final del orden personalizado existente, en el orden estable de importación. La migración conservará el orden visible actual para las pistas heredadas y no alterará las posiciones de las playlists.

### Persistencia y compatibilidad

La migración SQLite añadirá el registro de fuentes, asociaciones de fuentes y órdenes de biblioteca/carpeta. Se aplicará mediante el mecanismo transaccional de migración existente y conservará el respaldo previo automático. La eliminación de una fuente y el cambio de orden se realizarán en transacciones para evitar estados parciales.

Las consultas de biblioteca y las vistas derivadas excluirán las pistas sin pertenencia a biblioteca; las consultas de playlists continuarán recuperando las pistas por sus referencias existentes, incluidas las que ya no estén en la biblioteca. Las operaciones de actualización y eliminación de pistas existentes deberán mantener coherentes las asociaciones y los órdenes guardados.

### Interfaz y límites de módulos

- `app/database.py`: migración, persistencia de fuentes y orden, pertenencia visible a biblioteca y lecturas para playlists.
- `app/importer.py` y `app/ui/main_window.py`: asociar con la fuente las pistas nuevas y duplicadas descubiertas por los flujos de importación.
- `app/ui/sidebar.py` y `app/ui/main_window.py`: controles para agregar/quitar fuentes y refrescar selección, árbol y vistas.
- `app/ui/content_panel.py` y `app/ui/track_model.py`: soporte para arrastre y actualización de las listas, respetando la identidad de las entradas de playlist.
- `app/player.py`: no necesita un nuevo formato de cola; recibirá las pistas en el orden persistido a través de los flujos existentes.

La acción de quitar una fuente no llamará a `file_manager`, `file_ops` ni a las operaciones de papelera. Los errores de lectura, escritura o migración se comunicarán explícitamente y no se presentarán como éxito.

## Verificación y criterios de aceptación

1. Se pueden agregar dos fuentes, cerrar y abrir la aplicación, y seguir viéndolas en el panel izquierdo.
2. Quitar una fuente no modifica ni mueve ningún archivo, y las pistas exclusivas de esa fuente dejan de aparecer en «Canciones».
3. Las pistas de una fuente quitada que estén en una playlist continúan en ella y se pueden reproducir; las pistas compartidas con otra fuente activa permanecen en la biblioteca.
4. Agregar una fuente que contiene pistas ya conocidas las asocia sin duplicar registros ni entradas de playlist.
5. Se puede reordenar «Canciones», una carpeta y una playlist de forma independiente; los cambios sobreviven al reinicio.
6. La reproducción normal usa el orden manual guardado, incluida la reproducción desde una pista seleccionada. El modo aleatorio sigue siendo aleatorio.
7. El ordenamiento temporal por columna sigue funcionando; después de arrastrar, se vuelve al orden manual.
8. Las bases existentes migran sin perder pistas ni playlists, y se conserva la visibilidad de las pistas anteriores a la función.
9. Las pruebas verifican transacciones, duplicados de playlist, fuentes superpuestas, orden persistido y que las operaciones de fuente no llaman a funciones de modificación de archivos.
