"""Todas las pruebas del proyecto. Cada función test_* es una prueba independiente.

Uso: .venv/bin/python pruebas.py

Las saltadas no cuentan como pasadas: les falta un archivo de D: o un programa de Windows. Sale con código 1
si alguna falla. Las de svg_scrape abren una ventana de Chrome.
"""
import base64
import contextlib
import functools
import html as html_lib
import http.client
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import xml.dom.minidom
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

import catalogo
import comparar_musicxml as comparar
import svg2musicxml as s
import svg2pdf
import web

REPO = Path(__file__).parent
PARTITURAS = Path("/mnt/d/Nahum/omr_partituras")
RES = PARTITURAS / "test/svg"
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


def test_xml_night_dreamer_escritorio():
    # SVG exportados por MuseScore desde la referencia: 8va, adornos, seisillos, cambios de compás y casillas
    d = PARTITURAS / "test/Prueba_script/svg_test/night_dreamer"
    ref = PARTITURAS / "test/Prueba_script/xml_originales/night-dreamer-t-square-full-arrangement-Piano.musicxml"
    r = calificar([str(d / f"piano-{i}.svg") for i in range(1, 11)], ref, None)
    assert r["ok"] == r["ref"] == r["res"], f"{r['ok']} de {r['ref']} notas, {r['res']} escritas"
    assert r["sil_ok"] == r["sil_ref"] == r["sil_res"]


def test_xml_obras_web():
    # vals, preludio y Arabesque de musescore.com: tresillos sin número, voces compartidas, otra fuente, armaduras
    base = PARTITURAS / "test/Prueba_script"
    obras = {"waltz_in_a_minor_chopin": "waltz-in-a-minorchopin", "arabesque_l_66_no_1_in_e_major": "arabesque-l-66-no-1-in-e-major",
             "prelude_i_in_c_major_bwv_846_well_tempered_clavier_first_book": "prelude-i-in-c-major-bwv-846-well-tempered-clavier-first-book"}
    for carpeta, mxl in obras.items():
        z = base / "xml_originales" / f"{mxl}.mxl"
        if not z.exists():
            raise Saltar(f"falta {z.name}")
        with tempfile.TemporaryDirectory() as d, zipfile.ZipFile(z) as zf:
            ref = Path(d) / "ref.musicxml"
            ref.write_bytes(zf.read("score.xml"))
            r = calificar(sorted(map(str, (base / "svg_test" / carpeta).glob("*.svg"))), ref, None)
        assert r["ok"] == r["ref"] == r["res"], f"{carpeta}: {r['ok']} de {r['ref']} notas, {r['res']} escritas"
        assert r["sil_ok"] == r["sil_ref"] == r["sil_res"], carpeta


