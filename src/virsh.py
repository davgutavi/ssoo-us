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


def obtener_ip_agente(vm):
    """La primera IPv4 no local que reporta el guest agent, o "" si el agente
    no responde todavía."""
    for linea in virsh("domifaddr", vm, "--source", "agent")[1].split("\n"):
        campos = linea.split()
        if len(campos) >= 4 and campos[2] == "ipv4" and not campos[3].startswith("127."):
            return campos[3].split("/")[0]
    return ""


def on_reboot_vivo(vm):
    """on_reboot de la definición con la que se está ejecutando la máquina."""
    return "\n".join(re.findall(r"<on_reboot>([a-z-]*)</on_reboot>", virsh("dumpxml", vm)[1]))


# Expulsión del medio de cloud-init
#
# virt-install genera una ISO efímera en /var/lib/libvirt/boot/ con la
# configuración de cloud-init y la deja enganchada como CD-ROM. libvirt borra
# ese fichero más adelante, pero la referencia permanece en la definición de la
# máquina. Si se toma una instantánea mientras la referencia sigue ahí, al
# revertirla falla con "Cannot access storage file" (apartado B.6 del manual).
# Expulsando el medio en cuanto la máquina está configurada, las instantáneas
# que tome después el alumno ya no pueden heredar el problema.

def cloudinit_unidad(vm):
    """La unidad que tiene enganchada la ISO de cloud-init, mirando tanto la
    definición activa como la persistente, o "" si no hay ninguna."""
    salida = virsh("domblklist", vm)[1] + virsh("domblklist", vm, "--inactive")[1]
    for linea in salida.split("\n"):
        campos = linea.split()
        if len(campos) >= 2 and campos[1].endswith("cloudinit.iso"):
            return campos[0]
    return ""


def eject_cloudinit_media(vm):
    unidad = cloudinit_unidad(vm)
    if not unidad:
        return
    # Por separado sobre cada definición: según el momento, libvirt ya puede
    # haber limpiado una de las dos por su cuenta, y entonces esa llamada falla
    # ('The disk device doesn't have media') aunque la otra sea necesaria y
    # posible. En una sola llamada con --live --config fallarían las dos.
    virsh("change-media", vm, unidad, "--eject", "--live")
    virsh("change-media", vm, unidad, "--eject", "--config")
    # Lo que decide es el estado final, no el código de los intentos
    if not cloudinit_unidad(vm):
        print("✔ Medio de cloud-init expulsado de %s: ya puedes tomar instantáneas." % vm)
    else:
        print("AVISO: no se ha podido expulsar el medio de cloud-init de %s (unidad %s)."
              % (vm, unidad), file=sys.stderr)
        print("       Apaga la máquina antes de tomar instantáneas.", file=sys.stderr)
