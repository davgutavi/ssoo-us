"""ssoo-us: herramientas de la asignatura Sistemas Operativos para crear y
diagnosticar máquinas virtuales con cloud-init en los servidores de la
asignatura.

Asignatura Sistemas Operativos, Universidad de Sevilla.
https://github.com/davgutavi/ssoo-us

Este archivo se genera con tools/build.py a partir de src/: no lo edite a mano.
"""

import os
import subprocess
import sys

VERSION = "0.1.0-dev"
PROGRAMA = "ssoo-us"

# Código de salida de lo que todavía no está portado. No lo usa ci-provision
# (10..45, 70 y 71) ni ci-diagnosis (0, 1 y 2): un test de aceptación que
# espere un código concreto falla siempre con este.
NO_IMPLEMENTADO = 69


# --- Órdenes externas -------------------------------------------------------

def entorno_ordenes(extra=None):
    """Entorno de las órdenes externas.

    LC_ALL=C: salidas en inglés y formato neutro (warcry y megadeth responden en
    español). LIBVIRT_DEFAULT_URI=qemu:///system: sin una sesión de login, o con
    la variable heredada (el libvirt de Homebrew pone qemu:///session), virsh se
    conectaría a otro libvirt y no vería ninguna máquina. Como en ci-provision,
    solo para desarrollo se puede cambiar con CI_PROVISION_LIBVIRT_URI.
    """
    entorno = dict(os.environ, LC_ALL="C", LANG="C")
    entorno["LIBVIRT_DEFAULT_URI"] = (os.environ.get("CI_PROVISION_LIBVIRT_URI")
                                      or "qemu:///system")
    if extra:
        entorno.update(extra)
    return entorno


def ejecutar(argv, timeout=None, entrada=None, entorno=None):
    """Ejecuta una orden externa sin teclado y con entorno_ordenes().

    entrada: texto que recibe por la entrada estándar; sin ella, /dev/null (una
    orden que pregunte no puede quedarse esperando). entorno: variables que se
    añaden a las de entorno_ordenes().

    Devuelve (código, salida, errores). El código es None si la orden no existe
    o no termina a tiempo.
    """
    extra = ({"input": entrada.encode("utf-8")} if entrada is not None
             else {"stdin": subprocess.DEVNULL})
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=entorno_ordenes(entorno), timeout=timeout, **extra)
    except (OSError, subprocess.TimeoutExpired):
        return None, "", ""
    return (p.returncode, p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))
