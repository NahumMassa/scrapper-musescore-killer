# CLAUDE.md

Convierte partituras en SVG de MuseScore en un PDF para imprimir y un MusicXML para manipular, con una app de práctica MIDI como propuesta. Alcance, estado, flujos y resultados: [README.md](README.md). Responde en español.

No uses OMR (Audiveris, homr) ni amplíes la entrada a PDF o escaneos: esa fase se descartó.

## Entorno

- Se trabaja desde WSL Debian. Los `.exe` reciben rutas de Windows (`wslpath -w` las convierte).
- Carpetas en `/mnt/d/Nahum/omr_partituras`, ninguna entra al repo:
  - `svg_partituras/`: SVG de entrada. Su contenido cambia; míralo antes de nombrar una salida.
  - `svg_to_pdf/`: los PDF.
  - `svg_to_xml/`: los MusicXML.
  - `resultados/`: pruebas y referencias, no entregables.
- Python: `.venv/bin/python` (3.14). `svg2pdf.py`, `svg2musicxml.py`, `comparar_musicxml.py` y `partitura.py` solo usan la biblioteca estándar.
- Chrome: `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`. Solo se ha probado con archivos en `D:`.
- MuseScore: `/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe`. Para ver un resultado: `-r 110 -o salida.png entrada.musicxml`. Sin `-r`, las imágenes salen demasiado grandes.
- Captura: `partitura.py URL` hace captura → PDF → MusicXML (ver README). `svg_scrape.py` corre con el Python de Windows (`uvx.exe`) y conecta a Chrome por depuración remota (puerto 9222, perfil `~/.svg_scrape_chrome`). No inicies sesión en ese perfil ni repitas capturas seguidas; ante 403/429 se para y se espera horas.
- Pruebas: `.venv/bin/python pruebas.py`. Las saltadas no cuentan como pasadas. Las de `svg_scrape` abren una ventana de Chrome y usan un perfil temporal (`SVG_SCRAPE_PERFIL`).

## Reglas del flujo 2

- El flujo es lineal: convenciones → script → comparación → revisión humana en MuseScore. La revisión no vuelve a ejecutar el script.
- El MusicXML generado se conserva intacto. El revisado es otro archivo y regenerar nunca lo sobrescribe.
- Las convenciones solo guardan lo que no se puede leer del SVG. Si un mismo error de lectura se repite en varias partituras, arregla el script.
- La app de práctica usa solo el MusicXML revisado. Antes de construirla hay que probar las apps existentes.

## Trampas conocidas

- Hay dos formatos de SVG. **Web:** `<path>` con muchos símbolos juntos y coordenadas relativas; los huecos usan `m`. **Escritorio:** un elemento por símbolo, `<polyline>` en líneas y plicas, huecos con `M`.
- Algunos SVG traen coordenadas locales más `transform="matrix(...)"`.
- El texto viene como contornos: título, tempo, dinámicas, acordes y dígitos no se pueden leer sin OCR. Por eso el compás no sale del SVG.
- Un dosillo o tresillo puede repetirse en otra voz sin número impreso.
- Una ligadura de expresión alta puede quedar más cerca de otro sistema; asígnala por su nota más cercana.
- Una ligadura de prolongación puede saltar sobre otro acorde, como en el compás 1 de Clair de Lune.
- La barra de inicio de repetición tras clave y armadura crea un compás falso si no se filtra. Los puntos de repetición también son `BarLine`.
- Las unidades de `divisions` en MusicXML son por negra, no por corchea. MuseScore lo disimula porque usa `<type>`, así que el error no se ve en la imagen.
- `transform`, formato y tamaño cambian entre exportaciones: usa tolerancias relativas al espacio entre líneas, nunca píxeles fijos.
- Chrome no falla con un SVG vacío o cortado: termina bien y dibuja una imagen rota. Genera los PDF con `svg2pdf.py`, que lo comprueba antes.
- No cambies `USERPROFILE` para aislar Chrome: deja de arrancar. Windows tarda en alcanzar un puerto recién abierto en WSL.
- La carpeta temporal se vacía entre sesiones: guarda fuera de ella lo que deba conservarse.

## Cómo evaluar

- Compara contra una respuesta correcta, no a simple vista. Referencias: `resultados/svg/Clair_de_Lune_p1.musicxml` y `resultados/svg/prueba_ciega/ref.musicxml`, con `comparar_musicxml.py`.
- Las dos referencias sirvieron para afinar el script: su 100 % no demuestra que generalice. Mide también con partituras que no hayas visto antes de escribir el arreglo; las de `resultados/svg/prueba_ciega/otras/` ya se usaron una vez, así que necesitarás otras para una medida limpia.
- Un compás que suma bien puede tener notas equivocadas.
- Una imagen idéntica no garantiza un dato correcto: el mismo error puede leerse y escribirse igual.
- Di qué se midió y qué solo se miró.
- Los resultados de los motores OMR solo sirven para probar el script; no son la partitura correcta.
