# --- provision: libvirt por virsh ------------------------------------------------
#
# provision habla con libvirt con «virsh», como ci-provision.sh: los tests de
# aceptación lo simulan (tests/aceptacion/mocks/virsh) y cuentan sus llamadas.
# Todas pasan por ejecutar(), con LIBVIRT_DEFAULT_URI=qemu:///system.


def virsh(*argumentos):
    """(código, salida, errores) de «virsh ARGUMENTOS»."""
    return ejecutar(["virsh"] + list(argumentos))


def virsh_ok(*argumentos):
    """¿Ha terminado bien «virsh ARGUMENTOS»?"""
    return virsh(*argumentos)[0] == 0


def virsh_salida(*argumentos):
    """La salida de «virsh ARGUMENTOS», o cadena vacía si falla («|| true»)."""
    codigo, salida, _ = virsh(*argumentos)
    return salida if codigo == 0 else ""


def lineas_no_vacias(texto):
    return [linea for linea in texto.split("\n") if linea]


def dominios_del_servidor():
    """Todos los dominios (virsh list --all --name), en su orden."""
    return lineas_no_vacias(virsh_salida("list", "--all", "--name"))


def fuentes_de_domblklist(salida, admitir_guion=False):
    """Segunda columna de «virsh domblklist» tras las dos líneas de cabecera.
    Sin admitir_guion, solo las rutas absolutas (awk '$2 ~ /^\\//'); con él,
    todo lo que no sea «-» (las unidades sin medio)."""
    fuentes = []
    for linea in salida.split("\n")[2:]:
        campos = linea.split()
        if len(campos) < 2:
            continue
        if admitir_guion and campos[1] != "-":
            fuentes.append(campos[1])
        elif not admitir_guion and campos[1].startswith("/"):
            fuentes.append(campos[1])
    return fuentes


def discos_persistentes(dominio, admitir_guion=False):
    """Fuentes de los discos de la definición persistente de un dominio."""
    return fuentes_de_domblklist(virsh_salida("domblklist", dominio, "--inactive"),
                                 admitir_guion)


def red_existe(nombre):
    return virsh_ok("net-info", nombre)


def red_activa(nombre):
    """awk '/^Active:/ { print $2 }' de «virsh net-info» == yes."""
    for linea in virsh_salida("net-info", nombre).split("\n"):
        if linea.startswith("Active:"):
            campos = linea.split()
            return len(campos) > 1 and campos[1] == "yes"
    return False
