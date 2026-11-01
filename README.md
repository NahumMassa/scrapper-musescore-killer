# omr-musescore-killer

Convierte partituras en SVG exportadas de MuseScore en un PDF para imprimir y un MusicXML para manipular. Como siguiente paso se propone una app para practicar fragmentos con un teclado MIDI.

## Alcance

| | |
|---|---|
| **Entrada** | SVG de MuseScore: el de la web o el del programa de escritorio. Cada símbolo debe traer su clase (`class="Note"`, `class="Stem"`…). |
| **Flujo 1** | SVG → PDF para imprimir. |
| **Flujo 2** | SVG → MusicXML para abrir y editar en MuseScore. |
| **Propuesta: práctica** | Tocar fragmentos del MusicXML revisado con un MiniLab 3 y saber si se tocaron bien. Sin construir. |
| **Fuera de alcance** | PDF, escaneos, fotos y SVG de otros programas. Cómo conseguir los SVG tampoco es parte de los flujos. |

El nombre del repo viene de una fase anterior basada en reconocimiento óptico de música (OMR). Se descartó porque el SVG ya trae cada símbolo con sus coordenadas: en una partitura difícil, Audiveris y homr acertaban cerca del 95 % de las notas, y además hay que corregir a mano lo que confunden.

## Estado (1 de noviembre de 2026)

| Pieza | Estado |
|---|---|
| Flujo 1: PDF | [svg2pdf.py](svg2pdf.py) funciona; falta imprimir en papel |
| Flujo 2: script SVG → MusicXML | [svg2musicxml.py](svg2musicxml.py) funciona, pero no es fiable con cualquier partitura |
| Flujo 2: comparación | [comparar_musicxml.py](comparar_musicxml.py) existe, pero necesita un MusicXML de referencia, que normalmente no habrá |
| Flujo 2: convenciones | Sin construir |
| Flujo 2: revisión humana | Se hace en MuseScore; falta la lista de diferencias que la guíe |
| App de práctica | Sin construir; primero hay que probar las que ya existen |
| Pruebas | [pruebas.py](pruebas.py): 23 de 23 pasan |

## Partituras generadas

| Partitura | PDF (`svg_to_pdf`) | MusicXML (`svg_to_xml`) |
|---|---|---|
| Clair de Lune, página 1 | Generado | Comprobado contra el SVG; no se ha escuchado |
| Midnight Rendezvous, 3 páginas | Generado; no se ha mirado | **Sin revisar** |

En Midnight Rendezvous, el script dedujo 4/4 sin confirmarlo y el compás 1 no suma, sin saber si es una anacrusa o un error. No hay referencia, así que se desconoce cuántas notas acertó. Trae trinos, acordes, casillas de repetición, marcas de ensayo, tempo y otros textos que el script no conserva: hay que añadirlos en la revisión. Sin las repeticiones, el orden de reproducción no es el del original.

## Flujo 1: SVG → PDF

**Herramienta: Chrome sin ventana (`--headless --print-to-pdf`).** Ya está instalado, conserva los vectores, encaja cada SVG en una hoja A4 y une varias páginas sin más dependencias. Al cargar los SVG con `<img>`, el navegador no ejecuta los scripts que pudieran traer.

Con [svg2pdf.py](svg2pdf.py), desde WSL, indicando una carpeta de Windows que contenga solo los SVG de una partitura:

```bash
python svg2pdf.py /mnt/d/Nahum/omr_partituras/svg_partituras mi_partitura
```

El PDF se guarda en `D:\Nahum\omr_partituras\svg_to_pdf\mi_partitura.pdf`. Las páginas siguen el orden numérico: `score_2` va antes que `score_10`.

**Falla sin generar nada** si un SVG pesa 0 bytes, está cortado o no es un SVG, y dice cuál. Chrome no da error con ellos: termina bien y deja un icono de imagen rota en esa página. Si Chrome falla, un PDF anterior con ese nombre sigue intacto.

### Qué se probó

