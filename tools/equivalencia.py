#!/usr/bin/env python3
"""Pruebas de equivalencia: la misma orden con ci-provision.sh y con
«ssoo-us provision» tiene que dar la misma salida, los mismos errores y el
mismo código.

    python3 tools/equivalencia.py [--fase N] [RUTA_DE_CI_PROVISION_SH]

Por defecto, ../ci-provision/ci-provision.sh, con el bash del PATH (tiene que
ser bash 4 o posterior). Los tests de bats solo miran trozos de la salida;
esto compara el texto entero, normalizando lo que tiene que cambiar:

  - la orden («$0» en ci-provision.sh, «ssoo-us provision» aquí) → ORDEN;
  - «ci-provision.sh X.Y.Z» y «ssoo-us X.Y.Z» → VERSION.

Cada caso lleva la fase del port a partir de la cual tiene que coincidir; con
--fase N se prueban los de las fases 1 a N (por defecto, todos).
"""

import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSOO_US = os.path.join(RAIZ, "ssoo-us")

# (fase, argumentos, entorno extra)
CASOS = [
    (1, ["-h"], {}),
    (1, ["--help"], {}),
    (1, ["--version"], {}),
    (1, [], {}),
    (1, ["usuario-server1", "server1.qcow2", "server1", "usuario-red"], {}),
    (1, ["--enable-root", "server1"], {}),
    (1, ["--virt-viewer", "server1"], {}),
    (1, ["--user-pass", "x", "server1"], {}),
    (1, ["--noexiste", "server1"], {}),
    (1, ["-x"], {}),
    (1, ["-"], {}),
    (1, ["server1", "--ram"], {}),
    (1, ["--ssh-pass", "--extra-disks", "server1"], {}),
    (1, ["--ram", "", "server1"], {}),
    (1, ["--ram=4096", "server1"], {}),
    (1, ["--=x"], {}),
    (1, ["a b"], {}),
    (1, ["server_1"], {}),
    (1, ["-server1"], {}),
    (1, ["a" * 64], {}),
    (1, ["--prefijo", "demo", "demo-server1"], {}),
    (1, ["--prefijo", "Demo", "dEMO-web-1"], {}),
    (1, ["--prefijo", "demo/x", "server1"], {}),
    (1, ["--prefijo", "-x", "server1"], {}),
    (1, ["--dry-run", "--ram", "abc", "server1"], {}),
    (1, ["--dry-run", "--ram", "128", "server1"], {}),
    (1, ["--dry-run", "--ram", "0512x", "server1"], {}),
    (1, ["--dry-run", "--vcpus", "0", "server1"], {}),
    (1, ["--tam", "40", "server1"], {}),
    (1, ["--tam", "0g", "server1"], {}),
    (1, ["--tam", "ñ", "server1"], {}),
    (1, ["--disco", "../fuera.qcow2", "server1"], {}),
    (1, ["--base", "/abs.qcow2", "server1"], {}),
    (1, ["--red", "a red", "server1"], {}),
    (1, ["--ssh-pass", "contraseñá", "server1"], {}),
    (1, ["--ssh-pass", "con\ttab", "server1"], {}),
    (1, ["--ssh-pass", "-", "server1"], {}),
    (1, ["--imagen", "ubuntu", "server1"], {}),
    (1, ["--imagen", "ubuntu-base", "server1"], {}),
    (1, ["--base", "x.qcow2", "--imagen", "otra", "server1"], {}),
    (1, ["--gluster-cluster", "server1"], {}),
    (1, ["--gluster-cluster", "--disco", "x.qcow2"], {}),
    (1, ["--gluster-cluster", "--glusterfs"], {}),
    (1, ["--gluster-cluster", "--ip-inicial", "251"], {}),
    (1, ["--gluster-cluster", "--ip-inicial", "1"], {}),
    (1, ["--gluster-cluster", "--discos-nodo", "2"], {}),
    (1, ["--gluster-cluster", "--discos-nodo", "8"], {}),
    (1, ["--discos-nodo", "4", "server1"], {}),
    (1, ["--ip-inicial", "20", "server1"], {}),
    (1, ["--glusterfs", "--no-wait", "base"], {}),
    (1, ["--glusterfs", "--extra-disks", "base"], {}),
    (1, ["--glusterfs", "base", "192.168.7.2"], {}),
    (1, ["--listar", "--eliminar"], {}),
    (1, ["--listar", "--extra-disks"], {}),
    (1, ["--listar", "server1"], {}),
    (1, ["--menu", "server1"], {}),
    (1, ["--eliminar"], {}),
    (1, ["--eliminar", "server1", "mal_nombre"], {}),
    (1, ["--", "-raro"], {}),
    (1, ["server1"], {"CI_PROVISION_POLL_SECS": "x"}),
    (1, ["server1"], {"CI_PROVISION_POLL_SECS": "0"}),
    (1, ["server1"], {"CI_PROVISION_WAIT_TIMEOUT": "abc"}),
    (1, ["server1"], {"CI_PROVISION_GRACE_SECS": "-1"}),
    (1, ["server1"], {"CI_PROVISION_SHUTDOWN_TIMEOUT": "1.5"}),
]

NO_IMPLEMENTADO_RE = re.compile(r"ssoo-us provision: todavía no está implementado")


def ejecutar(argv, extra):
    entorno = dict(os.environ, **extra)
    p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=entorno, timeout=60)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def normalizar(texto, orden):
    texto = texto.replace(orden, "ORDEN")
    return re.sub(r"^(ci-provision\.sh|ssoo-us) [0-9][^\s]*$", "VERSION", texto, flags=re.M)


def main():
    argv = sys.argv[1:]
    fase = 99
    if argv[:1] == ["--fase"]:
        fase = int(argv[1])
        argv = argv[2:]
    script = os.path.abspath(argv[0] if argv else
                             os.path.join(RAIZ, "..", "ci-provision", "ci-provision.sh"))
    distintos = 0
    casos = [c for c in CASOS if c[0] <= fase]
    for _, args, extra in casos:
        a = ejecutar(["bash", script] + args, extra)
        b = ejecutar([sys.executable, SSOO_US, "provision"] + args, extra)
        a = (a[0], normalizar(a[1], script), normalizar(a[2], script))
        b = (b[0], normalizar(b[1], SSOO_US + " provision"),
             normalizar(b[2], SSOO_US + " provision"))
        if a != b:
            distintos += 1
            print("✘ %s %s" % (" ".join(repr(x) for x in args),
                               " ".join("%s=%s" % kv for kv in extra.items())))
            for nombre, x, y in (("código", a[0], b[0]), ("salida", a[1], b[1]),
                                 ("errores", a[2], b[2])):
                if x != y:
                    print("   %s:\n     ci-provision: %r\n     ssoo-us:      %r" % (nombre, x, y))
    print("%d de %d casos iguales." % (len(casos) - distintos, len(casos)))
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
