"""Genera glifos.json: el nombre de cada glifo de MuseScore (fuente por defecto) a partir de partituras de calibración.

Cada símbolo se escribe en su propio MusicXML, MuseScore lo exporta a SVG y el nombre sale de lo que escribí, no de
adivinar. Un glifo es una lista de contornos, cada uno [ancho, alto, puntos] en espacios entre líneas, con los puntos
relativos a su caja: así no importan el punto de inicio, el sentido ni si el hueco se escribió con 'm' o con 'M'.

Uso: python catalogo.py [-o glifos.json] [--probar pagina.svg]   (necesita MuseScore 4 de Windows, ver CLAUDE.md)
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from svg2musicxml import ARGS, NUM, numeros

MUSESCORE = "/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe"
TOL = 0.05  # espacios entre líneas
U = 5040  # divisions por negra: múltiplo de 16 y de 2520, así caben 64avos y grupos hasta el 10
COMPAS = 4 * U


def wpath(p):
    return subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()


# ---------- MusicXML ----------

def nota(pitch="C5", tipo="quarter", dur=U, extra="", antes="", alter=None, acc=None, pre=""):
    p = f"<pitch><step>{pitch[0]}</step>{'' if alter is None else f'<alter>{alter}</alter>'}<octave>{pitch[1]}</octave></pitch>"
    a = f"<accidental>{acc}</accidental>" if acc else ""
    return f"{antes}<note>{p}<duration>{dur}</duration><type>{tipo}</type>{a}{pre}{extra}</note>"


def resto(dur, tipo=None):
    return f"<note><rest/><duration>{dur}</duration>{f'<type>{tipo}</type>' if tipo else ''}</note>"


def relleno(usado):
    """Silencios de tamaño estándar hasta llenar el compás; un silencio de duración rara hace que MuseScore falle."""
    out, falta = "", (COMPAS - usado) // (U // 16)
    for tipo, n in (("whole", 64), ("half", 32), ("quarter", 16), ("eighth", 8), ("16th", 4), ("32nd", 2), ("64th", 1)):
        while falta >= n:
            out += resto(n * U // 16, tipo)
            falta -= n
    return out


def compas(cuerpo, n=1, clef=("G", 2), fifths=0, tiempo=(4, 4), cambia=True):
    """cambia=False: solo la armadura (clef=None tampoco escribe clave)."""
    at = f"<divisions>{U}</divisions>" if n == 1 else ""
    if cambia:
        at += f"<key><fifths>{fifths}</fifths></key>" + (f"<time><beats>{tiempo[0]}</beats><beat-type>{tiempo[1]}</beat-type></time>" if n == 1 else "")
        at += f"<clef><sign>{clef[0]}</sign>{f'<line>{clef[1]}</line>' if clef[1] else ''}</clef>" if clef else ""
    return f'<measure number="{n}"><attributes>{at}</attributes>{cuerpo}</measure>'


def partitura(*medidas):
    return ('<?xml version="1.0"?><score-partwise version="3.1"><part-list><score-part id="P1"><part-name></part-name></score-part>'
            f'</part-list><part id="P1">{"".join(medidas)}</part></score-partwise>')


def una(cuerpo, **kw):
    return partitura(compas(cuerpo, **kw))


def con_nota(**kw):
    """Una negra más silencios hasta llenar el compás."""
    return una(nota(**kw) + relleno(U))


def direccion(x, lugar="above", extra=""):
    return f'<direction placement="{lugar}"><direction-type>{x}</direction-type>{extra}</direction>'


def notac(x):
    return f"<notations>{x}</notations>"


BASE = con_nota()


def grupo(a):
    """a notas de corchea en el tiempo de las que caben en una potencia de 2 (o en 3 si a es 2)."""
    normal = {2: 3, 3: 2, 4: 3, 5: 4, 6: 4, 7: 4, 8: 6, 9: 8}[a]
    dur = U // 2 * normal // a
    out = ""
    for i in range(a):
        t = '<tuplet type="start"/>' if i == 0 else '<tuplet type="stop"/>' if i == a - 1 else ""
        out += nota(tipo="eighth", dur=dur, pre=f"<time-modification><actual-notes>{a}</actual-notes><normal-notes>{normal}</normal-notes></time-modification>",
                    extra=notac(t) if t else "")
    return una(out + relleno(U // 2 * normal))


# ---------- Entradas: clase|None, nombre, partes, xml, base, texto ----------
# clase: toma los primeros len(partes) elementos de esa clase. None: lo que sobra al quitar la base.
# texto: el elemento trae varias letras o cifras y se parte por geometría; si no, cada elemento es un glifo.

ENTRADAS = []


def E(nombre, partes, xml, clase=None, base=BASE, texto=False):
    ENTRADAS.append(dict(nombre=nombre, partes=partes, xml=xml, clase=clase, base=base, texto=texto))


for sign, line, n in (("G", 2, "G"), ("F", 4, "F"), ("C", 3, "C"), ("percussion", None, "percussion")):
    E(f"clef_{n}", [n], una(nota() + relleno(U), clef=(sign, line)), clase="Clef")
# la clave a mitad de sistema sale más pequeña y es otro contorno
for sign, line, n in (("G", 2, "G_chica"), ("F", 4, "F_chica"), ("C", 3, "C_chica")):
    dos = compas(nota() + relleno(U), clef=("G", 2) if sign != "G" else ("F", 4))
    E(f"clef_{n}", [n], partitura(dos, compas(nota() + relleno(U), 2, clef=(sign, line), cambia=True)),
      base=partitura(dos, compas(nota() + relleno(U), 2, clef=None)))
for fifths, n in ((1, "sharp"), (-1, "flat")):
    E(f"key_{n}", [n], una(nota() + relleno(U), fifths=fifths), clase="KeySig")
E("key_natural", ["natural"], partitura(compas(nota() + relleno(U), fifths=1), compas(nota() + relleno(U), 2, fifths=0, clef=None)),
  base=partitura(compas(nota() + relleno(U), fifths=1), compas(nota() + relleno(U), 2, fifths=1, clef=None)))
for num, den in ((2, 4), (3, 4), (5, 8), (6, 8), (7, 4), (9, 8), (10, 4), (12, 8)):
    E(f"time_{num}_{den}", list(str(num)) + list(str(den)), una(resto(U * 4 * num // den), tiempo=(num, den)), clase="TimeSig")
for t, dur, n in (("whole", 4, "whole"), ("half", 2, "half"), ("quarter", 1, "quarter"), ("eighth", .5, "eighth"), ("16th", .25, "16th"),
                  ("32nd", .125, "32nd"), ("64th", 1 / 16, "64th")):
    # redonda y blanca son el mismo rectángulo: las distingue la línea a la que se pegan, no la forma
    E(f"rest_{n}", ["whole/half" if n in ("whole", "half") else n], una(resto(int(U * dur), t) + relleno(int(U * dur))), clase="Rest")
for t, dur in (("quarter", 1), ("half", 2), ("whole", 4)):
    E(f"head_{t}", [t], una(nota(tipo=t, dur=U * dur) + relleno(U * dur)), clase="Note")
for h in ("x", "diamond", "triangle", "circle-x"):
    E(f"head_{h}", [h], con_nota(pre=f"<notehead>{h}</notehead>"), clase="Note")
for n, alt in (("sharp", 1), ("flat", -1), ("natural", 0), ("double-sharp", 2), ("flat-flat", -2)):
    E(f"acc_{n}", [n], con_nota(alter=alt, acc=n))
for d in ("p", "pp", "ppp", "f", "ff", "fff", "mp", "mf", "sf", "sfz", "fp", "rfz", "fz"):
    # pp, ppp, ff y fff son un solo glifo
    E(f"dyn_{d}", [d] if d in ("pp", "ppp", "ff", "fff") else list(d), con_nota(antes=direccion(f"<dynamics><{d}/></dynamics>", "below")), texto=True)
for a in ("accent", "strong-accent", "staccato", "tenuto", "staccatissimo", "breath-mark"):
    E(f"art_{a}", [a], con_nota(extra=notac(f"<articulations><{a}/></articulations>")))
for f in ("upright", "inverted"):
    E(f"fermata_{f}", [f], con_nota(extra=notac(f'<fermata type="{f}"/>')))
for o in ("trill-mark", "turn", "inverted-turn", "mordent", "inverted-mordent"):
    E(f"orn_{o}", [o], con_nota(extra=notac(f"<ornaments><{o}/></ornaments>")))
for o in ("up-bow", "down-bow", "open", "stopped", "snap-pizzicato"):
    E(f"tec_{o}", [o], con_nota(extra=notac(f"<technical><{o}/></technical>")))
for f in "12345":
    E(f"dedo_{f}", [f], con_nota(extra=notac(f"<technical><fingering>{f}</fingering></technical>")), texto=True)
for n, nombre in (("segno", "segno"), ("coda", "coda")):
    E(f"marca_{n}", [nombre], con_nota(antes=direccion(f"<{n}/>")))
for n, a in ((2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9)):
    E(f"grupo_{a}", [str(a)], grupo(a), clase="Tuplet", texto=True)
for tipo in ("whole", "half", "quarter", "eighth", "16th"):
    E(f"tempo_{tipo}", [tipo, "=", "8", "0"], con_nota(antes=direccion(
        f"<metronome><beat-unit>{tipo}</beat-unit><per-minute>80</per-minute></metronome>", extra='<sound tempo="80"/>')), texto=True)
E("tempo_cifras", ["quarter", "=", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"], con_nota(antes=direccion(
    "<metronome><beat-unit>quarter</beat-unit><per-minute>1234567890</per-minute></metronome>", extra='<sound tempo="120"/>')), texto=True)


# ---------- Leer SVG ----------

def contornos(d, mat):
    """Contornos de un path: lista de listas de puntos de la curva (extremos de cada tramo), en unidades de página."""
    a, _, _, dd, e, f = mat
    out, x, y, sx, sy = [], 0.0, 0.0, 0.0, 0.0
    for cmd, body in re.findall(r"([a-zA-Z])([^a-zA-Z]*)", d):
        size, n = ARGS[cmd.upper()], numeros(cmd, body)
        if not size:
            x, y = sx, sy
            continue
        for k in range(0, len(n), size):
            v, c = n[k:k + size], cmd
            if c in "Mm" and k:
                c = "L" if c == "M" else "l"
            bx, by = (x, y) if c.islower() else (0.0, 0.0)
            C = c.upper()
            if C == "H":
                x = v[0] + bx
            elif C == "V":
                y = v[0] + by
            else:
                x, y = v[-2] + bx, v[-1] + by
            if C == "M":
                sx, sy = x, y
                out.append([])
            out[-1].append((a * x + e, dd * y + f))
    return out


def leer(ruta):
    """(sp, elementos): cada elemento es (clase, [contornos]) de un <path>; el texto de MuseScore trae un elemento por texto."""
    t = Path(ruta).read_text(encoding="utf-8")
    escritorio = "<polyline" in t  # la web junta todos los glifos de una clase en un <path>; aquí se separan por 'M'
    if escritorio:
        ys = sorted({round(float(y), 2) for pts in re.findall(r'<polyline class="StaffLines"[^>]*? points="([^"]*)"', t)
                     for y in pts.replace(",", " ").split()[1::2]})
    else:
        ys = sorted({round(c[0][1], 2) for d in re.findall(r'<path class="StaffLines"[^>]*? d="([^"]*)"', t) for c in contornos(d, [1, 0, 0, 1, 0, 0])})
    sp = (ys[4] - ys[0]) / 4
    els = []
    for attrs in re.findall(r"<path\b([^>]*?)/?>", t):
        c, d = re.search(r'class="([^"]*)"', attrs), re.search(r'\sd="([^"]*)"', attrs)
        if not (c and d and c.group(1)):
            continue
        m = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
        mat = [float(v) for v in NUM.findall(m.group(1))] if m else [1, 0, 0, 1, 0, 0]
        cs = contornos(d.group(1), mat)
        if escritorio:
            els.append((c.group(1), cs))
        else:
            els += [(c.group(1), [x]) for x in cs]
    return sp, els


def caja(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def dentro(a, b):
    return a[0] >= b[0] - 1 and a[1] >= b[1] - 1 and a[2] <= b[2] + 1 and a[3] <= b[3] + 1


def agrupar(cs, sp):
    """Reúne contornos en glifos: huecos (caja dentro de otra) y piezas apiladas (como '=' o el punto de 'i')."""
    cajas = [caja(c) for c in cs]
    grupo = list(range(len(cs)))

    def raiz(i):
        while grupo[i] != i:
            i = grupo[i]
        return i
    for i in range(len(cs)):
        for j in range(i):
            a, b = cajas[i], cajas[j]
            ancho = min(a[2] - a[0], b[2] - b[0])
            solapa = min(a[2], b[2]) - max(a[0], b[0])
            hueco_y = max(a[1], b[1]) - min(a[3], b[3])
            if dentro(a, b) or dentro(b, a) or (solapa > .6 * ancho and hueco_y < .6 * sp):
                grupo[raiz(i)] = raiz(j)
    gs = {}
    for i in range(len(cs)):
        gs.setdefault(raiz(i), []).append(i)
    return [sorted(v) for v in gs.values()]


def forma(pts, sp):
    """[ancho, alto, puntos] de un contorno; los puntos repetidos (el cierre) cuentan una vez."""
    x0, y0, x1, y1 = caja(pts)
    q = []
    for p in pts:
        r = (round((p[0] - x0) / sp, 3), round((p[1] - y0) / sp, 3))
        if not any(abs(r[0] - o[0]) < .01 and abs(r[1] - o[1]) < .01 for o in q):
            q.append(r)
    return [round((x1 - x0) / sp, 3), round((y1 - y0) / sp, 3), q]


def firma(cs, sp):
    return [forma(c, sp) for c in cs]


def misma_forma(a, b):
    if abs(a[0] - b[0]) > TOL or abs(a[1] - b[1]) > TOL or abs(len(a[2]) - len(b[2])) > 1:
        return False
    cerca = lambda p, q: abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL
    return all(any(cerca(p, q) for q in b[2]) for p in a[2]) and all(any(cerca(p, q) for q in a[2]) for p in b[2])


def iguales(a, b):
    """Dos glifos con los mismos contornos, en cualquier orden."""
    return len(a) == len(b) and all(any(misma_forma(x, y) for y in b) for x in a)


def glifos_de(els, sp, texto):
    """[(clase, firma, x0, y0)] de una lista de elementos."""
    out = []
    for clase, cs in els:
        cs = [c for c in cs if len(c) > 1]
        grupos = agrupar(cs, sp) if texto else [list(range(len(cs)))]
        for g in grupos:
            sub = [cs[i] for i in g]
            x0, y0, _, _ = caja([p for c in sub for p in c])
            out.append((clase, firma(sub, sp), x0, y0))
    return out


def sin_base(els, base, sp):
    """Elementos que no están en la base (como multiconjunto)."""
    rest = list(base)
    out = []
    for e in els:
        for k, b in enumerate(rest):
            if e[0] == b[0] and iguales(firma(e[1], sp), firma(b[1], sp)):
                del rest[k]
                break
        else:
            out.append(e)
    return out


# ---------- Programa ----------

def exportar(xmls, carpeta, fuente=None):
    """Convierte todos los MusicXML con un solo arranque de MuseScore; devuelve {clave: ruta del svg}."""
    job = []
    for k, x in xmls.items():
        (carpeta / f"{k}.musicxml").write_text(x, encoding="utf-8")
        job.append(dict(**{"in": wpath(carpeta / f"{k}.musicxml"), "out": wpath(carpeta / f"{k}.svg")}))
    (carpeta / "job.json").write_text(json.dumps(job))
    estilo = []
    if fuente:
        (carpeta / "estilo.mss").write_text(f'<?xml version="1.0"?><museScore version="4.40"><Style><musicalSymbolFont>{fuente}</musicalSymbolFont>'
                                            f'<musicalTextFont>{fuente} Text</musicalTextFont></Style></museScore>')
        estilo = ["-S", wpath(carpeta / "estilo.mss")]
    subprocess.run([MUSESCORE, *estilo, "-j", wpath(carpeta / "job.json")], check=True, capture_output=True)
    return {k: carpeta / f"{k}-1.svg" for k in xmls}


def generar(salida, fuente=None):
    xmls = {f"e{i}": e["xml"] for i, e in enumerate(ENTRADAS)}
    bases = {x: f"b{i}" for i, x in enumerate(dict.fromkeys(e["base"] for e in ENTRADAS if e["clase"] is None))}
    xmls.update({k: x for x, k in bases.items()})
    with tempfile.TemporaryDirectory() as tmp:
        svgs = exportar(xmls, Path(tmp), fuente)
        cat, fallos = {}, []
        cache = {}
        for i, e in enumerate(ENTRADAS):
            sp, els = leer(svgs[f"e{i}"])
            if e["clase"]:
                els = [x for x in els if x[0] == e["clase"]]
            else:
                b = bases[e["base"]]
                cache.setdefault(b, leer(svgs[b]))
                els = sin_base(els, cache[b][1], sp)
            gl = glifos_de(els, sp, e["texto"])
            orden = lambda g: g[2]
            if e["nombre"].startswith("time_"):
                med = sum(g[3] for g in gl) / max(len(gl), 1)
                orden = lambda g: (g[3] > med, g[2])
            gl.sort(key=orden)
            gl = gl[:len(e["partes"])] if e["clase"] else gl
            if len(gl) != len(e["partes"]):
                fallos.append(f"{e['nombre']}: esperaba {len(e['partes'])} glifos y salieron {len(gl)} ({[g[0] for g in gl]})")
                continue
            for (clase, f, _, _), nombre in zip(gl, e["partes"]):
                previo = cat.setdefault(clase, {}).setdefault(nombre, f)
                if not iguales(previo, f):
                    fallos.append(f"{e['nombre']}: {clase}/{nombre} no coincide con otra entrada")
    Path(salida).write_text(json.dumps(dict(
        fuente=f"MuseScore 4, {fuente or 'fuente por defecto'}", unidad="glifo = lista de contornos [ancho, alto, puntos], en espacios entre líneas", tolerancia=TOL, glifos=cat),
        separators=(",", ":")))
    for c, v in cat.items():
        print(f"{c}: {len(v)} glifos")
    for f in fallos:
        print("FALLO", f)
    return fallos


def probar(ruta, catalogo):
    """Cuántos contornos de un SVG real se reconocen con el catálogo, por clase."""
    cat = json.loads(Path(catalogo).read_text())["glifos"]
    sp, els = leer(ruta)
    cuenta = {}
    for clase, cs in els:
        if clase not in cat:
            continue
        for c in cs:
            if len(c) > 1:
                f = forma(c, sp)
                a = cuenta.setdefault(clase, [0, 0])
                a[0] += any(misma_forma(f, o) for g in cat[clase].values() for o in g)
                a[1] += 1
    for c, (ok, n) in cuenta.items():
        print(f"{c}: {ok} de {n} contornos reconocidos")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", default="glifos.json")
    ap.add_argument("--probar", metavar="SVG")
    ap.add_argument("--fuente", help="fuente musical de MuseScore (Emmentaler, Bravura, Petaluma...); sin ella, la por defecto")
    a = ap.parse_args()
    if a.probar:
        probar(a.probar, a.o)
    else:
        sys.exit(bool(generar(a.o, a.fuente)))
