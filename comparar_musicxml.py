"""Califica un MusicXML contra una referencia, nota por nota.

Uso: python comparar_musicxml.py referencia.musicxml resultado.musicxml
Una nota cuenta como correcta si coinciden compás, tiempo, duración, nombre, alteración y octava.
"""
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction as F


def leer(ruta):
    notas, silencios, cuenta = Counter(), Counter(), Counter()
    div, en_pct = 1, False
    for part in ET.parse(ruta).getroot().findall("part"):
        for num, m in enumerate(part.findall("measure"), 1):
            t = ult = F(0)
            for e in m:
                if e.tag == "attributes":
                    if e.find("divisions") is not None:
                        div = int(e.find("divisions").text)
                    r = e.find("measure-style/measure-repeat")
                    if r is not None:
                        en_pct = r.get("type") == "start"
                elif e.tag == "backup":
                    t -= F(int(e.find("duration").text), div)
                elif e.tag == "forward":
                    t += F(int(e.find("duration").text), div)
                elif e.tag == "note" and e.find("duration") is not None:
                    d = F(int(e.find("duration").text), div)
                    if e.find("chord") is None:
                        ult = t
                        t += d
                    if e.find("rest") is not None:
                        if e.get("print-object") != "no" and not en_pct:  # bajo un % no se imprime
                            silencios[(num, ult, d)] += 1
                        continue
                    p, a = e.find("pitch"), e.find("pitch/alter")
                    alt = int(float(a.text)) if a is not None else 0
                    notas[(num, ult, d, p.find("step").text, alt, int(p.find("octave").text))] += 1
                    cuenta["ligaduras"] += sum(x.get("type") == "start" for x in e.findall("tie"))
                    cuenta["expresión"] += sum(x.get("type") == "start" for x in e.iter("slur"))
                    cuenta["tenutos"] += len(list(e.iter("tenuto")))
                    cuenta["dosillos/tresillos"] += sum(x.get("type") == "start" for x in e.iter("tuplet"))
    return notas, silencios, cuenta


def comparar(ref, res):
    a, b = leer(ref), leer(res)
    ok = sum((a[0] & b[0]).values())
    return dict(ref=sum(a[0].values()), res=sum(b[0].values()), ok=ok, falta=a[0] - b[0], sobra=b[0] - a[0],
                sil_ok=sum((a[1] & b[1]).values()), sil_ref=sum(a[1].values()), sil_res=sum(b[1].values()),
                cuenta_ref=a[2], cuenta_res=b[2])


if __name__ == "__main__":
    r = comparar(sys.argv[1], sys.argv[2])
    print(f"Notas correctas: {r['ok']} de {r['ref']} ({r['ok'] / r['ref']:.1%}); de más: {sum(r['sobra'].values())}")
    print(f"Silencios visibles correctos: {r['sil_ok']} de {r['sil_ref']} (el resultado tiene {r['sil_res']})")
    for k in sorted(set(r["cuenta_ref"]) | set(r["cuenta_res"])):
        print(f"{k}: referencia {r['cuenta_ref'][k]}, resultado {r['cuenta_res'][k]}")
    por = Counter(k[0] for k in r["falta"].elements())
    print("Compases con notas mal:", dict(sorted(por.items())) or "ninguno")
    for k in sorted(r["falta"].elements(), key=lambda k: k[:2])[:15]:
        print("  falta", k[0], str(k[1]), str(k[2]), *k[3:])
    for k in sorted(r["sobra"].elements(), key=lambda k: k[:2])[:15]:
        print("  sobra", k[0], str(k[1]), str(k[2]), *k[3:])