# --- svg_scrape ---
# Cubre: svg creado por JS, anidado, repetido, uno que solo existe mientras está en pantalla,
# uno que aparece al desplazar un contenedor interno, y uno que llega por la red como <img>
RED = '<svg xmlns="http://www.w3.org/2000/svg" id="red"/>'
HOJA = '<svg xmlns="http://www.w3.org/2000/svg" id="hoja"/>'
PAGINA = """<!DOCTYPE html><title>Mi Obra</title><body><img src="partitura.svg"><img src="score_3.svg"><img src="foto.png"><div style="height:5000px"></div><div id="abajo"></div>
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
        (d / "score_3.svg").write_text(HOJA, encoding="utf-8")
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
        return raices, [f.read_text(encoding="utf-8") for f in (d / "out").glob("red_*.svg")], sorted(f.name for f in (d / "out").glob("mi_obra_*"))


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


def test_scrape_nombra_la_hoja_con_titulo_y_numero():
    assert captura()[2] == ["mi_obra_04.svg"], captura()[2]


# --- practica.html ---

PRACTICA_XML = """<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">
<measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>
<clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>F</sign><line>4</line></clef></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff></note>
<note><chord/><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff></note>
<note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration><tie type="start"/><voice>1</voice><type>half</type><staff>1</staff><notations><tied type="start"/></notations></note>
<note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><tie type="stop"/><voice>1</voice><type>quarter</type><staff>1</staff><notations><tied type="stop"/></notations></note>
<backup><duration>4</duration></backup>
<note><pitch><step>C</step><octave>3</octave></pitch><duration>2</duration><voice>2</voice><type>half</type><staff>2</staff></note>
<note><rest/><duration>1</duration><voice>2</voice><type>quarter</type><staff>2</staff></note>
<note><pitch><step>F</step><alter>1</alter><octave>3</octave></pitch><duration>1</duration><voice>2</voice><type>quarter</type><staff>2</staff></note>
</measure>
<measure number="2">
<note><grace/><pitch><step>G</step><octave>5</octave></pitch><voice>1</voice><type>eighth</type><staff>1</staff></note>
<note><pitch><step>A</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type><staff>1</staff></note>
<backup><duration>4</duration></backup>
<note><rest/><duration>4</duration><voice>2</voice><type>whole</type><staff>2</staff></note>
</measure>
<measure number="3">
<note><pitch><step>C</step><octave>6</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type><staff>1</staff></note>
<backup><duration>4</duration></backup>
<note><rest/><duration>4</duration><voice>2</voice><type>whole</type><staff>2</staff></note>
</measure>
</part></score-partwise>"""

# Sustituye el teclado: el MiniLab no está conectado en las pruebas, y Chrome pediría permiso
PRACTICA_MIDI = """<script>
const puerto = (id, name) => ({id, name, open: async () => {}});
navigator.requestMIDIAccess = async () => ({inputs: new Map([['n', puerto('n', 'nanoKONTROL2')], ['m', puerto('m', 'Minilab3 MIDI')]])});
</script>"""

PRACTICA_ESCENARIO = """<script>
const pulsar = (nota, fuerza = 90, estado = 0x90) => tecla({data: [estado, nota, fuerza]});
const ajustar = async (mano, desde = '', hasta = '', octava = false) => {
  $('desde').value = desde; $('hasta').value = hasta; $('octava').checked = octava;
  $('mano').value = mano;
  await $('mano').onchange();
};
// Recorre el fragmento tocando lo que pide, hasta que vuelve a empezar
const recorrer = () => {
  const pasos = [];
  resultado = '';
  while (!resultado && exigidas.size) {
    if (pasos.length > 50) throw new Error('el fragmento no termina: ' + JSON.stringify(pasos.slice(0, 8)));
    pasos.push([...exigidas.keys()].sort((a, b) => a - b));
    for (const k of [...exigidas.keys()]) pulsar(k);
  }
  return pasos;
};
(async () => {
  const r = {};
  await new Promise(ok => setTimeout(ok));  // deja que responda requestMIDIAccess
  r.puerto = midi.inputs.get($('entrada').value).name;
  await cargar(new File([ENTRADA.xml], 'a.musicxml'));
  const pentagramas = () => osmd.GraphicSheet.MusicPages[0].MusicSystems[0].StaffLines.length;
  r.pentagramas_ambas = pentagramas();
  const clave_dibujada = () => osmd.GraphicSheet.MeasureList[0].find(m => m?.ParentMusicSystem).stave.clef;
  await ajustar('0'); r.pentagramas_derecha = pentagramas(); r.clave_derecha = clave_dibujada();
  await ajustar('1'); r.pentagramas_izquierda = pentagramas(); r.clave_izquierda = clave_dibujada();
  await ajustar('ambas'); r.ambas = recorrer();
  await ajustar('0'); r.derecha = recorrer();
  await ajustar('1'); r.izquierda = recorrer();
  await ajustar('ambas', 2, 2); r.compas2 = recorrer();
  await ajustar('ambas', '', '', true); r.sin_octava = recorrer();
  await ajustar('1', 3, 3); r.vacio = $('estado').textContent; r.vacio_exige = exigidas.size;

  await ajustar('ambas');
  const dibujo = altura => [...dibujadas].find(([n]) => !n.isRest() && alturaMidi(n) === altura)[1], colorDe = g => g.getNoteheadSVGs()[g.vfnoteIndex].querySelector('path').getAttribute('fill');
  const color = altura => colorDe(dibujo(altura));
  r.color_antes = color(76);
  pulsar(76); r.parcial = [aciertos, fallos, faltan.size];
  r.color_tocada = color(76); r.color_pendiente = color(72);
  pulsar(61); pulsar(76); r.fallo_y_repetida = [aciertos, fallos, $('estado').className];
  pulsar(72, 0); pulsar(72, 90, 0x80); pulsar(72, 90, 0x99); r.ignoradas = [aciertos, fallos];
  pulsar(72); pintar(); r.color_tras_redibujo = color(72);
  pulsar(48); r.tras_acorde = [...exigidas.keys()];
  $('saltar').click(); r.tras_saltar = [...exigidas.keys()];
  pulsar(54); pulsar(81); pulsar(84); r.final = $('estado').textContent;
  r.final_sigue_verde = color(84);
  $('reiniciar').click(); r.color_reiniciado = color(84);

  await cargar(new File([Uint8Array.from(atob(ENTRADA.mxl), c => c.charCodeAt(0))], 'b.mxl'));
  r.mxl = [...exigidas.keys()].sort((a, b) => a - b);
  await cargar(new File(['no es musicxml'], 'c.musicxml'));
  r.basura = [$('estado').textContent, cargada, $('estado').className];

  await cargar(new File([ENTRADA.larga], 'd.musicxml'));
  await ajustar('ambas');
  const sistemas = osmd.GraphicSheet.MusicPages[0].MusicSystems.length;
  const vista = () => [$('partitura').scrollTop, $('partitura').clientHeight];
  r.sistemas = sistemas;
  r.alto_svg = document.querySelector('#partitura svg').getBoundingClientRect().height;
  r.vista_inicial = vista();
  const primerSistema = osmd.GraphicSheet.MeasureList[0].find(Boolean).ParentMusicSystem;
  while (exigidas.size && osmd.GraphicSheet.MeasureList[osmd.cursor.Iterator.CurrentMeasureIndex].find(Boolean).ParentMusicSystem === primerSistema) pulsar([...faltan.keys()][0]);
  r.vista_siguiente = vista();
  const paso = osmd.cursor.Iterator.CurrentMeasureIndex, hechas = aciertos;
  $('vista').value = 'toda'; $('vista').onchange();
  r.toda_conserva = osmd.cursor.Iterator.CurrentMeasureIndex === paso && aciertos === hechas;
  r.toda_alto = $('partitura').clientHeight;
  $('vista').value = 'sistema'; $('vista').onchange();
  await ajustar('1');
  r.izquierda_recorta = $('partitura').clientHeight < r.alto_svg / 2;
  pulsar([...faltan.keys()][0]);
  r.franja_izquierda = [$('paso').hidden, $('paso').getBoundingClientRect().height > 0];
  $('vista').value = 'toda'; $('vista').onchange();
  await ajustar('ambas');
  while (exigidas.size && osmd.GraphicSheet.MeasureList[osmd.cursor.Iterator.CurrentMeasureIndex].find(Boolean).ParentMusicSystem === primerSistema) pulsar([...faltan.keys()][0]);
  const y = scrollY; pulsar([...faltan.keys()][0]); r.toda_no_desplaza = scrollY === y;
  $('resultado').textContent = JSON.stringify(r);
})().catch(e => { $('resultado').textContent = JSON.stringify({error: String(e.stack)}); });
</script>"""


def practica_en_chrome(entrada, escenario):
    """Corre practica.html en Chrome con un teclado falso. El escenario escribe un JSON en #resultado."""
    if not Path(svg2pdf.CHROME).exists():
        raise Saltar("falta Chrome")
    with carpeta_en_d() as d:
        d = Path(d)
        shutil.copytree(REPO / "vendor", d / "vendor")
        shutil.copy(REPO / "estilos.css", d)
        html = (REPO / "practica.html").read_text(encoding="utf-8")
        datos = f'<script>const ENTRADA = {json.dumps(entrada)};</script><pre id="resultado"></pre>'
        html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + PRACTICA_MIDI).replace("</html>", datos + escenario + "</html>")
        (d / "p.html").write_text(html, encoding="utf-8")
        r = subprocess.run([svg2pdf.CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={svg2pdf.windows(d / 'perfil')}",
                            "--virtual-time-budget=120000", "--dump-dom", "file:///" + svg2pdf.windows(d / "p.html").replace("\\", "/")],
                           capture_output=True, timeout=120)
        texto = r.stdout.decode("utf-8", "replace").partition('<pre id="resultado">')[2].partition("</pre>")[0]
        assert texto, r.stderr[-500:]
        return json.loads(html_lib.unescape(texto))


