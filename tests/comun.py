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
import tempfile

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


def lanzar(*argumentos, entorno=None):
    """Ejecuta ssoo-us como un proceso aparte, con el Python de los tests.
    Devuelve (código, salida, errores)."""
    p = subprocess.run([sys.executable, SCRIPT] + list(argumentos),
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=entorno)
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


_SIN_LIBVIRT = tempfile.TemporaryDirectory()


def entorno_sin_libvirt():
    """Un entorno con qemu-img, virsh y virt-install de mentira, y un virsh que
    no puede conectar con libvirt: provision se detiene con el error 38, aquí
    y en un servidor con libvirt de verdad."""
    directorio = _SIN_LIBVIRT.name
    for orden, codigo in (("qemu-img", 0), ("virt-install", 0), ("virsh", 1)):
        ruta = os.path.join(directorio, orden)
        if not os.path.exists(ruta):
            with open(ruta, "w") as f:
                f.write("#!/bin/sh\nexit %d\n" % codigo)
            os.chmod(ruta, 0o755)
    return dict(os.environ, PATH=directorio + os.pathsep + "/usr/bin:/bin")


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()
