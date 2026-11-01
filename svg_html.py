"""Extrae los <svg> de un HTML y los renderiza a PNG.

Uso: python svg_html.py entrada.html [carpeta_salida]
"""
import re
import sys
from pathlib import Path

import cairosvg

html = Path(sys.argv[1]).read_text(encoding="utf-8")
salida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(sys.argv[1]).with_suffix("")
salida.mkdir(parents=True, exist_ok=True)

# shortcut: regex no maneja <svg> anidados, usar un parser HTML si aparecen
svgs = re.findall(r"<svg\b.*?</svg>", html, re.S | re.I)
assert svgs, "no hay <svg> en el HTML"

for i, svg in enumerate(svgs, 1):
    if "xmlns=" not in svg[:200]:  # en HTML es opcional, para cairosvg no
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    destino = salida / f"svg_{i}.png"
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(destino))
    print(destino)
