"""Preparación común de los tests locales.

Los tests cargan el archivo distribuible (ssoo-us), que es lo que usará el
alumnado, no los fuentes de src/. Ningún test usa claves, cuentas ni UVUS
reales: el alumno de prueba es «alu0000» y las claves se generan al vuelo.
"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys

sys.dont_write_bytecode = True

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "ssoo-us")
UVUS = "alu0000"


def cargar():
    if "ssoo_us" not in sys.modules:
        cargador = importlib.machinery.SourceFileLoader("ssoo_us", SCRIPT)
        spec = importlib.util.spec_from_loader("ssoo_us", cargador)
        modulo = importlib.util.module_from_spec(spec)
        cargador.exec_module(modulo)
        sys.modules["ssoo_us"] = modulo
    return sys.modules["ssoo_us"]


su = cargar()


def lanzar(*argumentos):
    """Ejecuta ssoo-us como un proceso aparte, con el Python de los tests.
    Devuelve (código, salida, errores)."""
    p = subprocess.run([sys.executable, SCRIPT] + list(argumentos),
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()
