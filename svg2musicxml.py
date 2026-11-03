"""Convierte a MusicXML los SVG que exporta MuseScore, leyendo las coordenadas de cada símbolo. Sin OMR.

Uso: python svg2musicxml.py pagina1.svg [pagina2.svg ...] -o salida.musicxml [--compas 9/8]
(--compas solo cuenta si el SVG no trae cifras de compás reconocibles; sin él, se deduce de las duraciones)

Solo funciona con SVG cuyos <path> traen class="Note", "Stem", etc. El texto viene como contornos, no como
letras, así que títulos, tempo, dinámicas y letra se pierden. Los avisos van a stderr.
"""
import argparse
import json
import re
import sys
from collections import Counter
from fractions import Fraction as F
from functools import lru_cache
from itertools import combinations
from math import lcm
from pathlib import Path

NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
SEP = re.compile(r"[\s,]*")
ARGS = dict(M=2, L=2, H=1, V=1, C=6, S=4, Q=4, T=2, A=7, Z=0)
STEPS = "CDEFGAB"
CLEF_BASE = {"G": 4 * 7 + 2, "F": 2 * 7 + 4}  # línea inferior: E4 y G2
FLATS, SHARPS = "BEADGCF", "FCGDAEB"
TYPES = {F(8): "whole", F(4): "half", F(2): "quarter", F(1): "eighth", F(1, 2): "16th", F(1, 4): "32nd"}
TUPLET = {2: (2, 3), 3: (3, 2), 4: (4, 3), 5: (5, 4), 6: (6, 4), 7: (7, 4)}  # notas del grupo -> actual, normal


def aviso(msg):
    print(f"Aviso: {msg}", file=sys.stderr)


def numeros(cmd, body):
    if cmd not in "aA":
        return [float(x) for x in NUM.findall(body)]
    # las banderas de un arco pueden ir pegadas: "0 00-1.375"
    out, i = [], 0
    while True:
        i = SEP.match(body, i).end()
        if i >= len(body):
            return out
        if len(out) % 7 in (3, 4):
            out.append(float(body[i]))
            i += 1
        else:
            m = NUM.match(body, i)
            out.append(float(m.group()))
            i = m.end()


def glifos(d):
    """Parte un atributo d en glifos con su caja. Una 'm' tras una figura es hueco interior, no glifo nuevo."""
    out, x, y, sx, sy, cur = [], 0.0, 0.0, 0.0, 0.0, None
    for cmd, body in re.findall(r"([a-zA-Z])([^a-zA-Z]*)", d):
        size, n = ARGS[cmd.upper()], numeros(cmd, body)
        if not size:
            x, y = sx, sy
            continue
        for k in range(0, len(n), size):
            a, c = n[k:k + size], cmd
            if c in "Mm" and k:
                c = "L" if c == "M" else "l"
            bx, by = (x, y) if c.islower() else (0.0, 0.0)
            C = c.upper()
            if C == "M":
                x, y = a[0] + bx, a[1] + by
                sx, sy = x, y
                if c == "M" or cur is None:
                    cur = dict(start=(x, y), xs=[x], ys=[y], huecos=0)
                    out.append(cur)
                else:
                    cur["huecos"] += 1
                    cur.setdefault("inicios", [0]).append(len(cur["ys"]))  # dónde empieza cada trazo en ys
                continue
            if C == "H":
                x = a[0] + bx
            elif C == "V":
                y = a[0] + by
            elif C == "A":
                x, y = a[5] + bx, a[6] + by
            else:
                cur["xs"] += [v + bx for v in a[0::2]]
                cur["ys"] += [v + by for v in a[1::2]]
                x, y = a[-2] + bx, a[-1] + by
            cur["xs"].append(x)
            cur["ys"].append(y)
            cur.setdefault("fin", (x, y))  # en ligaduras: la otra punta, antes de volver por el grosor
    for g in out:
        g.update(x0=min(g["xs"]), x1=max(g["xs"]), y0=min(g["ys"]), y1=max(g["ys"]))
    for g in out:
        g["x"], g["y"] = (g["x0"] + g["x1"]) / 2, (g["y0"] + g["y1"]) / 2
        if "inicios" in g:  # altura del hueco en la caja, de 0 (arriba) a 1: el del bemol queda abajo
            i = g.pop("inicios") + [len(g["ys"])]
            trazos = [g["ys"][a:b] for a, b in zip(i, i[1:]) if b > a]
            trazos.sort(key=lambda t: max(t) - min(t), reverse=True)  # el exterior es el más alto, vaya antes o después
            if len(trazos) > 1:
                g["hueco_y"] = ((min(trazos[1]) + max(trazos[1])) / 2 - g["y0"]) / ((g["y1"] - g["y0"]) or 1)
        del g["xs"], g["ys"]
    return out


def unir(gs):
    """Junta los contornos de un elemento en un solo glifo."""
    g = max(gs, key=lambda o: (o["x1"] - o["x0"]) * (o["y1"] - o["y0"]))
    dentro = [o for o in gs if o is not g and g["x0"] <= o["x"] <= g["x1"] and g["y0"] <= o["y"] <= g["y1"]]
    if dentro and "hueco_y" not in g:
        g["hueco_y"] = (dentro[0]["y"] - g["y0"]) / ((g["y1"] - g["y0"]) or 1)
    g.update(x0=min(o["x0"] for o in gs), x1=max(o["x1"] for o in gs), y0=min(o["y0"] for o in gs), y1=max(o["y1"] for o in gs),
             huecos=len(gs) - 1 + sum(o["huecos"] for o in gs))
    g["x"], g["y"] = (g["x0"] + g["x1"]) / 2, (g["y0"] + g["y1"]) / 2
    return [g]


def aplicar_matriz(gs, m):
    """Algunos símbolos traen coordenadas locales más una matriz, también con giro (el arpegio va girado 90°)."""
    a, b, c, d, e, f = m
    T = lambda x, y: (a * x + c * y + e, b * x + d * y + f)
    for g in gs:
        esquinas = [T(x, y) for x in (g["x0"], g["x1"]) for y in (g["y0"], g["y1"])]
        g["x0"], g["x1"] = min(p[0] for p in esquinas), max(p[0] for p in esquinas)
        g["y0"], g["y1"] = min(p[1] for p in esquinas), max(p[1] for p in esquinas)
        g["x"], g["y"] = (g["x0"] + g["x1"]) / 2, (g["y0"] + g["y1"]) / 2
        g["start"] = T(*g["start"])
        if "fin" in g:
            g["fin"] = T(*g["fin"])


def leer_svg(ruta):
    items = {}
    texto = Path(ruta).read_text(encoding="utf-8")
    if not texto.strip():
        sys.exit(f"{ruta}: pesa 0 bytes; falta esa página")
    # MuseScore de escritorio escribe un elemento por símbolo; la web junta muchos en cada <path>
    escritorio = "<polyline" in texto
    # la web usa <path> con todo junto y coordenadas relativas; MuseScore de escritorio, además <polyline>
    for tag, attrs in re.findall(r"<(path|polyline)\b([^>]*?)/?>", texto):
        c, d = re.search(r'class="([^"]*)"', attrs), re.search(r'\s(?:d|points)="([^"]*)"', attrs)
        if c and d:
            gs = glifos(d.group(1) if tag == "path" else "M" + d.group(1))
            if tag == "polyline" and gs:  # el corchete de una casilla: ¿se cierra con un gancho al final?
                n = [float(v) for v in NUM.findall(d.group(1))]
                gs[0]["puntos"] = list(zip(n[0::2], n[1::2]))
            t = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
            if t:
                aplicar_matriz(gs, [float(v) for v in NUM.findall(t.group(1))])
            items.setdefault(c.group(1), []).extend(unir(gs) if escritorio and gs and c.group(1) != "Beam" else gs)
    if "Note" not in items or "StaffLines" not in items:
        sys.exit(f"{ruta}: no trae clases de MuseScore (Note, StaffLines); este script no sirve para él")
    return items