@functools.lru_cache(maxsize=1)
def _practica_una_vez():
    try:
        zona = io.BytesIO()
        with zipfile.ZipFile(zona, "w") as z:
            z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="s.musicxml"/></rootfiles></container>')
            z.writestr("s.musicxml", PRACTICA_XML)
        compases = "".join(f'<measure number="{i}"><note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type></note></measure>' for i in range(2, 61))
        larga = PRACTICA_XML.split('<measure number="2">')[0] + compases + "</part></score-partwise>"
        return practica_en_chrome({"xml": PRACTICA_XML, "mxl": base64.b64encode(zona.getvalue()).decode(), "larga": larga}, PRACTICA_ESCENARIO)
    except (Exception, Saltar) as e:
        return e


def practica():
    r = _practica_una_vez()
    if isinstance(r, Exception):
        raise r
    assert "error" not in r, r["error"]
    return r


def test_practica_elige_el_minilab_aunque_no_sea_el_primer_puerto():
    assert practica()["puerto"] == "Minilab3 MIDI"


def test_practica_exige_cada_paso_sin_ligadas_ni_adornos():
    # C3+C5+E5, D5, Fa#3 (el Re ligado no se repite), La5 (el Sol de adorno no se exige), Do6
    assert practica()["ambas"] == [[48, 72, 76], [74], [54], [81], [84]], practica()["ambas"]


