#!/usr/bin/env python3
"""Pruebas de equivalencia de diagnosis: las mismas situaciones con
ci-diagnosis y con «ssoo-us diagnosis», comparando la salida, los errores y el
código de salida.

    .venv/bin/python tools/equivalencia_diagnosis.py [RUTA_DE_CI_DIAGNOSIS] [-v]

Por defecto, RUTA_DE_CI_DIAGNOSIS es ../ci-diagnosis (su archivo generado,
ci-diagnosis). Necesita PyYAML (el .venv de DESARROLLO.md): sin él, las dos
omiten las mismas comprobaciones y la comparación dice poco.

Las dos se cargan en este proceso y se ejecutan con libvirt, ping, el puerto
22, ssh y guestfish simulados (falso_libvirt.py y los mismos parches que
tests/test_diagnosis_salida.py), sobre la cuenta de un alumno de prueba en un
directorio temporal. Antes de comparar se normaliza lo que cambia a propósito:
el nombre («./ci-diagnosis» es «ssoo-us diagnosis»), la versión, la línea
«(Versión en desarrollo.)» y los saltos de línea (el nombre nuevo es más largo
y los párrafos se parten en otro sitio). Con -v se muestra cada caso.

Código de salida: 0 si todas son iguales; 1 si alguna no.
"""

import contextlib
import difflib
import importlib.machinery
import importlib.util
import io
import os
import re
import sys
import tempfile
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.dont_write_bytecode = True

import falso_libvirt as fl  # noqa: E402
from comun_diagnosis import (META_DATA, NETWORK_CONFIG, USER_DATA, Claves,  # noqa: E402
                             cd as su, escribir)
from test_diagnosis_acceso import disco_bueno  # noqa: E402


def cargar(ruta, nombre):
    cargador = importlib.machinery.SourceFileLoader(nombre, ruta)
    spec = importlib.util.spec_from_loader(nombre, cargador)
    modulo = importlib.util.module_from_spec(spec)
    cargador.exec_module(modulo)
    return modulo


# --- La cuenta del alumno ------------------------------------------------------

def preparar_alumno(home, imagen):
    """Un alumno que lo ha hecho todo bien (como en test_diagnosis_salida)."""
    import subprocess
    os.mkdir(os.path.join(home, ".ssh"), 0o700)
    silo = os.path.join(home, "imagenesMV")
    os.mkdir(silo)
    Claves.preparar()
    with open(Claves.sin_frase, "rb") as f:
        escribir(os.path.join(home, ".ssh", "id_rsa"), f.read(), 0o600)
    escribir(os.path.join(home, ".ssh", "id_rsa.pub"), Claves.publica("sin_frase"))
    escribir(os.path.join(silo, "user-data"), USER_DATA.format(clave=Claves.publica("sin_frase")))
    escribir(os.path.join(silo, "meta-data"), META_DATA)
    escribir(os.path.join(silo, "network-config"), NETWORK_CONFIG)
    base = os.path.join(silo, imagen)
    for args in (["-f", "qcow2", base, "3758096384"],
                 [os.path.join(silo, "server1.qcow2"), "-f", "qcow2", "-b", imagen,
                  "-F", "qcow2", "40G"]):
        subprocess.run(["qemu-img", "create", "-q"] + args, check=True)
    os.chmod(base, 0o644)
    os.chmod(os.path.join(silo, "server1.qcow2"), 0o644)
    return silo


def conexion(silo, imagen, maquina=None, redes=True):
    dominios = [fl.Dominio("zzz9999-server1", ["/home/zzz9999/server1.qcow2"])]
    if maquina is not None:
        dominios.append(fl.Dominio("alu0000-server1", [os.path.join(silo, "server1.qcow2")],
                                   red="alu0000-red", **maquina))
    return fl.Conexion(
        silos=[fl.Silo("alu0000-imagenesMV", silo, volumenes=[fl.Volumen(imagen)])],
        redes=[fl.Red("alu0000-red")] if redes else [],
        dominios=dominios)


# --- Casos ---------------------------------------------------------------------
#
# Cada caso: (nombre, preparación, opciones). La preparación recibe (home,
# silo) y cambia lo que haga falta; las opciones son las de ejecutar().

def nada(home, silo):
    pass


def escribir_en(nombre, texto):
    def preparar(home, silo):
        escribir(os.path.join(silo, nombre), texto)
    return preparar


def borrar(nombre):
    def preparar(home, silo):
        os.remove(os.path.join(silo, nombre))
    return preparar


