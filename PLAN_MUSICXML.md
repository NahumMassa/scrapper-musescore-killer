# Plan: recuperar más información del SVG en el MusicXML

Sin construir. Fecha del análisis: 1 de noviembre de 2026.

**Objetivo:** que `svg2musicxml.py` conserve prolongaciones, cambios de compás, dinámicas, pedal, tempo y texto, sin OCR de imagen ni OMR.

**Idea central:** el SVG ya dice qué es cada símbolo con su clase (`Dynamic`, `PedalSegment`, `Arpeggio`…). Lo que falta es saber qué signo concreto es cada glifo, y eso se puede obtener comparando su contorno.

## Qué se comparó

Partitura: Merry-Go-Round Of Life, 7 páginas, regenerada con `--compas 3/4` (237 compases, 2418 notas).

- **Medido:** los SVG de las 7 páginas y el MusicXML generado.
- **Solo mirado:** las páginas 1 y 4 del original y la primera imagen del MusicXML.
- **Sin referencia:** no hay una versión correcta de esta partitura, así que las causas de abajo son diagnósticos, no resultados comprobados.

## Problemas encontrados

| Problema | Lo que se ve en los datos | Causa |
|---|---|---|
| Ligaduras mal | 0 `<tie>` en el XML. De 103 `SlurSegment`, 85 unen notas de igual altura y 18 tocan el borde del sistema | Este SVG no trae `TieSegment`: las prolongaciones llegan como `SlurSegment` y salen como ligaduras de expresión. Al reproducir, las notas se repiten |
| Cambios de compás | `TimeSig` en los compases 136 y 152, entre otros; el XML tiene un solo compás, 3/4 | El script no lee los dígitos y usa un largo fijo |
| Silencio de compás completo | Sale como negra con duración de 3 tiempos | Error de tipo al escribirlo |
| Avisos falsos | 7 de los 14 compases «malos» revisados suman bien (6, 7, 29, 65, 82, 119, 134) | Probablemente los mismos silencios de compás completo; sin confirmar |
| Grupos irregulares | Compás 23: el original tiene un 5 y sale un 3 | Cuenta notas, no lee el dígito |
| Silencios cortos | Compás 4: una semicorchea sale como negra | Atajo ya anotado en el código |
| Información perdida | 310 trazos de pedal, 50 de arpegio, 86 articulaciones, 4 de regulador, trémolo, dinámicas, tempo y texto | El script no los lee |

La numeración de compases sí coincide con la impresa: 7, 15, 23, 31 y 118, 124, 129, 134, 141, 147.

## Reconocer glifos por su contorno

MuseScore dibuja cada signo con la misma fuente, así que el mismo signo da el mismo contorno, salvo redondeo. La prueba comparó solo los puntos sobre la curva, relativos al inicio del contorno y divididos por el espacio entre líneas, con tolerancia de 0,05 espacios. Los tipos de comando (`c`/`s`, `l`/`h`) no se comparan porque cambian entre contornos iguales.

| Clase | Contornos | Formas distintas |
|---|---|---|
| `TimeSig` | 72 | 7 |
| `Rest` | 73 | 5 |
| `Dynamic` | 58 | 6 |
| `Articulation` | 93 | 4 |
| `Tuplet` | 35 | 6 |

Un glifo puede tener varios contornos (huecos, o varias partes), así que el número de formas no es el de signos.

**Entre partituras:**

- Moonlight comparte fuente musical con Merry: claves 8 de 8, silencios 3 de 3, dinámicas 2 de 2.
- Clair de Lune y Midnight usan otra: 0 coincidencias en todas las clases medidas.
- Hace falta un catálogo por fuente musical, pero cada uno es pequeño.
- El texto no se comparte ni con Moonlight (0 de 97 en `Text`), por eso va en una fase aparte.

## Fases

### Fase 0: poder medir

Sin esto, cada arreglo se juzga a ojo.

1. Ampliar `comparar_musicxml.py` para contar prolongaciones, dinámicas, pedal, compases, arpegios y articulaciones.
2. Transcribir a mano la página 1 de Merry como referencia de esos signos.
3. Reservar una partitura no vista para la medida final, como pide `CLAUDE.md`.

### Fase 1: arreglos sin catálogo

Es lo que más mejora con menos trabajo.

1. **Prolongaciones:** separarlas de la expresión por geometría y escribir `<tie>`/`<tied>`. Clair de Lune y Él siempre reina deben seguir dando 100 %.
2. **Silencio de compás completo:** escribir `measure="yes"` y quitar los avisos falsos.
3. **Arpegios:** `<arpeggiate>` en el acorde más cercano.
4. **Reguladores:** `<wedge>`. La forma ya dice cuál es: las dos líneas salen del mismo punto en un crescendo.
5. **Pedal:** `<pedal>` de inicio y fin, incluido el que sigue en el sistema siguiente. Falta confirmar cómo distinguir el «(Ped.)» de continuación.

### Fase 2: catálogo de glifos musicales

Un archivo `glifos.json` en el que cada forma se nombra una sola vez por fuente.

1. **Compás:** dígitos de `TimeSig`, con largo variable por compás. Hay que filtrar los de cortesía a final de sistema (por ejemplo 52/53 y 104/105). Es el cambio más invasivo, porque `convertir` y `xml` usan un solo largo.
2. **Grupos irregulares:** dígitos de `Tuplet`. Arreglan el compás 23.
3. **Silencios:** tipo por forma. Arreglan el compás 4 y el problema conocido de los silencios.
4. **Dinámicas, staccato, otras articulaciones y trémolo.**
5. **Forma desconocida:** no se adivina. Avisa y se escribe sin ese signo.

### Fase 3: texto

Título, compositor, tempo («♩ = 100»), «accel.», «rit.», «cantabile».

- El número de tempo tiene pocos dígitos y podría ir al catálogo. Es lo que más importa, porque afecta a la reproducción.
- `Tempo` y `StaffText` se escriben como `<words>` anclados a su compás; la clase ya dice su papel.
- Cómo leer el texto libre es la decisión abierta de abajo.

### Fase 4: cierre

1. Medir con la partitura no vista y decir qué se midió y qué solo se miró.
2. Volver a correr Moonlight, que tenía 67 de 69 compases que no sumaban.
3. Actualizar `README.md` y la trampa de `CLAUDE.md` que dice que el compás no sale del SVG.

## Decisión abierta

Cómo leer el texto libre de la Fase 3:

| Opción | A favor | En contra |
|---|---|---|
| **Catálogo por fuente** (recomendada para empezar) | Sin dependencias nuevas y exacto | Cada fuente de texto nueva pide nombrar sus letras. Merry tiene entre 74 y 89 formas por clase, contando huecos |
| **Tesseract sobre el recorte de cada elemento** | Funciona con cualquier fuente | Añade una dependencia y puede equivocarse, así que habría que revisarlo. No está instalado |

Las Fases 0 a 2 no dependen de esta decisión.

## Riesgos

- **Prolongaciones:** el 85 de 103 usa una regla sin validar, que no clasificó ninguna como expresión. Puede estar sobreajustada; hay que comprobarla contra la referencia manual.
- **Otras versiones de MuseScore:** los catálogos solo sirven para fuentes ya vistas. El aviso de forma desconocida es la defensa.
- **Fuera de este plan:** repeticiones y casillas. Sigue siendo un hueco para reproducir; se pueden añadir después.