def test_practica_separa_las_manos():
    assert practica()["derecha"] == [[72, 76], [74], [81], [84]], practica()["derecha"]
    assert practica()["izquierda"] == [[48], [54]], practica()["izquierda"]


def test_practica_limita_a_los_compases_elegidos():
    assert practica()["compas2"] == [[81]], practica()["compas2"]


def test_practica_ignorar_octava_compara_solo_el_nombre():
    assert practica()["sin_octava"] == [[0, 4], [2], [6], [9], [0]], practica()["sin_octava"]


def test_practica_avisa_si_no_hay_notas_en_la_seleccion():
    assert "No hay notas" in practica()["vacio"] and practica()["vacio_exige"] == 0, practica()["vacio"]


def test_practica_cuenta_aciertos_y_fallos():
    r = practica()
    assert r["parcial"] == [1, 0, 2], r["parcial"]  # el acorde no se completa con una nota
    assert r["fallo_y_repetida"] == [1, 1, "mal"], r["fallo_y_repetida"]  # repetir una acertada no es fallo
    assert r["ignoradas"] == [1, 1], r["ignoradas"]  # fuerza 0, soltar y pads del canal 10
    assert r["tras_acorde"] == [74] and r["tras_saltar"] == [54], (r["tras_acorde"], r["tras_saltar"])
    assert "Terminado" in r["final"], r["final"]


def test_practica_muestra_solo_el_pentagrama_de_la_mano():
    r = practica()
    assert [r["pentagramas_ambas"], r["pentagramas_derecha"], r["pentagramas_izquierda"]] == [2, 1, 1], r
    assert [r["clave_derecha"], r["clave_izquierda"]] == ["treble", "bass"], r
    assert r["izquierda_recorta"] and r["franja_izquierda"] == [False, True], r


def test_practica_gris_por_tocar_y_verde_tocada():
    r = practica()
    assert r["color_antes"] == r["color_pendiente"] == "#8a8a8a", r
    assert r["color_tocada"] == r["final_sigue_verde"] == "#1f9d3a", r
    assert r["color_reiniciado"] == "#8a8a8a", r
    assert r["color_tras_redibujo"] == "#1f9d3a", r


def test_practica_vista_de_sistema_recorta_y_sigue_al_tocar():
    r = practica()
    assert r["sistemas"] > 2 and r["vista_inicial"][1] < r["alto_svg"] / 2, r
    assert r["vista_siguiente"][0] > r["vista_inicial"][0], r


def test_practica_toda_la_partitura_conserva_el_paso_y_no_se_desplaza_sola():
    r = practica()
    assert r["toda_alto"] >= r["alto_svg"] and r["toda_conserva"] and r["toda_no_desplaza"], r


def test_practica_lee_mxl_y_rechaza_basura():
    r = practica()
    assert r["mxl"] == [48, 72, 76], r["mxl"]
    assert "no parece un MusicXML" in r["basura"][0] and r["basura"][1:] == [False, "mal"], r["basura"]


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


