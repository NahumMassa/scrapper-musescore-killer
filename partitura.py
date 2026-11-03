"""De un enlace de MuseScore al PDF y al MusicXML, en un paso. Correr desde WSL.

Uso: python partitura.py URL [--nombre NOMBRE] [--compas 9/8]

1. svg_scrape.py baja las hojas (abre Chrome) -> D:\\Nahum\\omr_partituras\\svg_partituras\\<nombre>\\<título>_NN.svg
2. svg2pdf.py   -> svg_to_pdf\\<nombre>.pdf
3. svg2musicxml.py -> svg_to_xml\\<nombre>.musicxml (el generado, sin revisar)

Si el paso 1 sale incompleto (código 2 o 3) no se sigue: un PDF con hojas de menos engaña.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent
BASE = Path("/mnt/d/Nahum/omr_partituras")
sys.path.insert(0, str(REPO))
from svg2pdf import orden_natural  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("url")
ap.add_argument("--nombre", help="nombre de los archivos de salida; por defecto, el título de la obra")
ap.add_argument("--compas", help="por ejemplo 9/8; si falta, 4/4 (el SVG no lo trae)")
args = ap.parse_args()

# uvx.exe no arranca bien desde una carpeta de WSL, y svg2pdf necesita una carpeta con solo esta obra
tmp = Path(tempfile.mkdtemp(prefix=".captura_", dir=BASE))
shutil.copy(REPO / "svg_scrape.py", tmp)
r = subprocess.run(["uvx.exe", "--python", "3.12", "--with", "playwright", "python", "svg_scrape.py", args.url, "out"], cwd=tmp)
svgs = sorted((tmp / "out").glob("*.svg"), key=orden_natural)
if r.returncode or not svgs:
    sys.exit(f"La captura terminó con código {r.returncode}; no se genera nada. Lo bajado queda en {tmp / 'out'}")

nombre = args.nombre or re.sub(r"_\d+$", "", svgs[0].stem)
if args.nombre is None and not all(re.fullmatch(rf"{re.escape(nombre)}_\d+", s.stem) for s in svgs):
    sys.exit(f"Los archivos no parecen hojas de una sola obra; usa --nombre. Quedan en {tmp / 'out'}")
destino = BASE / "svg_partituras" / nombre
destino.mkdir(parents=True, exist_ok=True)
for s in svgs:
    shutil.copy(s, destino / s.name)

fallos = []
pdf = subprocess.run([sys.executable, str(REPO / "svg2pdf.py"), str(tmp / "out"), nombre])
if pdf.returncode:
    fallos.append("PDF")
xml = BASE / "svg_to_xml" / f"{nombre}.musicxml"
xml.parent.mkdir(exist_ok=True)
cmd = [sys.executable, str(REPO / "svg2musicxml.py"), *map(str, svgs), "-o", str(xml)]
if args.compas:
    cmd += ["--compas", args.compas]
else:
    print("Aviso: sin --compas se supone 4/4; revísalo, el SVG no lo trae", file=sys.stderr)
if subprocess.run(cmd).returncode:
    fallos.append("MusicXML")

shutil.rmtree(tmp)
if fallos:
    sys.exit(f"Falló: {', '.join(fallos)}. Los SVG están en {destino}")
print(f"Listo: {len(svgs)} hojas -> {nombre}.pdf y {nombre}.musicxml")
