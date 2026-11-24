"""ssoo-us: herramientas de la asignatura Sistemas Operativos para crear y
diagnosticar máquinas virtuales con cloud-init en los servidores de la
asignatura.

Asignatura Sistemas Operativos, Universidad de Sevilla.
https://github.com/davgutavi/ssoo-us

Este archivo se genera con tools/build.py a partir de src/: no lo edite a mano.
"""

import base64
import glob
import grp
import hashlib
import ipaddress
import json
import os
import pwd
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import termios
import textwrap
import time
import unicodedata
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:  # diagnosis: sin PyYAML se omiten las comprobaciones de estructura
    yaml = None

# Cada instalación en los servidores lleva su versión (tools/instalar.sh no
# instala un ssoo-us distinto con la misma): se sube con cada una. X.Y.Z:
# Z para correcciones, Y para novedades, X si cambia la forma de usarlo.
VERSION = "1.1.1"
PROGRAMA = "ssoo-us"


# --- Lo que comparten provision y diagnosis ----------------------------------
#
# provision lo genera y diagnosis lo comprueba: si cambia, cambia en los dos.

IMAGEN_NOBLE = "noble-server-cloudimg-amd64.img"     # Ubuntu 24.04 (manual, 5.4.1)
INTERFAZ_VM = "enp1s0"
DNS_DE_LA_US = ("150.214.186.69", "150.214.130.15")
# Contraseña de consola de 'root' en las máquinas de provision (la misma que usa
# el manual de laboratorio)
PASS_CONSOLA = "s1st3mas"


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


def leer_bytes(ruta):
    """Contenido de un archivo, o None si no existe o no se puede leer."""
    try:
        with open(ruta, "rb") as f:
            return f.read()
    except OSError:
        return None


def ejecutar_visible(argv, cwd=None, salida=True):
    """Ejecuta una orden externa dejando que escriba en la terminal (sus errores
    siempre; su salida, si «salida»), sin teclado y con entorno_ordenes(), como
    las que ci-provision.sh lanza sin capturar (virt-install, qemu-img create,
    wget, cp). Devuelve su código, o 127 si no existe."""
    for flujo in (sys.stdout, sys.stderr):
        flujo.flush()
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, cwd=cwd,
                              stdout=None if salida else subprocess.DEVNULL,
                              env=entorno_ordenes()).returncode
    except OSError:
        return 127