def mover_imagen(home, silo):
    os.rename(os.path.join(silo, su.IMAGEN_NOBLE), os.path.join(silo, "movida.img"))


def clave_del_portatil(home, silo):
    escribir(os.path.join(silo, "user-data"), USER_DATA.format(clave=Claves.publica("portatil")))


def permisos_abiertos(home, silo):
    os.chmod(os.path.join(silo, "server1.qcow2"), 0o666)


# El registro de virt-install (~/.cache/virt-manager/virt-install.log)
LINEA = ("[Thu, 05 Nov 2026 10:00:00 virt-install 1234] DEBUG (cli:204) Launched with "
         "command line: /usr/bin/virt-install %s\n")
MANUAL = ("--name=alu0000-server1 --cloud-init user-data=user-data,meta-data=meta-data,"
          "network-config=network-config --ram=2048 --vcpus=2 --import --disk "
          "path=server1.qcow2 --os-variant=ubuntu24.04 --network network=alu0000-red "
          "--noautoconsole")
FIN_BIEN = "[Thu, 05 Nov 2026 10:00:09 virt-install 1234] DEBUG (x:1) Domain creation completed.\n"


def registro(orden, despues="", tambien=None):
    """La orden en el registro de virt-install (y, si se da, otra preparación)."""
    def preparar(home, silo):
        directorio = os.path.join(home, ".cache", "virt-manager")
        os.makedirs(directorio, exist_ok=True)
        escribir(os.path.join(directorio, "virt-install.log"),
                 LINEA % orden.replace("SILO", silo) + despues)
        if tambien:
            tambien(home, silo)
    return preparar


ENCENDIDA = {"activo": True}
RECHAZA = (255, "", "Permission denied (publickey).\n")
DISCO_MALO = ({}, None, None)

