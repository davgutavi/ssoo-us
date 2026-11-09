# --- Programa principal --------------------------------------------------------

USO = """\
Uso: ./ssoo-us SUBCOMANDO [opciones]

Herramientas de la asignatura Sistemas Operativos (Universidad de Sevilla)
para las máquinas virtuales de los servidores de la asignatura.

Subcomandos:
  provision   crea máquinas virtuales con cloud-init (sustituye a
              ci-provision.sh). Su ayuda: ./ssoo-us provision -h
  diagnosis   revisa la construcción de una máquina y dice qué falla
              (sustituye a ci-diagnosis). Su ayuda: ./ssoo-us diagnosis -h

Opciones:
  --version   muestra la versión.
  -h, --help  muestra esta ayuda.

Código de salida: el del subcomando; 2 si la orden está mal escrita.
"""

SUBCOMANDOS = ("provision", "diagnosis")


def nombre_programa():
    """Cómo se ha llamado al programa, para los mensajes (./ssoo-us, ssoo-us...)."""
    return sys.argv[0] if sys.argv and sys.argv[0] else PROGRAMA


def no_implementado(subcomando):
    print("%s %s: todavía no está implementado (versión %s, en desarrollo)."
          % (PROGRAMA, subcomando, VERSION), file=sys.stderr)
    return NO_IMPLEMENTADO


def provision(argv):
    return no_implementado("provision")


def diagnosis(argv):
    return no_implementado("diagnosis")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not argv:
        print(USO, end="", file=sys.stderr)
        return 2
    primero, resto = argv[0], argv[1:]
    if primero in ("-h", "--help", "--ayuda"):
        print(USO, end="")
        return 0
    if primero == "--version":
        print("%s %s" % (PROGRAMA, VERSION))
        return 0
    if primero == "provision":
        return provision(resto)
    if primero == "diagnosis":
        return diagnosis(resto)
    if primero.startswith("-"):
        problema = "opción desconocida: %s" % primero
    else:
        problema = "subcomando desconocido: %s" % primero
    print("%s: %s (los subcomandos son: %s)." % (PROGRAMA, problema, ", ".join(SUBCOMANDOS)),
          file=sys.stderr)
    print("Consulte la ayuda con: %s -h" % nombre_programa(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
