"""Une los SVG de una carpeta en un PDF A4 para imprimir, con Chrome de Windows. Correr desde WSL.

Uso: python svg2pdf.py carpeta nombre   -> D:\\Nahum\\omr_partituras\\svg_to_pdf\\nombre.pdf

Falla sin generar nada si algún SVG pesa 0 bytes o está dañado: Chrome no da error con ellos y deja un
icono de imagen rota en esa página.
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

CHROME = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
SALIDA = Path("/mnt/d/Nahum/omr_partituras/svg_to_pdf")
ESTILO = ("@page{size:A4;margin:0}html,body{margin:0}"
          "img{display:block;width:210mm;max-height:297mm;object-fit:contain;break-after:page}"
          "img:last-child{break-after:auto}")


def orden_natural(ruta):
    """score_2 antes que score_10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", ruta.name)]


def problemas(svgs):
    errores = []
    for ruta in svgs:
        if ruta.stat().st_size == 0:
            errores.append(f"{ruta.name}: pesa 0 bytes")
            continue
        try:
            raiz = ET.parse(ruta).getroot()
        except ET.ParseError as e:
            errores.append(f"{ruta.name}: está dañado ({e})")
            continue
        if not raiz.tag.endswith("svg"):
            errores.append(f"{ruta.name}: no es un SVG")
    return errores


def windows(ruta):
    return subprocess.run(["wslpath", "-w", str(ruta)], capture_output=True, text=True, check=True).stdout.strip()


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    carpeta, nombre = Path(sys.argv[1]).resolve(), sys.argv[2]
    if Path(nombre).name != nombre:
        sys.exit(f"el nombre no puede llevar carpetas: {nombre}")
    svgs = sorted(carpeta.glob("*.svg"), key=orden_natural)
    if not svgs:
        sys.exit(f"no hay SVG en {carpeta}")
    errores = problemas(svgs)
    if errores:
        sys.exit("No se generó el PDF:\n  " + "\n  ".join(errores))

    destino = SALIDA / f"{nombre}.pdf"
    temporal = SALIDA / f"{nombre}.tmp.pdf"  # si Chrome falla, un PDF anterior sigue intacto
    html = carpeta / "_imprimir.html"
    html.write_text(f'<!doctype html><meta charset="utf-8"><style>{ESTILO}</style>'
                    + "".join(f'<img src="{quote(r.name)}">' for r in svgs), encoding="utf-8")
    try:
        url = "file:///" + windows(html).replace("\\", "/")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={windows(temporal)}", url], capture_output=True, timeout=120, check=True)
        if not temporal.exists() or temporal.stat().st_size == 0:
            sys.exit("Chrome terminó, pero no generó el PDF")
        os.replace(temporal, destino)
    finally:
        html.unlink()
        temporal.unlink(missing_ok=True)
    print(f"{destino}: {len(svgs)} páginas")


if __name__ == "__main__":
    main()