CASOS = [
    ("--version", None, {"argv": ["--version"]}),
    ("--ayuda", None, {"argv": ["--ayuda"]}),
    ("-h", None, {"argv": ["-h"]}),
    ("opción desconocida", None, {"argv": ["--nada"]}),
    ("--antes y --acceso", None, {"argv": ["--antes", "--acceso"]}),
    ("--ip sin valor", None, {"argv": ["--ip"]}),
    ("--ip que no es IP", None, {"argv": ["--ip", "nada"]}),
    ("dos máquinas", None, {"argv": ["server1", "server2"]}),
    ("sin libvirt", None, {"sin_libvirt": True}),
    ("todo bien", nada, {}),
    ("todo bien, server1", nada, {"argv": ["server1"]}),
    ("todo bien, 1 --antes", nada, {"argv": ["1", "--antes"]}),
    ("todo bien, alu0000-server1", nada, {"argv": ["alu0000-server1"]}),
    ("todo bien, algo en la IP", nada, {"ping": True}),
    ("sin la red", nada, {"redes": False}),
    ("otra máquina (server2)", nada, {"argv": ["server2"]}),
    ("sin meta-data", borrar("meta-data"), {}),
    ("sin user-data", borrar("user-data"), {}),
    ("sin network-config", borrar("network-config"), {}),
    ("sin el disco", borrar("server1.qcow2"), {}),
    ("imagen base movida (antes)", mover_imagen, {}),
    ("clave del portátil", clave_del_portatil, {}),
    ("disco escribible por otros", permisos_abiertos, {}),
    ("user-data sin #cloud-config",
     escribir_en("user-data", USER_DATA.replace("#cloud-config\n", "")), {}),
    ("user-data con tabuladores y comillas tipográficas",
     escribir_en("user-data", USER_DATA.replace("  - name", "\t- name").replace(
         "['ALL=(ALL) NOPASSWD:ALL']", "[‘ALL=(ALL) NOPASSWD:ALL’]")), {}),
    ("user-data que no es YAML", escribir_en("user-data", "#cloud-config\nusers: [\n"), {}),
    ("meta-data de otra máquina", escribir_en("meta-data", META_DATA.replace("server1", "server2")),
     {}),
    ("network-config con eth0",
     escribir_en("network-config", NETWORK_CONFIG.replace("enp1s0", "eth0")), {}),
    ("network-config con gateway4",
     escribir_en("network-config", NETWORK_CONFIG.replace(
         "    routes:\n      - to: default\n        via: 192.168.7.1\n",
         "    gateway4: 192.168.7.1\n")), {}),
    ("network-config con otros DNS",
     escribir_en("network-config", NETWORK_CONFIG.replace("150.214.130.15", "8.8.8.8")), {}),
    ("IP en el DHCP",
     escribir_en("network-config", NETWORK_CONFIG.replace("192.168.7.2/24", "192.168.7.200/24")),
     {}),
    ("desde el home", nada, {"desde_home": True}),
    ("la máquina ya existe (--antes)", nada, {"maquina": {}, "argv": ["--antes"]}),
    ("--acceso sin la máquina", nada, {"argv": ["--acceso"]}),
    ("--acceso sin saber qué máquina", borrar("meta-data"), {"argv": ["--acceso"]}),
    ("acceso: entra", nada, {"maquina": ENCENDIDA, "puerto": "abierto", "ping": True,
                             "ssh": (0, "", "")}),
    ("acceso: rechaza la clave", nada, {"maquina": ENCENDIDA, "puerto": "abierto",
                                        "ping": True, "ssh": RECHAZA}),
    ("acceso: sin respuesta", nada, {"maquina": ENCENDIDA, "puerto": "sin respuesta"}),
    ("acceso: sin ruta", nada, {"maquina": ENCENDIDA}),
    ("acceso: meta-data de otra", escribir_en("meta-data", META_DATA.replace("server1", "server2")),
     {"maquina": ENCENDIDA, "argv": ["server1"]}),
    ("acceso: con --ip", escribir_en("meta-data", META_DATA.replace("server1", "server2")),
     {"maquina": ENCENDIDA, "argv": ["server1", "--ip", "192.168.7.5"], "puerto": "abierto",
      "ssh": (0, "", "")}),
    ("acceso: eth0", escribir_en("network-config", NETWORK_CONFIG.replace("enp1s0", "eth0")),
     {"maquina": ENCENDIDA, "puerto": "sin respuesta"}),
    ("acceso: apagada, disco bueno", nada, {"maquina": {}, "disco": "bueno"}),
    ("acceso: apagada, guestfish falla", nada, {"maquina": {}}),
    ("acceso: apagada, imagen base movida", mover_imagen, {"maquina": {}}),
    # La orden de virt-install, en su registro
    ("antes: intento anterior con espacio tras la coma",
     registro(MANUAL.replace("user-data,meta-data", "user-data, meta-data")), {}),
    ("antes: intento anterior sin --cloud-init",
     registro(MANUAL.replace("--cloud-init user-data=user-data,meta-data=meta-data,"
                             "network-config=network-config ", "")), {}),
    ("antes: intento anterior completado", registro(MANUAL, FIN_BIEN), {}),
    ("acceso: entra, orden del manual", registro(MANUAL, FIN_BIEN),
     {"maquina": ENCENDIDA, "puerto": "abierto", "ping": True, "ssh": (0, "", "")}),
    ("acceso: orden mala (sin network-config, red default), pasos para rehacerla",
     registro(MANUAL.replace(",network-config=network-config", "")
              .replace("network=alu0000-red", "network=default"), FIN_BIEN),
     {"maquina": ENCENDIDA, "puerto": "abierto", "ping": True, "ssh": RECHAZA}),
    ("acceso: --cloud-init con archivos de otro directorio (E.4)",
     registro(MANUAL.replace("user-data=user-data", "user-data=/tmp/x/user-data"), FIN_BIEN),
     {"maquina": {}, "disco": "bueno"}),
    ("acceso: apagada, error conocido en el registro",
     registro(MANUAL, "[Thu, 05 Nov 2026 10:00:02 virt-install 1234] ERROR (cli:255) "
                      "Size must be specified for non existent volume 'server1.qcow2'\n"),
     {"maquina": {}}),
]


def ejecutar(modulo, nombre_main, home, silo, imagen, opciones):
    """La herramienta en el silo, con todo simulado. Devuelve (código, salida,
    errores)."""
    entorno = {"HOME": home, "CI_DIAGNOSIS_USUARIO": "alu0000"}
    disco = opciones.get("disco")
    if disco == "bueno":
        disco = (disco_bueno(), ["alu0000-server1"], None)
    else:
        disco = ({}, None, modulo.error("guestfish simulado: sin disco"))
    salida, errores = io.StringIO(), io.StringIO()
    anterior = os.getcwd()
    try:
        os.chdir(home if opciones.get("desde_home") else silo)
        parches = [mock.patch.dict(os.environ, entorno)]
        if opciones.get("sin_libvirt"):
            parches.append(mock.patch.dict("sys.modules", {"libvirt": None}))
        else:
            parches.append(fl.instalado(conexion(silo, imagen, opciones.get("maquina"),
                                                 opciones.get("redes", True))))
        parches += [
            mock.patch.object(modulo, "responde_ping", return_value=opciones.get("ping", False)),
            mock.patch.object(modulo, "probar_puerto",
                              return_value=opciones.get("puerto", "sin ruta")),
            mock.patch.object(modulo, "_ssh", return_value=opciones.get("ssh", RECHAZA)),
            mock.patch.object(modulo, "leer_disco", return_value=disco),
        ]
        with contextlib.ExitStack() as pila:
            for p in parches:
                pila.enter_context(p)
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
                codigo = getattr(modulo, nombre_main)(list(opciones.get("argv", [])))
    finally:
        os.chdir(anterior)
    return codigo, salida.getvalue(), errores.getvalue()


