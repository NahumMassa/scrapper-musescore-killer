"""Servidor local de la página: sirve las pestañas y ejecuta los tres scripts. Correr desde WSL.

Uso: .venv/bin/python web.py [puerto]   -> http://localhost:8766

Solo escucha en 127.0.0.1 y rechaza otros orígenes: cualquier web abierta en el navegador podría, si no,
enviar formularios a este puerto y lanzar capturas.
"""
import contextlib
import email.parser
import email.policy
import functools
import http.server
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
from svg2pdf import orden_natural  # noqa: E402

REPO = Path(__file__).parent
BASE = Path("/mnt/d/Nahum/omr_partituras")
PUBLICAS = {"/", "/index.html", "/practica.html", "/estilos.css"}
MAX_SUBIDA = 500 * 1024 * 1024
NOMBRE = re.compile(r'[^-.\s<>:"/\\|?*\x00-\x1f]([^<>:"/\\|?*\x00-\x1f]*[^.\s<>:"/\\|?*\x00-\x1f])?')
# Un trabajo a la vez: dos capturas seguidas son justo lo que puede provocar un bloqueo de MuseScore.
OCUPADO = threading.Lock()


def leer_formulario(tipo, cuerpo):
    """Devuelve los campos de texto y los archivos de un multipart/form-data."""
    mensaje = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(f"Content-Type: {tipo}\r\n\r\n".encode() + cuerpo)
    campos, archivos = {}, {}
    for parte in mensaje.iter_parts():
        datos = parte.get_payload(decode=True)
        archivo = parte.get_filename()
        if archivo is None:
            campos[parte.get_param("name", header="content-disposition")] = datos.decode("utf-8", "replace").strip()
        elif archivo:  # sin nombre es que no se eligió archivo; uno de 0 bytes sigue y lo rechaza el script
            archivos[archivo] = datos
    return campos, archivos


def validar(accion, campos, archivos):
    """Falla con ValueError si la petición no es correcta."""
    nombre, compas = campos.get("nombre", ""), campos.get("compas", "")
    if accion == "/pipeline":
        if not re.fullmatch(r"""https?://[^\s"'<>]+""", campos.get("url", "")):
            raise ValueError("El enlace debe empezar por http:// o https://")
    else:
        if not nombre:
            raise ValueError("Falta el nombre de salida")
        if not archivos:
            raise ValueError("Elige al menos un SVG")
        for f in archivos:
            if not f.lower().endswith(".svg") or not NOMBRE.fullmatch(f):
                raise ValueError(f"Nombre de archivo no válido: {f}")
    if nombre and not NOMBRE.fullmatch(nombre):
        raise ValueError(f"Nombre no válido: {nombre}")
    if nombre.lower().endswith("_revisado"):
        raise ValueError("Ese nombre es de un MusicXML revisado: regenerar no debe sobrescribirlo")
    if compas and not re.fullmatch(r"[1-9]\d*/[1-9]\d*", compas):
        raise ValueError(f"Compás no válido: {compas}; usa la forma 9/8")


def comando(accion, campos, carpeta):
    py, nombre, compas = [sys.executable, "-u"], campos.get("nombre"), campos.get("compas")
    opcion_compas = ["--compas", compas] if compas else []
    if accion == "/pdf":
        return [*py, str(REPO / "svg2pdf.py"), str(carpeta), nombre]
    if accion == "/musicxml":
        (BASE / "svg_to_xml").mkdir(exist_ok=True)
        svgs = sorted(Path(carpeta).glob("*.svg"), key=orden_natural)
        return [*py, str(REPO / "svg2musicxml.py"), *map(str, svgs), "-o", str(BASE / "svg_to_xml" / f"{nombre}.musicxml"), *opcion_compas]
    return [*py, str(REPO / "partitura.py"), campos["url"], *(["--nombre", nombre] if nombre else []), *opcion_compas]


class Manejador(http.server.SimpleHTTPRequestHandler):
    def host_valido(self):
        # también frena el DNS rebinding: un dominio ajeno que apunte a 127.0.0.1 llega con otro Host
        puerto = self.server.server_port
        return self.headers.get("Host") in (f"localhost:{puerto}", f"127.0.0.1:{puerto}")

    def responder(self, codigo, texto):
        cuerpo = texto.encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def send_head(self):
        ruta = posixpath.normpath(urllib.parse.unquote(self.path.split("?")[0]))  # /vendor/../web.py es /web.py
        # el repo también tiene .git y .venv: solo se sirve lo que usa la página
        if not self.host_valido() or (ruta not in PUBLICAS and not ruta.startswith("/vendor/")):
            self.send_error(404)
            return None
        return super().send_head()

    def do_POST(self):
        if self.path not in ("/pdf", "/musicxml", "/pipeline"):
            return self.responder(404, "No existe esa acción")
        if not self.host_valido() or self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            return self.responder(403, "Origen no permitido")
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > MAX_SUBIDA:
            return self.responder(413, "La subida es demasiado grande")
        campos, archivos = leer_formulario(self.headers.get("Content-Type", ""), self.rfile.read(largo))
        try:
            validar(self.path, campos, archivos)
        except ValueError as e:
            return self.responder(400, str(e))
        if not BASE.exists():
            return self.responder(500, f"Falta la carpeta {BASE}")
        if not OCUPADO.acquire(blocking=False):
            return self.responder(409, "Ya hay un trabajo en marcha; espera a que termine")
        try:
            # en D:: Chrome y uvx.exe son de Windows
            with tempfile.TemporaryDirectory(dir=BASE, prefix=".web_", ignore_cleanup_errors=True) as carpeta:
                for f, datos in archivos.items():
                    (Path(carpeta) / f).write_bytes(datos)
                self.ejecutar(comando(self.path, campos, carpeta))
        finally:
            OCUPADO.release()

    def ejecutar(self, cmd):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        # WSLENV: uvx.exe es de Windows y solo recibe las variables que se le pasan por ahí
        entorno = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                       WSLENV=os.environ.get("WSLENV", "") + ":PYTHONUNBUFFERED:PYTHONIOENCODING")
        with subprocess.Popen(cmd, cwd=REPO, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as p:
            for linea in p.stdout:
                self.escribir(linea.decode("utf-8", "replace"))
            self.escribir(f"\n[código {p.wait()}]\n")

    def escribir(self, texto):
        # Si se cierra la pestaña el script sigue: cortar una captura a medias deja restos en D:.
        with contextlib.suppress(OSError):
            self.wfile.write(texto.encode())

    def log_message(self, *args):
        pass


def servidor(puerto):
    manejador = functools.partial(Manejador, directory=str(REPO))
    return http.server.ThreadingHTTPServer(("127.0.0.1", puerto), manejador)


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    print(f"http://localhost:{puerto}")
    servidor(puerto).serve_forever()
