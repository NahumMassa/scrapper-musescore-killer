# Reporte: reconocer glifos de MuseScore por su contorno

Fecha: 2 de noviembre de 2026. Corresponde a la Fase 2 de [PLAN_MUSICXML.md](PLAN_MUSICXML.md).

## Resumen

- **Funciona para lo que el catálogo trae:** el catálogo de Merry reconoce casi todo lo nuevo de Merry y, en Moonlight (que no se usó para nombrar), el 83 % de los contornos de las clases que el script aún no lee, sin contar el tempo. Con el tempo baja al 28 %.
- **Lo que más interesa falla en Moonlight:** compás 0/2 y dígitos de grupo 0/4. Son justo los dos errores que el plan quiere arreglar primero.
- **Hace falta un catálogo por fuente:** Midnight da 0/76 con el de Merry.
- **Todavía no mejora el MusicXML:** `svg2musicxml.py` no lee ningún catálogo.
- **«Reconocido» no es «bien nombrado»:** la medida solo comprueba que el contorno se parece a uno de su clase.

## Qué hay

| Archivo | Contenido |
|---|---|
| [catalogo.py](catalogo.py) | Genera catálogos con MuseScore y mide cuánto reconoce uno sobre SVG reales |
| [glifos.json](glifos.json) | 97 glifos de la fuente por defecto de MuseScore 4.7.5, generados por el script |
| [glifos_merry.json](glifos_merry.json) | 46 glifos de la fuente de Merry, nombrados a mano viendo una hoja con cada contorno. El propio archivo es la fuente de esos nombres |
| [pruebas.py](pruebas.py) | 3 pruebas del catálogo: comparación de contornos, comparación en los dos sentidos y nombres sin repetir en ambos catálogos |

## Cómo se comparan los contornos

Cada contorno se guarda como ancho, alto y puntos sobre la curva, en espacios entre líneas y relativos a su caja. Dos contornos son iguales si coinciden con tolerancia de 0,05 espacios, en los dos sentidos.

No dependen del punto de inicio, del sentido, ni de si el hueco se escribió con `m` o con `M`. Esa dependencia dio 0 coincidencias en la primera versión, y se atribuyó por error a la fuente.

Límites conocidos de la comparación:

- **Variantes del mismo glifo:** en Merry, el cuerpo de la clave de sol sale en 3 variantes que se separan hasta 0,118 espacios (la tolerancia es 0,05), y el «1» del tempo en 2. No se sabe la causa. Un glifo con una variante nueva no se reconocería.
- **Huecos:** un hueco pequeño puede coincidir con el de otra fuente. Por eso la medida cuenta solo contornos exteriores.
- **Glifos en varias piezas:** las claves de fa y de do llevan puntos separados del cuerpo, así que se reconocen contorno a contorno, no como glifo completo.

## Resultados

Medido con `catalogo.py --medir`. Se cuentan los contornos exteriores de cada clase del catálogo. `Note`, `NoteDot`, `KeySig`, `Clef` y `Accidental` se muestran pero se excluyen del total, porque `svg2musicxml.py` ya las lee sin catálogo y contarlas lo inflaría.

### Catálogo de Merry (`glifos_merry.json`)

| Partitura | Páginas | Clases nuevas: contornos | Clases nuevas: formas distintas |
|---|---|---|---|
| Merry | 7 | 389/393 | 34/38 |
| **Moonlight** | 4 | **35/124 (28 %)** | 6/40 |
| Moonlight, sin tempo | 4 | 35/42 (83 %) | 6/9 |
| Midnight | 3 | 0/76 | 0/11 |

- **Merry** es donde se nombró: no demuestra nada. Los 4 contornos sin reconocer son cuñas de corchetes de grupo, sin nombre a propósito.
- **Moonlight** no se usó para nombrar, pero ya se había examinado en el plan, así que la medida no es del todo limpia.
- **Moonlight por clase:**

  | Clase | Contornos |
  |---|---|
  | Silencios | 18/18 |
  | Dinámicas | 15/15 |
  | Banderas | 1/1 |
  | Articulaciones | 1/2 |
  | **Compás** | **0/2** |
  | **Grupos** | **0/4** |
  | **Tempo** | **0/82** |

- **Midnight** usa otra fuente: es el resultado esperado.
- **Clases leídas por el script en Moonlight:** notas 1105/1182, alteraciones 115/119, claves 80/80, armaduras 160/160. Las notas que faltan son de otra forma que Merry no tiene, quizá la redonda.

### Qué fuente usa cada partitura

Comparación contra los catálogos de 8 fuentes de MuseScore 4.7.5, en todas las páginas. **Medida con un script temporal que no está en el repo**, contando también los huecos, así que sirve para orientar y no se puede repetir.