def test_catalogo_firma_igual_en_ambos_formatos():
    # el mismo cuadrado con hueco, como lo escribe la web (relativo, 'm') y el escritorio (absoluto, 'M'), a otra escala
    web = catalogo.contornos("M10 10h10v10h-10m2 -8h6v6h-6", [1, 0, 0, 1, 0, 0])
    esc = catalogo.contornos("M0,0 L10,0 L10,10 L0,10 M2,2 L8,2 L8,8 L2,8", [2, 0, 0, 2, 100, 100])
    assert len(web) == 2 and len(esc) == 2
    # mismo cuadrado empezando por otra esquina y en sentido contrario
    assert catalogo.iguales(catalogo.firma(catalogo.contornos("M10 0L0 0L0 10L10 10", [1, 0, 0, 1, 0, 0]), 5),
                            catalogo.firma(catalogo.contornos("M0 0L10 0L10 10L0 10", [1, 0, 0, 1, 0, 0]), 5))
    # otra forma no coincide
    assert not catalogo.iguales(catalogo.firma(catalogo.contornos("M0 0L10 0L10 12L0 12", [1, 0, 0, 1, 0, 0]), 5),
                                catalogo.firma(catalogo.contornos("M0 0L10 0L10 10L0 10", [1, 0, 0, 1, 0, 0]), 5))
    assert catalogo.iguales(catalogo.firma(web, 5), catalogo.firma(esc, 10))


def test_iguales_compara_en_los_dos_sentidos():
    cuadrado = [[1, 1, [(0, 0), (1, 0), (1, 1), (0, 1)]]]
    otro = [[1, 1, [(0, 0), (1, 0), (1, 1), (0, 1)]], [1, 1, [(0, 0), (1, 1)]]]
    assert not catalogo.iguales(cuadrado * 2, otro)  # [x, x] no es [x, y]
    assert not catalogo.iguales(otro, cuadrado * 2)


def test_glifos_json_sin_nombres_repetidos():
    # dos nombres con la misma forma en una clase harían ambiguo el reconocimiento
    for nombre, requeridas in (("glifos.json", {"Clef", "TimeSig", "Rest", "Note", "Dynamic"}), ("glifos_merry.json", {"Clef", "TimeSig", "Rest", "Dynamic", "Tempo"})):
        cat = json.loads((REPO / nombre).read_text())["glifos"]
        assert requeridas <= set(cat), nombre
        for clase, v in cat.items():
            nombres = list(v)
            for i, a in enumerate(nombres):
                for b in nombres[:i]:
                    assert not catalogo.iguales(v[a], v[b]), f"{nombre} {clase}: {a} = {b}"
    assert all(str(d) in json.loads((REPO / "glifos.json").read_text())["glifos"]["TimeSig"] for d in range(10))


# --- web.py ---

@contextlib.contextmanager
def servidor_web():
    s = web.servidor(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        yield s.server_port
    finally:
        s.shutdown()
        s.server_close()


def peticion(puerto, ruta, campos=None, archivos=None, origen=True, metodo=None):
    """Devuelve (código, texto). Sin campos ni archivos, un GET."""
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=120)
    cabeceras = {"Host": f"localhost:{puerto}"}
    cuerpo = None
    if campos is not None or archivos is not None:
        limite = "limite-de-prueba"
        partes = [f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in (campos or {}).items()]
        partes += [f'--{limite}\r\nContent-Disposition: form-data; name="svg"; filename="{k}"\r\nContent-Type: image/svg+xml\r\n\r\n'.encode() + v + b"\r\n" for k, v in (archivos or {}).items()]
        cuerpo = b"".join(partes) + f"--{limite}--\r\n".encode()
        cabeceras["Content-Type"] = f"multipart/form-data; boundary={limite}"
        if origen:
            cabeceras["Origin"] = f"http://localhost:{puerto}" if origen is True else origen
    conexion.request(metodo or ("POST" if cuerpo else "GET"), ruta, cuerpo, cabeceras)
    r = conexion.getresponse()
    return r.status, r.read().decode("utf-8", "replace")


def test_web_no_sirve_lo_que_no_es_de_la_pagina():
    with servidor_web() as p:
        for ruta in ("/", "/practica.html", "/estilos.css", "/vendor/michroma.woff2"):
            assert peticion(p, ruta)[0] == 200, ruta
        for ruta in ("/.git/config", "/web.py", "/vendor/../web.py", "/vendor/%2e%2e/web.py", "/README.md"):
            assert peticion(p, ruta)[0] == 404, ruta
            assert peticion(p, ruta, metodo="HEAD")[0] == 404, ruta


