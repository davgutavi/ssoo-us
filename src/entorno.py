# --- El silo y la red virtual, si el alumno no los tiene ---------------------------
#
# No todos los grupos montan el silo y la red del manual (secciones 5.2 y 5.3)
# antes de usar la herramienta. Si faltan, provision ofrece crearlos, cada uno
# con su pregunta, igual que se crean en el manual con virt-manager:
#
#   - el silo: el directorio ~/imagenesMV y, en libvirt, el silo
#     «USUARIO-imagenesMV» (tipo dir) que apunta a él;
#   - la red: «USUARIO-red», NAT, 192.168.X.0/24, con DHCP de la .128 a la .254
#     y sin IPv6. X no puede salir del DNI, como en el manual (la herramienta no
#     lo conoce): es la primera 192.168.X.0/24 libre del servidor.
#
# Como con la clave: con --si, sin preguntar; sin terminal o con --dry-run, no
# se ofrece y siguen los errores de siempre (30 sin silo, 40 sin red).

NOMBRE_SILO_LIBVIRT = "%s-imagenesMV"
NOMBRE_RED_NUEVA = "%s-red"
RED_NUEVA = "192.168.%d"

PREGUNTA_CREAR_SILO = ("No tienes silo: el directorio %s,\ndonde se guardan los discos de tus "
                       "máquinas, registrado en libvirt como '%s' (sección 5.2 del manual).\n"
                       "¿Lo creo ahora?")
PREGUNTA_CREAR_RED = ("No tienes red virtual. Se creará '%s': NAT, %s.0/24, con DHCP de la .128 "
                      "a la .254\n(como en la sección 5.3 del manual, salvo el número de red: es "
                      "el primero libre del\nservidor, no el que sale de tu DNI).\n¿La creo ahora?")


def se_puede_ofrecer(o):
    """Con --si, o desde una terminal en la que se pueda preguntar; nunca con
    --dry-run, que no crea nada."""
    return not o.dry_run and (o.si or (sys.stdin.isatty() and sys.stdout.isatty()))


def exigir_silo(o):
    if not os.path.isdir(o.silo):
        fallar(30, "No existe el silo en: %s\nCréalo con: mkdir -p %s\n"
                   "y mapéalo como silo en el hipervisor, como se explica en el capítulo de "
                   "infraestructura virtual." % (o.silo, o.silo))


# --- El silo ---

def falta_el_silo(o):
    """No hay nada con ese nombre: si hubiera un fichero, no se toca."""
    return not os.path.lexists(o.silo)


def destino_de_silo(nombre):
    """El directorio al que apunta un silo de libvirt, o "" si no se puede leer."""
    try:
        raiz = ET.fromstring(virsh_salida("pool-dumpxml", nombre))
    except ET.ParseError:
        return ""
    return (raiz.findtext("target/path") or "").rstrip("/")


def silo_que_apunta_aqui(o):
    """El silo de libvirt (de cualquier nombre: el suyo, si lo hay, antes que
    ninguno) que apunta ya a ~/imagenesMV, o "". Solo se busca al crear el silo:
    son un pool-dumpxml por cada silo del servidor."""
    propio = NOMBRE_SILO_LIBVIRT % o.usuario
    nombres = lineas_no_vacias(virsh_salida("pool-list", "--all", "--name"))
    for nombre in sorted(nombres, key=lambda n: n != propio):
        if destino_de_silo(nombre) == o.silo.rstrip("/"):
            return nombre
    return ""


def crear_silo(o):
    """mkdir ~/imagenesMV y su silo en libvirt (o, si ya había uno que apunta
    ahí, ese). Devuelve las líneas que se le enseñan al alumno. Para crear
    máquinas basta con el directorio: si libvirt no deja registrarlo o
    arrancarlo, se avisa y se sigue."""
    try:
        os.makedirs(o.silo)   # como «mkdir»: los permisos, los de su umask
    except OSError as e:
        fallar(30, "No se ha podido crear el silo %s: %s\nCréalo con: mkdir -p %s\n"
                   "y mapéalo como silo en el hipervisor, como se explica en el capítulo de "
                   "infraestructura virtual." % (o.silo, e.strerror or e, o.silo))
    lineas = ["✔ Silo creado: %s" % o.silo]
    nombre = silo_que_apunta_aqui(o)
    if nombre:
        lineas.append("  Ya tenías en libvirt el silo '%s', que apunta ahí: se usa ese." % nombre)
    else:
        nombre = NOMBRE_SILO_LIBVIRT % o.usuario
        if virsh_ok("pool-info", nombre):
            lineas += ["AVISO: ya tienes en libvirt un silo llamado '%s', que apunta a %s." %
                       (nombre, destino_de_silo(nombre) or "otro sitio"),
                       "  No se ha cambiado. Revísalo con: virsh pool-dumpxml %s" % nombre]
            return lineas
        codigo, _, errores = virsh("pool-define-as", nombre, "dir", "--target", o.silo)
        if codigo != 0:
            lineas += ["AVISO: no se ha podido registrar el silo en libvirt (virsh pool-define-as%s)."
                       % (": " + errores.strip() if errores.strip() else ""),
                       "  Para crear máquinas basta con el directorio. Regístralo desde "
                       "virt-manager como dice la sección 5.2 del manual."]
            return lineas
    # pool-start de un silo que ya estaba activo falla, pero no es un fallo
    codigo, _, errores = virsh("pool-start", nombre)
    activo = codigo == 0 or silo_activo(nombre)
    solo = virsh_ok("pool-autostart", nombre)
    if activo:
        lineas.append("✔ Registrado en libvirt como '%s' (activo%s)."
                      % (nombre, " y con arranque automático" if solo else ""))
    else:
        lineas += ["AVISO: el silo '%s' está registrado en libvirt, pero no se ha podido "
                   "arrancar (virsh pool-start%s)." % (nombre, ": " + errores.strip()
                                                       if errores.strip() else ""),
                   "  Para crear máquinas basta con el directorio. Arráncalo con: "
                   "virsh pool-start %s" % nombre]
    if not solo:
        lineas += ["AVISO: no se ha podido hacer que el silo arranque solo con el servidor.",
                   "  Hazlo con: virsh pool-autostart %s" % nombre]
    return lineas


