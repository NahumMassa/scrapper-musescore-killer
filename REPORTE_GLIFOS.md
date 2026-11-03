# Reporte: reconocer glifos de MuseScore por su contorno

Fecha: 2 de noviembre de 2026. Corresponde a la Fase 2 de [PLAN_MUSICXML.md](PLAN_MUSICXML.md).

## Resumen

- **Funciona:** un catálogo de glifos nombrados reconoce signos en partituras que no se usaron para crearlo. El catálogo hecho con Merry reconoce el 92 % de los contornos musicales de Moonlight.
- **Hace falta un catálogo por fuente:** las partituras web probadas no usan la fuente por defecto de MuseScore 4.
- **Todavía no mejora el MusicXML:** `svg2musicxml.py` no lee ningún catálogo.

## Qué se hizo

| Archivo | Contenido |
|---|---|
| [catalogo.py](catalogo.py) | Escribe un MusicXML por símbolo, lo exporta con MuseScore y guarda el contorno con el nombre que se escribió |
| [glifos.json](glifos.json) | 97 glifos de la fuente por defecto de MuseScore 4.7.5, generados por el script |
| [glifos_merry.json](glifos_merry.json) | 46 glifos de la fuente de Merry, nombrados a mano |
| [pruebas.py](pruebas.py) | 2 pruebas nuevas: la comparación de contornos y la coherencia de `glifos.json`. Pasan 26 de 26 |

Ningún cambio tiene commit todavía. Las hojas usadas para nombrar están fuera del repo, en `resultados/glifos_merry/`.

## Cómo se comparan los contornos

Cada contorno se guarda como ancho, alto y puntos sobre la curva, en espacios entre líneas y relativos a su caja. Dos contornos son iguales si coinciden con una tolerancia de 0,05 espacios.

La primera versión comparaba los puntos en orden desde el inicio del glifo y separaba los glifos por `M`. Dio 0 coincidencias en todas las partituras web, y se atribuyó por error a la fuente. Los SVG web escriben el mismo hueco unas veces con `m` y otras con `M`, y pueden empezar el contorno en otro punto. Con la versión actual nada de eso influye.

## Resultados

### Fuente de cada partitura

Comparación contra los catálogos de 8 fuentes de MuseScore 4.7.5, con todas las páginas.

| Partitura | Fuente | Evidencia |
|---|---|---|
| Merry | Emmentaler de otra versión | Notas 2679/2679 y articulaciones 91/93, pero armaduras 0/296 y alteraciones 0/572 |
| Moonlight | Emmentaler de otra versión | Notas 1330/1407, pero armaduras 0/320 y alteraciones 0/234 |
| Midnight | MuseJazz | Claves 115/115, silencios 34/34, notas 468/500, pero armaduras 23/46 y compás 2/4 |

Que la otra versión sea la de MuseScore 3 es una hipótesis sin comprobar.

### Catálogo de Merry

| Partitura | Contornos reconocidos | Lectura |
|---|---|---|
| Merry | 4494/4498 | Es donde se nombró, no demuestra nada. Los 4 restantes son cuñas de corchetes de grupo, sin nombre a propósito |
| **Moonlight, sin tempo** | **2038/2205 (92 %)** | La medida útil |
| Moonlight, tempo | 0/115 | Trae texto y cifras con otra fuente o tamaño |
| Midnight | 0/892 | Otra fuente; es el resultado esperado |

Contornos de Moonlight sin reconocer, sin contar el tempo:

| Contornos | Clase | Qué parece (solo por sus medidas) |
|---|---|---|
| 154 | `Note` | Una cabeza de nota que Merry no tiene, quizá la redonda |
| 4 | `TimeSig` | Un compás sin dígitos, quizá de compasillo |
| 4 | `Accidental` | Doble sostenido |
| 4 | `Tuplet` | Un dígito de grupo con otra forma |
| 1 | `Articulation` | Sin identificar |

### Catálogo por defecto

Medido sobre la primera página de dos partituras exportadas aquí desde su MusicXML, con el mismo MuseScore.