def test_web_rechaza_otros_origenes():
    with servidor_web() as p:
        for origen in ("https://evil.example", False):
            assert peticion(p, "/pipeline", {"url": "https://musescore.com/a"}, origen=origen)[0] == 403, origen


def test_web_valida_los_campos_antes_de_ejecutar():
    malos = [
        ("/pipeline", {"url": "file:///etc/passwd"}, {}),
        ("/pipeline", {"url": "--nombre"}, {}),
        ("/pipeline", {"url": "https://a.b/c", "compas": "4/4; rm"}, {}),
        ("/pdf", {"nombre": "x"}, {}),
        ("/pdf", {}, {"a.svg": b"x"}),
        ("/pdf", {"nombre": "../x"}, {"a.svg": b"x"}),
        ("/pdf", {"nombre": "--compas"}, {"a.svg": b"x"}),
        ("/pdf", {"nombre": "x"}, {"../a.svg": b"x"}),
        ("/pdf", {"nombre": "x"}, {"a.txt": b"x"}),
        ("/musicxml", {"nombre": "obra_revisado"}, {"a.svg": b"x"}),
        ("/musicxml", {"nombre": "x", "compas": "9"}, {"a.svg": b"x"}),
    ]
    with servidor_web() as p:
        for ruta, campos, archivos in malos:
            codigo, texto = peticion(p, ruta, campos, archivos)
            assert codigo == 400, (ruta, campos, archivos, codigo, texto)


def falsos_scripts(d):
    """Sustituye los scripts por uno que imprime sus argumentos: sin Chrome ni capturas."""
    for script in ("svg2pdf.py", "svg2musicxml.py", "partitura.py"):
        (d / script).write_text("import sys\nprint(*sys.argv[1:], sep='\\n')\nprint('acción é')\nsys.exit(0)", encoding="utf-8")


@contextlib.contextmanager
def web_con_falsos():
    with carpeta_en_d() as d:
        d = Path(d)
        falsos_scripts(d)
        antes = web.REPO
        web.REPO = d
        try:
            with servidor_web() as p:
                yield p, d
        finally:
            web.REPO = antes


def test_web_arma_cada_comando_y_ordena_las_hojas():
    with web_con_falsos() as (p, _):
        codigo, texto = peticion(p, "/musicxml", {"nombre": "Mi obra", "compas": "9/8"}, {"h_10.svg": b"<svg/>", "h_2.svg": b"<svg/>", "ñandú é.svg": b"<svg/>"})
        assert codigo == 200 and texto.endswith("[código 0]\n"), texto
        lineas = texto.splitlines()
        assert [Path(x).name for x in lineas[:3]] == ["h_2.svg", "h_10.svg", "ñandú é.svg"], lineas
        assert lineas[3:6] == ["-o", str(web.BASE / "svg_to_xml/Mi obra.musicxml"), "--compas"] and lineas[6] == "9/8" and "acción é" in lineas, lineas

        _, pdf = peticion(p, "/pdf", {"nombre": "x"}, {"a.svg": b"<svg/>"})
        assert pdf.splitlines()[1] == "x" and Path(pdf.splitlines()[0]).name.startswith(".web_"), pdf

        _, todo = peticion(p, "/pipeline", {"url": "https://musescore.com/a/scores/1?x=1&y=2", "nombre": "", "compas": "3/4"})
        assert todo.splitlines()[:3] == ["https://musescore.com/a/scores/1?x=1&y=2", "--compas", "3/4"], todo
    assert not list(web.BASE.glob(".web_*")), "quedó una carpeta temporal"


def test_web_svg_de_0_bytes_llega_al_script_y_falla():
    with servidor_web() as p:
        if not web.BASE.exists():
            raise Saltar(f"falta {web.BASE}")
        codigo, texto = peticion(p, "/pdf", {"nombre": "_prueba_web_vacio"}, {"a.svg": b""})
    assert codigo == 200 and "0 bytes" in texto and texto.endswith("[código 1]\n"), texto


def test_web_un_trabajo_a_la_vez():
    with web_con_falsos() as (p, _), web.OCUPADO:
        assert peticion(p, "/pipeline", {"url": "https://a.b/c"})[0] == 409


