#!/usr/bin/env python3
"""Pruebas de equivalencia: la misma orden con ci-provision.sh y con
«ssoo-us provision» tiene que dar la misma salida, los mismos errores, el mismo
código y los mismos efectos.

    python3 tools/equivalencia.py [--fase N] [-v] [RUTA_DE_CI_PROVISION_SH]

Por defecto, ../ci-provision/ci-provision.sh, con el bash del PATH (tiene que
ser bash 4 o posterior). Los tests de bats solo miran trozos de la salida;
esto compara el texto entero.

Cada orden se ejecuta dos veces, en el mismo directorio y partiendo del mismo
estado: el entorno de los tests de aceptación (preparar_entorno de
tests/aceptacion/helpers.bash: HOME de mentira, silo, mocks de virsh y
virt-install...) más la preparación propia del caso (unas líneas de bash, que
pueden usar las funciones de helpers.bash). Se comparan:

  - el código, la salida y los errores;
  - los ficheros que quedan en el silo (nombre y contenido de los de texto);
  - el registro de llamadas a los mocks ($MOCK_STATE/log).

Se normaliza lo que tiene que cambiar o cambia solo: la orden («$0» en
ci-provision.sh, «ssoo-us provision» aquí) → ORDEN; «ci-provision.sh X.Y.Z» y
«ssoo-us X.Y.Z» → VERSION; la fecha del instance-id.

Cada caso lleva la fase del port a partir de la cual tiene que coincidir; con
--fase N se prueban los de las fases 1 a N (por defecto, todos).
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSOO_US = os.path.join(RAIZ, "ssoo-us")
ACEPTACION = os.path.join(RAIZ, "tests", "aceptacion")

# Preparaciones que se repiten
SIN_NOBLE = 'rm -f "$SILO/noble-server-cloudimg-amd64.img"'
RED_8 = 'definir_red "${USUARIO}-net" 192.168.8.1 255.255.255.0 192.168.8.128 192.168.8.254'
DHCP_10_13 = ('quitar_red "${USUARIO}-red"; definir_red "${USUARIO}-red" 192.168.144.1 '
              '255.255.255.0 192.168.144.2 192.168.144.127')
RED_SIN_MASCARA = r'''quitar_red "${USUARIO}-red"
printf '%s\n' "<network>" "  <name>${USUARIO}-red</name>" "  <ip address='192.168.7.1'>" \
  "    <dhcp><range start='192.168.7.128' end='192.168.7.254'/></dhcp>" "  </ip>" "</network>" \
  > "$MOCK_STATE/red-${USUARIO}-red.xml"
echo "${USUARIO}-red" >> "$MOCK_STATE/redes.txt"'''
RED_PREFIX = r'''quitar_red "${USUARIO}-red"
printf '%s\n' "<network>" "  <name>${USUARIO}-red</name>" '  <ip address="192.168.7.1" prefix="24">' \
  '    <dhcp><range start="192.168.7.128" end="192.168.7.254"/></dhcp>' "  </ip>" "</network>" \
  > "$MOCK_STATE/red-${USUARIO}-red.xml"
echo "${USUARIO}-red" >> "$MOCK_STATE/redes.txt"'''
RED_SOLO_IPV6 = r'''quitar_red "${USUARIO}-red"
printf '%s\n' "<network>" "  <name>${USUARIO}-red</name>" "  <ip family='ipv6' address='fd00::1' prefix='64'/>" \
  "</network>" > "$MOCK_STATE/red-${USUARIO}-red.xml"
echo "${USUARIO}-red" >> "$MOCK_STATE/redes.txt"'''
RED_DHCPV6 = r'''quitar_red "${USUARIO}-red"
printf '%s\n' "<network>" "  <name>${USUARIO}-red</name>" "  <ip family='ipv6' address='fd00::1' prefix='64'>" \
  "    <dhcp><range start='fd00::100' end='fd00::1ff'/><host name='x' ip='fd00::5'/></dhcp>" "  </ip>" \
  "  <ip address='192.168.7.1' netmask='255.255.255.0'>" \
  "    <dhcp><range start='192.168.7.128' end='192.168.7.254'/></dhcp>" "  </ip>" "</network>" \
  > "$MOCK_STATE/red-${USUARIO}-red.xml"
echo "${USUARIO}-red" >> "$MOCK_STATE/redes.txt"'''
CADENA_DEBIAN = ('(cd "$SILO" && qemu-img create -f qcow2 -b debian12.qcow2 -F qcow2 deb-base.qcow2 '
                 '>/dev/null && qemu-img create -f qcow2 -b deb-base.qcow2 -F qcow2 deb-nieta.qcow2 '
                 '>/dev/null)')
MI_NOBLE = 'cp "$SILO/noble-server-cloudimg-amd64.img" "$SILO/mi-noble.qcow2"'
CADENA_ROTA = ('(cd "$SILO" && qemu-img create -u -f qcow2 -b no-existe.qcow2 -F qcow2 rota.qcow2 1G '
               '>/dev/null)')

# (fase, argumentos, entorno extra, preparación en bash)
CASOS = [
    (1, ["-h"], {}, ""),
    (1, ["--help"], {}, ""),
    (1, ["--version"], {}, ""),
    (1, [], {}, ""),
    (1, ["usuario-server1", "server1.qcow2", "server1", "usuario-red"], {}, ""),
    (1, ["--enable-root", "server1"], {}, ""),
    (1, ["--virt-viewer", "server1"], {}, ""),
    (1, ["--user-pass", "x", "server1"], {}, ""),
    (1, ["--noexiste", "server1"], {}, ""),
    (1, ["-x"], {}, ""),
    (1, ["-"], {}, ""),
    (1, ["server1", "--ram"], {}, ""),
    (1, ["--ssh-pass", "--extra-disks", "server1"], {}, ""),
    (1, ["--ram", "", "server1"], {}, ""),
    (1, ["--ram=4096", "server1"], {}, ""),
    (1, ["--=x"], {}, ""),
    (1, ["a b"], {}, ""),
    (1, ["server_1"], {}, ""),
    (1, ["-server1"], {}, ""),
    (1, ["a" * 64], {}, ""),
    (1, ["--prefijo", "demo", "demo-server1"], {}, ""),
    (1, ["--prefijo", "Demo", "dEMO-web-1"], {}, ""),
    (1, ["--prefijo", "demo/x", "server1"], {}, ""),
    (1, ["--prefijo", "-x", "server1"], {}, ""),
    (1, ["--dry-run", "--ram", "abc", "server1"], {}, ""),
    (1, ["--dry-run", "--ram", "128", "server1"], {}, ""),
    (1, ["--dry-run", "--ram", "0512x", "server1"], {}, ""),
    (1, ["--dry-run", "--vcpus", "0", "server1"], {}, ""),
    (1, ["--tam", "40", "server1"], {}, ""),
    (1, ["--tam", "0g", "server1"], {}, ""),
    (1, ["--tam", "ñ", "server1"], {}, ""),
    (1, ["--disco", "../fuera.qcow2", "server1"], {}, ""),
    (1, ["--base", "/abs.qcow2", "server1"], {}, ""),
    (1, ["--red", "a red", "server1"], {}, ""),
    (1, ["--ssh-pass", "contraseñá", "server1"], {}, ""),
    (1, ["--ssh-pass", "con\ttab", "server1"], {}, ""),
    (1, ["--ssh-pass", "-", "server1"], {}, ""),
    (1, ["--imagen", "ubuntu", "server1"], {}, ""),
    (1, ["--imagen", "ubuntu-base", "server1"], {}, ""),
    (1, ["--base", "x.qcow2", "--imagen", "otra", "server1"], {}, ""),
    (1, ["--gluster-cluster", "server1"], {}, ""),
    (1, ["--gluster-cluster", "--disco", "x.qcow2"], {}, ""),
    (1, ["--gluster-cluster", "--glusterfs"], {}, ""),
    (1, ["--gluster-cluster", "--ip-inicial", "251"], {}, ""),
    (1, ["--gluster-cluster", "--ip-inicial", "1"], {}, ""),
    (1, ["--gluster-cluster", "--discos-nodo", "2"], {}, ""),
    (1, ["--gluster-cluster", "--discos-nodo", "8"], {}, ""),
    (1, ["--discos-nodo", "4", "server1"], {}, ""),
    (1, ["--ip-inicial", "20", "server1"], {}, ""),
    (1, ["--glusterfs", "--no-wait", "base"], {}, ""),
    (1, ["--glusterfs", "--extra-disks", "base"], {}, ""),
    (1, ["--glusterfs", "base", "192.168.7.2"], {}, ""),
    (1, ["--listar", "--eliminar"], {}, ""),
    (1, ["--listar", "--extra-disks"], {}, ""),
    (1, ["--listar", "server1"], {}, ""),
    (1, ["--menu", "server1"], {}, ""),
    (1, ["--eliminar"], {}, ""),
    (1, ["--eliminar", "server1", "mal_nombre"], {}, ""),
    (1, ["--", "-raro"], {}, ""),
    (1, ["server1"], {"CI_PROVISION_POLL_SECS": "x"}, ""),
    (1, ["server1"], {"CI_PROVISION_POLL_SECS": "0"}, ""),
    (1, ["server1"], {"CI_PROVISION_WAIT_TIMEOUT": "abc"}, ""),
    (1, ["server1"], {"CI_PROVISION_GRACE_SECS": "-1"}, ""),
    (1, ["server1"], {"CI_PROVISION_SHUTDOWN_TIMEOUT": "1.5"}, ""),

    # Fase 2: entorno y --dry-run
    (2, ["--dry-run", "server1"], {"MOCK_SIN_LIBVIRT": "1"}, ""),
    (2, ["--dry-run", "server1"], {}, 'rm -rf "$SILO"'),
    (2, ["--dry-run", "server1"], {}, ""),
    (2, ["--dry-run", "server1"], {}, SIN_NOBLE),
    (2, ["--dry-run", "server1"], {}, SIN_NOBLE + '; cp "$UBUNTU_BASE_COMPARTIDA" '
                                             '"$CI_PROVISION_DIR_COMPARTIDO/noble-server-cloudimg-amd64.img"'),
    (2, ["--dry-run", "--imagen", "debian12", "server1"], {}, 'rm -f "$SILO/debian12.qcow2"'),
    (2, ["--dry-run", "server1"], {}, 'echo "<html>404</html>" > "$SILO/noble-server-cloudimg-amd64.img"'),
    (2, ["--dry-run", "server1"], {}, 'rm -f "$HOME/.ssh/id_rsa.pub"'),
    (2, ["--dry-run", "server1"], {}, r'''printf 'ssh-rsa AAAA a@b\nssh-ed25519 BBBB c@d\n' > "$HOME/.ssh/id_rsa.pub"'''),
    (2, ["--dry-run", "server1"], {}, ': > "$HOME/.ssh/id_rsa.pub"'),
    (2, ["--dry-run", "server1"], {}, r'''printf '  \n\t\n' > "$HOME/.ssh/id_rsa.pub"'''),
    (2, ["--dry-run", "server1"], {}, 'echo "esto no es una clave" > "$HOME/.ssh/id_rsa.pub"'),
    (2, ["--dry-run", "server1"], {}, r'''printf '\n  ssh-ed25519 AAAA x@y  \r\n\n' > "$HOME/.ssh/id_rsa.pub"'''),
    (2, ["--dry-run", "server1"], {}, '''echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFalsa David: '''
                                      '''portátil #1 'x'" > "$HOME/.ssh/id_rsa.pub"'''),
    (2, ["--dry-run", "server1"], {"CI_PROVISION_PUBKEY": "/no/existe.pub"}, ""),
    (2, ["--dry-run", "server1"], {}, 'quitar_red "${USUARIO}-red"; ' + RED_8),
    (2, ["--dry-run", "server1"], {}, 'quitar_red "${USUARIO}-red"; definir_red "${USUARIO}" '
                                      '192.168.8.1 255.255.255.0 192.168.8.128 192.168.8.254'),
    (2, ["--dry-run", "server1"], {}, 'quitar_red "${USUARIO}-red"; definir_red "${USUARIO^^}-network" '
                                      '192.168.8.1 255.255.255.0 192.168.8.128 192.168.8.254'),
    (2, ["--dry-run", "server1"], {}, 'definir_red "${USUARIO}" 192.168.8.1 255.255.255.0 '
                                      '192.168.8.128 192.168.8.254'),
    (2, ["--dry-run", "server1"], {}, 'quitar_red "${USUARIO}-red"; ' + RED_8 + '; definir_red '
                                      '"${USUARIO}_red2" 192.168.9.1 255.255.255.0 192.168.9.128 192.168.9.254'),
    (2, ["--dry-run", "server1"], {}, 'quitar_red "${USUARIO}-red"; definir_red otro-red 192.168.8.1 '
                                      '255.255.255.0 192.168.8.128 192.168.8.254; definir_red '
                                      '"${USUARIO}x-red" 192.168.9.1 255.255.255.0 192.168.9.128 192.168.9.254'),
    (2, ["--dry-run", "--red", "no-existe", "server1"], {}, ""),
    (2, ["--dry-run", "--red", "red-boletin", "server1", "192.168.113.50"], {},
     'definir_red red-boletin 192.168.113.1 255.255.255.0 192.168.113.100 192.168.113.200'),
    (2, ["--dry-run", "server1"], {}, 'touch "$MOCK_STATE/red-${USUARIO}-red.inactiva"'),
    (2, ["--dry-run", "server1", "192.168.7.2"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.200"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.1"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.0"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.255"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.9.2"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.999"], {}, ""),
    (2, ["--dry-run", "server1", "hola"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.007.020"], {}, ""),
    (2, ["--dry-run", "server1", "192.168.7.10"], {}, 'quitar_red "${USUARIO}-red"; definir_red '
                                                      '"${USUARIO}-red" 192.168.7.1 255.255.255.0 '
                                                      '192.168.7.128 192.168.7.254 192.168.7.10'),
    (2, ["--dry-run", "--red", "corchu-nat", "server1", "192.168.200.2"], {},
     'definir_red corchu-nat 192.168.200.254 255.255.255.0 192.168.200.1 192.168.200.253'),
    (2, ["--dry-run", "--red", "rara", "server1", "10.0.5.3"], {},
     'definir_red rara 10.0.0.1 255.0.255.0 10.0.0.100 10.0.0.200'),
    (2, ["--dry-run", "--extra-disks", "server1", "192.168.7.2"], {}, ""),
    (2, ["--dry-run", "--no-virt-viewer", "--no-root", "--ssh-pass", "a'b: #c", "web"], {}, ""),
    (2, ["--dry-run", "--prefijo", "demo", "--disco", "otro.qcow2", "--ram", "4096", "server1"], {}, ""),
    (2, ["--si", "--dry-run", "--limpiar", "server1"], {}, 'touch "$SILO/server1.qcow2"'),
    (2, ["--dry-run", "server1"], {}, 'touch "$SILO/server1.qcow2"'),
    (2, ["--dry-run", "--extra-disks", "server1"], {}, 'touch "$SILO/server1-vdc.qcow2"; '
                                                       'definir_dominio "${USUARIO}-server1" running '
                                                       '"$SILO/server1.qcow2"'),
    (2, ["--dry-run", "server1"], {}, 'definir_dominio "${USUARIO}-server1" running /otro/sitio.qcow2'),
    (2, ["--dry-run", "server1"], {}, 'touch "$SILO/server1.qcow2"; definir_dominio a-mano running '
                                      '"$SILO/server1.qcow2"'),
    (2, ["--dry-run", "server1"], {}, '(cd "$SILO" && qemu-img create -f qcow2 server1.qcow2 1G >/dev/null '
                                      '&& qemu-img create -f qcow2 -b server1.qcow2 -F qcow2 copia.qcow2 >/dev/null)'),
    (2, ["--dry-run", "--gluster-cluster"], {}, 'touch "$SILO/gluster-base.qcow2"'),
    (2, ["--dry-run", "--imagen", "ubuntu-base", "server1"], {}, ""),
    (2, ["--dry-run", "--imagen", "fedora", "server1"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--imagen", "ubuntu-base"], {}, 'rm -f "$UBUNTU_BASE_COMPARTIDA"'),
    (2, ["--dry-run", "--gluster-cluster", "--imagen", "ubuntu-base"], {}, ""),
    (2, ["--dry-run", "--glusterfs", "--imagen", "ubuntu-base", "--no-root", "gbase"], {}, ""),
    (2, ["--dry-run", "--glusterfs", "gbase"], {}, ""),
    (2, ["--dry-run", "--imagen", "fedora", "--base", "debian12.qcow2", "server1"], {}, ""),
    (2, ["--dry-run", "--extra-disks", "--disco", "server1-vdb.qcow2", "server1"], {}, ""),
    (2, ["--dry-run", "--tam", "1G", "server1"], {}, ""),
    (2, ["--dry-run", "--tam", "20G", "--base", "mibase.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/mibase.qcow2" 40G >/dev/null'),
    (2, ["--dry-run", "--tam", "40G", "--base", "mibase.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/mibase.qcow2" 40G >/dev/null'),
    (2, ["--dry-run", "--base", "mibase.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/mibase.qcow2" 50G >/dev/null'),
    (2, ["--dry-run", "--base", "deb-nieta.qcow2", "server1"], {}, CADENA_DEBIAN),
    (2, ["--dry-run", "--gluster-cluster", "--base", "gluster-base.qcow2"], {},
     'cp "$UBUNTU_BASE_COMPARTIDA" "$SILO/gluster-base.qcow2"'),
    (2, ["--dry-run", "server1"], {}, RED_SIN_MASCARA),
    (2, ["--dry-run", "server1", "192.168.7.50"], {}, RED_PREFIX),
    (2, ["--dry-run", "server1"], {}, RED_SOLO_IPV6),
    (2, ["--dry-run", "server1", "192.168.7.2"], {}, RED_DHCPV6),
    (2, ["--dry-run", "server1", "192.168.7.130"], {}, RED_DHCPV6),
    (2, ["--dry-run", "--red", "a,b", "server1"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--prefijo", "demo", "--discos-nodo", "7",
         "--no-virt-viewer", "--imagen", "debian12"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--discos-nodo", "4"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--base", "noexiste.qcow2"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--base", "rota.qcow2"], {}, 'echo hola > "$SILO/rota.qcow2"'),
    (2, ["--dry-run", "--gluster-cluster", "--base", "server1.qcow2"], {},
     'qemu-img create -f qcow2 "$SILO/server1.qcow2" 1G >/dev/null'),
    (2, ["--dry-run", "--base", "server1.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/server1.qcow2" 1G >/dev/null'),
    (2, ["--dry-run", "--base", "noble-server-cloudimg-amd64.img", "noble-server-cloudimg-amd64"], {}, ""),
    (2, ["--dry-run", "--disco", "debian12.qcow2", "server1"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--ram", "2048", "--vcpus", "2"], {}, ""),
    (2, ["--dry-run", "--base", "rota.qcow2", "server1"], {}, CADENA_ROTA),
    (2, ["--dry-run", "--base", "mi-noble.qcow2", "server1"], {}, MI_NOBLE),
    (2, ["--dry-run", "--base", "mi-noble.qcow2", "--imagen", "debian12", "server1"], {}, MI_NOBLE),
    (2, ["--dry-run", "--base", "en-uso.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/en-uso.qcow2" 1G >/dev/null; definir_dominio otro shut\\ off '
     '"$SILO/en-uso.qcow2"'),
    (2, ["--dry-run", "--gluster-cluster"], {}, DHCP_10_13),
    (2, ["--dry-run", "--gluster-cluster", "--ip-inicial", "200"], {}, DHCP_10_13),
    (2, ["--dry-run", "--gluster-cluster"], {}, 'quitar_red "${USUARIO}-red"; definir_red '
                                               '"${USUARIO}-red" 192.168.144.1 255.255.255.0 '
                                               '192.168.144.2 192.168.144.254'),
    (2, ["--dry-run", "--tam", "080G", "--ram", "0900", "--vcpus", "02", "server1", "192.168.7.020"], {}, ""),
    (2, ["--dry-run", "--gluster-cluster", "--discos-nodo", "07"], {}, ""),
    (2, ["--dry-run", "--tam", "08G", "server1"], {}, ""),
    (2, ["--dry-run", "server1"], {"WAIT_TIMEOUT": "abc", "POLL_SECS": "x"}, ""),
    (2, ["--dry-run", "server1", "192.168.7.2"], {}, 'echo 192.168.7.2 > "$MOCK_STATE/ping_responde"'),
    (2, ["--dry-run", "--gluster-cluster"], {}, 'echo 192.168.7.12 > "$MOCK_STATE/ping_responde"'),
    (2, ["--dry-run", "server1", "192.168.7.2"], {},
     r'''mkdir -p "$SILO/cloudinit-${USUARIO}-web" && printf '    addresses:\n      - 192.168.7.2/24\n' > "$SILO/cloudinit-${USUARIO}-web/cip-net.yaml" && definir_dominio "${USUARIO}-web" running "$SILO/web.qcow2"'''),
    (2, ["--dry-run", "server1", "192.168.7.2"], {},
     r'''mkdir -p "$SILO/cloudinit-demo-web" && printf '      - 192.168.7.2/24\n' > "$SILO/cloudinit-demo-web/cip-net.yaml" && definir_dominio demo-web running "$SILO/demo-web.qcow2"'''),
    (2, ["--dry-run", "--limpiar", "--si", "server1", "192.168.7.2"], {},
     r'''mkdir -p "$SILO/cloudinit-${USUARIO}-server1" && printf '      - 192.168.7.2/24\n' > "$SILO/cloudinit-${USUARIO}-server1/cip-net.yaml" && echo 192.168.7.2 > "$MOCK_STATE/ping_responde"'''),
]


def preparar(directorio):
    """Un directorio vacío y siempre el mismo, como el $BATS_TEST_TMPDIR de bats."""
    if os.path.exists(directorio):
        shutil.rmtree(directorio)
    os.makedirs(directorio)


def ejecutar_caso(directorio, orden, extra, preparacion):
    """Prepara el entorno de helpers.bash, aplica la preparación y lanza la
    orden en el mismo bash. Devuelve (código, salida, errores)."""
    preparar(directorio)
    # Las variables del caso, después de preparar_entorno, que fija las suyas
    exportar = "".join("export %s=%s; " % (k, shlex.quote(v)) for k, v in extra.items())
    guion = ('source "$1"; preparar_entorno || exit 99; eval "$2" || exit 98; shift 2; '
             + exportar + '"$@"')
    entorno = dict(os.environ, BATS_TEST_FILENAME=os.path.join(ACEPTACION, "ci-provision.bats"),
                   BATS_TEST_TMPDIR=directorio)
    p = subprocess.run(["bash", "-c", guion, "_", os.path.join(ACEPTACION, "helpers.bash"),
                        preparacion] + orden,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=entorno, timeout=300)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def estado(directorio):
    """Los ficheros del HOME (nombre y, si es texto, contenido) y el registro
    de los mocks."""
    resultado = {}
    home = os.path.join(directorio, "home")
    for raiz, dirs, ficheros in os.walk(home):
        dirs.sort()
        for nombre in sorted(ficheros) + [d + "/" for d in dirs]:
            ruta = os.path.join(raiz, nombre)
            clave = os.path.relpath(ruta, home)
            if nombre.endswith("/"):
                resultado[clave] = oct(os.stat(ruta).st_mode & 0o777)
                continue
            modo = oct(os.stat(ruta).st_mode & 0o777)
            with open(ruta, "rb") as f:
                datos = f.read(4096)
            if b"\0" in datos:
                resultado[clave] = modo + " (binario)"
            else:
                resultado[clave] = modo + " " + datos.decode("utf-8", "replace")
    registro = os.path.join(directorio, "mock", "log")
    if os.path.exists(registro):
        with open(registro, encoding="utf-8", errors="replace") as f:
            resultado["(registro de los mocks)"] = f.read()
    return resultado


def normalizar(texto, orden):
    texto = texto.replace(orden, "ORDEN")
    texto = re.sub(r"^(ci-provision\.sh|ssoo-us) [0-9][^\s]*$", "VERSION", texto, flags=re.M)
    return re.sub(r"(instance-id: \S*)-[0-9]{14}$", r"\1-FECHA", texto, flags=re.M)


def main():
    argv = sys.argv[1:]
    fase, detalle = 99, False
    while argv[:1] in (["--fase"], ["-v"]):
        if argv[0] == "--fase":
            fase, argv = int(argv[1]), argv[2:]
        else:
            detalle, argv = True, argv[1:]
    script = os.path.abspath(argv[0] if argv else
                             os.path.join(RAIZ, "..", "ci-provision", "ci-provision.sh"))
    distintos = 0
    casos = [c for c in CASOS if c[0] <= fase]
    with tempfile.TemporaryDirectory() as tmp:
        directorio = os.path.join(tmp, "caso")
        for _, args, extra, preparacion in casos:
            a = ejecutar_caso(directorio, ["bash", script] + args, extra, preparacion)
            ea = estado(directorio)
            b = ejecutar_caso(directorio, [sys.executable, SSOO_US, "provision"] + args, extra,
                              preparacion)
            eb = estado(directorio)
            orden_b = SSOO_US + " provision"
            a = (a[0], normalizar(a[1], script), normalizar(a[2], script))
            b = (b[0], normalizar(b[1], orden_b), normalizar(b[2], orden_b))
            ea = {k: normalizar(v, script) for k, v in ea.items()}
            eb = {k: normalizar(v, orden_b) for k, v in eb.items()}
            if a[0] in (98, 99):
                print("? %r: la preparación ha fallado (%d)\n%s" % (args, a[0], a[2]))
                distintos += 1
                continue
            if a == b and ea == eb:
                if detalle:
                    print("✔ [%d] %s" % (a[0], " ".join(args)))
                continue
            distintos += 1
            print("✘ %s %s %s" % (" ".join(repr(x) for x in args),
                                  " ".join("%s=%s" % kv for kv in extra.items()),
                                  "(con preparación)" if preparacion else ""))
            for nombre, x, y in (("código", a[0], b[0]), ("salida", a[1], b[1]),
                                 ("errores", a[2], b[2])):
                if x != y:
                    print("   %s:\n     ci-provision: %r\n     ssoo-us:      %r" % (nombre, x, y))
            for clave in sorted(set(ea) | set(eb)):
                if ea.get(clave) != eb.get(clave):
                    print("   %s:\n     ci-provision: %r\n     ssoo-us:      %r"
                          % (clave, ea.get(clave), eb.get(clave)))
    print("%d de %d casos iguales." % (len(casos) - distintos, len(casos)))
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
