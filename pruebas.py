"""Todas las pruebas del proyecto. Cada función test_* es una prueba independiente.

Uso: .venv/bin/python pruebas.py

Las saltadas no cuentan como pasadas: les falta un archivo de D: o un programa de Windows. Sale con código 1
si alguna falla. Las de svg_scrape abren una ventana de Chrome.
"""
import contextlib
import functools
import http.server
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import xml.dom.minidom
from pathlib import Path

sys.dont_write_bytecode = True

import comparar_musicxml as comparar
import svg2musicxml as s
import svg2pdf

REPO = Path(__file__).parent
PARTITURAS = Path("/mnt/d/Nahum/omr_partituras")
RES = PARTITURAS / "resultados/svg"
SVG_MINIMO = '<svg xmlns="http://www.w3.org/2000/svg"/>'


class Saltar(Exception):
    pass


def carpeta_en_d():
    """Chrome y uvx.exe son de Windows: sus archivos tienen que estar en una carpeta de Windows."""
    if not PARTITURAS.exists():
        raise Saltar(f"falta {PARTITURAS}")
    return tempfile.TemporaryDirectory(dir=PARTITURAS, prefix="_prueba_", ignore_cleanup_errors=True)


def errores_de(nombre, contenido):
    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / nombre
        ruta.write_text(contenido, encoding="utf-8")
        return svg2pdf.problemas([ruta])


def correr_svg2pdf(carpeta, nombre, salida):
    """Ejecuta main() como desde la terminal. Devuelve el error con el que terminó, o None."""
    antes, svg2pdf.SALIDA, argv = svg2pdf.SALIDA, salida, sys.argv
    sys.argv = ["svg2pdf.py", str(carpeta), nombre]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            svg2pdf.main()
    except SystemExit as e:
        return str(e)
    finally:
        svg2pdf.SALIDA, sys.argv = antes, argv


def calificar(svgs, ref, compas):
    if not ref.exists() or not svgs or not all(Path(x).exists() for x in svgs):
        raise Saltar(f"falta {ref.name} o sus SVG")
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(io.StringIO()):
        salida = Path(d) / "x.musicxml"
        salida.write_text(s.convertir(svgs, compas)[0], encoding="utf-8")
        return comparar.comparar(ref, salida)


# --- svg2pdf ---

def test_pdf_acepta_svg_correcto():
    assert errores_de("bien.svg", SVG_MINIMO) == []


def test_pdf_rechaza_0_bytes():
    errores = errores_de("vacio.svg", "")
    assert len(errores) == 1 and "pesa 0 bytes" in errores[0], errores


def test_pdf_rechaza_svg_cortado():
    errores = errores_de("cortado.svg", '<svg xmlns="http://www.w3.org/2000/svg"><path')
    assert len(errores) == 1 and "dañado" in errores[0], errores


def test_pdf_rechaza_lo_que_no_es_svg():
    errores = errores_de("otro.svg", "<html/>")
    assert len(errores) == 1 and "no es un SVG" in errores[0], errores


def test_pdf_orden_numerico_de_paginas():
    nombres = sorted(map(Path, ["score_10.svg", "score_2.svg", "score_0.svg"]), key=svg2pdf.orden_natural)
    assert [p.name for p in nombres] == ["score_0.svg", "score_2.svg", "score_10.svg"]


def test_pdf_no_genera_nada_si_un_svg_pesa_0_bytes():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as salida:
        (Path(d) / "a1.svg").write_text(SVG_MINIMO)
        (Path(d) / "a2.svg").write_text("")
        error = correr_svg2pdf(d, "x", Path(salida))
        assert error and "a2.svg: pesa 0 bytes" in error, error
        assert list(Path(salida).iterdir()) == []
        assert not (Path(d) / "_imprimir.html").exists()


def test_pdf_falla_si_la_carpeta_no_tiene_svg():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as salida:
        error = correr_svg2pdf(d, "x", Path(salida))
        assert error and "no hay SVG" in error, error


def test_pdf_rechaza_nombre_con_carpetas():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as salida:
        error = correr_svg2pdf(d, "../x", Path(salida))
        assert error and "carpetas" in error, error