| Partitura | Mejor coincidencia | Evidencia |
|---|---|---|
| Merry | Emmentaler, pero no igual | Notas 2679/2679, articulaciones 91/93; armaduras 0/296, alteraciones 0/572, claves 158/279, compás 32/72, silencios 20/73 |
| Moonlight | Emmentaler, pero no igual | Notas 1330/1407; armaduras 0/320, alteraciones 0/234, claves 80/140 |
| Midnight | MuseJazz | Claves 115/115, silencios 34/34, notas 468/500; armaduras 23/46, compás 2/4 |

Que Merry y Moonlight vengan de otra versión de Emmentaler (¿MuseScore 3?) es una hipótesis sin comprobar. Se descargó MuseScore 3.6.2, pero el sistema de permisos bloqueó ejecutarlo.

### Catálogo por defecto (`glifos.json`)

Medido en la página 1 de dos partituras exportadas con el mismo MuseScore: Clair de Lune (notas 403/403, claves 58/58, armaduras 100/100, compás 10/10, silencios 18/18) y `ref.musicxml` (notas 88/92 y el resto al 100 %). Solo muestra que el catálogo es coherente consigo mismo; son referencias ya usadas y no miden generalización. Las 4 notas sin reconocer no se investigaron. Esas cifras son anteriores a los cambios de comparación de este reporte.

## Qué se midió y qué solo se miró

- **Medido:** las tablas de Merry, Moonlight y Midnight con `--medir`; que el catálogo regenerado es idéntico al anterior tras los cambios; que ningún catálogo tiene dos nombres con la misma forma.
- **Solo mirado:** que los nombres de `glifos_merry.json` son correctos (incluida la dirección de las banderas), y el recuento de letras de dinámicas y cifras de tempo contra la hoja de Merry. No hay referencia correcta.
- **Sin medir:** el efecto en el MusicXML, porque aún no se usa el catálogo, y cuántos reconocimientos son coincidencias.

## Limitaciones

- **Cobertura de `glifos_merry.json`:** solo incluye lo que aparece en Merry. Le faltan, entre otros, la redonda, el doble sostenido y el «3» de grupo de Moonlight.
- **Redonda y blanca:** en silencio son el mismo rectángulo. Hay que distinguirlas por su altura respecto a la línea.
- **`--fuente`:** con Emmentaler da 6 fallos (las dinámicas se parten distinto), y desde este cambio no se escribe ningún catálogo si hay fallos. Las otras fuentes no se han revisado con la comparación actual.
- **Sin catálogo:** banderas en `glifos.json`, texto libre, y signos sin forma fija (arpegios, reguladores, pedal).
- **`segno` y `coda`:** en `glifos.json` quedaron bajo `StaffText`; en una partitura real pueden venir con otra clase.
- **Clases sin catálogo en las partituras reales:** además de las líneas, `Text` y `StaffText` (más de 100 contornos por partitura), y en Midnight `Harmony` (403), `TrillSegment` y `RehearsalMark`.

## Siguientes pasos

1. **Completar `glifos_merry.json` con lo de Moonlight:** compás, dígito de grupo, redonda y doble sostenido. Sin eso, el primer arreglo no funcionaría en una partitura no vista.
2. **Entender las variantes** de la clave de sol y del «1» antes de fiarse de la tolerancia.
3. **Conectar el catálogo a `svg2musicxml.py`**, empezando por el compás variable, los dígitos de grupo (Merry, compás 23) y el tipo de silencio (Merry, compás 4). Una forma desconocida avisa y no se adivina.
4. **Elegir el catálogo de cada partitura:** el que más contornos reconozca, avisando si ninguno alcanza un mínimo por definir.
5. **Medir el resultado** contra una referencia: ampliar `comparar_musicxml.py` y transcribir la página 1 de Merry (Fase 0 del plan). Evaluar además con una partitura que no se haya visto.
6. **Más catálogos:** MuseJazz para Midnight, y MuseScore 3 si se autoriza ejecutarlo.
7. **Actualizar la documentación:** `README.md` y la trampa de `CLAUDE.md` que dice que el compás no se puede leer del SVG.

## Cómo repetirlo

```bash
# Generar el catálogo de la fuente por defecto (necesita MuseScore 4 de Windows).
# Si algún símbolo falla, no escribe nada
.venv/bin/python catalogo.py -o glifos.json

# Otra fuente
.venv/bin/python catalogo.py -o glifos_musejazz.json --fuente MuseJazz

# Cuánto reconoce un catálogo; acepta varias páginas
.venv/bin/python catalogo.py --medir pagina1.svg pagina2.svg -c glifos_merry.json
```

`--medir` no genera ni sobrescribe nada. La tabla de fuentes no se puede repetir con estos comandos.
