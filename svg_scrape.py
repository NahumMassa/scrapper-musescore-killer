"""Descarga los SVG de una página: los <svg> del DOM (svg_N) y los que llegan por la red (red_N).

Abre tu Chrome instalado (con ventana, como proceso normal y no el que lanza Playwright, que
Cloudflare bloquea más) con depuración remota, y se conecta a él. Si ya hay un Chrome escuchando en
el puerto, lo reutiliza. Desde WSL hay que correrlo con el Python de Windows:

uvx.exe --python 3.12 --with playwright python svg_scrape.py URL [carpeta_salida]

Por defecto guarda en D:\\Nahum\\omr_partituras\\svg_partituras\\<título>\\. En musescore.com solo guarda las hojas
(.../score_N.svg), como <título>_<N+1>.svg, y las pide todas aunque la página no las cargue.
En otras páginas guarda svg_N / red_N.
Si falta alguna hoja, avisa; si faltan más de 3, reintenta dos veces con espera y, si siguen faltando, sale con 3.
Un 403/429 en una hoja detiene todo sin reintentar (así no se daña la reputación del navegador).
Códigos de salida: 2 = página bloqueada o petición rechazada, 3 = hojas incompletas.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

MAX_PASOS = 200  # el scroll infinito nunca llega al final
# guarda cookies: fuera del repo, y no puede ser el de uso diario (Chrome 136+ ignora la depuración ahí).
# Las pruebas usan otro para no tocar este
PERFIL = Path(os.environ.get("SVG_SCRAPE_PERFIL", Path.home() / ".svg_scrape_chrome"))
ESPERA_VERIFICACION = 120_000
PUERTO = 9222
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BLOQUEO = "!/^(Un momento|Just a moment)/i.test(document.title)"
MAX_HOJAS = 500
PAUSA = 1  # s entre peticiones de hojas, para no parecer una ráfaga
TOLERADAS = 3  # hojas que pueden faltar sin reintentar: solo se avisa
REINTENTOS = 2
# La ficha de MuseScore tiene una fila "Páginas | N" (o "Pages")
TOTAL_HOJAS = """[...document.querySelectorAll('th')]
    .find(t => /^(p[aá]ginas|pages)$/i.test(t.innerText.trim()))?.nextElementSibling?.innerText.trim()"""


class Rechazo(Exception):
    pass
SALIDA_POR_DEFECTO = r"D:\Nahum\omr_partituras\svg_partituras"  # este script corre con el Python de Windows

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
por_defecto = len(sys.argv) <= 2
salida = Path(SALIDA_POR_DEFECTO if por_defecto else sys.argv[2])

red = {}


def guardar_respuesta(r):
    es_svg = "svg" in r.headers.get("content-type", "") or urlparse(r.url).path.endswith(".svg")
    if r.ok and es_svg:
        try:
            red[r.body()] = r.url
        except PlaywrightError as e:
            print(f"Aviso: no se pudo leer {r.url}: {e}", file=sys.stderr)


def chrome_listo():
    try:
        urlopen(f"http://127.0.0.1:{PUERTO}/json/version", timeout=1)
        return True
    except OSError:
        return False


proceso = None
if not chrome_listo():
    proceso = subprocess.Popen([CHROME, f"--remote-debugging-port={PUERTO}", f"--user-data-dir={PERFIL}",
                                "--no-first-run", "about:blank"])
    for _ in range(40):
        if chrome_listo():
            break
        time.sleep(.5)
    else:
        sys.exit("Chrome no abrió el puerto de depuración")

with sync_playwright() as p:
    navegador = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PUERTO}")
    contexto = navegador.contexts[0]
    pagina = contexto.new_page()
    pagina.on("response", guardar_respuesta)
    respuesta = pagina.goto(url, wait_until="load")
    bloqueada = False
    if "Un momento" in pagina.title() or "Just a moment" in pagina.title():
        print("Cloudflare pide una verificación: resuélvela en la ventana", file=sys.stderr)
        try:
            pagina.wait_for_function(BLOQUEO, timeout=ESPERA_VERIFICACION)
        except PlaywrightTimeout:
            bloqueada = True
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

    # Hojas score_N.svg: el visor solo carga las que se ven, así que se piden las que faltan
    hojas = {}
    plantilla = None
    for cuerpo, origen in red.items():
        m = re.search(r"/score_(\d+)\.svg", origen)
        if m:
            hojas[int(m[1])] = cuerpo
            plantilla = origen[:m.start(1)] + "{}" + origen[m.end(1):]
    total = pagina.evaluate(TOTAL_HOJAS)  # None si la página no lo dice
    total = int(total) if total and total.isdigit() else None
    print(f"Hojas según la ficha: {total or 'desconocido'}", file=sys.stderr)
    rechazo = None  # HTTP 403/429 de una hoja: se para en seco para no dañar la reputación del navegador

    def pedir(n):
        """El cuerpo de la hoja n, None si no existe (404). Reintenta los fallos del servidor."""
        for intento in range(3):
            r = contexto.request.get(plantilla.replace("{}", str(n)))
            if r.ok:
                return r.body()
            if r.status in (404, 410):
                return None
            if r.status in (403, 429):
                raise Rechazo(r.status)
            time.sleep(5 * 3 ** intento)
        raise Rechazo(0)

    def completar():
        global rechazo
        for n in range(total) if total else range(MAX_HOJAS):
            if n in hojas:
                continue
            time.sleep(PAUSA)
            try:
                cuerpo = pedir(n)
            except Rechazo as e:
                if e.args[0]:
                    rechazo = e.args[0]
                    return
                continue  # fallo pasajero del servidor: la hoja queda como faltante
            if cuerpo is None:
                return
            hojas[n] = cuerpo

    def faltan():
        return [n + 1 for n in range(total) if n not in hojas] if total else []

    if plantilla:
        completar()
        for ronda in range(REINTENTOS):
            if rechazo or len(faltan()) <= TOLERADAS:
                break
            espera = 30 * 4 ** ronda
            print(f"Faltan {len(faltan())} hojas: reintento en {espera} s", file=sys.stderr)
            time.sleep(espera)
            completar()

    titulo = pagina.evaluate(
        "document.querySelector('meta[property=\"og:title\"]')?.content || document.querySelector('h1')?.innerText"
    ) or pagina.title()
    # Una página de bloqueo también carga bien: sin esto parecería que no tiene <svg>
    estado = f"HTTP {respuesta.status if respuesta else '?'}, título: {pagina.title()!r}"
    pagina.close()
    navegador.close()  # por CDP solo se desconecta; Chrome sigue abierto
if proceso:
    proceso.terminate()

if bloqueada:
    print(f"{url} sigue bloqueada ({estado}). No se reintenta: espera unas horas.", file=sys.stderr)
    sys.exit(2)
if not svgs and not red and not hojas:
    sys.exit(f"no hay SVG en {url} ({estado})")



def guardar(nombre, cuerpo, origen=""):
    destino = salida / nombre
    if destino.exists():
        print(f"Aviso: se sobrescribe {destino}", file=sys.stderr)
    destino.write_bytes(cuerpo)
    print(destino, "<-" if origen else "", origen)


solo_hojas = hojas and "musescore.com" in urlparse(url).netloc
base = re.sub(r"\W+", "_", titulo.strip().lower()).strip("_") or "hoja"
if por_defecto and solo_hojas:
    salida /= base  # una carpeta por obra; con carpeta explícita se respeta tal cual
salida.mkdir(parents=True, exist_ok=True)
if not solo_hojas:
    for i, svg in enumerate(svgs, 1):
        guardar(f"svg_{i}.svg", svg.encode("utf-8"))
for n, cuerpo in sorted(hojas.items()):
    guardar(f"{base}_{n + 1:02d}.svg", cuerpo)
if not solo_hojas:
    for i, (cuerpo, origen) in enumerate(red.items(), 1):
        if not re.search(r"/score_(\d+)\.svg", origen):
            guardar(f"red_{i}.svg", cuerpo, origen)

if rechazo:
    print(f"El sitio rechazó una petición (HTTP {rechazo}). Se paró sin reintentar y se guardaron "
          f"{len(hojas)} hojas. Espera unas horas antes de volver a intentarlo.", file=sys.stderr)
    sys.exit(2)
if faltan():
    print(f"Aviso: faltan las hojas {faltan()} de {total}", file=sys.stderr)
    if len(faltan()) > TOLERADAS:
        sys.exit(3)
