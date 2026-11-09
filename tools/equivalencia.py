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
pueden usar las funciones de helpers.bash y «programa ARGS», que lanza la
misma implementación que se está probando: así se preparan los casos de varios
pasos, como crear una máquina y después repetirla con --limpiar). Se comparan:

  - el código, la salida y los errores;
  - los ficheros que quedan en el HOME (nombre, permisos y contenido de los de
    texto);
  - las máquinas que quedan en el libvirt simulado ($MOCK_STATE/dominios);
  - el registro de llamadas a los mocks ($MOCK_STATE/log), salvo en los casos
    marcados con «registro: False», en los que el número de consultas depende
    del reloj (esperas que se agotan).

Se normaliza lo que tiene que cambiar o cambia solo: la orden («$0» en
ci-provision.sh, «ssoo-us provision» aquí) → ORDEN; «ci-provision.sh X.Y.Z» y
«ssoo-us X.Y.Z» → VERSION; la fecha del instance-id; los segundos de «tras Ns»;
el PID del fichero temporal de la descarga; y el «Terminated: 15 …» que escribe
bash cuando una señal mata a uno de sus hijos.

Cada caso lleva la fase del port a partir de la cual tiene que coincidir; con
--fase N se prueban los de las fases 1 a N (por defecto, todos).
"""

import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

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

SIN_REGISTRO = {"registro": False}
# virt-install lento a partir de la segunda llamada (los nodos, tras la base)
NODOS_LENTOS = r'''mkdir -p "$BATS_TEST_TMPDIR/lento"
printf '#!/bin/bash\n[[ -f "$MOCK_STATE/virt_install_n" ]] && sleep 15\nexec "%s" "$@"\n' "$MOCKS_DIR/virt-install" > "$BATS_TEST_TMPDIR/lento/virt-install"
chmod +x "$BATS_TEST_TMPDIR/lento/virt-install"; export PATH="$BATS_TEST_TMPDIR/lento:$PATH"'''
VIRT_INSTALL_LENTO = r'''mkdir -p "$BATS_TEST_TMPDIR/lento"
printf '#!/bin/bash\nsleep 6\nexec "%s" "$@"\n' "$MOCKS_DIR/virt-install" > "$BATS_TEST_TMPDIR/lento/virt-install"
chmod +x "$BATS_TEST_TMPDIR/lento/virt-install"; export PATH="$BATS_TEST_TMPDIR/lento:$PATH"'''
CREAR_SERVER1 = 'programa server1 >/dev/null 2>&1'


def respuestas(*lineas):
    """Preparación: las respuestas del whiptail simulado, una por diálogo. Van
    entre comillas dobles: $SILO y ${USUARIO} se expanden."""
    return ('printf "%%s\\n" %s > "$BATS_TEST_TMPDIR/respuestas"; '
            'export MOCK_WHIPTAIL="$BATS_TEST_TMPDIR/respuestas"'
            % " ".join('"%s"' % x.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
                       for x in lineas))

# (fase, argumentos, entorno extra, preparación en bash[, opciones])
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

    # Fase 3: máquina suelta
    (3, ["--no-wait", "server1"], {}, SIN_NOBLE),
    (3, ["--no-wait", "--imagen", "debian12", "server1"], {}, 'rm -f "$SILO/debian12.qcow2"'),
    (3, ["server1"], {"MOCK_WGET_FALLA": "1"}, SIN_NOBLE),
    (3, ["server1"], {"MOCK_WGET_CORRUPTO": "1"}, SIN_NOBLE),
    (3, ["--no-wait", "server1"], {"MOCK_SUMAS_FALLA": "1"}, SIN_NOBLE),
    (3, ["server1"], {"MOCK_SUMAS_MAL": "1"}, SIN_NOBLE),
    (3, ["--no-wait", "server1"], {}, SIN_NOBLE + '; cp "$SILO/debian12.qcow2" '
                                                 '"$CI_PROVISION_DIR_COMPARTIDO/noble-server-cloudimg-amd64.img"'),
    (3, ["server1"], {}, ""),
    (3, ["--no-root", "server1"], {}, ""),
    (3, ["--no-virt-viewer", "server1"], {}, ""),
    (3, ["--no-root", "--ssh-pass", "MiPass1", "server1"], {}, ""),
    (3, ["--base", "mibase.qcow2", "server1", "192.168.7.10"], {},
     'qemu-img create -f qcow2 -b noble-server-cloudimg-amd64.img -F qcow2 "$SILO/mibase.qcow2" 3G '
     '>/dev/null; rm -f "$SILO/debian12.qcow2"'),
    (3, ["--ssh-pass", "MiPass1", "server1"], {}, ""),
    (3, ["--extra-disks", "server1", "192.168.7.2"], {}, ""),
    (3, ["--disco", "mio.qcow2", "--tam", "20G", "server1"], {}, ""),
    (3, ["--si", "--limpiar", "--prefijo", "demo", "--extra-disks", "server1"], {}, CREAR_SERVER1),
    (3, ["--extra-disks", "server1"], {"MOCK_VIRT_INSTALL_FALLA_TARDE": "1"}, ""),
    (3, ["--extra-disks", "server1"], {"MOCK_VIRT_INSTALL_FALLA": "1"}, ""),
    (3, ["--no-wait", "--base", "grande.qcow2", "server1"], {},
     'qemu-img create -f qcow2 "$SILO/grande.qcow2" 50G >/dev/null'),
    (3, ["server1"], {"MOCK_CI_RESULT": "degraded"}, ""),
    (3, ["server1"], {"MOCK_CI_RESULT": "error"}, ""),
    (3, ["server1"], {"MOCK_CI_RUNNING": "999", "CI_PROVISION_WAIT_TIMEOUT": "3"}, "", SIN_REGISTRO),
    (3, ["server1", "192.168.7.2"], {"MOCK_CI_RUNNING": "999", "CI_PROVISION_WAIT_TIMEOUT": "3"},
     "", SIN_REGISTRO),
    (3, ["server1"], {"MOCK_EXEC_PENDIENTE": "3"}, ""),
    (3, ["server1"], {"MOCK_AGENT_DELAY": "3"}, ""),
    (3, ["server1"], {"MOCK_CI_RUNNING": "3"}, ""),
    (3, ["server1"], {"MOCK_EXEC_UNSUPPORTED": "1"}, "", SIN_REGISTRO),
    (3, ["server1"], {"MOCK_AGENT_DELAY": "999", "CI_PROVISION_WAIT_TIMEOUT": "3"}, "", SIN_REGISTRO),
    (3, ["--si", "--limpiar", "server1"], {"MOCK_UNDEFINE_FALLA": "1"}, CREAR_SERVER1),
    (3, ["server1"], {"MOCK_EJECT_NUNCA": "1"}, ""),
    (3, ["server1"], {"MOCK_ISO_PERSISTENTE": "1"}, ""),
    (3, ["server1"], {"MOCK_VARIAS_IFACES": "1"}, ""),
    (3, ["server1"], {"MOCK_SHUTDOWN_NUNCA": "1"}, "", SIN_REGISTRO),
    (3, ["server1", "192.168.7.2"], {},
     'echo "192.168.7.2 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOldKeyOldKeyOldKeyOldKeyOldKeyOldKeyOldKey" '
     '> "$HOME/.ssh/known_hosts"'),
    (3, ["server1"], {},
     'echo "192.168.7.201 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOldKeyOldKeyOldKeyOldKeyOldKeyOldKeyOldKey" '
     '> "$HOME/.ssh/known_hosts"'),
    (3, ["--ram", "4096", "--vcpus", "4", "server1"], {}, ""),
    (3, ["--no-wait", "server1"], {}, ""),
    (3, ["server1"], {}, 'programa --no-wait server1 >/dev/null 2>&1; rm -f "$SILO/server1.qcow2"'),
    (3, ["--si", "--limpiar", "--extra-disks", "server1"], {},
     'programa --no-wait --extra-disks server1 >/dev/null 2>&1; touch "$SILO/otro.qcow2" '
     '"$SILO/server2.qcow2"; : > "$MOCK_STATE/log"'),
    (3, ["--limpiar", "server1"], {}, CREAR_SERVER1),
    (3, ["--si", "--limpiar", "server1"], {}, 'touch "$SILO/server1.qcow2"'),
    (3, ["--si", "--limpiar", "server1"], {}, 'touch "$SILO/server1.qcow2"; definir_dominio '
                                              '"${USUARIO}-server1" shut\\ off "$SILO/server1.qcow2"'),
    (3, ["--dry-run", "server2", "192.168.7.2"], {}, 'programa server1 192.168.7.2 >/dev/null 2>&1'),
    (3, ["--si", "--limpiar", "server1", "192.168.7.2"], {},
     'programa server1 192.168.7.2 >/dev/null 2>&1; echo 192.168.7.2 > "$MOCK_STATE/ping_responde"'),
    (3, ["--dry-run", "--base", "server1.qcow2", "server2"], {},
     CREAR_SERVER1 + '; virsh shutdown "${USUARIO}-server1" >/dev/null'),
    (3, ["--prefijo", "demo", "--no-root", "--no-virt-viewer", "--ssh-pass", "a b'c", "web",
         "192.168.7.3"], {}, ""),
    # Ctrl+C (SIGINT a todo el grupo, como la terminal) y SIGTERM durante la espera
    (3, ["server1"], {"MOCK_AGENT_DELAY": "999", "CI_PROVISION_WAIT_TIMEOUT": "60"}, "",
     {"registro": False, "senal": ("SIGINT", 4)}),
    (3, ["server1"], {"MOCK_AGENT_DELAY": "999", "CI_PROVISION_WAIT_TIMEOUT": "60"}, "",
     {"registro": False, "senal": ("SIGTERM", 4)}),
    # Ctrl+C mientras virt-install trabaja: se deshace lo creado
    (3, ["--extra-disks", "server1"], {}, VIRT_INSTALL_LENTO, {"registro": False, "senal": ("SIGINT", 3)}),

    # Fase 4: GlusterFS
    (4, ["--glusterfs", "gluster-base"], {}, ""),
    (4, ["--imagen", "ubuntu-base", "--glusterfs", "gluster-base"], {}, ""),
    (4, ["--no-root", "--imagen", "ubuntu-base", "--glusterfs", "gluster-base"], {}, ""),
    (4, ["--glusterfs", "gluster-base"], {"MOCK_CI_RESULT": "error"}, ""),
    (4, ["--no-root", "--glusterfs", "gluster-base"], {"MOCK_CI_RESULT": "degraded"}, ""),
    (4, ["--glusterfs", "gluster-base"], {"MOCK_EXEC_UNSUPPORTED": "1"}, "", SIN_REGISTRO),
    (4, ["--glusterfs", "--disco", "mibase.qcow2", "--prefijo", "demo", "gb"], {}, ""),
    (4, ["--prefijo", "demo", "--gluster-cluster"], {}, 'touch "$SILO/gluster-base.qcow2" "$SILO/server1.qcow2"'),
    (4, ["--si", "--limpiar", "--glusterfs", "gluster-base"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; (cd "$SILO" && qemu-img create -f qcow2 -b '
     'gluster-base.qcow2 -F qcow2 nodo1.qcow2 64G >/dev/null)'),
    (4, ["--gluster-cluster"], {"MOCK_VIRT_INSTALL_FALLA_EN": "4"}, ""),
    (4, ["--gluster-cluster", "--tam", "20G", "--no-root", "--ssh-pass", "Clave1", "--no-virt-viewer"],
     {}, ""),
    (4, ["--gluster-cluster", "--imagen", "ubuntu-base", "--tam", "80G"], {}, ""),
    (4, ["--prefijo", "demo", "--gluster-cluster", "--base", "gluster2.qcow2"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; programa --glusterfs --base gluster-base.qcow2 '
     'gluster2 >/dev/null 2>&1'),
    (4, ["--gluster-cluster"], {}, ""),
    (4, ["--gluster-cluster", "--discos-nodo", "7"], {}, ""),
    (4, ["--gluster-cluster", "--imagen", "debian12"], {}, ""),
    (4, ["--si", "--limpiar", "--gluster-cluster"], {}, 'touch "$SILO/server3-vdd.qcow2"'),
    (4, ["--si", "--limpiar", "--gluster-cluster", "--base", "mibase.qcow2"], {},
     'qemu-img create -f qcow2 -b debian12.qcow2 -F qcow2 "$SILO/mibase.qcow2" 40G >/dev/null; '
     'touch "$SILO/server2.qcow2"'),
    (4, ["--gluster-cluster"], {"MOCK_SHUTDOWN_NUNCA": "1"}, "", SIN_REGISTRO),
    (4, ["--gluster-cluster"], {"MOCK_CI_RESULT": "error"}, ""),
    (4, ["--no-wait", "--gluster-cluster"], {}, ""),
    (4, ["--gluster-cluster", "--imagen", "ubuntu-base", "--no-wait"], {}, ""),
    (4, ["--si", "--limpiar", "--gluster-cluster", "--no-wait"], {},
     'programa --gluster-cluster --imagen ubuntu-base --no-wait >/dev/null 2>&1'),
    (4, ["--dry-run", "--gluster-cluster"], {}, 'programa --glusterfs gluster-base >/dev/null 2>&1'),
    (4, ["--dry-run", "--prefijo", "demo", "--gluster-cluster"], {},
     'programa --prefijo demo --glusterfs gluster-base >/dev/null 2>&1'),
    # Ctrl+C mientras se crean los nodos: se deshacen, la base terminada se conserva
    (4, ["--gluster-cluster"], {}, NODOS_LENTOS, {"registro": False, "senal": ("SIGINT", 9)}),

    # Fase 5: --listar, --eliminar y --eliminar-todo
    (5, ["--listar"], {}, ""),
    (5, ["--listar"], {}, SIN_NOBLE),
    (5, ["--listar"], {}, 'programa --no-wait --extra-disks server1 >/dev/null 2>&1; '
                          'programa --imagen debian12 --glusterfs gluster-base >/dev/null 2>&1'),
    (5, ["--listar"], {}, CREAR_SERVER1 + '; programa server2 >/dev/null 2>&1; '
                          'virsh shutdown "${USUARIO}-server2" >/dev/null; ' + CADENA_DEBIAN + '; '
                          + CADENA_ROTA + '; touch "$SILO/suelto.qcow2"'),
    (5, ["--listar"], {"MOCK_AGENT_DELAY": "999"}, 'programa --no-wait server1 >/dev/null 2>&1'),
    (5, ["--prefijo", "demo", "--listar"], {},
     'programa --prefijo demo server1 >/dev/null 2>&1; definir_dominio demo-ajena running '
     '/otra/parte/ajena.qcow2; definir_dominio demo-vacia shut\\ off'),
    (5, ["--listar"], {}, 'definir_dominio "${USUARIO}-a-mano" paused "$SILO/a-mano.qcow2"; '
                          'touch "$SILO/a-mano.qcow2"'),
    (5, ["--si", "--eliminar", "server1"], {},
     'programa --extra-disks server1 >/dev/null 2>&1; programa server2 >/dev/null 2>&1'),
    (5, ["--si", "--dry-run", "--eliminar", "server1", "server2"], {},
     'programa --extra-disks server1 >/dev/null 2>&1; programa server2 >/dev/null 2>&1'),
    (5, ["--si", "--eliminar", "server1", "server1"], {}, CREAR_SERVER1),
    (5, ["--si", "--eliminar", "server9"], {}, ""),
    (5, ["--si", "--eliminar", "debian12"], {}, ""),
    (5, ["--si", "--eliminar", "server9", "debian12"], {}, CREAR_SERVER1),
    (5, ["--si", "--eliminar", "server1"], {}, 'programa --disco server1.qcow2 otra >/dev/null 2>&1'),
    (5, ["--si", "--eliminar", "gluster-base"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; '
     'programa --base gluster-base.qcow2 nodo1 >/dev/null 2>&1'),
    (5, ["--si", "--eliminar", "nodo1", "gluster-base"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; '
     'programa --base gluster-base.qcow2 nodo1 >/dev/null 2>&1'),
    (5, ["--si", "--eliminar", "server1", "gluster-base"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; programa --base gluster-base.qcow2 server1 '
     '>/dev/null 2>&1; definir_dominio "${USUARIO}-copia" running "$SILO/server1.qcow2"'),
    (5, ["--si", "--eliminar", "ajena"], {},
     'definir_dominio "${USUARIO}-ajena" running /otra/parte/ajena.qcow2'),
    (5, ["--si", "--eliminar", "server1"], {}, 'touch "$SILO/server1-vdc.qcow2" "$SILO/server1-vdzz.qcow2"; '
                                               'mkdir "$SILO/cloudinit-${USUARIO}-server1.dry-run"'),
    (5, ["--si", "--eliminar", "server1"], {"MOCK_UNDEFINE_FALLA": "1"}, CREAR_SERVER1),
    (5, ["--eliminar", "server1"], {}, CREAR_SERVER1),
    (5, ["--si", "--prefijo", "demo", "--eliminar", "server1"], {},
     CREAR_SERVER1 + '; programa --prefijo demo server1 >/dev/null 2>&1'),
    (5, ["--si", "--eliminar-todo"], {},
     CREAR_SERVER1 + '; programa --glusterfs gluster-base >/dev/null 2>&1; '
     'programa --prefijo demo server1 >/dev/null 2>&1'),
    (5, ["--si", "--dry-run", "--eliminar-todo"], {},
     CREAR_SERVER1 + '; programa --glusterfs gluster-base >/dev/null 2>&1; '
     'programa --prefijo demo server1 >/dev/null 2>&1'),
    (5, ["--si", "--prefijo", "demo", "--eliminar-todo"], {},
     CREAR_SERVER1 + '; programa --prefijo demo server1 >/dev/null 2>&1; touch "$SILO/demo-suelto.qcow2" '
     '"$SILO/otro.qcow2"'),
    (5, ["--si", "--eliminar-todo"], {}, ""),
    (5, ["--si", "--eliminar-todo"], {}, 'mkdir -p "$SILO/cloudinit-${USUARIO}-fantasma" '
                                         '"$SILO/cloudinit-${USUARIO}-otro.dry-run"'),
    (5, ["--si", "--eliminar-todo"], {}, 'touch "$SILO/suelto.qcow2"; ' + CADENA_DEBIAN),
    (5, ["--si", "--eliminar-todo"], {},
     'programa --glusterfs gluster-base >/dev/null 2>&1; (cd "$SILO" && qemu-img create -f qcow2 -b '
     'gluster-base.qcow2 -F qcow2 intermedia.qcow2 >/dev/null && qemu-img create -f qcow2 -b '
     'intermedia.qcow2 -F qcow2 copia.qcow2 >/dev/null); '
     'definir_dominio SERVIDOR-A-MANO running "$SILO/copia.qcow2"'),
    (5, ["--si", "--eliminar-todo"], {},
     'programa --disco server1.qcow2 otra >/dev/null 2>&1; touch "$SILO/suelto.qcow2"; '
     'definir_dominio "${USUARIO}-ajena" running /otra/parte/ajena.qcow2'),
    (5, ["--eliminar-todo"], {}, CREAR_SERVER1 + '; touch "$SILO/mi-copia-seguridad.qcow2"'),
    (5, ["--eliminar-todo"], {}, 'touch "$SILO/mi-copia-seguridad.qcow2"'),
    (5, ["--si", "--eliminar-todo"], {"MOCK_UNDEFINE_FALLA": "1"}, CREAR_SERVER1),

    # Fase 6: el asistente (--menu). Las respuestas del whiptail simulado, una
    # por diálogo: «0 valor» acepta, «1» cancela, «255» es Esc
    (6, ["--menu"], {}, respuestas("1")),
    (6, ["--menu"], {}, respuestas("255")),
    (6, ["--menu"], {}, respuestas("0 salir")),
    (6, ["--menu"], {}, respuestas("0 basica", "0 server1", "0 ", "0 debian12",
                                   '0 "extra-disks" "no-root"', "0", "0 salir")),
    (6, ["--menu"], {}, respuestas("0 cluster", "0 debian12", '0 "discos-crea-entorno"', "0", "1")),
    (6, ["--menu"], {}, 'programa --glusterfs gluster-base >/dev/null 2>&1; '
                        + respuestas("0 cluster", "0", '0 "limpiar"', "0", "1")),
    (6, ["--menu"], {}, 'programa --glusterfs gluster-base >/dev/null 2>&1; '
                        + respuestas("0 cluster", "1", "0 ubuntu-base", '0 "no-root"', "1", "1")),
    (6, ["--menu", "--si"], {}, respuestas("0 extra", "0 server1", "0 192.168.7.2", "0 noble",
                                           '0 "extra-disks"', "0", "0 eliminar", '0 "server1"', "0",
                                           "1")),
    (6, ["--menu"], {}, 'programa --extra-disks server1 >/dev/null 2>&1; programa --imagen debian12 '
                        '--glusterfs glusterbase >/dev/null 2>&1; '
                        + respuestas("0 listar", "0 m:${USUARIO}-server1", "0",
                                     "0 d:$SILO/glusterbase.qcow2", "0", "0 d:$SILO/debian12.qcow2",
                                     "0", "1", "1")),
    (6, ["--menu"], {}, respuestas("0 basica", "0 web", "0 ", "0 noble", '0 "ssh-pass"',
                                   "0 Secreta1", "0", "1")),
    (6, ["--menu", "--dry-run"], {}, respuestas("0 basica", "0 web", "0 ", "0 noble",
                                                '0 "ssh-pass" "limpiar"', "0 Secreta1", "0", "1")),
    (6, ["--menu"], {}, respuestas("0 basica", "0 web", "0 ", "0 noble", '0 "ssh-pass"', "0 ",
                                   "1")),
    (6, ["--menu"], {}, respuestas("0 basica", "0 -x", "0", "0 extra", "0 a b", "0", "0 base",
                                   "0 " + "a" * 64, "0", "1")),
    (6, ["--prefijo", "demo", "--menu"], {},
     'programa --prefijo demo server1 >/dev/null 2>&1; '
     + respuestas("0 listar", "0 m:demo-server1", "0", "1", "0 extra", "0 web", "0", "0 noble",
                  '0 "no-virt-viewer"', "0", "1")),
    (6, ["--menu"], {}, respuestas("0 listar", "0", "0 eliminar", "0 visto", "1")),
    (6, ["--menu", "--si"], {}, respuestas("0 todo", "0", "1")),
    (6, ["--menu", "--si"], {}, CREAR_SERVER1 + '; touch "$SILO/suelto.qcow2"; '
                                + respuestas("0 todo", "0", "1")),
    (6, ["--menu"], {}, respuestas("0 base", "0 mibase", "0 ubuntu-base", "0", "0", "1")),
    (6, ["--menu"], {}, respuestas("0 base", "0 ", "0 base", "0 gb", "1", "0 base", "0 gb",
                                   "0 noble", "1", "1", "1")),
    (6, ["--menu"], {}, CREAR_SERVER1 + '; programa server2 >/dev/null 2>&1; '
                        + respuestas("0 eliminar", "0", "0 eliminar", '0 "server1" "server2"', "1",
                                     "1")),
    (6, ["--menu"], {}, respuestas("0 basica", "0 server1", "0 192.168.7.300", "0 noble", "0", "0",
                                   "1")),
    (6, ["--menu"], {}, respuestas("0 basica", "1", "0 extra", "0 s1", "1", "0 extra", "0 s1", "0 ",
                                   "1", "0 extra", "0 s1", "0 ", "0 noble", "1", "1")),
    (6, ["--menu"], {}, DHCP_10_13 + '; ' + respuestas("0 extra", "0 s1", "1", "1")),
    (6, ["--menu"], {}, 'quitar_red "${USUARIO}-red"; ' + respuestas("0 extra", "0 s1", "1", "1")),
    # Sin whiptail, error 38
    (6, ["--menu"], {}, 'bin="$BATS_TEST_TMPDIR/bin"; mkdir -p "$bin"; for p in virsh virt-install '
                        'wget; do ln -s "$MOCKS_DIR/$p" "$bin/$p"; done; '
                        'export PATH="$bin:${PATH#"$MOCKS_DIR:"}"'),
    # La lista vuelve a leer las imágenes base (hasta la 3.0.2, ci-provision.sh
    # las leía una vez por sesión del asistente)
    (6, ["--menu", "--si"], {}, CREAR_SERVER1 + '; '
                                + respuestas("0 listar", "1", "0 base", "0 gb", "0 noble", "1", "0",
                                             "0 listar", "0 d:$SILO/gb.qcow2", "0", "1", "1")),
]


def preparar(directorio):
    """Un directorio vacío y siempre el mismo, como el $BATS_TEST_TMPDIR de bats."""
    if os.path.exists(directorio):
        shutil.rmtree(directorio)
    os.makedirs(directorio)


def ejecutar_caso(directorio, programa, args, extra, preparacion, senal=None):
    """Prepara el entorno de helpers.bash, aplica la preparación y lanza
    «programa ARGS» en el mismo bash. Devuelve (código, salida, errores)."""
    preparar(directorio)
    # Las variables del caso, después de preparar_entorno (que fija las suyas)
    # y de la preparación
    exportar = "".join("export %s=%s; " % (k, shlex.quote(v)) for k, v in extra.items())
    guion = ('source "$1"; preparar_entorno || exit 99; prep="$2"; shift 2; ORDEN_PRUEBA=(); '
             'while [[ "$1" != "--" ]]; do ORDEN_PRUEBA+=("$1"); shift; done; shift; '
             'programa() { "${ORDEN_PRUEBA[@]}" "$@"; }; eval "$prep" || exit 98; '
             + exportar + 'programa "$@"')
    entorno = dict(os.environ, BATS_TEST_FILENAME=os.path.join(ACEPTACION, "ci-provision.bats"),
                   BATS_TEST_TMPDIR=directorio)
    orden = (["bash", "-c", guion, "_", os.path.join(ACEPTACION, "helpers.bash"), preparacion]
             + programa + ["--"] + args)
    # Con señal: en su propio grupo de procesos, que la recibe entero a los N
    # segundos, como con Ctrl+C en una terminal
    p = subprocess.Popen(orden, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=entorno, start_new_session=bool(senal))
    if senal:
        time.sleep(senal[1])
        os.killpg(p.pid, getattr(signal, senal[0]))
    salida, errores = p.communicate(timeout=300)
    return p.returncode, salida.decode("utf-8", "replace"), errores.decode("utf-8", "replace")


def estado(directorio, con_registro=True):
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
    dominios = os.path.join(directorio, "mock", "dominios")
    if os.path.isdir(dominios):
        for dominio in sorted(os.listdir(dominios)):
            for nombre in ("estado", "discos", "ip", "iso", "iso_persistente", "on_reboot_vivo"):
                ruta = os.path.join(dominios, dominio, nombre)
                if os.path.exists(ruta):
                    with open(ruta, encoding="utf-8", errors="replace") as f:
                        resultado["(libvirt) %s/%s" % (dominio, nombre)] = f.read()
    registro = os.path.join(directorio, "mock", "log")
    if con_registro and os.path.exists(registro):
        with open(registro, encoding="utf-8", errors="replace") as f:
            resultado["(registro de los mocks)"] = f.read()
    return resultado


def normalizar(texto, orden):
    texto = texto.replace(orden, "ORDEN")
    texto = re.sub(r"^(ci-provision\.sh|ssoo-us) [0-9][^\s]*$", "VERSION", texto, flags=re.M)
    # El título de los diálogos del asistente (en el registro de los mocks)
    texto = re.sub(r"^whiptail --title (ci-provision|ssoo-us) \S+", "whiptail --title TITULO",
                   texto, flags=re.M)
    texto = re.sub(r"(instance-id: \S*)-[0-9]{14}$", r"\1-FECHA", texto, flags=re.M)
    texto = re.sub(r"\.descargando\.[0-9]+", ".descargando.PID", texto)
    # Lo que escribe bash (no el script) cuando una señal mata a un hijo suyo
    texto = re.sub(r"^Terminated: 15 .*\n", "", texto, flags=re.M)
    return re.sub(r" tras [0-9]+s", " tras Ns", texto)


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
    distintos = conocidas = 0
    casos = [c for c in CASOS if c[0] <= fase]
    with tempfile.TemporaryDirectory() as tmp:
        directorio = os.path.join(tmp, "caso")
        for caso in casos:
            _, args, extra, preparacion = caso[:4]
            opciones = caso[4] if len(caso) > 4 else {}
            con_registro, senal = opciones.get("registro", True), opciones.get("senal")
            conocida = opciones.get("conocida")
            a = ejecutar_caso(directorio, ["bash", script], args, extra, preparacion, senal)
            ea = estado(directorio, con_registro)
            b = ejecutar_caso(directorio, [sys.executable, SSOO_US, "provision"], args, extra,
                              preparacion, senal)
            eb = estado(directorio, con_registro)
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
                if detalle or conocida:
                    print("✔ [%d] %s%s" % (a[0], " ".join(args),
                                           "  (se esperaba una diferencia conocida)" if conocida else ""))
                continue
            if conocida:
                conocidas += 1
                print("≈ %s  (diferencia conocida: %s)" % (" ".join(repr(x) for x in args), conocida))
            else:
                distintos += 1
            print("%s %s %s %s" % ("  " if conocida else "✘", " ".join(repr(x) for x in args),
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
    print("%d de %d casos iguales%s." % (
        len(casos) - distintos - conocidas, len(casos),
        "; %d con una diferencia conocida" % conocidas if conocidas else ""))
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
