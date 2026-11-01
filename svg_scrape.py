"""Descarga los SVG de una página: los <svg> del DOM (svg_N) y los que llegan por la red (red_N).

Usa el Chrome instalado, con ventana visible. Desde WSL hay que correrlo con el Python de Windows,
porque Playwright no puede controlar chrome.exe desde Linux:

uvx.exe --python 3.12 --with playwright python svg_scrape.py URL [carpeta_salida]
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

MAX_PASOS = 200  # el scroll infinito nunca llega al final
# guarda cookies: fuera del repo. Las pruebas usan otro para no tocar este
PERFIL = Path(os.environ.get("SVG_SCRAPE_PERFIL", Path.home() / ".svg_scrape_chrome"))
ESPERA_VERIFICACION = 120_000

# XMLSerializer y no outerHTML: añade xmlns y da XML válido, abrible fuera de la página
LEER_SVGS = """els => els
    .filter(e => !e.parentElement?.closest('svg'))
    .map(e => new XMLSerializer().serializeToString(e))"""

# Devuelve si algo se movió. Mira todos los elementos porque hay páginas que desplazan
# un contenedor interno y la ventana no se mueve
BAJAR = """() => {
    const cajas = [document.scrollingElement, ...document.querySelectorAll('*')].filter(e =>
        e === document.scrollingElement || ['auto', 'scroll'].includes(getComputedStyle(e).overflowY));
    return cajas.map(e => {
        const antes = e.scrollTop;
        e.scrollBy(0, e.clientHeight);
        return e.scrollTop !== antes;
    }).some(Boolean);
}"""

url = sys.argv[1]
salida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "prueba"

red = {}


def guardar_respuesta(r):
    es_svg = "svg" in r.headers.get("content-type", "") or urlparse(r.url).path.endswith(".svg")
    if r.ok and es_svg:
        try:
            red[r.body()] = r.url
        except PlaywrightError as e:
            print(f"Aviso: no se pudo leer {r.url}: {e}", file=sys.stderr)


with sync_playwright() as p:
    navegador = p.chromium.launch_persistent_context(PERFIL, channel="chrome", headless=False)
    pagina = navegador.pages[0]
    pagina.on("response", guardar_respuesta)
    respuesta = pagina.goto(url, wait_until="load")
    if respuesta and respuesta.status in (403, 503):
        print(f"HTTP {respuesta.status}: si la ventana pide una verificación, resuélvela", file=sys.stderr)
        try:
            respuesta = pagina.wait_for_event(
                "response",
                lambda r: r.request.is_navigation_request() and r.frame == pagina.main_frame and r.ok,
                timeout=ESPERA_VERIFICACION,
            )
        except PlaywrightTimeout:
            pass  # el mensaje final dirá que sigue bloqueada
    try:
        pagina.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass  # hay páginas que nunca dejan de pedir datos; se sigue con lo cargado

    # Se lee en cada paso porque hay páginas que quitan del DOM lo que sale de pantalla
    svgs = {}
    for paso in range(MAX_PASOS):
        svgs.update(dict.fromkeys(pagina.locator("svg").evaluate_all(LEER_SVGS)))
        if not pagina.evaluate(BAJAR):
            break
        pagina.wait_for_timeout(500)
    else:
        print(f"Aviso: se paró tras {MAX_PASOS} pantallas, puede faltar contenido", file=sys.stderr)
    pagina.wait_for_timeout(2000)  # lo pedido por el último scroll aún puede venir en camino
    # Una página de bloqueo también carga bien: sin esto parecería que no tiene <svg>
    estado = f"HTTP {respuesta.status if respuesta else '?'}, título: {pagina.title()!r}"
    navegador.close()

if not svgs and not red:
    sys.exit(f"no hay SVG en {url} ({estado})")

salida.mkdir(parents=True, exist_ok=True)
for i, svg in enumerate(svgs, 1):
    destino = salida / f"svg_{i}.svg"
    destino.write_text(svg, encoding="utf-8")
    print(destino)
for i, (cuerpo, origen) in enumerate(red.items(), 1):
    destino = salida / f"red_{i}.svg"
    destino.write_bytes(cuerpo)
    print(destino, "<-", origen)