def silo_activo(nombre):
    for linea in virsh_salida("pool-info", nombre).split("\n"):
        if linea.startswith("State:"):
            return linea.split()[1:2] == ["running"]
    return False


def ofrecer_crear_silo(o):
    """Si no tiene silo, lo crea tras preguntar (con --si, sin preguntar)."""
    if not falta_el_silo(o) or not se_puede_ofrecer(o):
        return
    if confirmar(o, PREGUNTA_CREAR_SILO % (o.silo, NOMBRE_SILO_LIBVIRT % o.usuario)):
        for linea in crear_silo(o):
            print(linea)
        print()


# --- La red ---

def redes_del_usuario(o):
    """Las redes que empiezan por su nombre de usuario (sin distinguir
    mayúsculas): USUARIO, USUARIO-algo o USUARIO_algo."""
    usuario = minusculas_c(o.usuario)
    candidatas = []
    for r in lineas_no_vacias(virsh_salida("net-list", "--all", "--name")):
        r_min = minusculas_c(r)
        if r_min == usuario or r_min.startswith(usuario + "-") or r_min.startswith(usuario + "_"):
            candidatas.append(r)
    return candidatas


def subred_de_xml(xml):
    """La red IPv4 (ipaddress.IPv4Network) de la definición de una red de
    libvirt, o None si no se puede saber."""
    datos = analizar_xml_red(xml)
    if datos is None or not ipv4_valida(datos["address"]):
        return None
    if datos["netmask"]:
        prefijo = mascara_a_prefijo(datos["netmask"])
    elif datos["prefix"]:
        prefijo = int(datos["prefix"], 10) if datos["prefix"].isdigit() else None
    else:
        prefijo = prefijo_por_clase(datos["address"])
    if prefijo is None or prefijo > 32:
        return None
    return ipaddress.ip_network("%s/%d" % (entero_a_ip(ip_a_entero(datos["address"])), prefijo),
                                strict=False)


# Lo que puede ir delante del destino en una línea de «ip route»
TIPOS_DE_RUTA = ("unicast", "local", "broadcast", "multicast", "throw", "unreachable",
                 "prohibit", "blackhole", "nat", "anycast")


def rutas_del_servidor():
    """Las redes IPv4 de las rutas del servidor (ip -4 route, de todas las
    tablas): las de sus interfaces, las redes de libvirt activas, las VPN, las
    que bloquea (blackhole, unreachable...)."""
    codigo, salida, _ = ejecutar(["ip", "-4", "route", "show", "table", "all"], timeout=10)
    redes = []
    if codigo != 0:
        return redes
    for linea in salida.split("\n"):
        campos = linea.split()
        if campos and campos[0] in TIPOS_DE_RUTA:
            campos = campos[1:]
        if not campos or campos[0] == "default":
            continue
        try:
            redes.append(ipaddress.ip_network(campos[0], strict=False))
        except ValueError:
            pass
    return redes


def redes_ocupadas():
    """Las de todas las redes de libvirt del servidor (de cualquier usuario,
    también las inactivas, que chocarían al arrancarlas) y las de sus rutas."""
    ocupadas = []
    for nombre in lineas_no_vacias(virsh_salida("net-list", "--all", "--name")):
        subred = subred_de_xml(virsh_salida("net-dumpxml", nombre))
        if subred is not None:
            ocupadas.append(subred)
    return ocupadas + rutas_del_servidor()