def normalizar(texto, home):
    texto = texto.replace(home, "HOME")
    texto = re.sub(r"^ci-diagnosis \S+$", "VERSION", texto, flags=re.M)
    texto = re.sub(r"^ssoo-us \S+$", "VERSION", texto, flags=re.M)
    texto = re.sub(r"^ci-diagnosis \S+ · ", "CABECERA · ", texto, flags=re.M)
    texto = re.sub(r"^ssoo-us diagnosis \S+ · ", "CABECERA · ", texto, flags=re.M)
    texto = texto.replace("(Versión en desarrollo.)\n", "")
    # ci-diagnosis se nombra «./ci-diagnosis» (se descarga en el silo); ssoo-us,
    # «ssoo-us diagnosis» (se instala en el servidor)
    texto = texto.replace("./ci-diagnosis", "ssoo-us diagnosis")
    texto = re.sub(r"^ci-diagnosis: ", "ssoo-us diagnosis: ", texto, flags=re.M)
    # La ayuda se pide con -h, como en provision (ci-diagnosis anunciaba --ayuda)
    texto = texto.replace("ssoo-us diagnosis --ayuda", "ssoo-us diagnosis -h")
    texto = texto.replace("  --ayuda     muestra esta ayuda.", "  -h          muestra esta ayuda (también --ayuda).")
    return texto


def sin_saltos(texto):
    return re.sub(r"\s+", " ", texto).strip()


def main():
    argumentos = [a for a in sys.argv[1:] if a != "-v"]
    detalle = "-v" in sys.argv[1:]
    origen = os.path.abspath(argumentos[0] if argumentos
                             else os.path.join(RAIZ, "..", "ci-diagnosis"))
    ci = cargar(os.path.join(origen, "ci-diagnosis"), "ci_diagnosis_referencia")
    if su.yaml is None:
        print("Aviso: sin PyYAML. Use el .venv de DESARROLLO.md.", file=sys.stderr)
    print("ci-diagnosis %s frente a ssoo-us %s" % (ci.VERSION, su.VERSION))
    iguales, distintos = 0, []
    for nombre, preparar, opciones in CASOS:
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.realpath(tmp)
            silo = os.path.join(home, "imagenesMV")
            if preparar is not None:
                preparar_alumno(home, ci.IMAGEN_BASE)
                preparar(home, silo)
            else:
                os.mkdir(silo)
            # diagnosis solo lee: las dos ven la misma cuenta
            r_ci = ejecutar(ci, "main", home, silo, ci.IMAGEN_BASE, opciones)
            r_su = ejecutar(su, "diagnosis", home, silo, su.IMAGEN_NOBLE, opciones)
            n_ci = [r_ci[0]] + [normalizar(t, home) for t in r_ci[1:]]
            n_su = [r_su[0]] + [normalizar(t, home) for t in r_su[1:]]
        if n_ci[0] == n_su[0] and all(sin_saltos(a) == sin_saltos(b)
                                      for a, b in zip(n_ci[1:], n_su[1:])):
            iguales += 1
            if detalle:
                print("  igual    %s (código %d)" % (nombre, n_ci[0]))
            continue
        distintos.append(nombre)
        print("  DISTINTO %s" % nombre)
        if n_ci[0] != n_su[0]:
            print("    código: ci-diagnosis %s, ssoo-us %s" % (n_ci[0], n_su[0]))
        for flujo, a, b in (("salida", n_ci[1], n_su[1]), ("errores", n_ci[2], n_su[2])):
            if sin_saltos(a) != sin_saltos(b):
                print("    %s:" % flujo)
                for linea in difflib.unified_diff(a.splitlines(), b.splitlines(),
                                                  "ci-diagnosis", "ssoo-us", lineterm="", n=1):
                    print("      " + linea)
    print("Casos: %d. Iguales: %d. Distintos: %d." % (len(CASOS), iguales, len(distintos)))
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