def test_pdf_genera_con_chrome():
    if not Path(svg2pdf.CHROME).exists():
        raise Saltar("falta Chrome")
    with carpeta_en_d() as d:
        d = Path(d)
        entrada, salida = d / "entrada", d / "salida"
        entrada.mkdir()
        salida.mkdir()
        (entrada / "página 1.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="141"><path d="M0 0h50v50H0z"/></svg>', encoding="utf-8")
        assert correr_svg2pdf(entrada, "x", salida) is None
        pdf = salida / "x.pdf"
        assert pdf.read_bytes().startswith(b"%PDF")
        assert [p.name for p in salida.iterdir()] == ["x.pdf"]  # sin temporales
        assert [p.name for p in entrada.iterdir()] == ["página 1.svg"]  # sin el HTML auxiliar


# --- svg2musicxml ---

def test_xml_cabeza_negra_sin_hueco():
    g = s.glifos("M0 0h10v10h-10z")
    assert len(g) == 1 and g[0]["huecos"] == 0 and (g[0]["x1"], g[0]["y1"]) == (10, 10)


def test_xml_cabeza_blanca_con_hueco():
    g = s.glifos("M0 0h10v10h-10zm2 2h6v6h-6z")
    assert len(g) == 1 and g[0]["huecos"] == 1


def test_xml_arco_con_banderas_pegadas():
    assert s.numeros("a", "5.9 5.9 0 00-1.375 2") == [5.9, 5.9, 0, 0, 0, -1.375, 2]


def test_xml_aplica_matriz():
    g = s.glifos("M0,0 L10,10")
    s.aplicar_matriz(g, [2, 0, 0, 2, 100, 200])
    assert (g[0]["x0"], g[0]["y1"]) == (100, 220)


def test_xml_armadura_con_bemoles():
    assert s.altera_armadura(-2) == dict(B=-1, E=-1)


def test_xml_armadura_con_sostenidos():
    assert s.altera_armadura(1) == dict(F=1)


def test_xml_armadura_sin_alteraciones():
    assert s.altera_armadura(0) == {}


def test_xml_falla_si_un_svg_pesa_0_bytes():
    with tempfile.NamedTemporaryFile(suffix=".svg") as f:
        try:
            s.leer_svg(f.name)
        except SystemExit as e:
            assert "pesa 0 bytes" in str(e), e
        else:
            raise AssertionError("no falló")


def test_xml_falla_si_el_svg_no_es_de_musescore():
    with tempfile.NamedTemporaryFile("w", suffix=".svg") as f:
        f.write(SVG_MINIMO)
        f.flush()
        try:
            s.leer_svg(f.name)
        except SystemExit as e:
            assert "clases de MuseScore" in str(e), e
        else:
            raise AssertionError("no falló")


def test_xml_clair_de_lune_web():
    r = calificar([str(RES / "Clair_de_Lune_p1.svg")], RES / "Clair_de_Lune_p1.musicxml", None)
    assert r["ok"] == r["ref"] == r["res"], f"{r['ok']} de {r['ref']} notas, {r['res']} escritas"
    assert r["sil_ok"] == r["sil_ref"] == r["sil_res"]


def test_xml_el_siempre_reina_escritorio():
    ciega = RES / "prueba_ciega"
    r = calificar(sorted(map(str, ciega.glob("er-*.svg"))), ciega / "ref.musicxml", "6/8")
    assert r["ok"] == r["ref"] == r["res"], f"{r['ok']} de {r['ref']} notas, {r['res']} escritas"
    assert r["sil_ok"] == r["sil_ref"] == r["sil_res"]


# --- svg_scrape ---
# Cubre: svg creado por JS, anidado, repetido, uno que solo existe mientras está en pantalla,
# uno que aparece al desplazar un contenedor interno, y uno que llega por la red como <img>
RED = '<svg xmlns="http://www.w3.org/2000/svg" id="red"/>'
PAGINA = """<!DOCTYPE html><body><img src="partitura.svg"><img src="foto.png"><div style="height:5000px"></div><div id="abajo"></div>
<div id="caja" style="height:300px;overflow:auto"><div style="height:5000px"></div></div><script>
const svg = id => `<svg id="${id}" viewBox="0 0 1 1"><svg id="${id}-dentro"></svg></svg>`;
setTimeout(() => document.body.insertAdjacentHTML('afterbegin', svg('a') + svg('a')), 100);
addEventListener('scroll', () => {
  abajo.innerHTML = scrollY > 1000 && scrollY < 3000 ? svg('efimero') : '';
});
caja.addEventListener('scroll', () => {
  if (caja.scrollTop > 2000 && !document.getElementById('en-caja')) document.body.insertAdjacentHTML('beforeend', svg('en-caja'));
});
</script></body>"""


class SilencioHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def esperar_puerto_desde_windows(url):
    """Windows tarda en alcanzar un puerto recién abierto en WSL."""
    for _ in range(40):
        if subprocess.run(["curl.exe", "-s", "-o", "NUL", url], capture_output=True).returncode == 0:
            return
        time.sleep(.5)
    raise AssertionError(f"Windows no alcanza {url}")


def _capturar():
    if not shutil.which("uvx.exe"):
        raise Saltar("falta uvx.exe")
    with carpeta_en_d() as d:
        d = Path(d)
        shutil.copy(REPO / "svg_scrape.py", d)  # uvx.exe no arranca bien desde una carpeta de WSL
        (d / "p.html").write_text(PAGINA, encoding="utf-8")
        (d / "partitura.svg").write_text(RED, encoding="utf-8")
        (d / "foto.png").write_bytes(b"no es svg")
        manejador = functools.partial(SilencioHandler, directory=str(d))
        servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{servidor.server_port}/p.html"
            esperar_puerto_desde_windows(url)
            # perfil temporal: la prueba no debe tocar ni depender del perfil real de svg_scrape
            entorno = dict(os.environ, SVG_SCRAPE_PERFIL=str(d / "perfil"), WSLENV=os.environ.get("WSLENV", "") + ":SVG_SCRAPE_PERFIL/p")
            r = subprocess.run(
                ["uvx.exe", "--python", "3.12", "--with", "playwright", "python", "svg_scrape.py", url, "out"],
                cwd=d, env=entorno, capture_output=True, text=True, errors="replace", timeout=300)
        finally:
            servidor.shutdown()
            servidor.server_close()
        assert r.returncode == 0, r.stderr[-500:]
        raices = [xml.dom.minidom.parse(str(f)).documentElement for f in sorted((d / "out").glob("svg_*.svg"))]
        return raices, [f.read_text(encoding="utf-8") for f in (d / "out").glob("red_*.svg")]


@functools.lru_cache(maxsize=1)
def _captura_una_vez():
    # el error también se guarda: si falla, Chrome no se abre una vez por cada prueba
    try:
        return _capturar()
    except (Exception, Saltar) as e:
        return e


def captura():
    r = _captura_una_vez()
    if isinstance(r, Exception):
        raise r
    return r


def test_scrape_encuentra_cada_svg_una_vez():
    ids = sorted(x.getAttribute("id") for x in captura()[0])
    assert ids == ["a", "efimero", "en-caja"], ids


def test_scrape_guarda_xml_valido_con_xmlns():
    assert all(x.getAttribute("xmlns") == "http://www.w3.org/2000/svg" for x in captura()[0])


def test_scrape_captura_svg_de_la_red_e_ignora_lo_demas():
    assert captura()[1] == [RED], captura()[1]


# --- ejecución ---

def main():
    pruebas = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    pasaron, fallaron, saltadas = 0, 0, 0
    for nombre, prueba in pruebas:
        try:
            prueba()
        except Saltar as e:
            saltadas += 1
            print(f"saltada  {nombre}: {e}")
        except BaseException as e:  # un sys.exit dentro de una prueba no debe cortar las demás
            if isinstance(e, KeyboardInterrupt):
                raise
            fallaron += 1
            detalle = traceback.format_exc(limit=-1).strip().splitlines()
            print(f"FALLÓ    {nombre}\n         " + "\n         ".join(detalle[-3:]))
        else:
            pasaron += 1
            print(f"ok       {nombre}")
    print(f"\n{pasaron} de {len(pruebas)} pruebas pasaron ({fallaron} fallaron, {saltadas} saltadas)")
    sys.exit(1 if fallaron else 0)


if __name__ == "__main__":
    main()
