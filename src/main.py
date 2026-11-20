# --- Programa principal --------------------------------------------------------

USO = """\
Uso: ssoo-us SUBCOMANDO [opciones]

Herramientas de la asignatura Sistemas Operativos (Universidad de Sevilla)
para las máquinas virtuales de los servidores de la asignatura.

Subcomandos:
  provision   crea máquinas virtuales con cloud-init (sustituye a
              ci-provision.sh). Su ayuda: ssoo-us provision -h
  diagnosis   revisa la construcción de una máquina hecha a mano y dice qué
              falla (sustituye a ci-diagnosis). Su ayuda: ssoo-us diagnosis -h
  acceso      dice por qué no puede entrar por ssh en una de sus máquinas
              y cómo arreglarlo. Su ayuda: ssoo-us acceso -h

Opciones:
  --version   muestra la versión.
  -h, --help  muestra esta ayuda.

Código de salida: el del subcomando; 2 si la orden está mal escrita.
"""

SUBCOMANDOS = ("provision", "diagnosis", "acceso")


def ruta_del_programa():
    """El archivo del programa, tal y como se lanzó (para volver a lanzarlo)."""
    return sys.argv[0] if sys.argv and sys.argv[0] not in ("", "-") else PROGRAMA


def nombre_programa():
    """Cómo se ha llamado al programa, para los mensajes: como el alumno lo
    escribió (./ssoo-us, ~/bin/ssoo-us...), salvo si lo encontró en el PATH
    (instalado en /usr/local/bin): entonces, sin la ruta («ssoo-us»), aunque
    Python reciba la ruta completa."""
    ruta = ruta_del_programa()
    nombre = os.path.basename(ruta)
    en_el_path = shutil.which(nombre)
    if en_el_path and os.path.realpath(en_el_path) == os.path.realpath(ruta):
        return nombre
    return ruta


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for flujo in (sys.stdout, sys.stderr):
        try:
            # Por líneas: así la salida y los errores se mezclan en el orden en que
            # se escriben, como en bash
            flujo.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
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
    if primero == "acceso":
        return acceso(resto)
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