Se compararon Chrome y [CairoSVG](https://cairosvg.org/) con tres SVG: uno de la web, uno de escritorio y uno con `transform="matrix(...)"`.

| Comprobación | Chrome | CairoSVG |
|---|---|---|
| PDF vectorial, sin imágenes incrustadas | Sí | Sí |
| Conserva todos los trazos del SVG (109 y 669 en los dos primeros) | Sí | Sí |
| Tamaño de página con un SVG que no es A4 | A4 | Sigue al SVG (210 × 272 mm) |
| Une varias páginas | Sí; probado con 2 y 3, sin hojas en blanco | No; haría falta otra biblioteca |

Los dos motores coinciden: a 150 DPI difieren en menos del 0,05 % de los píxeles con tinta. Es una buena señal porque son motores distintos, aunque no prueba que ambos acierten; también se miró una página a simple vista contra el original.

**Sin probar:** imprimirlo en papel; Inkscape y `rsvg-convert`, que no están instalados. Las partituras probadas solo usan trazos, sin fuentes, así que el riesgo es bajo. Si un SVG trae `<text>`, habría que revisar el resultado.

## Flujo 2: SVG → MusicXML

```text
convenciones de la partitura
          ↓
   svg2musicxml.py
          ↓
  MusicXML generado
          ↓
  script de comparación
          ↓
  lista de diferencias
          ↓
revisión humana en MuseScore: repara los errores
          ↓
  MusicXML revisado (final)
```

**El flujo va en una sola dirección.** La revisión repara los errores directamente en MuseScore y no vuelve a ejecutar el script.

**Regla:** el MusicXML generado se conserva intacto y la revisión se guarda como un archivo aparte. Regenerar no sobrescribe nunca el archivo revisado, porque perdería las reparaciones.

### 1. Convenciones (sin construir)

Un archivo corto por partitura, junto a sus SVG, con lo que el script no puede leer del SVG. Se escribe antes de ejecutarlo. Este formato es una propuesta; se usaría TOML porque Python lo lee sin dependencias.

```toml
# clair_de_lune.toml
[partitura]
titulo = "Clair de Lune"
compositor = "Claude Debussy"
compas = "9/8"                       # el script no lee los dígitos del SVG

# Lo que no se puede leer del SVG se añade al MusicXML
[[anadir]]
compas = 1
tiempo = 0
tipo = "tempo"
texto = "Andante très expressif"

[[anadir]]
compas = 1
tiempo = 0
tipo = "dinamica"
texto = "pp"
```

Hay dos tipos de anotación:

- **Datos de la partitura:** el script los usa al leer, como el compás.
- **Añadidos:** el script los escribe en el MusicXML, como título, tempo, dinámicas, acordes o repeticiones.

Los errores de lectura de una nota no van aquí: se reparan en la revisión. Si el mismo error se repite en varias partituras, se arregla el script.

### 2. Script: `svg2musicxml.py`

```bash
python svg2musicxml.py pagina1.svg pagina2.svg -o /mnt/d/Nahum/omr_partituras/svg_to_xml/mi_partitura.musicxml --compas 9/8
```

Los MusicXML se guardan en `D:\Nahum\omr_partituras\svg_to_xml`.

Solo usa la biblioteca estándar. Lee cada símbolo y calcula:

- **Altura:** posición vertical, clave vigente, armadura y alteraciones.
- **Figura:** cabeza hueca o llena, plica, barras, corchete y puntillo.
- **Ritmo:** agrupa por columnas; cada columna empieza cuando termina la nota sonando que acaba antes.
- **Voces:** las reparte sin que se pisen; un grupo con barra va entero a la misma voz.
- **Otros:** ligaduras de ambos tipos, dosillos, tresillos, tenutos y signos `%`.

**Resultados.** Una nota es correcta si coinciden compás, tiempo, duración, nombre, alteración y octava.

| Partitura | Notas correctas | Validez |
|---|---|---|
| Clair de Lune, página 1 (SVG web) | 345 de 345 | El script se afinó con ella |
| Él siempre reina | 119 de 119 | También se retocó con ella |
| Audiveris, Beethoven II | 409 de 421 (97,1 %) | No vista |
| homr, Beethoven p4 | 357 de 394 (90,6 %) | No vista |
| homr, Beethoven p10 | 421 de 475 (88,6 %) | No vista |
| Audiveris, Piano exam | 19 de 22 (86,4 %) | No vista |
| homr, Piano exam | 19 de 23 (82,6 %) | No vista |
| homr, Night Dreamer p6 | 245 de 416 (58,9 %) | No vista |
| homr, Night Dreamer p2 | 16 de 453 (3,5 %) | No vista |

Las 7 últimas son salidas de OMR exportadas a SVG por MuseScore. La referencia es lo que dice cada archivo, no la partitura impresa. Tienen compases que ya no cuadran, lo que quizá las hace más difíciles que una partitura limpia, aunque no se ha medido. Se contaron tras corregir un fallo del parser, sin más ajustes.

**Problemas conocidos:**

- Un error de compás se arrastra: en Night Dreamer p2 las notas revisadas salen un compás antes y casi todo cuenta como error. Causa sin confirmar.
- Lee mal muchos silencios: en los dos Piano exam acierta 1 y 2 de 9. Causa sin investigar.
- No interpreta algunos grupos irregulares, como uno de 12 notas.
- El formato web solo se ha probado con una página.

**No hace:**

- Texto: título, tempo, dinámicas, acordes y letra vienen como contornos.
- Repeticiones, casillas y reguladores.
- Articulaciones distintas del tenuto.
- Cambios de compás o armadura, y claves distintas de sol y fa.
- Notas de adorno, que trata como notas normales.

### 3. Comparación

[comparar_musicxml.py](comparar_musicxml.py) califica nota por nota contra un MusicXML de referencia. Sirve para medir el script, pero en el uso normal no hay referencia.

**Propuesta (sin construir):** comparar contra el propio SVG original:

1. MuseScore convierte el MusicXML generado a SVG.
2. El extractor lee ese SVG y el original.
3. Se comparan compás por compás: posición de las cabezas respecto al pentagrama, plicas, barras, puntillos, silencios, ligaduras y alteraciones.
4. Sale una lista de compases con diferencias, con el recorte de cada versión.

**Lo que esta comparación no ve:** si el script se equivoca igual al leer y al escribir, la imagen regenerada coincide con el original aunque el dato esté mal. Por ejemplo, una armadura mal leída que se vuelve a dibujar igual. Por eso la revisión humana mira toda la partitura y no solo lo marcado.

También hay que distinguir las diferencias de maquetación, que son esperables, de las musicales: MuseScore reparte los compases a su manera. Por eso se compara por compás y sin usar coordenadas absolutas.

### 4. Revisión humana

Se abre el MusicXML generado en MuseScore y se repara a mano:

1. Primero, los compases de la lista de diferencias.
2. Después, el resto de la partitura contra el SVG o el PDF, escuchándola.
3. Se guarda en `svg_to_xml` como `<partitura>_revisado.musicxml`, sin tocar el generado.

Vale la pena medir cuánto tarda una página: es lo que dirá si conviene seguir mejorando el script.

**Sin MCP por ahora.** Reparar es trabajo visual en la ventana de MuseScore, y un agente ya puede editar el MusicXML como archivo. Los MCP existentes no se han probado; quedan como opción si aparecen ediciones repetitivas.

## Propuesta: app de práctica (sin construir)

Elegir un fragmento (por ejemplo, compases 5 a 8, una mano), tocarlo en el MiniLab 3 y saber si se tocó bien. Usa siempre el MusicXML **revisado**: si la partitura tiene una nota mal, la app corregiría al revés.

**Antes de construirla:** probar [midipiano.app](https://alternativeto.net/software/midipiano-app/about/) y [PianoML](https://hunted.space/dashboard/pianoml), que dicen leer MusicXML y dar respuesta con teclado MIDI. Solo se han visto sus fichas, no se han usado. Lo que no cubran es lo que justificaría la app propia.

**Si hay que construirla:** una página local en Chrome.

| Pieza | Herramienta | Motivo |
|---|---|---|
| Teclado | Web MIDI | Chrome corre en Windows, donde está conectado el USB; WSL no lo ve sin configuración extra |
| Partitura | [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay/wiki/Exploring-the-Demo) | Dibuja MusicXML y tiene un cursor que expone las notas de cada tiempo |
| Evaluación | Código propio | No se encontró ningún ejemplo que lo resuelva |

**Primera versión:**

1. Modo espera: el cursor avanza cuando se tocan todas las notas del tiempo actual. Sin medir ritmo.
2. Elegir compases y mano, y repetir el fragmento.
3. Marcar cada nota como correcta o incorrecta y dar el total al terminar.

**Casos que definen si funciona:**

- **Rango:** el MiniLab 3 tiene 25 teclas y solo la primera página de Clair de Lune va de Mi♭1 a Sol♭6, más de cinco octavas. Hace falta transportar el fragmento a una octava que quepa, y comprobar que el fragmento entero cabe.
- **Ligaduras de prolongación:** una nota ligada no se vuelve a tocar, así que no debe exigirse.
- **Acordes:** las notas de un acorde nunca llegan a la vez; hace falta una ventana de tiempo.
- **Voces:** cada nota debe saberse de qué pentagrama es para poder separar las manos, también en los grupos que cruzan de pentagrama.

**Después:** medir ritmo contra un metrónomo. Es la parte difícil, porque hay que decidir cuánta desviación se tolera.

## Pruebas

Todas están en [pruebas.py](pruebas.py). Cada una corre por separado y al final dice cuántas pasaron:

```bash
.venv/bin/python pruebas.py
```
```text
ok       test_pdf_rechaza_0_bytes
ok       test_xml_clair_de_lune_web
...
23 de 23 pruebas pasaron (0 fallaron, 0 saltadas)
```

| Script | Pruebas | Qué cubren |
|---|---|---|
| `svg2pdf.py` | 9 | SVG vacío, cortado o que no es SVG; orden de páginas; un PDF real generado con Chrome |
| `svg2musicxml.py` | 11 | Lectura de contornos, matrices y armaduras; SVG vacío o ajeno; Clair de Lune y Él siempre reina nota por nota |
| `svg_scrape.py` | 3 | SVG creados por JS, anidados, repetidos, efímeros, en contenedores con desplazamiento y recibidos por la red |

- **Si una falla:** las demás siguen corriendo y el script termina con código 1.
- **Si falta algo:** una prueba que necesita un archivo de `D:` o un programa de Windows sale como «saltada» y no cuenta como pasada.
- **Ventana de Chrome:** las pruebas de `svg_scrape` abren una durante unos 13 segundos. Usan un perfil temporal (`SVG_SCRAPE_PERFIL`) para no tocar el real.
- **Sin pruebas propias:** `comparar_musicxml.py` solo se usa dentro de las de partituras, y `svg_html.py` no tiene ninguna.
- **Su alcance:** las dos partituras completas sirvieron para afinar el script, así que su 100 % no demuestra que generalice. Las cifras reales están en [los resultados del flujo 2](#2-script-svg2musicxmlpy).

## Próximos pasos

1. Imprimir una partitura en papel.
2. Construir la comparación contra el SVG original y comprobar que detecta errores introducidos a propósito.
3. Definir las convenciones con partituras reales, empezando por título, compás, tempo y dinámicas.
4. Investigar los silencios y el error de compás arrastrado.
5. Conseguir una partitura completa de varias páginas en formato web y medirla.
6. Revisar una página en MuseScore y medir cuánto se tarda.
7. Probar las apps de práctica existentes con el MiniLab 3 y un MusicXML revisado; decidir si hace falta la propia.
8. Resolver el fallo intermitente de `svg_scrape.py` con el perfil real.

## Otros archivos

| Archivo | Para qué |
|---|---|
| [pruebas.py](pruebas.py) | Todas las pruebas. Cada una corre por separado y al final dice cuántas pasaron |
| [svg_scrape.py](svg_scrape.py) | Descarga los SVG de una página. Solo se ha capturado 1 de las 22 páginas de una partitura; falta confirmar que capture la obra completa |
| [svg_html.py](svg_html.py) | Extrae los `<svg>` de un HTML y los pasa a PNG |

### Problemas conocidos de `svg_scrape.py`

- **Python de Windows:** no funciona con el de WSL. Se ejecuta con `uvx.exe --python 3.12 --with playwright python svg_scrape.py URL carpeta`, desde una carpeta de Windows.
- **Fallo intermitente con el perfil real:** al ejecutarlo varias veces seguidas, a veces el navegador se cierra a mitad de la captura o una navegación se interrumpe por `about:blank`. Con un perfil temporal pasó todas las veces, así que se sospecha del perfil persistente, sin confirmarlo. Las pruebas no cubren este caso. Si falla, espera unos segundos y vuelve a lanzarlo.

## Derechos

Las partituras y sus resultados se quedan fuera del repo. Antes de descargar una partitura de un sitio hay que revisar sus derechos y los términos del sitio. El SVG de una obra de dominio público puede ser una edición con sus propias condiciones. El PDF de Night Dreamer lleva una marca de agua que prohíbe compartirlo y muestra datos de la cuenta: no debe subirse ni publicarse.
