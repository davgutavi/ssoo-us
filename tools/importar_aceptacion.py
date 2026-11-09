#!/usr/bin/env python3
"""Importa los tests de bats de ci-provision como tests de aceptación de
«ssoo-us provision».

    python3 tools/importar_aceptacion.py [RUTA_DE_CI_PROVISION]

Por defecto, RUTA_DE_CI_PROVISION es ../ci-provision. Escribe en
tests/aceptacion/:

    ci-provision.bats   test/ci-provision.bats, con las sustituciones de abajo
    helpers.bash        test/helpers.bash, con las sustituciones de abajo
    mocks/              test/mocks/, tal cual
    ORIGEN              de qué commit de ci-provision salen

No se editan a mano: si cambian los tests de ci-provision, se vuelve a
importar. Cada sustitución tiene que encontrar exactamente las apariciones
previstas; si no, no se escribe nada y se dice cuál falla (los tests de
ci-provision han cambiado y hay que revisar la lista).
"""

import os
import re
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "tests", "aceptacion")

AVISO = """\
# ARCHIVO GENERADO por tools/importar_aceptacion.py a partir de
# ci-provision/{origen} ({commit}). No lo edite a mano: vuelva a importarlo.
# Las diferencias con el original están en la lista SUSTITUCIONES del
# importador.
"""

# (texto original, texto nuevo, apariciones esperadas, por qué)
SUSTITUCIONES_HELPERS = [
    ('REPO_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"\n'
     'SCRIPT="$REPO_DIR/ci-provision.sh"\n',
     'ACEPTACION_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"\n'
     'REPO_DIR="$(cd "$ACEPTACION_DIR/../.." && pwd)"\n'
     'MOCKS_DIR="$ACEPTACION_DIR/mocks"\n'
     '# El envoltorio: «bash "$SCRIPT" ARGS» ejecuta «ssoo-us provision ARGS»\n'
     'SCRIPT="$ACEPTACION_DIR/ssoo-us-provision"\n'
     '# Se puede probar otro ejecutable (una copia instalada, por ejemplo)\n'
     'export SSOO_US="${SSOO_US:-$REPO_DIR/ssoo-us}"\n'
     '# El intérprete, con ruta absoluta: algunos tests cambian el PATH\n'
     'export SSOO_US_PYTHON="${SSOO_US_PYTHON:-$(command -v python3)}"\n'
     '# Cómo se ve la orden en la salida (en ci-provision.sh, «$0»)\n'
     'ORDEN="$SSOO_US provision"\n',
     1, "SCRIPT es el envoltorio de ssoo-us provision"),
    ('$REPO_DIR/test/mocks', '$MOCKS_DIR', 1, "los mocks están en tests/aceptacion/mocks"),
]

SUSTITUCIONES_BATS = [
    ("load '../test_helper/bats-support/load'", "load 'bats/bats-support/load'", 1,
     "bats-support es un submódulo de tests/aceptacion/bats"),
    ("load '../test_helper/bats-assert/load'", "load 'bats/bats-assert/load'", 1,
     "bats-assert es un submódulo de tests/aceptacion/bats"),
    ('$REPO_DIR/test/mocks', '$MOCKS_DIR', 7, "los mocks están en tests/aceptacion/mocks"),
    ('"→ $SCRIPT ', '"→ $ORDEN ', 7,
     "el asistente muestra la orden que lanza: «ssoo-us provision ...»"),
    (r"'^ci-provision.sh [0-9]+\.[0-9]+\.[0-9]+$'",
     r"'^ssoo-us [0-9]+\.[0-9]+\.[0-9]+(-dev)?$'", 1,
     "--version dice «ssoo-us X.Y.Z» (propuesta, pendiente del visto bueno de David)"),
]

# Tests que no tienen sentido en ssoo-us: se conservan (para que el número y
# los nombres sigan siendo los de ci-provision) con un skip al principio
OMITIDOS = {
    "ci-provision.sh está al día respecto a src/ y lib/":
        "en ssoo-us lo comprueba tests/test_build.py",
    "auditoría 18: los fuentes funcionan sin generar el script (src/main.sh carga todas las librerías)":
        "ssoo-us no tiene fuentes en bash",
}


class ErrorDeImportacion(Exception):
    pass


def sustituir(texto, sustituciones, archivo):
    for viejo, nuevo, esperadas, _ in sustituciones:
        n = texto.count(viejo)
        if n != esperadas:
            raise ErrorDeImportacion("%s: «%s» aparece %d veces y se esperaban %d"
                                     % (archivo, viejo.splitlines()[0], n, esperadas))
        texto = texto.replace(viejo, nuevo)
    return texto


def omitir(texto):
    for nombre, motivo in OMITIDOS.items():
        cabecera = '@test "%s" {\n' % nombre
        if texto.count(cabecera) != 1:
            raise ErrorDeImportacion("ci-provision.bats: no encuentro el test «%s»" % nombre)
        texto = texto.replace(cabecera, cabecera + '    skip "ssoo-us: %s"\n' % motivo)
    return texto


def commit_de(origen):
    def git(*args):
        p = subprocess.run(["git", "-C", origen] + list(args), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
        return p.stdout.decode().strip() if p.returncode == 0 else ""
    commit = git("rev-parse", "--short", "HEAD") or "sin git"
    if git("status", "--porcelain", "--", "test"):
        commit += ", con cambios sin commit en test/"
    return commit


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def escribir(ruta, texto):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)


def importar(origen):
    commit = commit_de(origen)
    pruebas = os.path.join(origen, "test")
    helpers = sustituir(leer(os.path.join(pruebas, "helpers.bash")),
                        SUSTITUCIONES_HELPERS, "helpers.bash")
    bats = sustituir(leer(os.path.join(pruebas, "ci-provision.bats")),
                     SUSTITUCIONES_BATS, "ci-provision.bats")
    bats = omitir(bats)
    # El aviso, tras el shebang de bats
    primera, resto = bats.split("\n", 1)
    bats = primera + "\n" + AVISO.format(origen="test/ci-provision.bats", commit=commit) + resto
    helpers = AVISO.format(origen="test/helpers.bash", commit=commit) + helpers

    os.makedirs(DESTINO, exist_ok=True)
    escribir(os.path.join(DESTINO, "helpers.bash"), helpers)
    escribir(os.path.join(DESTINO, "ci-provision.bats"), bats)
    mocks = os.path.join(DESTINO, "mocks")
    if os.path.isdir(mocks):
        shutil.rmtree(mocks)
    shutil.copytree(os.path.join(pruebas, "mocks"), mocks)

    n = len(re.findall(r"^@test ", bats, re.M))
    lineas = ["Importado de ci-provision %s." % commit,
              "Tests: %d (%d con skip en ssoo-us)." % (n, len(OMITIDOS)),
              "Mocks: %s." % ", ".join(sorted(os.listdir(mocks)))]
    escribir(os.path.join(DESTINO, "ORIGEN"), "\n".join(lineas) + "\n")
    return lineas


def main():
    origen = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                             else os.path.join(RAIZ, "..", "ci-provision"))
    try:
        for linea in importar(origen):
            print(linea)
    except ErrorDeImportacion as e:
        print("importar_aceptacion: %s" % e, file=sys.stderr)
        print("No se ha escrito nada en tests/aceptacion.", file=sys.stderr)
        return 1
    except OSError as e:
        print("importar_aceptacion: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