| Partitura | Notas | Claves | Armaduras | Compás | Silencios |
|---|---|---|---|---|---|
| Clair de Lune p. 1 | 403/403 | 58/58 | 100/100 | 10/10 | 18/18 |
| `ref.musicxml` p. 1 | 88/92 | 40/40 | 60/60 | 5/5 | 38/38 |

Esto solo muestra que el catálogo y la comparación son coherentes. Son referencias ya usadas en el proyecto y con la misma fuente, así que no miden generalización. Las 4 notas sin reconocer no se investigaron.

## Qué se midió y qué solo se miró

- **Medido:** todos los conteos de las tablas, y que el recuento de letras de dinámicas y de cifras de tempo cuadra con lo que se lee en las hojas de Merry.
- **Solo mirado:** el resto de nombres de `glifos_merry.json`, incluida la dirección de las banderas. Merry no tiene referencia correcta.
- **Sin medir:** el efecto en el MusicXML, porque aún no se usa el catálogo.

## Limitaciones

- **Medida no del todo limpia:** Moonlight no se usó para nombrar, pero ya se había examinado en el plan. Falta una partitura realmente nueva.
- **Cobertura de `glifos_merry.json`:** solo incluye lo que aparece en Merry, y `pruebas.py` no lo comprueba.
- **Forma igual, significado distinto:** los silencios de redonda y de blanca son el mismo rectángulo. Hay que distinguirlos por su altura respecto a la línea.
- **Otras fuentes con `--fuente`:** con Emmentaler da 6 fallos, porque sus dinámicas se parten en otro número de piezas. No se han revisado las demás con la comparación actual.
- **Sin catálogo:** banderas en `glifos.json`, texto libre, y signos sin forma fija como arpegios y reguladores.
- **`segno` y `coda`:** en `glifos.json` quedaron bajo `StaffText`; en una partitura real pueden venir con otra clase.
- **MuseScore 3:** se descargó la versión oficial 3.6.2, pero el sistema de permisos bloqueó ejecutarla. Sus fuentes van compiladas en el binario, así que no se pudieron leer por separado.

## Siguientes pasos

1. **Conectar el catálogo a `svg2musicxml.py`.** Empezar por tres errores concretos del plan: compás variable, dígitos de grupo (Merry, compás 23) y tipo de silencio (Merry, compás 4). Una forma desconocida avisa y no se adivina.
2. **Elegir el catálogo de cada partitura.** Usar el que reconozca más contornos y avisar si ninguno alcanza un mínimo por definir.
3. **Medir el resultado.** Ampliar `comparar_musicxml.py` y hacer la referencia manual de la página 1 de Merry (Fase 0 del plan), y evaluar con una partitura nueva.
4. **Ampliar los catálogos.**
    - Generar el de MuseJazz para Midnight y corregir los fallos de `--fuente`.
    - Añadir los signos de Moonlight que Merry no tiene, nombrados a mano.
    - Probar MuseScore 3 si se autoriza ejecutarlo. Si confirma la hipótesis, el catálogo sale completo sin nombrar nada.
5. **Actualizar la documentación.** `README.md`, y la trampa de `CLAUDE.md` que dice que el compás no se puede leer del SVG.

El texto libre sigue siendo la decisión abierta de la Fase 3 del plan. Los dígitos y letras de tempo y dinámicas ya se reconocen por contorno en Merry, aunque el tempo de Moonlight muestra que no basta con un solo catálogo.

## Cómo repetirlo

```bash
# Catálogo de la fuente por defecto (necesita MuseScore 4 de Windows)
.venv/bin/python catalogo.py -o glifos.json

# Catálogo de otra fuente
.venv/bin/python catalogo.py -o glifos_musejazz.json --fuente MuseJazz

# Cuántos contornos de una página reconoce un catálogo
.venv/bin/python catalogo.py --probar pagina.svg -o glifos_merry.json

# Pruebas
.venv/bin/python pruebas.py
```

`glifos_merry.json` no se regenera con un comando: los nombres se asignaron a mano y el propio archivo es la fuente de esos datos. Los scripts de la comparación entre fuentes y del nombrado fueron temporales y no están en el repo.