def primera_red_libre(ocupadas):
    """«192.168.X» de la primera 192.168.X.0/24 que no se solapa con ninguna
    ocupada, o None si no queda ninguna."""
    for x in range(1, 255):
        candidata = ipaddress.ip_network((RED_NUEVA % x) + ".0/24")
        if not any(candidata.overlaps(r) for r in ocupadas):
            return RED_NUEVA % x
    return None


def xml_red_nueva(nombre, base):
    """La red del manual: NAT, base.0/24, pasarela en .1, DHCP de .128 a .254,
    sin IPv6."""
    return ("<network>\n"
            "  <name>%s</name>\n"
            "  <forward mode='nat'/>\n"
            "  <ip address='%s.1' netmask='255.255.255.0'>\n"
            "    <dhcp>\n"
            "      <range start='%s.128' end='%s.254'/>\n"
            "    </dhcp>\n"
            "  </ip>\n"
            "</network>\n" % (nombre, base, base, base))


INTENTOS_RED = 5


def definir_red(nombre, base):
    """virsh net-define con la red del manual en base.0/24: (código, errores)."""
    fd, ruta = tempfile.mkstemp(prefix="ssoo-us-red-", suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml_red_nueva(nombre, base))
        codigo, _, errores = virsh("net-define", ruta)
    finally:
        os.unlink(ruta)
    return codigo, errores


def crear_red(o, base):
    """virsh net-define, net-start y net-autostart. Si no arranca (otro alumno
    ha cogido la misma red a la vez, o la usa algo que no se ha visto al
    buscar), se deshace y se prueba con la siguiente libre, hasta INTENTOS_RED
    veces; si ninguna arranca, error 40. Devuelve las líneas que se le enseñan
    al alumno."""
    nombre = NOMBRE_RED_NUEVA % o.usuario
    probadas = []
    while True:
        codigo, errores = definir_red(nombre, base)
        if codigo != 0:
            fallar(40, "No se ha podido crear la red '%s' (virsh net-define%s).\n"
                       "Créala desde virt-manager como dice la sección 5.3 del manual."
                   % (nombre, ": " + errores.strip() if errores.strip() else ""))
        codigo, _, errores = virsh("net-start", nombre)
        if codigo == 0:
            break
        virsh("net-undefine", nombre)
        probadas.append(base)
        siguiente = None
        if len(probadas) < INTENTOS_RED:
            ocupadas = redes_ocupadas() + [ipaddress.ip_network(b + ".0/24") for b in probadas]
            siguiente = primera_red_libre(ocupadas)
        if siguiente is None:
            fallar(40, "No se ha podido poner en marcha la red '%s' (virsh net-start%s).\n"
                       "Se ha deshecho. Se ha probado con: %s.\n"
                       "Avisa a tu profesor con este mensaje."
                   % (nombre, ": " + errores.strip() if errores.strip() else "",
                      ", ".join(b + ".0/24" for b in probadas)))
        base = siguiente
    lineas = ["✔ Red virtual creada: %s (%s.0/24, NAT, DHCP de %s.128 a %s.254)."
              % (nombre, base, base, base),
              "  Las IP de la .2 a la .127 quedan para tus máquinas con IP fija."]
    if probadas:
        lineas.insert(0, "AVISO: %s ya estaba en uso en el servidor; se ha usado la siguiente "
                         "libre." % ", ".join(b + ".0/24" for b in probadas))
    if not virsh_ok("net-autostart", nombre):
        lineas += ["AVISO: no se ha podido hacer que arranque sola con el servidor.",
                   "  Hazlo con: virsh net-autostart %s" % nombre]
    return lineas


def necesita_red(o):
    """No tiene ninguna red suya y no ha elegido otra con --red."""
    return not o.red_opt and not redes_del_usuario(o)


def red_libre():
    """La primera «192.168.X» libre; si no queda ninguna, error 40."""
    base = primera_red_libre(redes_ocupadas())
    if base is None:
        fallar(40, "No tienes red virtual y no queda ninguna red 192.168.X.0/24 libre en el "
                   "servidor para crearla.\nAvisa a tu profesor.")
    return base


def red_para_ofrecer(o):
    """La red «192.168.X» que se ofrecería crear, o None si el alumno ya tiene
    alguna (o eligió una con --red). Si no queda ninguna libre, error 40."""
    return red_libre() if necesita_red(o) else None


def ofrecer_crear_red(o):
    """Si no tiene ninguna red, la crea tras preguntar (con --si, sin preguntar)."""
    if not se_puede_ofrecer(o) or not necesita_red(o):
        return
    # Hay que mirar todas las redes del servidor: puede tardar unos segundos
    print("→ No tienes red virtual: buscando una red libre en el servidor…")
    sys.stdout.flush()
    base = red_libre()
    if confirmar(o, PREGUNTA_CREAR_RED % (NOMBRE_RED_NUEVA % o.usuario, base)):
        for linea in crear_red(o, base):
            print(linea)
        print()