class Pagina:
    def __init__(self, ruta):
        self.ruta = ruta
        self.it = it = leer_svg(ruta)
        for g in it.values():
            g.sort(key=lambda s: s["x0"])
        lineas = sorted((round(g["start"][1], 2), g["x0"]) for g in it["StaffLines"])
        filas = [lineas[i:i + 5] for i in range(0, len(lineas), 5)]
        self.sp = sp = (filas[0][4][0] - filas[0][0][0]) / 4
        anchos = sorted(g["x1"] - g["x0"] for g in it["Note"])
        self.cabeza = anchos[len(anchos) // 2]  # ancho habitual de una cabeza; las de adorno son más estrechas
        self.pentas = [dict(top=f[0][0], bot=f[4][0], x0=f[0][1]) for f in filas]
        # dos pentagramas son del mismo sistema si una barra de compás los une
        self.sistemas, actual = [], [self.pentas[0]]
        for a, b in zip(self.pentas, self.pentas[1:]):
            unidos = any(a["top"] - sp <= g["y0"] <= a["bot"] and g["y1"] >= b["top"] - sp for g in it["BarLine"])
            if unidos:
                actual.append(b)
            else:
                self.sistemas.append(actual)
                actual = [b]
        self.sistemas.append(actual)

    def sistema_de(self, y):
        return min(self.sistemas, key=lambda s: max(s[0]["top"] - y, y - s[-1]["bot"], 0))

    def penta_de(self, sistema, y):
        return min(range(len(sistema)), key=lambda i: abs((sistema[i]["top"] + sistema[i]["bot"]) / 2 - y))

    def penta_cabeza(self, n):
        """Pentagrama de la página al que pertenece una cabeza. Entre dos pentagramas, aunque sean de sistemas
        distintos, gana aquel del que salen sus líneas adicionales: hay una en cada espacio hasta la cabeza."""
        sp, y, ps = self.sp, n["y"], self.pentas
        cerca = min(range(len(ps)), key=lambda i: abs((ps[i]["top"] + ps[i]["bot"]) / 2 - y))
        if ps[cerca]["top"] - .75 * sp <= y <= ps[cerca]["bot"] + .75 * sp:
            return ps[cerca]
        otro = cerca + 1 if y > ps[cerca]["bot"] else cerca - 1
        if not 0 <= otro < len(ps):
            return ps[cerca]

        def completas(i):
            borde = ps[i]["top"] if y < ps[i]["top"] else ps[i]["bot"]
            k = int(abs(y - borde) / sp + .25)
            en = {round(abs(g["y"] - borde) / sp) for g in self.it.get("LedgerLine", [])
                  if g["x0"] - .2 * sp <= n["x"] <= g["x1"] + .2 * sp and (g["y"] - borde) * (y - borde) > 0
                  and abs(abs(g["y"] - borde) / sp - round(abs(g["y"] - borde) / sp)) < .2}
            return all(j in en for j in range(1, k + 1))
        return ps[otro] if completas(otro) and not completas(cerca) else ps[cerca]

    def barras(self, sistema):
        sp = self.sp
        xs = sorted(g["x"] for g in self.it["BarLine"] if sistema[0]["top"] - sp <= g["y"] <= sistema[-1]["bot"] + sp and g["y1"] - g["y0"] > 3 * sp)
        # shortcut: una barra doble o de repetición cuenta como una sola, las repeticiones se pierden
        uniq = [x for i, x in enumerate(xs) if i == 0 or x - xs[i - 1] > 2 * sp]
        if not uniq or uniq[0] - sistema[0]["x0"] > 2 * sp:
            uniq.insert(0, sistema[0]["x0"])
        # barra de inicio de repetición tras clave y armadura: el tramo anterior no es un compás
        if len(uniq) > 2 and not any(uniq[0] <= g["x"] < uniq[1] and sistema[0]["top"] - 6 * sp <= g["y"] <= sistema[-1]["bot"] + 6 * sp
                                     for k in ("Note", "Rest", "MeasureRepeat") for g in self.it.get(k, [])):
            del uniq[1]
        return uniq


def clase_alteracion(g, sp):
    """Sin depender del tamaño ni de la fuente: el bemol lleva el hueco abajo; el becuadro es más estrecho que el sostenido."""
    proporcion = (g["x1"] - g["x0"]) / (g["y1"] - g["y0"])
    if g.get("hueco_y", .5) > .6:
        return "flat-flat" if proporcion > .5 else "flat"
    if proporcion > .8:  # el doble sostenido es una cruz casi cuadrada
        return "double-sharp"
    return "natural" if proporcion < .3 else "sharp"


def leer_armaduras(pag):
    """Armaduras de la página como [(sistema, x, fifths)]: grupos de alteraciones seguidas en el pentagrama de arriba.
    Los becuadros solo anulan la anterior; sin más alteraciones queda do mayor."""
    sp, out = pag.sp, []
    for s in pag.sistemas:
        k = sorted((g for g in pag.it.get("KeySig", []) if pag.sistema_de(g["y"]) is s and pag.penta_de(s, g["y"]) == 0), key=lambda g: g["x0"])
        while k:
            grupo = [k[0]]
            for g in k[1:]:
                if g["x0"] - grupo[-1]["x1"] >= 1.5 * sp:
                    break
                grupo.append(g)
            k = k[len(grupo):]
            altera = [g for g in grupo if clase_alteracion(g, sp) != "natural"]
            n = len(altera)
            out.append((s, grupo[0]["x0"], n if n and clase_alteracion(altera[0], sp) == "sharp" else -n))
    return out


def altera_armadura(fifths):
    return {p: -1 for p in FLATS[:-fifths]} if fifths < 0 else {p: 1 for p in SHARPS[:fifths]}


def tiene_puntillo(h, up, d, sistema, sp, libre=False):
    if not 0 < d["x"] - h["x1"] < 2.4 * sp:
        return False
    dy = d["y"] - h["y"]
    en_linea = round((h["y"] - sistema[h["penta"]]["top"]) / (sp / 2)) % 2 == 0
    if not en_linea:
        return abs(dy) < .25 * sp
    # en una línea el puntillo sube al espacio (voz de arriba) o baja (voz de abajo); con varias voces en el pentagrama
    # la de plica arriba también puede bajarlo: vale si ninguna cabeza de ese espacio lo reclama (libre)
    return -.75 * sp < dy < -.25 * sp or (not up or libre) and .25 * sp < dy < .75 * sp


def construir_eventos(pag, sistema, npag):
    """Agrupa cabezas por plica y les da figura. Devuelve una lista de eventos por compás del sistema."""
    it, sp = pag.it, pag.sp
    barras = pag.barras(sistema)
    en_sistema = lambda g: pag.sistema_de(g["y"]) is sistema
    stems = [dict(g, cabezas=[]) for g in it.get("Stem", []) if en_sistema(g)]
    beams = [b for b in it.get("Beam", []) if en_sistema(b)]
    hooks = [h for h in it.get("Hook", []) if en_sistema(h)]
    dots = [d for d in it.get("NoteDot", []) if en_sistema(d)]
    sin_plica, tocadas = [], []
    for n in it["Note"]:
        p = pag.penta_cabeza(n)
        penta = next((i for i, x in enumerate(sistema) if x is p), None)
        if penta is None:
            continue
        h = dict(n, penta=penta)
        c = [s for s in stems if s["y0"] - .6 * sp <= n["y"] <= s["y1"] + .6 * sp and min(abs(n["x0"] - s["x"]), abs(n["x1"] - s["x"])) < .25 * sp]
        if n["huecos"] and n["x1"] - n["x0"] > 1.1 * pag.cabeza:
            c = []  # redonda (más ancha): no tiene plica, aunque la de otra nota llegue hasta ella
        if c:
            # dos voces al unísono dibujan dos cabezas superpuestas: cada una a una plica distinta, y la hueca a la sin barra
            ocupada = lambda s: any(abs(o["y"] - n["y"]) < .2 * sp and abs(o["x"] - n["x"]) < .2 * sp for o in s["cabezas"])
            con_barra = lambda s: any(b["x0"] - .2 * sp <= s["x"] <= b["x1"] + .2 * sp and (b["y0"] - .25 * sp <= s["y0"] <= b["y1"] + .25 * sp
                                      or b["y0"] - .25 * sp <= s["y1"] <= b["y1"] + .25 * sp) for b in beams)
            min(c, key=lambda s: (ocupada(s), bool(n["huecos"]) and con_barra(s), min(abs(n["x0"] - s["x"]), abs(n["x1"] - s["x"]))))["cabezas"].append(h)
            tocadas.append((h, c))
        else:
            sin_plica.append(h)
    for s in stems:  # cabeza compartida por dos voces con figuras distintas: una sola cabeza y dos plicas
        c = [h for h, ss in tocadas if any(o is s for o in ss)]
        if not s["cabezas"] and c:
            s["cabezas"].append(dict(min(c, key=lambda h: min(abs(h["y"] - s["y0"]), abs(h["y"] - s["y1"]))), huecos=0))
    eventos = []
    for s in stems:
        if not s["cabezas"]:
            continue
        hs = s["cabezas"]
        # acorde partido entre pentagramas: las cabezas fuera de las líneas siguen a las que están dentro de uno
        dentro = {h["penta"] for h in hs if sistema[h["penta"]]["top"] - .25 * sp <= h["y"] <= sistema[h["penta"]]["bot"] + .25 * sp}
        if len({h["penta"] for h in hs}) > 1 and len(dentro) == 1:
            for h in hs:
                h["penta"] = next(iter(dentro))
        # plica arriba si las cabezas están en su punta de abajo; con una segunda hay cabezas a los dos lados de la plica
        up = sum(h["y"] for h in hs) / len(hs) > (s["y0"] + s["y1"]) / 2
        toca = lambda b, y: b["x0"] - .2 * sp <= s["x"] <= b["x1"] + .2 * sp and b["y0"] - .25 * sp <= y <= b["y1"] + .25 * sp
        extremo = s["y0"] if up else s["y1"]
        en_barra = [b for b in beams if toca(b, extremo)] or [b for b in beams if toca(b, s["y0"]) or toca(b, s["y1"])]
        # una bandera por contorno: en escritorio el corchete de semicorchea es un glifo con un hueco, en web dos glifos
        banderas = sum(1 + h["huecos"] for h in hooks if h["x0"] - .3 * sp <= s["x"] <= h["x0"] + .3 * sp
                       and (h["y0"] - .5 * sp <= s["y0"] <= h["y1"] or h["y0"] <= s["y1"] <= h["y1"] + .5 * sp))
        # las barras siguientes quedan hacia la cabeza, sin tocar el extremo de la plica (una cada ~0,75 sp)
        n_barras = sum(b["x0"] - .2 * sp <= s["x"] <= b["x1"] + .2 * sp and (extremo - .25 * sp <= b["y1"] and b["y0"] <= extremo + 2.3 * sp if up else
                       extremo - 2.3 * sp <= b["y1"] and b["y0"] <= extremo + .25 * sp) for b in beams)
        if hs[0]["huecos"]:
            base = F(4)
        elif n_barras >= 2:
            base = F(1, 2) if n_barras == 2 else F(1, 4)
        elif banderas >= 2:
            base = F(1, 2) if banderas == 2 else F(1, 4)
        elif en_barra or banderas:
            base = F(1)
        else:
            base = F(2)
        ev = dict(tipo="nota", base=base, cabezas=hs, up=up, plica=True, x=s["x"] + (-.65 if up else .65) * sp, plica_x=s["x"],
                  barra=id(max(en_barra, key=lambda b: b["x1"] - b["x0"])) if en_barra else None,
                  penta=hs[0]["penta"], extremo=extremo,
                  adorno=all(h["x1"] - h["x0"] < .8 * pag.cabeza for h in hs))  # cabeza pequeña: nota de adorno
        eventos.append(ev)
    for h in sin_plica:  # redondas: sin plica; las de un mismo acorde comparten columna. Se alinean por el borde
        # izquierdo como una cabeza normal: la redonda es más ancha y su centro queda a la derecha
        # en una segunda, una de las dos cabezas va desplazada a un lado (~1,4 sp)
        mismo = lambda e: any(abs(o["x"] - h["x"]) < sp or abs(o["x"] - h["x"]) < 1.8 * sp and abs(o["y"] - h["y"]) < .75 * sp for o in e["cabezas"])
        ev = next((e for e in eventos if not e["plica"] and e["penta"] == h["penta"] and mismo(e)), None)
        if ev:
            ev["cabezas"].append(h)
            ev["x"] = sorted(o["x0"] for o in ev["cabezas"])[len(ev["cabezas"]) // 2] + pag.cabeza / 2  # la columna principal, no la desplazada
        else:
            # shortcut: la barra diagonal de ritmo se toma por negra; si hay blancas en barra, saldrán negras
            barra_ritmo = (h["x1"] - h["x0"]) / sp > 1.9 and (h["y1"] - h["y0"]) / sp > 1.5  # la redonda es igual de ancha en algunas fuentes, pero baja
            eventos.append(dict(tipo="nota", base=F(2) if barra_ritmo else F(8), cabezas=[h], up=None, plica=False, x=h["x0"] + pag.cabeza / 2, barra=None, penta=h["penta"], extremo=h["y"], slash=barra_ritmo))
    en_espacio = [h for o in eventos for h in o["cabezas"] if round((h["y"] - sistema[h["penta"]]["top"]) / (sp / 2)) % 2]
    libres = [d for d in dots if not any(tiene_puntillo(h, None, d, sistema, sp) for h in en_espacio)]
    for e in eventos:
        e["puntillo"] = False
    # cada punto, de una sola cabeza a su izquierda: primero la que lo tiene a su misma altura (en un espacio), luego
    # la más cercana; así no se lo queda la nota anterior ni la de otra voz que tiene el suyo en el otro espacio
    for d in dots:
        cand = [(abs(d["y"] - h["y"]) > .25 * sp, d["x"] - h["x1"], e) for e in eventos for h in e["cabezas"]
                if tiene_puntillo(h, e["up"], d, sistema, sp, any(d is o for o in libres))]
        if cand:
            lejos, cerca, _ = min(cand, key=lambda a: a[:2])
            for l, dx, e in cand:
                if l == lejos and dx < cerca + .3 * sp:
                    e["puntillo"] = True
    for r in (g for g in it.get("Rest", []) if en_sistema(g)):
        penta = pag.penta_de(sistema, r["y"])
        alto = (r["y1"] - r["y0"]) / sp
        if alto < .8:  # bloque: la redonda cuelga de una línea, la blanca se apoya en ella
            lineas = [sistema[penta]["top"] + i * sp for i in range(5)]
            cuelga = r["y"] > min(lineas, key=lambda y: abs(y - r["y"]))
            base = None if cuelga else F(4)  # None: compás completo, se resuelve con la duración del compás
        elif alto < 2.3:
            base = F(1)
        else:
            # igual de altos: la semicorchea (dos banderas) es más ancha que la negra (~1,37 sp frente a ~0,94)
            base = F(1, 2) if (r["x1"] - r["x0"]) / sp > 1.15 else F(2)
        d = any(0 < p["x"] - r["x1"] < 1.5 * sp and abs(p["y"] - r["y"]) <= sp for p in dots)
        eventos.append(dict(tipo="silencio", base=base, cabezas=[], up=None, plica=False, x=r["x"], barra=None, penta=penta, y=r["y"], puntillo=d,
                            completo=base is None))
    for e in eventos:
        e["factor"] = F(1)
    aplicar_tresillos(pag, sistema, eventos, en_sistema)
    compases = [[] for _ in barras[:-1]] if len(barras) > 1 else [[]]
    for e in eventos:
        i = next((i for i in range(len(barras) - 1) if barras[i] <= e["x"] < barras[i + 1]), None)
        if i is None:
            aviso(f"página {npag}: evento fuera de los compases en x={e['x']:.0f}")
            continue
        compases[i].append(e)
    return compases, barras


def aplicar_tresillos(pag, sistema, eventos, en_sistema):
    """El número de un grupo irregular se deduce del tamaño del grupo: el dígito es un contorno que no leemos."""
    sp = pag.sp
    grupos = {}
    for e in eventos:
        if e["barra"] is not None:
            grupos.setdefault(e["barra"], []).append(e)
    # solo el número: los trozos del corchete son más bajos (<1 sp frente a ~1,4)
    tuplets = [g for g in pag.it.get("Tuplet", []) if en_sistema(g)]
    corchetes = [g for g in tuplets if g["y1"] - g["y0"] <= 1.1 * sp]
    for t in (g for g in tuplets if g["y1"] - g["y0"] > 1.1 * sp):
        izq = [c for c in corchetes if 0 <= t["x0"] - c["x1"] < sp and abs(c["y"] - t["y"]) < sp]
        der = [c for c in corchetes if 0 <= c["x0"] - t["x1"] < sp and abs(c["y"] - t["y"]) < sp]
        if izq and der:  # con corchete, sus puntas marcan el grupo, silencios incluidos
            a, b = izq[0]["x0"] - .5 * sp, der[0]["x1"] + .5 * sp
            penta = min(range(len(sistema)), key=lambda i: max(sistema[i]["top"] - t["y"], t["y"] - sistema[i]["bot"]))
            dentro = sorted((e for e in eventos if e["penta"] == penta and a <= e["x"] <= b and not e.get("adorno")
                             and not (e["barra"] is not None and any(not a <= o["x"] <= b for o in grupos[e["barra"]]))), key=lambda e: e["x"])
            # una sola voz: entre eventos de la misma columna, el más cercano al número
            miembros = [min(c, key=lambda e: min([abs(e.get("extremo", e.get("y", 0)) - t["y"])] + [abs(h["y"] - t["y"]) for h in e["cabezas"]]))
                        for c in columnas(dentro, sp)]
            if len(miembros) in TUPLET and not any("tresillo" in e for e in miembros):
                marcar_grupo(miembros, *TUPLET[len(miembros)])
                continue

        def cercania(g):
            xs = [e["x"] for e in g]
            if not min(xs) - sp <= t["x"] <= max(xs) + sp:
                return None
            # en un grupo con barra el número va del lado de la barra: las cabezas de otro pentagrama pueden estar más cerca
            return min(abs(e["extremo"] - t["y"]) for e in g)
        cand = [(c, g) for g in grupos.values() if (c := cercania(g)) is not None and c < 5 * sp]
        if cand:
            # el número va centrado sobre las plicas de su grupo, o de parte de él: las notas consecutivas bajo él.
            # Ese centrado decide entre grupos mejor que la distancia vertical, que entre pentagramas engaña.
            centro = lambda v: abs((v[0].get("plica_x", v[0]["x"]) + v[-1].get("plica_x", v[-1]["x"])) / 2 - t["x"])
            opciones = []
            for c, g in cand:
                # un silencio pegado al grupo puede ser parte del tresillo aunque la barra no lo toque
                a, b = min(e["x"] for e in g) - 2.5 * sp, max(e["x"] for e in g) + 2.5 * sp
                g = sorted(g + [e for e in eventos if e["tipo"] == "silencio" and e["penta"] == g[0]["penta"] and a <= e["x"] <= b],
                           key=lambda e: e["x"])
                ventanas = [g[i:i + n] for n in TUPLET for i in range(len(g) - n + 1)]
                if not ventanas:
                    continue
                v = min(ventanas, key=centro)
                if len(g) in TUPLET and centro(g) <= centro(v) + .3 * sp:
                    v = g
                opciones.append((centro(v) + .2 * c, v))
            if not opciones:
                continue
            miembros = min(opciones, key=lambda a: a[0])[1]
            if any("tresillo" in e for e in miembros):  # ya marcado desde la voz paralela
                continue
        else:  # silencio + nota con corchete, sin barra que los una
            penta = pag.penta_de(sistema, t["y"])
            cerca = [e for e in eventos if e["penta"] == penta and e["barra"] is None and e["base"] == F(1) and abs(e["x"] - t["x"]) < 8 * sp]
            izq = [e for e in cerca if e["x"] < t["x"]]
            der = [e for e in cerca if e["x"] >= t["x"]]
            if not izq or not der:
                aviso(f"número de grupo irregular sin grupo en x={t['x']:.0f}")
                continue
            miembros = [max(izq, key=lambda e: e["x"]), min(der, key=lambda e: e["x"])]
        if len(miembros) not in TUPLET:
            aviso(f"grupo irregular de {len(miembros)} notas sin interpretar en x={t['x']:.0f}")
            continue
        real, normal = TUPLET[len(miembros)]
        miembros = sorted(miembros, key=lambda e: e["x"])
        marcar_grupo(miembros, real, normal)
        # la voz paralela puede llevar el mismo ritmo sin número impreso
        junto = [[o for o in eventos if abs(o["x"] - e["x"]) < .7 * sp and "tresillo" not in o and o["base"] == e["base"]] for e in miembros]
        for penta in {o["penta"] for o in junto[0]}:
            paralelos = [[o for o in c if o["penta"] == penta] for c in junto]
            if all(len(c) == 1 for c in paralelos):
                marcar_grupo([c[0] for c in paralelos], real, normal)


def marcar_grupo(miembros, real, normal):
    for e in miembros:
        e["factor"], e["tresillo"] = F(normal, real), (real, normal)
    miembros[0]["t_ini"] = miembros[-1]["t_fin"] = True


def quitar_implicitos(c):
    for e in c["ev"]:
        if e.pop("implicito", False):
            e["factor"] = F(1)
            for k in ("tresillo", "t_ini", "t_fin"):
                e.pop(k, None)


def probar_numerador(c, den):
    """Numerador de una cifra sin reconocer: el que llena el compás en todos sus pentagramas (con tresillos implícitos
    si hace falta); si ninguno los llena todos, el primero con el que cuadra."""
    cuadra = []
    for n in range(1, 13):
        largo = F(8 * n, den)
        total, fallos = barrer(c["ev"], c["pag"].sp, largo)
        if total != largo or fallos:
            total, fallos = tresillos_implicitos(c, largo, total, fallos)
        if total == largo and not fallos:
            fin = {}
            for e in c["ev"]:
                fin[e["penta"]] = max(fin.get(e["penta"], 0), e["t"] + duracion(e))
            if all(v == largo for v in fin.values()):
                quitar_implicitos(c)
                return n
            cuadra.append(n)
        quitar_implicitos(c)
    return cuadra[0] if cuadra else None


def tresillos_implicitos(c, largo, total, fallos):
    """Marca como tresillo cada grupo con barra de tres notas iguales sin número; se queda solo si el compás cuadra."""
    grupos = {}
    for e in c["ev"]:
        if e["barra"] is not None and not e.get("adorno"):
            grupos.setdefault(e["barra"], []).append(e)
    tres = []
    for g in grupos.values():
        g = sorted(g, key=lambda e: e["x"])
        if len({e["base"] for e in g}) != 1 or any("tresillo" in e for e in g):
            continue
        if len(g) == 2:  # silencio + dos notas: el silencio de la misma figura justo delante completa el grupo
            sp = c["pag"].sp
            sil = [e for e in c["ev"] if e["tipo"] == "silencio" and e["base"] == g[0]["base"] and "tresillo" not in e
                   and 0 < g[0]["x"] - e["x"] < 2.5 * sp]
            g = [max(sil, key=lambda e: e["x"])] + g if sil else g
        if len(g) == 3:
            tres.append(g)
    # el mayor subconjunto que cuadre: una mano puede ir en tresillos y la otra en corcheas normales
    # shortcut: con más de 10 grupos solo se prueba marcarlos todos; ampliarlo si aparece un compás así
    for r in range(len(tres), 0, -1) if len(tres) <= 10 else [len(tres)]:
        for elegidos in combinations(tres, r):
            for g in elegidos:
                marcar_grupo(g, 3, 2)
                for e in g:
                    e["implicito"] = True
            nuevo, nuevos_fallos = barrer(c["ev"], c["pag"].sp, largo)
            if nuevo == largo and not nuevos_fallos:
                return nuevo, nuevos_fallos
            quitar_implicitos(c)
    return barrer(c["ev"], c["pag"].sp, largo)


def duracion(e):
    if e.get("adorno"):
        return F(0)
    return e["base"] * (F(3, 2) if e["puntillo"] else 1) * e["factor"]


def columnas(eventos, sp):
    cols = []
    orden = sorted(eventos, key=lambda e: e["x"])
    for i, e in enumerate(orden):
        # dos notas de un mismo grupo con barra nunca suenan a la vez, aunque una escala apretada las acerque
        # dos notas simultáneas se alinean; solo se apartan ~1,3 sp si sus cabezas chocarían en el mismo pentagrama
        # (segunda, unísono o un acorde metido entre las notas del otro). Así una corchea con puntillo contra
        # seisillos, o un tresillo apretado, no se juntan.
        if cols:
            ult = cols[-1]
            def rango(ev, p):  # por pentagrama: un acorde puede repartirse entre los dos
                ys = [h["y"] for h in ev["cabezas"] if h["penta"] == p]
                return (min(ys) - .6 * sp, max(ys) + .6 * sp) if ys else None
            choque = lambda o: any((a := rango(o, p)) and (b := rango(e, p)) and a[0] < b[1] and b[0] < a[1]
                                   for p in {h["penta"] for h in e["cabezas"]})
            solo_notas = e["tipo"] == "nota" and all(o["tipo"] == "nota" for o in ult)
            lim = .7 * sp if solo_notas and not any(choque(o) for o in ult) else 1.5 * sp
            opuestas = lambda o: o["up"] is not None and e["up"] is not None and o["up"] != e["up"]
            if any(choque(o) and opuestas(o) and o["puntillo"] for o in ult):
                lim = 2.5 * sp  # dos voces que chocan: la otra se aparta también del puntillo
            if i + 1 < len(orden) and orden[i + 1]["x"] - e["x"] < .7 * sp < e["x"] - ult[0]["x"]:
                lim = .7 * sp  # el siguiente está casi alineado con este: el choque es con él, no con la columna anterior
            misma_barra = e["barra"] is not None and any(o["barra"] == e["barra"] for o in ult)
        if cols and e["x"] - ult[0]["x"] < lim and not misma_barra:
            cols[-1].append(e)
        else:
            cols.append([e])
    return cols


def barrer(eventos, sp, largo=None):
    """Da tiempo a cada columna: la siguiente empieza cuando termina la nota sonando que acaba antes."""
    t, total, fallos = F(0), F(0), 0
    activos = []
    adornos = [e for e in eventos if e.get("adorno")]
    for e in eventos:  # el silencio de compás entero va centrado en el compás, pero empieza al principio
        if e.get("completo"):
            e["t"], e["base"] = F(0), largo if largo else F(0)
            total = max(total, e["base"])
    for col in columnas([e for e in eventos if not e.get("adorno") and not e.get("completo")], sp):
        if activos or t:
            futuros = [f for f in activos if f > t]
            if futuros:
                t = min(futuros)
            else:
                fallos += 1  # hueco: nadie termina justo aquí
                t = total
        for e in col:
            e["t"] = t
            d = duracion(e)
            activos.append(t + d)
            total = max(total, t + d)
    for a in adornos:  # sin duración: suena justo antes de la siguiente nota de su pentagrama
        a["t"] = min((e["t"] for e in eventos if not e.get("adorno") and e["penta"] == a["penta"] and e["x"] > a["x"]), default=total)
    return total, fallos


def repartir_voces(eventos):
    """Colorea por intervalos: los grupos con barra van enteros a una voz, por si cruzan de pentagrama."""
    grupos = {}
    for e in eventos:
        grupos.setdefault(e["barra"] if e["barra"] is not None else id(e), []).append(e)
    orden = lambda g: (g[0]["tipo"] == "silencio", g[0]["up"] is False, min(e["t"] for e in g))
    ocupado = {}
    for g in sorted(grupos.values(), key=orden):
        penta = min(g, key=lambda e: e["t"])["penta"]
        tramos = [(e["t"], e["t"] + duracion(e)) for e in g]
        v = 0
        while any(a < d and c < b for a, b in tramos for c, d in ocupado.get((penta, v), [])):
            v += 1
        ocupado.setdefault((penta, v), []).extend(tramos)
        for e in g:
            e["voz"] = penta * 4 + v + 1
            e["penta_voz"] = penta


def enganchar_ligaduras(pag, sistema, evs_sistema):
    sp = pag.sp
    cabezas = [h for e in evs_sistema for h in e["cabezas"]]
    der = pag.barras(sistema)[-1]
    pares = []
    # por cercanía al sistema no: la ligadura de un acorde muy agudo queda más cerca del sistema de arriba
    ties = [g for g in pag.it.get("TieSegment", []) if sistema[0]["top"] - 8 * sp <= g["start"][1] <= sistema[-1]["bot"] + 8 * sp]
    for i, tie in enumerate(ties):
        sy = tie["start"][1]
        arriba = abs(sy - tie["y1"]) < abs(sy - tie["y0"])
        esperado = sy + (.4 * sp if arriba else -.4 * sp)
        for j, h in enumerate(cabezas):
            if h["x"] < tie["x0"] + sp and tie["x0"] - h["x1"] < 2 * sp and abs(h["y"] - esperado) < .9 * sp:
                # en un acorde varias cabezas encajan con el inicio: la otra punta cae sobre una cabeza a la misma altura
                # (salvo si la ligadura sigue en el sistema siguiente)
                llega = tie["x1"] >= der - sp or any(abs(o["y"] - h["y"]) < .3 * sp and -1.5 * sp <= o["x0"] - tie["x1"] <= sp for o in cabezas)
                pares.append((abs(h["y"] - esperado) + abs(tie["x0"] - h["x"]) * .3 + (0 if llega else sp), i, j))
    usadas, hechas = set(), set()
    for _, i, j in sorted(pares):
        if i not in usadas and j not in hechas:
            usadas.add(i)
            hechas.add(j)
            cabezas[j]["liga"] = True


def enganchar_expresion(pag, compases_pag, pendientes):
    """Cada extremo va al evento más cercano de la página: una ligadura alta puede quedar más cerca de otro
    sistema. Un tramo que empieza o acaba en el borde continúa en el sistema vecino."""
    sp = pag.sp
    notas = [e for c in compases_pag for e in c["ev"] if e["tipo"] == "nota"]
    if not notas:
        return

    def mas_cerca(punto):
        x, y = punto
        return min(notas, key=lambda e: abs(e["x"] - x) + .25 * min(abs(v - y) for v in [e["extremo"], *(h["y"] for h in e["cabezas"])]))

    for s in sorted(pag.it.get("SlurSegment", []), key=lambda g: (g["y0"] // (20 * sp), g["x0"])):
        ini, fin = mas_cerca(s["start"]), mas_cerca(s["fin"])
        sistema = next(c["sistema"] for c in compases_pag if any(e is fin for e in c["ev"]))
        en_sis = [e["x"] for c in compases_pag if c["sistema"] is sistema for e in c["ev"]]
        der = pag.barras(sistema)[-1]
        if s["x0"] > min(en_sis) - 1.6 * sp:
            ligadura = {}
            ini.setdefault("abre", []).append(ligadura)
        else:
            ligadura = pendientes.pop(0) if pendientes else {}
        if s["x1"] < der:
            fin.setdefault("cierra", []).append(ligadura)
        else:
            pendientes.append(ligadura)


ARTICULACIONES = {"accent", "staccato", "staccatissimo", "tenuto", "strong-accent"}  # nombres de glifos.json = MusicXML


def enganchar_articulaciones(pag, sistema, evs_sistema):
    """Cada articulación va a la nota más cercana. El nombre sale del catálogo; sin él, solo el tenuto, por ser plano."""
    sp = pag.sp
    notas = [e for e in evs_sistema if e["tipo"] == "nota"]
    otras = 0
    for a in (g for g in reconocer(pag.ruta, "Articulation") if pag.sistema_de(g["y"]) is sistema):
        nombre = a["nombre"] or ("tenuto" if (a["y1"] - a["y0"]) / sp < .3 else None)
        if nombre not in ARTICULACIONES or not notas:
            otras += 1
            continue
        e = min(notas, key=lambda e: abs(e["x"] - a["x"]) * 3 + min(abs(h["y"] - a["y"]) for h in e["cabezas"]))
        e.setdefault("artic", []).append(nombre)
    # la fermata, sobre la nota o el silencio de debajo (o encima, si va invertida)
    for f in (g for g in reconocer(pag.ruta, "Fermata") if pag.sistema_de(g["y"]) is sistema and evs_sistema):
        alto = lambda e: min([abs(h["y"] - f["y"]) for h in e["cabezas"]] or [abs(e["y"] - f["y"])])
        min(evs_sistema, key=lambda e: abs(e["x"] - f["x"]) * 3 + alto(e))["fermata"] = f["nombre"] or "upright"
    return otras


DINAMICAS = {"p", "pp", "ppp", "pppp", "mp", "mf", "f", "ff", "fff", "ffff", "sf", "sfz", "sffz", "fz", "rf", "rfz", "fp", "sfp"}


def enganchar_dinamicas(pag, sistema, evs_sistema):
    """Las letras contiguas forman la dinámica (m + f; se solapan por el kerning). Entre dos pentagramas pertenece al de arriba, como en piano;
    va delante del evento más cercano de su pentagrama."""
    sp = pag.sp
    letras = sorted((g for g in reconocer(pag.ruta, "Dynamic") if pag.sistema_de(g["y"]) is sistema and g["nombre"]), key=lambda g: g["x0"])
    palabras = []
    for g in letras:
        p = next((p for p in palabras if min(p[-1]["y1"], g["y1"]) > max(p[-1]["y0"], g["y0"]) and -sp < g["x0"] - p[-1]["x1"] < .5 * sp), None)
        (p.append(g) if p else palabras.append([g]))
    for p in palabras:
        nombre, y, x = "".join(g["nombre"] for g in p), p[0]["y"], p[0]["x0"]
        encima = [i for i in range(len(sistema)) if sistema[i]["top"] < y]
        penta = max(encima) if encima else 0
        en = [e for e in evs_sistema if e["penta"] == penta]
        if nombre in DINAMICAS and en:
            min(en, key=lambda e: abs(e["x"] - x)).setdefault("dinamicas", []).append((nombre, penta, "below" if encima else "above"))


def enganchar_arpegios(pag, sistema, evs_sistema):
    """La línea ondulada viene en trozos apilados; el más ancho es la flecha. Va al acorde de su derecha en cada
    pentagrama que cubre."""
    sp = pag.sp
    arpegios = []
    for g in sorted((g for g in pag.it.get("Arpeggio", []) if pag.sistema_de(g["y"]) is sistema), key=lambda g: g["y0"]):
        a = next((a for a in arpegios if abs(a[-1]["x"] - g["x"]) < sp and g["y0"] - a[-1]["y1"] < .5 * sp), None)
        (a.append(g) if a else arpegios.append([g]))
    for a in arpegios:
        y0, y1, x1 = a[0]["y0"], a[-1]["y1"], max(g["x1"] for g in a)
        ancho = lambda g: g["x1"] - g["x0"]
        flecha = max(a, key=ancho) if ancho(max(a, key=ancho)) > 1.5 * ancho(min(a, key=ancho)) else None
        sentido = "" if flecha is None else "down" if flecha is a[-1] else "up" if flecha is a[0] else ""
        cand = [e for e in evs_sistema if e["tipo"] == "nota" and any(y0 - .5 * sp <= h["y"] <= y1 + .5 * sp for h in e["cabezas"])
                and 0 < min(h["x0"] for h in e["cabezas"]) - x1 < 3 * sp]
        if cand:
            d = min(min(h["x0"] for h in e["cabezas"]) for e in cand)
            for e in cand:
                if min(h["x0"] for h in e["cabezas"]) < d + sp:
                    e["arpegio"] = sentido


def repeticiones(pag, compases_pag):
    """Los puntos de repetición son BarLine diminutos: a la derecha de su barra abren la repetición del compás en que
    caen; a la izquierda la cierran."""
    sp = pag.sp
    barras = [g for g in pag.it.get("BarLine", []) if g["y1"] - g["y0"] > 3 * sp]
    for p in (g for g in pag.it.get("BarLine", []) if g["y1"] - g["y0"] < .6 * sp and g["x1"] - g["x0"] < .6 * sp):
        sistema = pag.sistema_de(p["y"])
        c = next((c for c in compases_pag if c["sistema"] is sistema and c["x0"] <= p["x"] < c["x1"]), None)
        cerca = [b for b in barras if pag.sistema_de(b["y"]) is sistema]
        if c and cerca:
            c["rep_ini" if p["x"] > min(cerca, key=lambda b: abs(b["x"] - p["x"]))["x"] else "rep_fin"] = True


def casillas(paginas, compases):
    """Casillas de 1.ª y 2.ª vez. El corchete es una polilínea; con gancho al final se cierra (stop), sin él queda
    abierta (discontinue) o sigue en el sistema siguiente. El número es texto: se deduce del orden, una casilla
    pegada a la anterior es la siguiente.
    shortcut: solo el formato de escritorio (polilínea); en web el corchete va en un path y se ignora."""
    tramos = []
    for pag in paginas:
        sp = pag.sp
        for g in sorted((g for g in pag.it.get("VoltaSegment", []) if "puntos" in g), key=lambda g: (g["y0"], g["x0"])):
            debajo = [s for s in pag.sistemas if s[0]["top"] > g["y0"]]  # el corchete va encima de su sistema
            if not debajo:
                continue
            sistema = min(debajo, key=lambda s: s[0]["top"])
            cs = [c for c in compases if c["sistema"] is sistema and c["x0"] < g["x1"] - sp and c["x1"] > g["x0"] + sp]
            if not cs:
                continue
            cerrada = g["puntos"][-1][1] > g["puntos"][-2][1] + .5 * sp
            sigue = not cerrada and g["x1"] >= pag.barras(sistema)[-1] - sp
            if tramos and tramos[-1]["sigue"] and cs[0]["n"] == tramos[-1]["cs"][-1]["n"] + 1 and (cs[0]["nuevo"] or cs[0]["pagina"]):
                tramos[-1].update(cs=tramos[-1]["cs"] + cs, cerrada=cerrada, sigue=sigue)
            else:
                tramos.append(dict(cs=cs, cerrada=cerrada, sigue=sigue))
    for i, t in enumerate(tramos):
        pegada = i and t["cs"][0]["n"] == tramos[i - 1]["cs"][-1]["n"] + 1
        t["num"] = tramos[i - 1]["num"] + 1 if pegada else 1
        t["cs"][0]["casilla_ini"] = t["num"]
        t["cs"][-1]["casilla_fin"] = (t["num"], "stop" if t["cerrada"] else "discontinue")


def octavas(pag):
    """Tramos de 8va/8vb de la página como (pentagrama, x0, x1, octavas, cierra). La línea sale de la parte alta del dígito
    en un 8va (afecta al pentagrama de debajo) y de la baja en un 8vb (al de encima). La posición no basta: una línea
    alta de 8va puede quedar más cerca del sistema anterior.
    Sin gancho al final, el tramo sigue en el sistema siguiente.
    shortcut: el dígito no se lee, así que 15ma cuenta como 8va; leerlo si aparece una partitura con 15ma."""
    sp = pag.sp
    gs = pag.it.get("OttavaSegment", [])
    digitos = [g for g in gs if g["y1"] - g["y0"] > 1.3 * sp]
    ganchos = [g for g in gs if .5 * sp < g["y1"] - g["y0"] <= 1.3 * sp]
    tramos = []  # los guiones de la línea pueden venir sueltos: se juntan los que siguen a la misma altura
    for g in sorted((g for g in gs if g["y1"] - g["y0"] < .3 * sp), key=lambda g: g["x0"]):
        t = next((t for t in tramos if abs(t["y"] - g["y"]) < .3 * sp and 0 <= g["x0"] - t["x1"] < 3 * sp), None)
        if t:
            t["x1"] = max(t["x1"], g["x1"])
        else:
            tramos.append(dict(x0=g["x0"], x1=g["x1"], y=g["y"]))
    out = []
    for t in tramos:
        izq = [d for d in digitos if -.5 * sp < t["x0"] - d["x1"] < 2 * sp and abs(d["y"] - t["y"]) < 1.5 * sp]
        alta = not izq or t["y"] < max(izq, key=lambda d: d["x1"])["y"]  # sin dígito: 8va, lo habitual
        debajo = [p for p in pag.pentas if p["top"] > t["y"]]
        encima = [p for p in pag.pentas if p["bot"] < t["y"]]
        p = (min(debajo, key=lambda p: p["top"]) if debajo else None) if alta else (max(encima, key=lambda p: p["bot"]) if encima else None)
        if p:
            cierra = any(abs(g["x"] - t["x1"]) < .5 * sp for g in ganchos)
            out.append((p, min(d["x0"] for d in izq) if izq else t["x0"], t["x1"], 1 if alta else -1, cierra))
    return out


def nota_xml(e, h, chord, slurs, bm, u):
    x = ["<note>"]
    if e.get("adorno"):
        x.append('<grace slash="yes"/>')
    if chord:
        x.append("<chord/>")
    if h is None:
        x.append("<rest/>")
    else:
        a = f"<alter>{h['alter']}</alter>" if h["alter"] else ""
        x.append(f"<pitch><step>{h['step']}</step>{a}<octave>{h['octava']}</octave></pitch>")
    if not e.get("adorno"):
        x.append(f"<duration>{u(duracion(e))}</duration>")
    if h and h.get("liga_fin"):
        x.append('<tie type="stop"/>')
    if h and h.get("liga_ini"):
        x.append('<tie type="start"/>')
    x.append(f"<voice>{e['voz']}</voice><type>{TYPES.get(e['base'], 'quarter')}</type>" + ("<dot/>" if e["puntillo"] else ""))
    if h and h.get("impresa"):
        x.append(f"<accidental>{h['impresa']}</accidental>")
    if "tresillo" in e:
        x.append(f"<time-modification><actual-notes>{e['tresillo'][0]}</actual-notes><normal-notes>{e['tresillo'][1]}</normal-notes></time-modification>")
    if h and e["up"] is not None:
        x.append(f"<stem>{'up' if e['up'] else 'down'}</stem>")
    if h and e.get("slash"):
        x.append("<stem>none</stem><notehead>slash</notehead>")
    x.append(f"<staff>{e['penta'] + 1}</staff>")
    if h and bm:
        x.append(f'<beam number="1">{bm}</beam>')
    n = []
    if h and h.get("liga_fin"):
        n.append('<tied type="stop"/>')
    if h and h.get("liga_ini"):
        n.append('<tied type="start"/>')
    if h and "arpegio" in e:  # en cada cabeza del acorde
        sentido = f' direction="{e["arpegio"]}"' if e["arpegio"] else ""
        n.append(f"<arpeggiate{sentido}/>")
    if not chord:
        n += slurs
        if e.get("t_ini"):
            n.append('<tuplet type="start" bracket="no" show-number="actual"/>')
        if e.get("t_fin"):
            n.append('<tuplet type="stop"/>')
        if e.get("fermata"):
            n.append(f'<fermata type="{e["fermata"]}"/>')
        if h and e.get("artic"):
            n.append("<articulations>" + "".join(f"<{a}/>" for a in e["artic"]) + "</articulations>")
    if n:
        x.append("<notations>" + "".join(n) + "</notations>")
    x.append("</note>")
    return "".join(x)


@lru_cache(maxsize=None)
def contornos_svg(ruta):
    import catalogo  # aquí: catalogo importa de este módulo
    return catalogo.leer(ruta)


@lru_cache(maxsize=None)
def catalogo_glifos():
    ruta = Path(__file__).with_name("glifos.json")
    return json.loads(ruta.read_text(encoding="utf-8"))["glifos"] if ruta.exists() else {}


def reconocer(ruta, clase):
    """Glifos de una clase como [dict(nombre, x0, y0, x1, y1, x, y)], nombrados por su contorno con glifos.json (la
    fuente por defecto de MuseScore 4). Un contorno dentro de otro es su hueco. Sin coincidencia, nombre None."""
    import catalogo
    sp, els = contornos_svg(ruta)
    nombres = catalogo_glifos().get(clase, {})
    cs = [c for k, cc in els if k == clase for c in cc if len(c) > 1]
    cajas = [catalogo.caja(c) for c in cs]
    out = []
    for i in range(len(cs)):
        if any(j != i and catalogo.dentro(cajas[i], cajas[j], sp) and not catalogo.dentro(cajas[j], cajas[i], sp) for j in range(len(cs))):
            continue
        grupo = [cs[i]] + [cs[j] for j in range(len(cs)) if j != i and catalogo.dentro(cajas[j], cajas[i], sp)]
        nombre = next((k for k, g in nombres.items() if catalogo.iguales(catalogo.firma(grupo, sp), g)), None)
        x0, y0, x1, y1 = cajas[i]
        out.append(dict(nombre=nombre, firma=catalogo.firma(grupo, sp), x0=x0, y0=y0, x1=x1, y1=y1, x=(x0 + x1) / 2, y=(y0 + y1) / 2))
    return out


def leer_cifras(ruta, pag):
    """Cifras de compás de una página como [(sistema, x, num, den)], con num y den como listas de dígitos: dict con
    d (el dígito, o None si el catálogo no lo conoce) y la firma de su contorno, para nombrarlo con la partitura."""
    sp = pag.sp
    leidos = [dict(g, d=g["nombre"]) for g in reconocer(ruta, "TimeSig")]
    out = []
    for sistema in pag.sistemas:
        p = sistema[0]  # basta el pentagrama de arriba: todos llevan la misma cifra
        medio = (p["top"] + p["bot"]) / 2
        en = sorted((d for d in leidos if p["top"] - .5 * sp <= d["y"] <= p["bot"] + .5 * sp), key=lambda d: d["x0"])
        while en:  # columnas: dígitos que se solapan en x (12/8 lleva dos arriba)
            col = [d for d in en if d["x0"] < en[0]["x0"] + 2 * sp]
            en = en[len(col):]
            num = [d for d in col if d["y"] < medio]
            den = [d for d in col if d["y"] > medio]
            if num and den:
                out.append((sistema, min(d["x0"] for d in col), num, den))
    return out


def convertir(rutas, compas, defecto=None):
    """compas fija el compás si el SVG no trae cifras reconocibles; si tampoco hay compas, se deduce de las duraciones
    y, si no se puede, se usa defecto. Las cifras reconocidas mandan, también en los cambios a mitad de obra."""
    paginas = [Pagina(r) for r in rutas]
    primero = paginas[0]
    n = len(primero.sistemas[0])
    compases = []  # dict(eventos, sistema, pag, barras, nuevo_sistema, nueva_pagina, x0, x1)
    articulaciones = 0
    for np, pag in enumerate(paginas, 1):
        for ns, sistema in enumerate(pag.sistemas):
            if len(sistema) != n:
                aviso(f"página {np}: un sistema con {len(sistema)} pentagramas en vez de {n}; se omite")
                continue
            evs, barras = construir_eventos(pag, sistema, np)
            for i, e in enumerate(evs):
                pct = {pag.penta_de(sistema, g["y"]) for g in pag.it.get("MeasureRepeat", []) if pag.sistema_de(g["y"]) is sistema and barras[i] <= g["x"] < barras[i + 1]}
                compases.append(dict(ev=e, pag=pag, sistema=sistema, x0=barras[i], x1=barras[i + 1], pct=pct, nuevo=i == 0 and bool(compases), pagina=i == 0 and ns == 0 and np > 1))
    # cifras de compás: antes de las notas de un compás valen para él; después, para el siguiente (la de cortesía
    # al final del sistema, o la que MuseScore pone antes de una barra de inicio de repetición)
    for ruta, pag in zip(rutas, paginas):
        for sistema, x, a, b in leer_cifras(ruta, pag):
            k = next((k for k, c in enumerate(compases) if c["sistema"] is sistema and c["x0"] - pag.sp <= x < c["x1"]), None)
            if k is not None and not all(e["x"] > x for e in compases[k]["ev"]):
                k = k + 1 if k + 1 < len(compases) else None
            if k is not None:
                compases[k]["cifra"] = (a, b)
    import catalogo
    aprendidos = []  # (firma, dígito): cifras que el catálogo no conoce, nombradas con la propia partitura

    def valor(digitos):
        ds = [d["d"] or next((v for f, v in aprendidos if catalogo.iguales(f, d["firma"])), None) for d in digitos]
        return int("".join(ds)) if all(ds) else None

    def aprender(digitos, v):
        if len(digitos) == len(str(v)):
            aprendidos.extend((d["firma"], ch) for d, ch in zip(digitos, str(v)) if d["d"] is None)

    cifra = compases[0].get("cifra")
    if compas:
        actual = tuple(map(int, compas.split("/")))
    elif cifra and valor(cifra[0]) and valor(cifra[1]):
        actual = (valor(cifra[0]), valor(cifra[1]))
    else:
        largos = Counter()  # los silencios de compás completo no cuentan
        for c in compases:
            ev = [e for e in c["ev"] if e["base"] is not None]
            if ev:
                largos[barrer(ev, primero.sp)[0]] += 1
        largo = largos.most_common(1)[0][0] if largos else None
        if largo and largo.denominator == 1:
            aviso(f"compás deducido de las duraciones ({largo} corcheas); no se distingue 6/8 de 3/4: usa --compas para fijarlo")
            actual = (int(largo), 8) if largo % 2 else (int(largo) // 2, 4)
        elif defecto:
            aviso(f"no se reconocen las cifras del SVG ni se deduce el compás: se usa {defecto}")
            actual = tuple(map(int, defecto.split("/")))
        else:
            sys.exit(f"no se pudo deducir el compás ({largo} corcheas): usa --compas")
    if cifra:  # la primera cifra, ya sabida, enseña sus dígitos para leer las siguientes
        aprender(cifra[0], actual[0])
        aprender(cifra[1], actual[1])
    # armaduras, con el mismo criterio de compás que las cifras; la de cada sistema repite la vigente
    for pag in paginas:
        for sistema, x, f in leer_armaduras(pag):
            k = next((k for k, c in enumerate(compases) if c["sistema"] is sistema and c["x0"] - pag.sp <= x < c["x1"]), None)
            if k is not None and not all(e["x"] > x for e in compases[k]["ev"]):
                k = k + 1 if k + 1 < len(compases) else None
            if k is not None:
                compases[k]["armadura_leida"] = f
    fifths = 0
    for c in compases:
        fifths = c["fifths"] = c.get("armadura_leida", fifths)
    malos = []
    t_abs = F(0)
    for idx, c in enumerate(compases, 1):
        if "cifra" in c and idx > 1:
            num, den = valor(c["cifra"][0]), valor(c["cifra"][1])
            if den and not num:
                num = probar_numerador(c, den)
                if num:
                    aprender(c["cifra"][0], num)
            if num and den:
                actual = (num, den)
        c["compas"] = actual
        largo = F(8 * c["compas"][0], c["compas"][1])
        total, fallos = barrer(c["ev"], c["pag"].sp, largo)
        if total != largo or fallos:  # tresillos sin número: muchas ediciones lo imprimen solo en los primeros
            total, fallos = tresillos_implicitos(c, largo, total, fallos)
        c["n"], c["largo"], c["t0"] = idx, max(total, F(0)), t_abs
        if (total != largo and not c["pct"]) or fallos:
            malos.append(idx)
        t_abs += total
        repartir_voces(c["ev"])
    for pag in paginas:
        repeticiones(pag, [c for c in compases if c["pag"] is pag])
    casillas(paginas, compases)
    # claves, alturas: por sistema
    clave = {i: None for i in range(n)}
    for c in compases:
        c["claves"] = []
    for k, c in enumerate(compases):
        sistema, pag = c["sistema"], c["pag"]
        cols = sorted({(e["x"], e["t"]) for e in c["ev"]})
        for g in sorted((g for g in pag.it.get("Clef", []) if pag.sistema_de(g["y"]) is sistema and c["x0"] <= g["x"] < c["x1"]), key=lambda g: g["x"]):
            sign = "G" if (g["y1"] - g["y0"]) / pag.sp > 4.5 else "F"
            penta = pag.penta_de(sistema, g["y"])
            if clave[penta] == sign:
                continue
            clave[penta] = sign
            siguiente = [t for x, t in cols if x > g["x"]]
            if siguiente:
                c["claves"].append((min(siguiente), penta, sign))
            elif k + 1 < len(compases):
                compases[k + 1]["claves"].append((F(0), penta, sign))
    # alturas: la clave vigente en cada cabeza, en orden de tiempo
    clave = {i: None for i in range(n)}
    octs = {}
    for c in compases:
        pag, sistema = c["pag"], c["sistema"]
        if id(pag) not in octs:
            octs[id(pag)] = octavas(pag)
        cambios = sorted(c["claves"], key=lambda a: a[0])
        for t, penta, sign in cambios:
            if t == 0:
                clave[penta] = sign
        for e in sorted(c["ev"], key=lambda e: e["t"]):
            vig = dict(clave)
            for t, penta, sign in cambios:
                if t <= e["t"]:
                    vig[penta] = sign
            for h in e["cabezas"]:
                pos = round((sistema[h["penta"]]["bot"] - h["y"]) / (pag.sp / 2))
                num_paso = CLEF_BASE[vig[h["penta"]]] + pos
                h["tramo"] = next((o for o in octs[id(pag)] if o[0] is sistema[h["penta"]] and o[1] <= h["x"] <= o[2]), None)
                sube = h["tramo"][3] if h["tramo"] else 0
                h["step"], h["octava"], h["sube"] = STEPS[num_paso % 7], num_paso // 7 + sube, sube
        for t, penta, sign in cambios:
            clave[penta] = sign
    # 8va para dibujar (la altura ya es la real): uno por racha de notas desplazadas; un tramo con gancho final
    # termina aunque el siguiente empiece justo después, como en las casillas
    for p in range(n):
        antes, ult, tramo = 0, None, None
        for _, e in sorted(((c["t0"] + e["t"], e) for c in compases for e in c["ev"] if e["tipo"] == "nota" and e["penta"] == p), key=lambda a: a[0]):
            sube, nuevo = e["cabezas"][0]["sube"], e["cabezas"][0]["tramo"]
            if sube != antes or sube and nuevo is not tramo and tramo[4]:
                if antes:
                    ult["oct_fin"] = antes
                if sube:
                    e["oct_ini"] = sube
            antes, ult, tramo = sube, e, nuevo
        if antes:
            ult["oct_fin"] = antes
    # alteraciones impresas
    for c in compases:
        pag, sistema = c["pag"], c["sistema"]
        cabezas = [h for e in c["ev"] for h in e["cabezas"]]
        for a in (g for g in pag.it.get("Accidental", []) if pag.sistema_de(g["y"]) is sistema and c["x0"] <= g["x"] < c["x1"]):
            cand = [h for h in cabezas if h["x0"] > a["x0"]]
            if not cand:
                continue
            tipo = clase_alteracion(a, pag.sp)
            off = .2 * pag.sp if tipo in ("flat", "flat-flat") else 0
            h = min(cand, key=lambda h: abs(h["y"] - a["y"] - off) + (h["x0"] - a["x1"]) * .2)
            h["impresa"] = tipo
    # ligaduras: cada tramo marca su nota de origen; el destino es la siguiente con la misma altura
    pendientes = []
    otras = 0
    for pag in paginas:
        for sistema in pag.sistemas:
            evs = [e for c in compases if c["sistema"] is sistema for e in c["ev"]]
            enganchar_ligaduras(pag, sistema, evs)
            otras += enganchar_articulaciones(pag, sistema, evs)
            enganchar_dinamicas(pag, sistema, evs)
            enganchar_arpegios(pag, sistema, evs)
        enganchar_expresion(pag, [c for c in compases if c["pag"] is pag], pendientes)
    if otras:
        aviso(f"{otras} articulaciones sin reconocer")
    todos = [(c["t0"] + e["t"], e, h) for c in compases for e in c["ev"] for h in e["cabezas"]]
    todos.sort(key=lambda a: a[0])
    sin_destino = 0
    for t, e, h in todos:
        if not h.get("liga"):
            continue
        fin = t + duracion(e)
        cand = [(t2, h2) for t2, e2, h2 in todos if t2 >= fin and not h2.get("liga_fin") and (h2["penta"], h2["step"], h2["octava"]) == (h["penta"], h["step"], h["octava"])]
        if not cand:
            sin_destino += 1
            continue
        h["liga_ini"] = True
        min(cand, key=lambda a: a[0])[1]["liga_fin"] = True
    if sin_destino:
        aviso(f"{sin_destino} ligaduras de prolongación sin nota de destino")
    # alteración final: armadura + impresas + arrastre dentro del compás + ligada desde el compás anterior
    PRINT = {"flat-flat": -2, "flat": -1, "natural": 0, "sharp": 1, "double-sharp": 2}
    for c in compases:
        memo = {}
        for e in sorted(c["ev"], key=lambda e: e["t"]):
            for h in e["cabezas"]:
                key = (h["penta"], h["step"], h["octava"] - h["sube"])  # la alteración sigue a la nota escrita, no a la que suena con 8va
                if "impresa" in h:
                    memo[key] = PRINT[h["impresa"]]
                h["alter"] = memo.get(key, altera_armadura(c["fifths"]).get(h["step"], 0))
    for i, (t, e, h) in enumerate(todos):  # una nota ligada hereda la alteración de la anterior
        if h.get("liga_ini"):
            fin = t + duracion(e)
            for t2, e2, h2 in todos[i + 1:]:
                if t2 >= fin and h2.get("liga_fin") and (h2["penta"], h2["step"], h2["octava"]) == (h["penta"], h["step"], h["octava"]):
                    if "impresa" not in h2:
                        h2["alter"] = h["alter"]
                    break
    # barras
    grupos = {}
    for c in compases:
        for e in c["ev"]:
            if e["barra"] is not None:
                grupos.setdefault((c["n"], e["barra"]), []).append(e)
    for g in grupos.values():
        g.sort(key=lambda e: e["t"])
        for i, e in enumerate(g):
            e["bm"] = None if len(g) < 2 else "begin" if i == 0 else "end" if i == len(g) - 1 else "continue"
    # ligaduras de expresión: un número libre mientras cada una siga abierta
    orden = [e for _, e in sorted(((c["t0"] + e["t"], e) for c in compases for e in c["ev"]), key=lambda a: a[0])]
    if pendientes:  # siguen en una página que no tenemos: se cierran en la última nota
        ultima = next(e for e in reversed(orden) if e["tipo"] == "nota")
        ultima.setdefault("cierra", []).extend(pendientes)
    abiertas, libres = {}, list(range(1, 7))
    for e in orden:
        e["slurs"] = []
        for lig in e.get("abre", []):
            abiertas[id(lig)] = libres.pop(0) if libres else 6
            e["slurs"].append(f'<slur type="start" number="{abiertas[id(lig)]}"/>')
        for lig in e.get("cierra", []):
            if id(lig) in abiertas:
                numero = abiertas.pop(id(lig))
                e["slurs"].append(f'<slur type="stop" number="{numero}"/>')
                libres.append(numero)
    for m in malos[:20]:
        aviso(f"el compás {m} no suma {'/'.join(map(str, compases[m - 1]['compas']))}: revísalo")
    return xml(compases, n), compases, malos


def xml(compases, n):
    largo = lambda c: F(8 * c["compas"][0], c["compas"][1])
    # unidades por corchea: el mínimo común múltiplo de los denominadores, para que fusas y grupos irregulares sean enteros
    por_corchea = lcm(*(largo(c).denominator for c in compases), *(f.denominator for c in compases for e in c["ev"] for f in (duracion(e), e["t"])),
                      *(t.denominator for c in compases for t, _, _ in c["claves"]))
    u = lambda f: int(f * por_corchea)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
           '<score-partwise version="4.0">',
           f'<part-list><score-part id="P1"><part-name>Instrumento</part-name></score-part></part-list><part id="P1">']
    for c in compases:
        out.append(f'<measure number="{c["n"]}">')
        if c["pagina"]:
            out.append('<print new-page="yes"/>')
        elif c["nuevo"]:
            out.append('<print new-system="yes"/>')
        claves = sorted(c["claves"], key=lambda a: a[0])
        inicio = {p: s for t, p, s in claves if t == 0}
        cl = "".join(f'<clef number="{p + 1}"><sign>{s}</sign><line>{2 if s == "G" else 4}</line></clef>' for p, s in sorted(inicio.items()))
        tiempo = f'<time><beats>{c["compas"][0]}</beats><beat-type>{c["compas"][1]}</beat-type></time>'
        if c["n"] == 1:
            out.append(f'<attributes><divisions>{2 * u(F(1))}</divisions><key><fifths>{c["fifths"]}</fifths></key>{tiempo}<staves>{n}</staves>{cl}</attributes>')
        else:
            ant = compases[c["n"] - 2]
            clave_nueva = f'<key><fifths>{c["fifths"]}</fifths></key>' if c["fifths"] != ant["fifths"] else ""
            tiempo = tiempo if c["compas"] != ant["compas"] else ""
            if clave_nueva or tiempo or cl:
                out.append("<attributes>" + clave_nueva + tiempo + cl + "</attributes>")
        for t, p, s in claves:  # cambio a media medida: antes de las notas, en su tiempo
            if t:
                d = u(t)
                out.append(f'<forward><duration>{d}</duration></forward><attributes><clef number="{p + 1}"><sign>{s}</sign><line>{2 if s == "G" else 4}</line></clef></attributes><backup><duration>{d}</duration></backup>')
        ant = compases[c["n"] - 2]["pct"] if c["n"] > 1 else set()
        for p in sorted(c["pct"] - ant):
            out.append(f'<attributes><measure-style number="{p + 1}"><measure-repeat type="start">1</measure-repeat></measure-style></attributes>')
        for p in sorted(ant - c["pct"]):
            out.append(f'<attributes><measure-style number="{p + 1}"><measure-repeat type="stop"/></measure-style></attributes>')
        if c.get("rep_ini") or "casilla_ini" in c:
            out.append('<barline location="left">' + ("<bar-style>heavy-light</bar-style>" if c.get("rep_ini") else "")
                       + (f'<ending number="{c["casilla_ini"]}" type="start"/>' if "casilla_ini" in c else "")
                       + ('<repeat direction="forward"/>' if c.get("rep_ini") else "") + "</barline>")
        cursor = F(0)
        for p in sorted(c["pct"]):  # el compás con % no lleva notas: un silencio de compás que no se imprime
            out.append(f'<note print-object="no"><rest measure="yes"/><duration>{u(largo(c))}</duration><voice>{p * 4 + 1}</voice><staff>{p + 1}</staff></note><backup><duration>{u(largo(c))}</duration></backup>')
        for v in sorted({e["voz"] for e in c["ev"]}):
            if cursor:
                out.append(f"<backup><duration>{u(cursor)}</duration></backup>")
                cursor = F(0)
            for e in sorted((e for e in c["ev"] if e["voz"] == v), key=lambda e: (e["t"], not e.get("adorno"))):
                if e["t"] > cursor:
                    out.append(f'<forward><duration>{u(e["t"] - cursor)}</duration><voice>{v}</voice><staff>{e["penta_voz"] + 1}</staff></forward>')
                    cursor = e["t"]
                for nombre, p, lugar in e.pop("dinamicas", []):  # una vez, aunque el evento tenga varias cabezas
                    out.append(f'<direction placement="{lugar}"><direction-type><dynamics><{nombre}/></dynamics></direction-type><staff>{p + 1}</staff></direction>')
                octava = lambda tipo, o: (f'<direction placement="{"above" if o > 0 else "below"}"><direction-type><octave-shift type="{tipo}" '
                                          f'size="{8 if abs(o) == 1 else 15}"/></direction-type><staff>{e["penta"] + 1}</staff></direction>')
                if e.get("oct_ini"):  # 8va: la nota se escribe una octava más baja de como suena
                    out.append(octava("down" if e["oct_ini"] > 0 else "up", e["oct_ini"]))
                if e["tipo"] == "silencio":
                    out.append(nota_xml(e, None, False, e.get("slurs", []), None, u))
                else:
                    for i, h in enumerate(sorted(e["cabezas"], key=lambda h: -h["y"])):
                        out.append(nota_xml(e, h, i > 0, e.get("slurs", []), e.get("bm"), u))
                if e.get("oct_fin"):
                    out.append(octava("stop", e["oct_fin"]))
                cursor = e["t"] + duracion(e)
        if c.get("rep_fin") or "casilla_fin" in c:
            out.append('<barline location="right">' + ("<bar-style>light-heavy</bar-style>" if c.get("rep_fin") else "")
                       + ('<ending number="{}" type="{}"/>'.format(*c["casilla_fin"]) if "casilla_fin" in c else "")
                       + ('<repeat direction="backward"/>' if c.get("rep_fin") else "") + "</barline>")
        out.append("</measure>")
    out.append("</part></score-partwise>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg", nargs="+", help="páginas en orden")
    ap.add_argument("-o", "--salida", required=True)
    ap.add_argument("--compas", help="por ejemplo 9/8; solo si el SVG no trae cifras reconocibles. Si falta, se deduce")
    a = ap.parse_args()
    texto, compases, malos = convertir(a.svg, a.compas, defecto="4/4")
    Path(a.salida).write_text(texto, encoding="utf-8")
    notas = sum(len(e["cabezas"]) for c in compases for e in c["ev"])
    print(f"{a.salida}: {len(compases)} compases, {notas} notas, {len(malos)} compases que no cuadran")


if __name__ == "__main__":
    main()