def test_web_genera_pdf_y_musicxml_de_verdad():
    svg = RES / "Clair_de_Lune_p1.svg"
    if not svg.exists() or not Path(svg2pdf.CHROME).exists():
        raise Saltar("falta el SVG de Clair de Lune o Chrome")
    pdf, xml = svg2pdf.SALIDA / "_prueba_web.pdf", web.BASE / "svg_to_xml/_prueba_web.musicxml"
    try:
        with servidor_web() as p:
            _, texto = peticion(p, "/pdf", {"nombre": "_prueba_web"}, {"p1.svg": svg.read_bytes()})
            assert texto.endswith("[código 0]\n"), texto
            _, texto = peticion(p, "/musicxml", {"nombre": "_prueba_web", "compas": "9/8"}, {"p1.svg": svg.read_bytes()})
            assert texto.endswith("[código 0]\n"), texto
        assert pdf.read_bytes().startswith(b"%PDF")
        assert xml.read_text(encoding="utf-8").count("<note") > 300
    finally:
        pdf.unlink(missing_ok=True)
        xml.unlink(missing_ok=True)


FORMULARIO_ESCENARIO = """<pre id="resultado"></pre><script>
(async () => {
  const r = {};
  r.inicio = [$('panel-home').hidden, $('panel-convertir').hidden];
  location.hash = '#convertir';
  await new Promise(f => setTimeout(f, 50));
  r.pestana = [$('panel-home').hidden, $('panel-convertir').hidden, document.querySelector('[aria-current]').textContent];
  const lista = new DataTransfer();
  lista.items.add(new File(['<svg/>'], 'obra_10.svg'));
  lista.items.add(new File(['<svg/>'], 'obra_02.svg'));
  $('svgs').files = lista.files;
  $('svgs').dispatchEvent(new Event('change'));
  r.nombre = $('nombre').value;
  r.pdf_oculta_url = document.querySelector('[name=url]').disabled;
  // el tiempo virtual no espera a un fetch: se le dan pasos hasta que termine
  let fin = false;
  $('formulario').onsubmit({preventDefault() {}, target: $('formulario')}).then(() => { fin = true; });
  while (!fin) await new Promise(f => setTimeout(f, 100));
  r.pdf = $('registro').textContent;
  r.pdf_clase = $('registro').className;
  document.querySelector('[value=pipeline]').click();
  document.querySelector('[name=url]').value = 'https://musescore.com/a/scores/1';
  r.pipeline_valido = $('formulario').checkValidity();
  document.querySelector('[name=url]').value = '';
  r.pipeline_sin_url = $('formulario').checkValidity();
  document.getElementById('resultado').textContent = JSON.stringify(r);
})().catch(e => { document.getElementById('resultado').textContent = JSON.stringify({error: String(e.stack)}); });
</script>"""


def test_web_formulario_en_chrome():
    if not Path(svg2pdf.CHROME).exists():
        raise Saltar("falta Chrome")
    with web_con_falsos() as (p, d):
        html = (REPO / "index.html").read_text(encoding="utf-8").replace("</html>", FORMULARIO_ESCENARIO + "</html>")
        (d / "index.html").write_text(html, encoding="utf-8")
        shutil.copy(REPO / "estilos.css", d)
        esperar_puerto_desde_windows(f"http://localhost:{p}/")
        sal = subprocess.run([svg2pdf.CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={svg2pdf.windows(d / 'perfil')}",
                              "--virtual-time-budget=100000000", "--dump-dom", f"http://localhost:{p}/"], capture_output=True, timeout=120)
        texto = sal.stdout.decode("utf-8", "replace").partition('<pre id="resultado">')[2].partition("</pre>")[0]
        assert texto, sal.stderr[-500:]
        r = json.loads(html_lib.unescape(texto))
    assert "error" not in r, r["error"]
    assert r["inicio"] == [False, True] and r["pestana"] == [True, False, "Convertir"], r
    assert r["nombre"] == "obra" and r["pdf_oculta_url"] is True, r
    assert "obra" in r["pdf"] and "[código 0]" in r["pdf"] and "mal" not in r["pdf_clase"], r
    assert r["pipeline_valido"] is True and r["pipeline_sin_url"] is False, r


if __name__ == "__main__":
    main()
