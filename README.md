# omr-musescore-killer

Convierte partituras en SVG exportadas de MuseScore en un PDF para imprimir y un MusicXML para manipular. Incluye una página para practicar nota por nota con un teclado MIDI.

## Alcance

| | |
|---|---|
| **Entrada** | SVG de MuseScore: el de la web o el del programa de escritorio. Cada símbolo debe traer su clase (`class="Note"`, `class="Stem"`…). |
| **Flujo 1** | SVG → PDF para imprimir. |
| **Flujo 2** | SVG → MusicXML para abrir y editar en MuseScore. |
| **Práctica** | Tocar un MusicXML nota por nota con un MiniLab 3 en [practica.html](practica.html), sin medir ritmo. |
| **Página** | Home, Convertir (los tres scripts) y Práctica, servidas por [web.py](#página-webpy). |
| **Fuera de alcance** | PDF, escaneos, fotos y SVG de otros programas. Bajar los SVG de MuseScore no es parte de los flujos; lo hace [svg_scrape.py](#descarga-de-svg-svg_scrapepy), y [partitura.py](#todo-en-un-paso-partiturapy) encadena todo desde un enlace. |

El nombre del repo viene de una fase anterior basada en reconocimiento óptico de música (OMR). Se descartó porque el SVG ya trae cada símbolo con sus coordenadas: en una partitura difícil, Audiveris y homr acertaban cerca del 95 % de las notas, y además hay que corregir a mano lo que confunden.

## Estado (2 de noviembre de 2026)

| Pieza | Estado |
|---|---|
| Flujo 1: PDF | [svg2pdf.py](svg2pdf.py) funciona; falta imprimir en papel |
| Flujo 2: script SVG → MusicXML | [svg2musicxml.py](svg2musicxml.py) funciona, pero no es fiable con cualquier partitura |
| Flujo 2: comparación | [comparar_musicxml.py](comparar_musicxml.py) existe, pero necesita un MusicXML de referencia, que normalmente no habrá |
| Flujo 2: convenciones | Sin construir |
| Flujo 2: revisión humana | Se hace en MuseScore; falta la lista de diferencias que la guíe |
| App de práctica | Primera versión; aún sin probar pulsando teclas reales |
| Descarga de SVG | [svg_scrape.py](svg_scrape.py) baja partituras completas de musescore.com (4 y 23 hojas probadas); reintentos y rechazos sin probar |
| Todo en un paso | [partitura.py](partitura.py): enlace → PDF + MusicXML; probado con un enlace |
| Página | [web.py](web.py): Home, Convertir y Práctica; pipeline probada solo contra una página local |
| Pruebas | [pruebas.py](pruebas.py): 49 de 49 pasan |

## Partituras generadas

| Partitura | PDF (`svg_to_pdf`) | MusicXML (`svg_to_xml`) |
|---|---|---|
| Clair de Lune, página 1 | Generado | Comprobado contra el SVG; no se ha escuchado |
| Midnight Rendezvous, 3 páginas | Generado; no se ha mirado | **Sin revisar** |
| Sonata «Moonlight» 1.er mov., 4 hojas (con `partitura.py`) | Generado; no se ha mirado | **Sin revisar**; 67 de 69 compases no suman 4/4 |

En Midnight Rendezvous, el script dedujo 4/4 sin confirmarlo y el compás 1 no suma, sin saber si es una anacrusa o un error. No hay referencia, así que se desconoce cuántas notas acertó. Trae trinos, acordes, casillas de repetición, marcas de ensayo, tempo y otros textos que el script no conserva: hay que añadirlos en la revisión. Sin las repeticiones, el orden de reproducción no es el del original.

## Flujo 1: SVG → PDF

**Herramienta: Chrome sin ventana (`--headless --print-to-pdf`).** Ya está instalado, conserva los vectores, encaja cada SVG en una hoja A4 y une varias páginas sin más dependencias. Al cargar los SVG con `<img>`, el navegador no ejecuta los scripts que pudieran traer.

Con [svg2pdf.py](svg2pdf.py), desde WSL, indicando una carpeta de Windows que contenga solo los SVG de una partitura:

```bash
python svg2pdf.py /mnt/d/Nahum/omr_partituras/svg_partituras/mi_partitura mi_partitura
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
python svg2musicxml.py pagina1.svg pagina2.svg -o /mnt/d/Nahum/omr_partituras/svg_to_xml/mi_partitura.musicxml
```

Las cifras de compás se leen del SVG, cambios incluidos, si usan la fuente por defecto de MuseScore 4 (se comparan con [glifos.json](glifos.json)). Si no se reconocen, vale `--compas 9/8`; sin él, se deduce de la duración más frecuente de los compases (no distingue 6/8 de 3/4) y, si tampoco se puede, 4/4.

Los MusicXML se guardan en `D:\Nahum\omr_partituras\svg_to_xml`.

Solo usa la biblioteca estándar. Lee cada símbolo y calcula:

- **Altura:** posición vertical, clave vigente, armadura y alteraciones.
- **Figura:** cabeza hueca o llena, plica, barras, corchete y puntillo.
- **Ritmo:** agrupa por columnas; cada columna empieza cuando termina la nota sonando que acaba antes.
- **Voces:** las reparte sin que se pisen; un grupo con barra va entero a la misma voz.
- **Otros:** ligaduras de ambos tipos, grupos irregulares (también los tresillos sin número), notas de adorno, 8va, arpegios, reguladores, repeticiones, casillas, cambios de armadura y signos `%`.
- **Con el catálogo de glifos:** cifras de compás, articulaciones, fermatas y dinámicas de la fuente por defecto de MuseScore 4. Con otra fuente, las cifras se calibran con la propia partitura, y el staccato, el tenuto y la fermata se leen por su forma.

**Resultados.** Una nota es correcta si coinciden compás, tiempo, duración, nombre, alteración y octava.

| Partitura | Notas correctas | Validez |
|---|---|---|
| Clair de Lune, página 1 (SVG web) | 345 de 345 | El script se afinó con ella |
| Él siempre reina | 119 de 119 | También se retocó con ella |
| Night Dreamer, reducción de piano (escritorio) | 3329 de 3329 | Se afinó con ella: empezó en 55,4 % |
| Vals en la menor, Chopin (web) | 603 de 603 | Se afinó con ella: empezó en 99,5 % |
| Preludio en do, BWV 846 (web) | 619 de 619 | Se afinó con ella: empezó en 96,6 % |
| Arabesque n.º 1, Debussy (web) | 1545 de 1545 | Se afinó con ella: empezó en 43,9 % |
| Audiveris, Beethoven II | 409 de 421 (97,1 %) | Entrada de OMR |
| homr, Beethoven p4 | 357 de 394 (90,6 %) | Entrada de OMR |
| homr, Beethoven p10 | 421 de 475 (88,6 %) | Entrada de OMR |
| Audiveris, Piano exam | 19 de 22 (86,4 %) | Entrada de OMR |
| homr, Piano exam | 19 de 23 (82,6 %) | Entrada de OMR |
| homr, Night Dreamer p6 | 245 de 416 (58,9 %) | Entrada de OMR |
| homr, Night Dreamer p2 | 16 de 453 (3,5 %) | Entrada de OMR |

**Estas 7 filas no miden el script.** Son SVG que salieron de motores OMR (Audiveris y homr) y que MuseScore exportó con sus errores y compases que no cuadran. Se conservan solo para comparar entre sí, no como la precisión del script con partituras reales. Con esos archivos el rango fue de 3,5 % a 97,1 %, que no sirve como medida.

**Medición limpia (2 de noviembre de 2026):** tres obras de musescore.com en SVG web, no vistas al escribir el script, contra su MusicXML original, antes de afinar nada con ellas.

| Partitura | Notas correctas | Silencios |
|---|---|---|
| Vals en la menor, Chopin | 600 de 603 (99,5 %) | 16 de 16 |
| Preludio en do, BWV 846 | 598 de 619 (96,6 %) | 132 de 132 |
| Arabesque n.º 1, Debussy | 678 de 1545 (43,9 %) | 22 de 44 |

Después se afinó el script con ellas (tabla de arriba), así que ya no sirven como medida limpia. En Arabesque faltan 29 de los 93 extremos de regulador porque no están dibujados en el SVG.

**Pendiente: repetir la medición** con partituras de MuseScore bien hechas que el script no haya visto, y con una referencia correcta. Hasta entonces no hay cifra fiable de generalización; todas las filas de partituras de MuseScore se usaron para afinar el script.

**Problemas conocidos** (observados con esas entradas de OMR, sin confirmar con partituras limpias):

- Un error de compás se arrastra: en Night Dreamer p2 las notas revisadas salen un compás antes y casi todo cuenta como error. Causa sin confirmar.
- Lee mal muchos silencios: en los dos Piano exam acierta 1 y 2 de 9. Causa sin investigar.
- No interpreta algunos grupos irregulares, como uno de 12 notas.
- El formato web solo se ha probado con una página.

**No hace:**

- Texto: título, tempo, acordes, marcas de ensayo y letra vienen como contornos.
- Claves distintas de sol y fa.
- Con una fuente distinta de la de MuseScore 4: dinámicas, acentos y ornamentos (trinos, mordentes).
- Casillas en SVG web: solo se leen en el de escritorio.
- Saltos (D.C., D.S., coda): las repeticiones y casillas se escriben, pero no se reordena nada.

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

## Práctica: `practica.html`

Página local en Chrome: sueltas un MusicXML (o `.mxl`), tocas en el MiniLab 3 y cada nota pasa de gris (por tocar) a verde (tocada) y la franja gris avanza solo cuando aciertas todas las del paso. Los pasos sin nada que tocar (silencios, notas ligadas, la otra mano) se pasan de largo. No mide ritmo ni produce sonido.

```bash
.venv/bin/python web.py
```

Abre `http://localhost:8766/practica.html` en Chrome (el de Windows, que es donde está el USB) y acepta el permiso de MIDI. Web MIDI solo se probó por `localhost`, no abriendo el archivo directamente.

**Sonido:** abre tu VST en Ableton o Analog Lab con la entrada `Minilab3 MIDI`, como siempre; la página no reenvía nada. El servicio MIDI de Windows (`midisrv`) deja compartir el puerto: dos procesos de Chrome lo tuvieron abierto a la vez. No se ha probado junto a Ableton; si no se puede, la página avisa de que no pudo abrir el puerto.

| Control | Qué hace |
|---|---|
| Mano | Derecha es el primer pentagrama e izquierda el segundo; se dibuja solo el de esa mano |
| Ver | Sistema actual (por defecto) o toda la partitura, que no se desplaza sola. Cambiar de vista no pierde el paso |
| Compases | Limita el fragmento; al terminar da el total y espera a que pulses Reiniciar |
| Ignorar octava | Activado por defecto: el MiniLab tiene 25 teclas y las partituras no caben, así que solo compara el nombre de la nota. Desactívalo para exigir la altura exacta con los botones de octava |
| Saltar | Pasa al siguiente paso sin tocarlo, por si una nota no se puede tocar o está mal en la partitura |

**Qué exige:** las notas que empiezan en cada paso. Las notas ligadas, los adornos y los silencios no se piden. Las notas de un acorde pueden llegar en cualquier orden y sin límite de tiempo. Los pads no cuentan.

**Medido:** en las 4 partituras de `svg_to_xml/` se comparó paso a paso, con ambas manos y con cada una, lo que exige la página con una lectura independiente del XML: 3 coinciden del todo; en Clair de Lune sobra un acorde de 2 notas (de 278) en el compás 1, porque OSMD no empareja una ligadura entre dos voces y lo pide otra vez. Esas 4 partituras son MusicXML generados, no revisados.

**Límites:** usa el MusicXML revisado, porque la página exige lo que ponga el archivo. Solo evalúa los dos primeros pentagramas, así que está pensada para piano. Partituras dibujadas con [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) 2.2.1, copiado en [vendor/](vendor/) para funcionar sin internet.

**Después:** medir ritmo contra un metrónomo. Es la parte difícil, porque hay que decidir cuánta desviación se tolera.

## Página: `web.py`

```bash
.venv/bin/python web.py
```

Abre `http://localhost:8766` en el Chrome de Windows. La pestaña **Convertir** ejecuta `svg2pdf.py`, `svg2musicxml.py` o `partitura.py` y muestra su salida mientras corren. Los SVG elegidos se copian a una carpeta temporal `.web_*` de `omr_partituras`, porque Chrome es de Windows, y se borra al terminar. Sin `web.py`, Convertir no funciona.

| Pestaña | Qué hace |
|---|---|
| Home | Presenta el proyecto, sus pasos y el aviso de cuánto acierta el MusicXML |
| Convertir | `SVG → PDF` y `SVG → MusicXML` piden las hojas y un nombre; `Enlace → Todo` pide el enlace. El compás es opcional en los dos últimos, y sin él se supone 4/4 |
| Práctica | La página de [práctica](#práctica-practicahtml), en su propio archivo: al cambiar de pestaña se pierde la partitura cargada |

- **Un trabajo a la vez:** otro responde 409. No hay botón para cancelarlo, y cerrar la pestaña no lo detiene.
- **Sobrescribe** el PDF y el MusicXML generados con ese nombre, igual que los scripts. Rechaza nombres que acaben en `_revisado`.
- **Solo local:** escucha en `127.0.0.1`, rechaza otros `Host` y `Origin`, y solo sirve las páginas y `vendor/`. Sin esto, cualquier web abierta podría lanzar capturas.
- **Salida:** los archivos quedan en `svg_to_pdf/` y `svg_to_xml/`; la página no los descarga.

**Medido:** PDF y MusicXML reales de Clair de Lune por el servidor, y el formulario en Chrome con scripts falsos ([pruebas.py](pruebas.py)). Una vez, a mano, la pipeline completa contra una página local con ese SVG: PDF y MusicXML de 345 notas. **Solo mirado:** capturas de las tres pestañas, Práctica sin partitura. **Sin probar:** un enlace real de MuseScore.

Letra: [Michroma](https://fonts.google.com/specimen/Michroma) y [VT323](https://fonts.google.com/specimen/VT323), licencia OFL, copiadas en [vendor/](vendor/). `PARTITURA` es un nombre provisional; colores y letra se inspiran en el Yamaha DX7, sin usar su marca.

## Pruebas

Todas están en [pruebas.py](pruebas.py). Cada una corre por separado y al final dice cuántas pasaron:

```bash
.venv/bin/python pruebas.py
```
```text
ok       test_pdf_rechaza_0_bytes
ok       test_xml_clair_de_lune_web
...
49 de 49 pruebas pasaron (0 fallaron, 0 saltadas)
```

| Script | Pruebas | Qué cubren |
|---|---|---|
| `svg2pdf.py` | 9 | SVG vacío, cortado o que no es SVG; orden de páginas; un PDF real generado con Chrome |
| `svg2musicxml.py` | 13 | Lectura de contornos, matrices y armaduras; SVG vacío o ajeno; Clair de Lune, Él siempre reina, Night Dreamer y tres obras web nota por nota |
| `svg_scrape.py` | 4 | SVG creados por JS, anidados, repetidos, efímeros, en contenedores con desplazamiento, recibidos por la red y nombrado `<título>_NN` |
| `partitura.py` | 0 | Sin pruebas propias |
| `web.py` e `index.html` | 8 | Rutas servidas, orígenes, validación, comando y orden de hojas, un trabajo a la vez, PDF y MusicXML reales, y el formulario en Chrome con scripts falsos |
| `practica.html` | 12 | Con un teclado falso en Chrome: elección de puerto, pasos exigidos, manos, vistas, colores, compases, octava, aciertos y fallos, `.mxl` y archivos que no son MusicXML |

- **Si una falla:** las demás siguen corriendo y el script termina con código 1.
- **Si falta algo:** una prueba que necesita un archivo de `D:` o un programa de Windows sale como «saltada» y no cuenta como pasada.
- **Ventana de Chrome:** las pruebas de `svg_scrape` abren una durante unos 13 segundos. Lanzan Chrome por depuración remota con un perfil temporal (`SVG_SCRAPE_PERFIL`) para no tocar el real.
- **Sin pruebas propias:** `comparar_musicxml.py` solo se usa dentro de las de partituras, y `svg_html.py` no tiene ninguna.
- **Su alcance:** las dos partituras completas sirvieron para afinar el script, así que su 100 % no demuestra que generalice. Las cifras reales están en [los resultados del flujo 2](#2-script-svg2musicxmlpy).

## Próximos pasos

1. Imprimir una partitura en papel.
2. Construir la comparación contra el SVG original y comprobar que detecta errores introducidos a propósito.
3. Definir las convenciones con partituras reales, empezando por título, compás, tempo y dinámicas.
4. Repetir la medición del script con partituras de MuseScore sin OMR y no vistas; investigar los silencios y el error de compás arrastrado.
5. Conseguir una partitura completa de varias páginas en formato web y medirla.
6. Revisar una página en MuseScore y medir cuánto se tarda.
7. Practicar con el MiniLab 3 y un MusicXML revisado, y comparar con [midipiano.app](https://alternativeto.net/software/midipiano-app/about/) y [PianoML](https://hunted.space/dashboard/pianoml), que no se llegaron a probar.
8. Quitar las peticiones directas de `svg_scrape.py` (ver sus riesgos) y probar los reintentos.

## Otros archivos

| Archivo | Para qué |
|---|---|
| [pruebas.py](pruebas.py) | Todas las pruebas. Cada una corre por separado y al final dice cuántas pasaron |
| [svg_scrape.py](svg_scrape.py) | Descarga los SVG de una página con tu Chrome. Ver la sección «Descarga de SVG» |
| [partitura.py](partitura.py) | De un enlace de MuseScore al PDF y al MusicXML. Ver «Todo en un paso» |
| [web.py](web.py), [index.html](index.html), [estilos.css](estilos.css) | La página. Ver «Página» |
| [svg_html.py](svg_html.py) | Extrae los `<svg>` de un HTML y los pasa a PNG |

## Todo en un paso: `partitura.py`

```bash
python partitura.py https://musescore.com/usuario/scores/123 [--nombre NOMBRE] [--compas 9/8]
```

Captura las hojas con `svg_scrape.py` (abre Chrome), las copia a `svg_partituras/<nombre>/`, y genera `svg_to_pdf/<nombre>.pdf` y `svg_to_xml/<nombre>.musicxml`. `<nombre>` es el título de la obra salvo que lo des con `--nombre`. Si la captura sale con código 2 o 3 (bloqueo u hojas incompletas) no genera nada y deja lo bajado en una carpeta `.captura_*` de `omr_partituras`. Si el PDF falla, igual intenta el MusicXML, y al revés. El MusicXML es el generado sin revisar: el revisado sigue siendo otro archivo.

Probado una vez, con `classicman/scores/55352` (4 hojas, `--compas 4/4`): generó el PDF y el MusicXML. El MusicXML tiene 67 de 69 compases que no suman, así que para esa obra no es utilizable sin una revisión larga. Sin `--compas` supone 4/4. Con otro enlace o con fallos de captura no se ha probado.

## Descarga de SVG: `svg_scrape.py`

### Uso

Desde WSL, con el Python de Windows y desde una carpeta de Windows (`D:`):

```
uvx.exe --python 3.12 --with playwright python svg_scrape.py URL [carpeta_salida]
```

Sin `carpeta_salida` guarda en `D:\Nahum\omr_partituras\svg_partituras\<título>\`, una carpeta por obra (con carpeta explícita se usa tal cual). En musescore.com solo guarda las hojas, como `<título>_NN.svg` (título en minúsculas con `_`, número de hoja con dos dígitos). En otras páginas guarda los `<svg>` del DOM (`svg_N`) y los de la red (`red_N`). Si el archivo ya existe, avisa y lo sobrescribe.

### Flujo

1. **Chrome:** si nada escucha en el puerto 9222, abre tu Chrome instalado como proceso normal con `--remote-debugging-port` y el perfil `~/.svg_scrape_chrome` (variable `SVG_SCRAPE_PERFIL` para cambiarlo). Si ya hay uno escuchando, lo reutiliza. Se conecta con `connect_over_cdp`. Al terminar cierra solo el que abrió él.
2. **Página:** abre una pestaña, navega y, si el título es «Un momento…» (Cloudflare), espera hasta 2 minutos a que el desafío se resuelva. No recarga ni reintenta la navegación.
3. **Scroll:** baja por todos los contenedores desplazables y lee los `<svg>` del DOM en cada paso. El visor de MuseScore solo carga la hoja 1 así.
4. **Hojas restantes:** toma la URL de `score_N.svg` capturada y pide las demás con `contexto.request.get`, una cada segundo, hasta el total que dice la ficha («Páginas | N»). Si la ficha no lo dice, hasta el primer 404.
5. **Guardado:** lo hace al final, con el título de `og:title`, `<h1>` o `<title>`.

### Qué hace cuando algo falla

| Situación | Comportamiento | Salida |
|---|---|---|
| Faltan 1 a 3 hojas | Guarda lo que hay y avisa cuáles faltan | 0 |
| Faltan más de 3 | Reintenta solo las que faltan, 2 veces, con esperas de 30 s y 120 s | 3 si siguen faltando |
| Error 5xx de una hoja | Reintenta esa hoja 3 veces (5, 15 y 45 s); si no, queda como faltante | |
| 404 de una hoja | Se toma como el final de la partitura | |
| 403/429 de una hoja | Para en seco, sin reintentar; guarda lo ya descargado | 2 |
| Página sigue bloqueada tras 2 minutos | No reintenta | 2 |
| Sin ningún SVG | Falla con el estado HTTP y el título | 1 |

### Consideraciones y riesgos

- **Huella y bloqueo.** Cloudflare califica la IP, la huella del navegador y las cookies de la sesión; no conoce tu cuenta de MuseScore. Un bloqueo suele liberarse con horas. Tras un rechazo, espera varias horas. Rotar la IP (reiniciar el router) solo sirve si tu proveedor te da una dinámica, no arregla lo ligado al navegador y es esquivar el bloqueo: no está en el script.
- **Las peticiones del paso 4 son directas.** Comparten las cookies de Chrome, pero salen por el cliente HTTP de Playwright, no por la red de Chrome. Su huella TLS, sus cabeceras (`Sec-Fetch-*`, `Referer`) y el patrón sin interacción pueden delatarlas. Es el punto más débil frente a Cloudflare y no está medido. Mejoras posibles, sin hacer:
  1. Que el visor cargue todas las hojas con el scroll correcto y capturar solo eso, sin peticiones propias. El scroll actual no lo consigue.
  2. Pedir las hojas con `fetch()` dentro de la página (`pagina.evaluate`), que usa la red real de Chrome. Falta ver si el sitio lo permite.
- **Cuenta:** no inicies sesión en MuseScore en el perfil `~/.svg_scrape_chrome`. Las hojas se descargan sin cuenta, y así un problema nunca toca la cuenta. Ese perfil conserva la cookie de Cloudflare: no lo borres sin motivo.
- **Ritmo:** no lances el script muchas veces seguidas sobre la misma partitura.
- **Títulos repetidos:** dos obras con el mismo título se sobrescriben (con aviso). El título viene de la página; si cambia su estructura, sale `hoja_NN.svg`.
- **Total de hojas:** se lee de una fila de la ficha en español («Páginas») o inglés («Pages»). Otro idioma o cambio de diseño lo deja en «desconocido» y se pide hasta el primer 404.
- **Chrome 136+** ignora la depuración remota sobre el perfil por defecto de uso diario; por eso hay un perfil propio. Esto está tomado de la documentación de Chrome, sin comprobarlo aquí.
- **Derechos:** ver la sección final.

### Qué se probó

- **Medido:** 2 partituras de musescore.com completas (4 de 4 y 23 de 23 hojas según la ficha) con Chrome por CDP. Las pruebas de `svg_scrape` en `pruebas.py` pasan (SVG por JS, anidados, efímeros, de la red, y el nombrado `<título>_NN`).
- **No probado:** los reintentos, el rechazo 403/429, la salida 3 y la ficha en inglés; solo revisados leyendo el código. Tampoco se miró el contenido de los SVG descargados, solo su tamaño. Antes de conectar por CDP, con el Chrome lanzado por Playwright, 2 de 3 intentos dieron 403.

## Derechos

Las partituras y sus resultados se quedan fuera del repo. Antes de descargar una partitura de un sitio hay que revisar sus derechos y los términos del sitio. El SVG de una obra de dominio público puede ser una edición con sus propias condiciones. El PDF de Night Dreamer lleva una marca de agua que prohíbe compartirlo y muestra datos de la cuenta: no debe subirse ni publicarse.
