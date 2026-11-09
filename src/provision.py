# --- provision: configuración, opciones y validaciones -------------------------
#
# Port de src/main.sh de ci-provision 3.0.2. Los mensajes y los códigos de
# salida son los mismos: los tests de aceptación (tests/aceptacion) son los de
# ci-provision.

# Contraseña de consola de 'root' (la misma que usa el manual de laboratorio).
# 'administrador' no tiene contraseña: por SSH se entra con clave; solo con
# --ssh-pass se le da una, y entonces la elige el alumno.
PASS_CONSOLA = "s1st3mas"

# Discos
TAM_DISCO_DEFECTO = "40G"
TAM_DISCO_EXTRA = "40G"
UNIDADES_EXTRA = ("vdb", "vdc", "vdd", "vde", "vdf", "vdg")   # --extra-disks (boletín 2, 2.1)

# Clúster GlusterFS (boletín 2, epígrafe 2.4)
CLUSTER_BASE = "gluster-base"
CLUSTER_NODOS = ("server1", "server2", "server3", "server4")
CLUSTER_IP_INICIAL = 10                    # server1 = .10, server2 = .11, ... (--ip-inicial)
CLUSTER_RAM_MB = 1024                      # recursos por nodo: los mismos que
CLUSTER_VCPUS = 1                          # usa crea-entorno.sh
CLUSTER_MONTAJES = ("/gluster1", "/gluster2", "/gluster3")   # vdb, vdc y vdd, en xfs
OPCIONES_FSTAB_CLUSTER = "auto,async,nofail"  # las mismas líneas de fstab que crea-entorno.sh
# Discos extra por nodo (--discos-nodo): los tres del boletín por defecto;
# crea-entorno.sh conecta siete (vdb..vdh), de los que solo formatea tres
UNIDADES_POSIBLES_NODO = ("vdb", "vdc", "vdd", "vde", "vdf", "vdg", "vdh")
DISCOS_NODO_DEFECTO = 3

# Recursos por defecto de una máquina suelta
RAM_MB_DEFECTO = 2048
VCPUS_DEFECTO = 2
RAM_MB_MINIMO = 512

# Opciones que llevan valor
OPCIONES_CON_VALOR = ("--red", "--disco", "--base", "--tam", "--ram", "--vcpus", "--ssh-pass",
                      "--prefijo", "--imagen", "--discos-nodo", "--ip-inicial")

# Nombre corto de máquina, prefijo, red, disco: solo ASCII (como en bash con LC_ALL=C)
NOMBRE_CORTO_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?")
NOMBRE_FICHERO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ErrorProvision(Exception):
    """Un error propio, con su código: «ERROR [código] mensaje» y se sale con él."""

    def __init__(self, codigo, mensaje):
        Exception.__init__(self, mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class FinProvision(Exception):
    """Terminar ya con este código, sin error (la ayuda, --version, cancelar)."""

    def __init__(self, codigo=0):
        Exception.__init__(self, codigo)
        self.codigo = codigo


class NoImplementado(Exception):
    """Lo que todavía no está portado (fases siguientes del port)."""


class FalloInesperado(Exception):
    """Ha fallado una orden externa de la que no se espera que falle (qemu-img
    create, virt-install, cp...): como set -e en ci-provision.sh, la ejecución
    termina con su código y se deshace lo creado."""

    def __init__(self, codigo):
        Exception.__init__(self, codigo)
        self.codigo = codigo


class Interrumpido(Exception):
    """Ctrl+C, o las señales TERM y HUP."""


def fallar(codigo, mensaje):
    raise ErrorProvision(codigo, mensaje)


def orden_provision():
    """Cómo se escribe la orden en los mensajes (en ci-provision.sh, «$0»)."""
    return "%s provision" % nombre_programa()


def usuario_actual():
    return pwd.getpwuid(os.geteuid()).pw_name


class Opciones:
    """Lo que dice la línea de órdenes, la configuración que se puede cambiar
    desde el entorno y lo que se deduce de ambas."""

    def __init__(self, entorno=None):
        env = os.environ if entorno is None else entorno
        self.usuario = usuario_actual()
        self.home = env.get("HOME") or os.path.expanduser("~")
        # Las rutas se forman como en ci-provision.sh, concatenando: así los
        # mensajes las escriben igual aunque HOME acabe en «/»
        self.silo = self.home + "/imagenesMV"
        # La clave del manual. La batería de pruebas del servidor pone aquí su
        # clave de usar y tirar
        self.pubkey_path = (env.get("CI_PROVISION_PUBKEY")
                            or self.home + "/.ssh/id_rsa.pub")
        # Directorio compartido de los profesores: ubuntu-base.qcow2 y, si
        # están, copias de las imágenes cloud. Los tests lo cambian.
        self.dir_compartido = env.get("CI_PROVISION_DIR_COMPARTIDO") or "/home/ssoo-shared"
        self.ubuntu_base_compartida = self.dir_compartido + "/ubuntu-base.qcow2"
        # Espera a que cloud-init termine (segundos). Con nombres propios, para
        # no recoger por accidente variables del alumno; se validan en
        # validar_entorno_numerico.
        self.esperas = {
            "WAIT_TIMEOUT": env.get("CI_PROVISION_WAIT_TIMEOUT") or "300",
            "POLL_SECS": env.get("CI_PROVISION_POLL_SECS") or "3",
            "GRACE_SECS": env.get("CI_PROVISION_GRACE_SECS") or "5",
            "SHUTDOWN_TIMEOUT": env.get("CI_PROVISION_SHUTDOWN_TIMEOUT") or "120",
        }
        self.cluster_ip_inicial = CLUSTER_IP_INICIAL

        # Opciones
        self.extra_disks = self.glusterfs = self.cluster = self.limpiar = False
        self.dry_run = self.no_wait = self.no_root = self.no_graficos = self.si = False
        self.listar = self.eliminar = self.eliminar_todo = self.menu = False
        self.red_opt = self.disco_opt = self.base_opt = self.imagen_opt = ""
        self.discos_nodo_opt = self.ip_inicial_opt = self.ram_opt = self.vcpus_opt = ""
        self.ssh_pass = self.prefijo_opt = ""
        self.tam_disco = TAM_DISCO_DEFECTO
        self.tam_explicito = False   # sin --tam, el disco crece hasta el tamaño de la imagen
        self.args = []               # parámetros posicionales
        self.nombres = []            # --eliminar: máquinas a eliminar
        self.maquina = self.ip = ""

        # Derivados
        self.ram_mb = self.vcpus = None
        self.imagen = self.base_img = self.base_img_url = self.base_img_sumas = ""
        self.os_variant = ""
        self.unidades_cluster = ()
        self.prefijo_dominio = self.prefijo_fichero = ""
        self.vm_name = self.host_name = self.disco_main = ""

        # Lo que se averigua al validar el entorno
        self.pubkey = ""              # la clave pública, ya validada (una sola línea)
        self.red = None               # RedIPv4 elegida
        self.cluster_ips = []         # IPs de los nodos del clúster
        self.extras = []              # discos extra de una máquina suelta
        self.obj_dominios = []        # lo que va a crear esta ejecución
        self.obj_ficheros = []
        self.base_img_falta = False   # en --dry-run: la imagen no está y se descargaría
        self.disco_usado_por = {}     # fichero → dominio vecino que lo usa
        self.respaldos = None         # fichero del silo → su imagen base (cargar_respaldos)

        # Ficheros cloud-init y orden de virt-install de la máquina en curso
        self.workdir = self.user_data = self.meta_data = self.network_data = ""
        self.virt_install_cmd = []

        # Registro de lo creado, para deshacerlo si algo falla a medias
        self.dominios_creados = []
        self.discos_creados = []
        self.dirs_creados = []        # directorios cloud-init nuevos de esta ejecución
        self.base_conservada = ""     # base GlusterFS ya terminada: no se deshace
        self.creacion_completa = False  # ya solo queda esperar: no se deshace nada

        # Espera a cloud-init (espera.py)
        self.ips_detectadas = {}      # dominio → IP que reporta el agente
        self.estado_ci = {}           # dominio → done | error | asumido
        self.ip_esperada = {}         # dominio → IP fija que debe tener
        self.fallos_consulta = {}     # dominio → veces seguidas sin poder consultar cloud-init
        self.asumido_desde = {}       # dominio → instante en que se empezó a asumir que está lista
        self.exigir_estado_ci = False  # True: no vale asumir (la base GlusterFS)
        self.ip_vista = {}            # dominio → última IP del agente, esté lista o no

    @property
    def modo_gestion(self):
        """--listar, --eliminar, --eliminar-todo o --menu: no crean nada."""
        return self.listar or self.eliminar or self.eliminar_todo or self.menu


# --- Ayuda ---------------------------------------------------------------------

AYUDA_PROVISION = """\
{programa} {version}

Uso:
  {orden} [opciones] MAQUINA [IP]
  {orden} [opciones] --gluster-cluster
  {orden} --listar
  {orden} --eliminar MAQUINA [MAQUINA...]
  {orden} --eliminar-todo
  {orden} --menu                  (asistente con menús; también al ejecutarlo sin argumentos)

Crea una máquina virtual con cloud-init en tu silo ({silo}).
De MAQUINA salen el nombre del dominio ({usuario}-MAQUINA), el nombre de
host (MAQUINA) y el disco (MAQUINA.qcow2), que el script crea como copia COW
de la imagen cloud de Ubuntu 24.04 ({imagen_noble}; si no está en
el silo, la descarga). La red virtual se busca por tu nombre de usuario.

Parámetros:
  MAQUINA              Nombre corto de la máquina (server1, server2, gluster-base, ...)
  IP                   (Opcional) IP fija dentro de tu red virtual. Sin ella, DHCP.

Opciones:
  --extra-disks        Crea y conecta 6 discos extra de {tam_extra} (vdb..vdg)
  --imagen IMAGEN      Imagen de partida:
                         noble        Ubuntu 24.04, {imagen_noble} (por defecto,
                                      también para la base GlusterFS)
                         debian12     Debian 12, {imagen_debian} (la del boletín 1)
                         ubuntu-base  la imagen del boletín 1 de {compartido};
                                      solo para la base GlusterFS, como en la construcción
                                      manual del boletín 2
                       Las dos primeras se descargan al silo si no están.
                       Con --base, indica de qué imagen sale ese fichero si el script
                       no sabe deducirlo (te lo avisa).
  --glusterfs          Construye una imagen base GlusterFS: crea la máquina con
                       glusterfs-server instalado, glusterd habilitado y el
                       machine-id vacío y, al terminar, la apaga y elimina el
                       dominio. Queda solo MAQUINA.qcow2, listo para hacer copias.
                       Con ubuntu-base, MAQUINA.qcow2 es una copia completa de esa
                       imagen (no depende del fichero de {compartido}).
  --gluster-cluster    Construye la infraestructura completa del epígrafe 2.4 del
                       boletín 2: la base anterior ({cluster_base}.qcow2) y {n_nodos} nodos
                       ({nodos}) con IP fija, /etc/hosts, {discos_nodo} discos
                       cada uno y {montajes} en xfs. No lleva MAQUINA.
  --discos-nodo N      Discos extra por nodo del clúster, de {discos_nodo} a {max_discos_nodo} (por defecto
                       {discos_nodo}, como el boletín; con {max_discos_nodo}, como crea-entorno.sh). Solo los
                       tres primeros se formatean y se montan.
  --ip-inicial N       Último número de la IP del primer nodo del clúster (por defecto
                       {ip_inicial}: .{ip_inicial} a .{ip_final}). Útil si el DHCP de tu red las ocupa.
  --base FICHERO       Imagen del silo de la que hacer la copia COW (p.ej. una
                       imagen base GlusterFS que ya tengas). Con --gluster-cluster
                       se omite la fase 1 y los nodos parten de ella.
  --no-root            No habilita al usuario root (queda sin contraseña, como en
                       las máquinas que se crean a mano)
  --no-virt-viewer     No habilita la consola gráfica (virt-viewer). La consola de
                       texto (virsh console) sigue funcionando.
  --limpiar            Si ya existen los dominios o discos que el script va a
                       crear, los elimina antes (solo esos; nada más), previa
                       confirmación
  --si                 Da por contestadas que sí las confirmaciones de --limpiar,
                       --eliminar y --eliminar-todo. Sin terminal (p.ej. desde otro
                       script) son obligatorias: sin --si no se elimina nada.
  --red NOMBRE         Red virtual a usar (por defecto se busca {usuario}-red)
  --prefijo PREFIJO    Sustituye a tu usuario en los nombres: dominio PREFIJO-MAQUINA
                       y, en ese caso, también los discos (PREFIJO-MAQUINA.qcow2)
  --disco NOMBRE       Nombre del disco principal (por defecto MAQUINA.qcow2)
  --tam TAMAÑO         Tamaño del disco principal (por defecto {tam_defecto}, o el de la
                       imagen de partida si es mayor: ubuntu-base tiene 64G)
  --ram MB             Memoria (por defecto {ram}; en el clúster, {ram_cluster} por nodo)
  --vcpus N            vCPUs (por defecto {vcpus}; en el clúster, {vcpus_cluster} por nodo)
  --ssh-pass CONTRASEÑA
                       Da esa contraseña a 'administrador' y permite entrar por SSH
                       escribiéndola (sin --ssh-pass, por SSH solo se entra con tu
                       clave pública). Solo caracteres ASCII. Mejor '--ssh-pass -':
                       te la pide por teclado y no la ven los demás usuarios del
                       servidor ni queda en el historial.
  --dry-run            Comprueba los datos y muestra lo que se haría, SIN crear nada
  --no-wait            No esperar a que cloud-init termine de configurar la máquina
                       (en el clúster solo afecta a los nodos: la base se espera siempre)
  -h, --help           Muestra esta ayuda

Ver y eliminar lo que ya tienes:
  --listar             Muestra tus máquinas (estado, IP, discos) y los discos del silo
                       que no usa ninguna. No lleva MAQUINA.
  --eliminar MAQUINA...
                       Elimina esas máquinas con sus discos y sus ficheros cloud-init,
                       previa confirmación. Nunca borra un disco que use otra máquina
                       ni una imagen de la que dependan otras copias.
  --eliminar-todo      Elimina todas tus máquinas (las {usuario}-*) con sus discos y
                       ofrece borrar los discos del silo que queden sin máquina.
  --version            Muestra la versión del script
  --menu               Asistente con menús para hacer todo lo anterior sin tener que
                       recordar las opciones. Es lo que se abre al ejecutar el script
                       sin argumentos desde una terminal.

En todas las máquinas:
  - Usuario 'administrador' con tu clave pública ({pubkey}) y
    sudo sin contraseña. Sin contraseña propia salvo que uses --ssh-pass.
    En las que salen de ubuntu-base (la base GlusterFS y sus nodos) se queda
    como en esa imagen: con la contraseña del boletín 1, que sudo pide; el
    script solo le añade tu clave pública.
  - Usuario 'root' con contraseña '{pass_consola}', solo para la consola
    (virsh console o virt-viewer); por SSH no puede entrar. Con --no-root,
    sin contraseña.
  - Consola gráfica activa (virt-viewer), salvo con --no-virt-viewer.

Ejemplos (XXX es el tercer número de tu red virtual; lo ves en el resumen de --dry-run):
  {orden} server1                                    # Ubuntu 24.04 con DHCP
  {orden} --imagen debian12 server1 192.168.XXX.2    # SERVER1 del boletín 1 (Debian 12)
  {orden} --extra-disks server1 192.168.XXX.2        # SERVER1 del boletín 2, epígrafe 2.1
  {orden} --gluster-cluster                          # infraestructura del boletín 2, epígrafe 2.4
  {orden} --glusterfs gluster-base                   # solo la imagen base GlusterFS
  {orden} --gluster-cluster --base gluster-base.qcow2   # la infraestructura a partir de esa imagen
  {orden} --dry-run --extra-disks server1 192.168.XXX.2 # solo comprobar
"""


def texto_ayuda(o):
    return AYUDA_PROVISION.format(
        programa=PROGRAMA, version=VERSION, orden=orden_provision(), silo=o.silo,
        usuario=o.usuario, imagen_noble=IMAGEN_NOBLE, imagen_debian=IMAGEN_DEBIAN,
        tam_extra=TAM_DISCO_EXTRA, compartido=o.dir_compartido, cluster_base=CLUSTER_BASE,
        n_nodos=len(CLUSTER_NODOS), nodos=" ".join(CLUSTER_NODOS),
        discos_nodo=DISCOS_NODO_DEFECTO, montajes=" ".join(CLUSTER_MONTAJES),
        max_discos_nodo=len(UNIDADES_POSIBLES_NODO), ip_inicial=CLUSTER_IP_INICIAL,
        ip_final=CLUSTER_IP_INICIAL + len(CLUSTER_NODOS) - 1, tam_defecto=TAM_DISCO_DEFECTO,
        ram=RAM_MB_DEFECTO, ram_cluster=CLUSTER_RAM_MB, vcpus=VCPUS_DEFECTO,
        vcpus_cluster=CLUSTER_VCPUS, pubkey=o.pubkey_path, pass_consola=PASS_CONSOLA)


# --- Opciones --------------------------------------------------------------------

def analizar_opciones(o, argv):
    """parse_args de ci-provision. La ayuda y --version terminan (FinProvision)."""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--extra-disks":
            o.extra_disks = True
        elif a == "--glusterfs":
            o.glusterfs = True
        elif a == "--gluster-cluster":
            o.cluster = True
        elif a == "--limpiar":
            o.limpiar = True
        elif a == "--dry-run":
            o.dry_run = True
        elif a == "--no-wait":
            o.no_wait = True
        elif a == "--no-root":
            o.no_root = True
        elif a == "--no-virt-viewer":
            o.no_graficos = True
        elif a == "--si":
            o.si = True
        elif a == "--listar":
            o.listar = True
        elif a == "--eliminar":
            o.eliminar = True
        elif a == "--eliminar-todo":
            o.eliminar_todo = True
        elif a == "--menu":
            o.menu = True
        elif a == "--version":
            print("%s %s" % (PROGRAMA, VERSION))
            raise FinProvision(0)
        elif a in OPCIONES_CON_VALOR:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                fallar(11, "Falta el valor de la opción %s. Escríbelo a continuación, "
                           "separado por un espacio: %s VALOR" % (a, a))
            valor = argv[i + 1]
            if valor == "":
                fallar(11, "La opción %s no admite un valor vacío." % a)
            if a == "--tam":
                o.tam_disco, o.tam_explicito = valor, True
            else:
                setattr(o, {"--red": "red_opt", "--disco": "disco_opt", "--base": "base_opt",
                            "--imagen": "imagen_opt", "--discos-nodo": "discos_nodo_opt",
                            "--ip-inicial": "ip_inicial_opt", "--ram": "ram_opt",
                            "--vcpus": "vcpus_opt", "--ssh-pass": "ssh_pass",
                            "--prefijo": "prefijo_opt"}[a], valor)
            i += 1
        elif a in ("-h", "--help"):
            print(texto_ayuda(o), end="")
            raise FinProvision(0)
        # Opciones de la versión anterior: se explica qué ha cambiado
        elif a == "--enable-root":
            fallar(12, "La opción --enable-root ya no existe: root está habilitado por consola "
                       "de forma predeterminada (contraseña %s); usa --no-root si no lo "
                       "quieres." % PASS_CONSOLA)
        elif a == "--virt-viewer":
            fallar(12, "La opción --virt-viewer ya no existe: la consola gráfica está activa de "
                       "forma predeterminada; usa --no-virt-viewer si no la quieres.")
        elif a == "--user-pass":
            fallar(12, "La opción --user-pass ha sido sustituida por --ssh-pass CONTRASEÑA (o "
                       "'--ssh-pass -' para escribirla por teclado).\n"
                       "Sin ella, 'administrador' no tiene contraseña y por SSH se entra con tu "
                       "clave; por consola entra root (contraseña %s)." % PASS_CONSOLA)
        elif a == "--":
            o.args += argv[i + 1:]
            break
        elif a.startswith("--") and "=" in a:
            nombre, valor = a.split("=", 1)
            fallar(12, "La opción '%s' se escribe con un espacio, no con '=': %s %s"
                   % (nombre, nombre, valor))
        elif a.startswith("-"):
            fallar(12, "Opción desconocida '%s'. Consulta la ayuda con -h." % a)
        else:
            o.args.append(a)
        i += 1

    if o.ssh_pass == "-":
        o.ssh_pass = leer_contrasena()


def leer_contrasena():
    """--ssh-pass -: la contraseña se pide por teclado, para que no quede en el
    historial ni la vean otros usuarios del servidor en 'ps'. El asistente, que
    ya la ha pedido, la pasa por el entorno (que solo puede leer el propio
    usuario) en lugar de en la línea de órdenes."""
    if os.environ.get("CI_PROVISION_SSH_PASS"):
        contrasena = os.environ.pop("CI_PROVISION_SSH_PASS")
        return contrasena
    if not sys.stdin.isatty():
        fallar(11, "Con '--ssh-pass -' la contraseña se pide por teclado, y aquí no hay terminal.")
    # Como «read -r -s -p»: el texto por stderr, sin eco, y el salto de línea
    # (que no se ve al no haber eco) por stdout
    sys.stderr.write("Contraseña para administrador: ")
    sys.stderr.flush()
    fd = sys.stdin.fileno()
    antes = termios.tcgetattr(fd)
    sin_eco = termios.tcgetattr(fd)
    sin_eco[3] &= ~termios.ECHO
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, sin_eco)
        linea = sys.stdin.readline()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, antes)
    print()
    contrasena = linea[:-1] if linea.endswith("\n") else ""
    if not contrasena:
        fallar(11, "La contraseña no puede estar vacía.")
    return contrasena


def decimal(texto):
    """Número entero escrito en decimal (los ceros a la izquierda no lo hacen
    octal), o None si no son solo cifras."""
    if re.fullmatch(r"[0-9]+", texto) is None:
        return None
    return int(texto, 10)


# --- Validación de las opciones -------------------------------------------------

def validar_opciones(o):
    """Comprobaciones de las opciones ya leídas: modos, parámetros y valores."""
    validar_modos(o)
    if o.cluster:
        validar_cluster(o)
    elif not o.modo_gestion:
        validar_maquina(o)
    validar_valores(o)
    validar_entorno_numerico(o)


def validar_modos(o):
    """Modos: --gluster-cluster, --listar, --eliminar, --eliminar-todo, --menu."""
    if sum((o.cluster, o.listar, o.eliminar, o.eliminar_todo, o.menu)) > 1:
        fallar(10, "--gluster-cluster, --listar, --eliminar, --eliminar-todo y --menu son "
                   "modos distintos: usa solo uno.")
    if o.modo_gestion:
        if (o.extra_disks or o.glusterfs or o.limpiar or o.no_wait or o.no_root
                or o.no_graficos or o.tam_explicito
                or (o.red_opt + o.disco_opt + o.base_opt + o.ram_opt + o.vcpus_opt
                    + o.ssh_pass + o.imagen_opt + o.discos_nodo_opt + o.ip_inicial_opt)):
            fallar(10, "Con --listar, --eliminar, --eliminar-todo y --menu solo se admiten "
                       "--prefijo, --dry-run y --si.")
        if o.eliminar:
            if not o.args:
                orden = orden_provision()
                fallar(10, "Falta el nombre de la máquina a eliminar: %s --eliminar MAQUINA "
                           "[MAQUINA...]\n(p.ej. %s --eliminar server1). Para ver las que "
                           "tienes: %s --listar" % (orden, orden, orden))
            o.nombres = list(o.args)
            for m in o.nombres:
                validar_nombre_corto(o, m)
        elif o.args:
            fallar(10, "--listar, --eliminar-todo y --menu no llevan MAQUINA (sobra: '%s')."
                   % " ".join(o.args))

    if o.glusterfs and o.no_wait:
        fallar(10, "--no-wait no se puede combinar con --glusterfs: la base hay que apagarla\n"
                   "cuando cloud-init termine, así que es imprescindible esperar.")
    if o.discos_nodo_opt and not o.cluster:
        fallar(10, "--discos-nodo solo se aplica a --gluster-cluster. En una máquina suelta, "
                   "usa --extra-disks.")
    if o.ip_inicial_opt and not o.cluster:
        fallar(10, "--ip-inicial solo se aplica a --gluster-cluster. En una máquina suelta, "
                   "indica la IP después del nombre.")


def validar_nombre_corto(o, m):
    """Nombre corto de una máquina: válido como hostname y sin el usuario (o el
    prefijo) delante, que lo antepone el script: 'usuario-server1' daría
    'usuario-usuario-server1', que nadie quiere."""
    pref = o.prefijo_opt or o.usuario
    if NOMBRE_CORTO_RE.fullmatch(m) is None or len(m) > 63:
        fallar(20, "El nombre de máquina '%s' no es válido.\n"
                   "Solo letras, números y guiones, empezando por letra o número (p.ej. "
                   "server1, gluster-base)." % m)
    if m.lower().startswith(pref.lower() + "-"):
        # ${m#"${m%%-*}-"}: lo que hay tras el primer guion
        fallar(20, "El nombre de máquina '%s' ya empieza por '%s-': el dominio sería '%s-%s'.\n"
                   "Indica solo el nombre corto (p.ej. '%s'); '%s-' lo antepone el script."
               % (m, pref, pref, m, m.split("-", 1)[1], pref))


def validar_cluster(o):
    if o.args:
        fallar(10, "Con --gluster-cluster no se indica MAQUINA ni IP: los nombres (%s, %s) son "
                   "fijos\ny las IPs van de la .%d en adelante (cámbialo con --ip-inicial N)."
               % (CLUSTER_BASE, " ".join(CLUSTER_NODOS), o.cluster_ip_inicial))
    if o.disco_opt:
        fallar(10, "La opción --disco no se aplica a --gluster-cluster: los discos se llaman "
                   "como los nodos.")
    if o.glusterfs or o.extra_disks:
        fallar(10, "--gluster-cluster ya construye la imagen base y los discos de cada nodo:\n"
                   "no se combina con --glusterfs ni con --extra-disks.")
    if o.ip_inicial_opt:
        n = decimal(o.ip_inicial_opt)
        if n is None or n < 2 or n > 250:
            fallar(13, "La IP inicial '%s' no es válida: indica el último número de la IP del "
                       "primer nodo (de 2 a 250)." % o.ip_inicial_opt)
        o.cluster_ip_inicial = n


def validar_maquina(o):
    orden = orden_provision()
    if not o.args:
        fallar(10, "Falta el nombre de la máquina.\n"
                   "Uso: %s [opciones] MAQUINA [IP]      (p.ej. %s server1)\n"
                   "Consulta la ayuda con -h. En el servidor de la asignatura también puedes\n"
                   "ejecutarlo sin argumentos desde una terminal: se abre un asistente con "
                   "menús." % (orden, orden))
    if len(o.args) > 2:
        fallar(10, "Sobran parámetros: '%s'.\n"
                   "Parece la sintaxis de la versión anterior. Ahora solo se indica el nombre "
                   "corto\nde la máquina y, opcionalmente, la IP; el disco y la red se deducen "
                   "de tu usuario:\n"
                   "  %s [opciones] MAQUINA [IP]      (p.ej. %s --extra-disks server1 "
                   "192.168.XXX.2)\n"
                   "Consulta la ayuda con -h." % (" ".join(o.args), orden, orden))
    o.maquina = o.args[0]
    o.ip = o.args[1] if len(o.args) > 1 else ""
    validar_nombre_corto(o, o.maquina)

    if o.glusterfs and o.extra_disks:
        fallar(10, "--extra-disks no se combina con --glusterfs: la imagen base es un solo "
                   "disco,\nque es lo único que queda al terminar. Los discos extra se crean al "
                   "hacer las copias\n(p.ej. --gluster-cluster, o --extra-disks --base %s.qcow2 "
                   "server1)." % o.maquina)
    if o.glusterfs and o.ip:
        fallar(10, "Con --glusterfs no se indica IP: la máquina es provisional (se elimina al "
                   "terminar)\ny la IP la reciben las copias que hagas de %s.qcow2." % o.maquina)


def validar_valores(o):
    """Valores de las opciones: recursos, tamaños, nombres, imagen, discos por nodo."""
    if o.cluster:
        ram, vcpus = o.ram_opt or str(CLUSTER_RAM_MB), o.vcpus_opt or str(CLUSTER_VCPUS)
    else:
        ram, vcpus = o.ram_opt or str(RAM_MB_DEFECTO), o.vcpus_opt or str(VCPUS_DEFECTO)
    n = decimal(ram)
    if n is None or n < RAM_MB_MINIMO:
        fallar(13, "La memoria RAM '%s' no es válida. Debe ser un número de MB igual o mayor "
                   "que %d." % (ram, RAM_MB_MINIMO))
    o.ram_mb = n
    n = decimal(vcpus)
    if n is None or n < 1:
        fallar(13, "El número de vCPUs '%s' no es válido. Debe ser un número igual o mayor "
                   "que 1." % vcpus)
    o.vcpus = n

    # ${TAM_DISCO^^} con LC_ALL=C: solo pasa a mayúsculas las letras ASCII
    tam = "".join(c.upper() if "a" <= c <= "z" else c for c in o.tam_disco)
    if re.fullmatch(r"[0-9]+[MGT]", tam) is None or int(tam[:-1], 10) == 0:
        fallar(15, "El tamaño de disco '%s' no es válido. Indícalo como 40G, 20G, 512M..." % tam)
    o.tam_disco = "%d%s" % (int(tam[:-1], 10), tam[-1])

    if o.red_opt and NOMBRE_FICHERO_RE.fullmatch(o.red_opt) is None:
        fallar(40, "El nombre de red '%s' no es válido. Consulta tus redes con: "
                   "virsh net-list --all" % o.red_opt)
    if o.disco_opt and NOMBRE_FICHERO_RE.fullmatch(o.disco_opt) is None:
        fallar(16, "El nombre de disco '%s' no es válido. Indica solo el nombre del fichero "
                   "(sin rutas), p.ej. server1.qcow2." % o.disco_opt)
    if o.base_opt and NOMBRE_FICHERO_RE.fullmatch(o.base_opt) is None:
        fallar(16, "El nombre de imagen '%s' (--base) no es válido. Indica solo el nombre del "
                   "fichero del silo (sin rutas), p.ej. gluster-base.qcow2." % o.base_opt)
    elegir_imagen(o)

    n = decimal(o.discos_nodo_opt or str(DISCOS_NODO_DEFECTO))
    if n is None or n < len(CLUSTER_MONTAJES) or n > len(UNIDADES_POSIBLES_NODO):
        fallar(13, "El número de discos por nodo '%s' no es válido. Debe estar entre %d (los "
                   "que se montan\nen %s) y %d (vdb..vdh, como crea-entorno.sh)."
               % (o.discos_nodo_opt, len(CLUSTER_MONTAJES), " ".join(CLUSTER_MONTAJES),
                  len(UNIDADES_POSIBLES_NODO)))
    o.unidades_cluster = UNIDADES_POSIBLES_NODO[:n]

    if o.prefijo_opt and NOMBRE_CORTO_RE.fullmatch(o.prefijo_opt) is None:
        fallar(20, "El prefijo '%s' no es válido. Solo letras, números y guiones, p.ej. demo."
               % o.prefijo_opt)

    # La contraseña se teclea en la consola de la máquina virtual, cuyo teclado
    # no tiene por qué corresponderse con el del alumno. El manual ya advierte
    # de no usar tildes ni caracteres del alfabeto español.
    if any(c != "\n" and not " " <= c <= "~" for c in o.ssh_pass):
        fallar(14, "La contraseña contiene caracteres no ASCII (tildes, ñ, etc.).\n"
                   "No podrías teclearla en la consola de la máquina virtual.\n"
                   "Usa solo letras sin tilde, números y signos básicos.")


def validar_entorno_numerico(o):
    """Los tiempos de espera que se pueden ajustar desde el entorno."""
    for nombre in ("WAIT_TIMEOUT", "POLL_SECS", "GRACE_SECS", "SHUTDOWN_TIMEOUT"):
        valor = o.esperas[nombre]
        n = decimal(valor)
        if n is None or (nombre == "POLL_SECS" and n < 1):
            fallar(13, "La variable de entorno CI_PROVISION_%s ('%s') no es válida: debe ser "
                       "un número de segundos." % (nombre, valor))
        o.esperas[nombre] = n


def calcular_derivados(o):
    """Nombres que salen de las opciones (dominio, hostname, disco principal).
    Sin --prefijo: dominio USUARIO-MAQUINA y ficheros MAQUINA.qcow2, como en el
    boletín. Con él, el prefijo va también en los ficheros, para que dos juegos
    de máquinas convivan en el mismo silo sin pisarse."""
    o.prefijo_dominio = o.prefijo_opt or o.usuario
    o.prefijo_fichero = o.prefijo_opt + "-" if o.prefijo_opt else ""
    if not o.cluster:
        o.vm_name = "%s-%s" % (o.prefijo_dominio, o.maquina)
        o.host_name = o.maquina
        o.disco_main = o.silo + "/" + (o.disco_opt or disco_de(o, o.maquina))


def disco_de(o, maquina):
    """Nombre del disco principal de una máquina en el silo: MAQUINA.qcow2, o
    PREFIJO-MAQUINA.qcow2 con --prefijo (solo el nombre, sin ruta)."""
    return "%s%s.qcow2" % (o.prefijo_fichero, maquina)


# --- Entorno: libvirt, silo, clave, red, IPs e imagen -------------------------------

def validar_entorno(o):
    """Validaciones generales, contra el servidor. Con --listar, --eliminar,
    --eliminar-todo y --menu solo las que necesitan (no crean nada)."""
    # Herramientas necesarias (jq y base64 ya no: los hace Python)
    faltan = [c for c in ("qemu-img", "virsh", "virt-install") if shutil.which(c) is None]
    if faltan:
        fallar(38, "No se encuentran estas herramientas necesarias: %s\n"
                   "Avisa al administrador del servidor." % " ".join(faltan))
    if not virsh_ok("list", "--name"):
        fallar(38, "No se puede conectar con libvirt (virsh).\n"
                   "¿Estás en el servidor de la asignatura? Prueba: virsh list --all")
    if not os.path.isdir(o.silo):
        fallar(30, "No existe el silo en: %s\nCréalo con: mkdir -p %s\n"
                   "y mapéalo como silo en el hipervisor, como se explica en el capítulo de "
                   "infraestructura virtual." % (o.silo, o.silo))
    if o.modo_gestion:
        return

    comprobar_clave_publica(o)

    # Red: elegirla y leer sus datos reales
    o.red = cargar_red(detectar_red(o))

    # IPs fijas, contra la red real
    if o.cluster:
        calcular_ips_cluster(o)
        for ip in o.cluster_ips:
            validar_ip_fija(o, ip)
    elif o.ip:
        validar_ip_fija(o, o.ip)
        o.ip = entero_a_ip(ip_a_entero(o.ip))

    # Antes de la descarga, que cuesta tiempo: qué se va a crear y si choca
    # con algo existente. Con --limpiar, la eliminación se hace después.
    calcular_objetivos(o)
    comprobar_base_no_objetivo(o)
    comprobar_conflictos(o, solo_detectar=True)

    # Que la IP fija no la tenga ya otra máquina
    if o.cluster:
        for ip, nodo in zip(o.cluster_ips, CLUSTER_NODOS):
            comprobar_ip_en_uso(o, ip, "%s-%s" % (o.prefijo_dominio, nodo))
    elif o.ip:
        comprobar_ip_en_uso(o, o.ip, o.vm_name)

    # La imagen base, en último lugar: si falta hay que descargarla, y no
    # tiene sentido hacerlo para fallar después por un dato mal escrito
    comprobar_imagen_base(o)
    comprobar_tam_disco(o)


def minusculas_c(texto):
    """${texto,,} con LC_ALL=C: solo las letras ASCII."""
    return "".join(c.lower() if "A" <= c <= "Z" else c for c in texto)


def detectar_red(o):
    """La red virtual del alumno. El manual pide llamarla USUARIO-red, pero en
    los servidores hay redes con otros sufijos (-net, -network, _red, sin
    sufijo) y usuarios con más de una. Se busca entre las que empiezan por el
    usuario; si hay dudas, se pide --red. Tiene que estar activa."""
    if o.red_opt:
        if not red_existe(o.red_opt):
            fallar(40, "La red '%s' (--red) no existe.\n"
                       "Consulta las redes disponibles con: virsh net-list --all" % o.red_opt)
        nombre = o.red_opt
    else:
        usuario = minusculas_c(o.usuario)
        candidatas = []
        for r in lineas_no_vacias(virsh_salida("net-list", "--all", "--name")):
            r_min = minusculas_c(r)
            if (r_min == usuario or r_min.startswith(usuario + "-")
                    or r_min.startswith(usuario + "_")):
                candidatas.append(r)
        if o.usuario + "-red" in candidatas:
            nombre = o.usuario + "-red"
        elif len(candidatas) == 1:
            nombre = candidatas[0]
        elif not candidatas:
            fallar(40, "No encuentro ninguna red virtual con tu nombre de usuario ('%s').\n"
                       "Crea tu red virtual con el nombre '%s-red', o indica cuál usar con: "
                       "--red NOMBRE\nRedes existentes: virsh net-list --all"
                   % (o.usuario, o.usuario))
        else:
            fallar(44, "Hay varias redes virtuales con tu nombre de usuario: %s\n"
                       "Indica cuál usar con: --red NOMBRE" % " ".join(candidatas))
    # La red tiene que estar activa para que virt-install pueda conectar la máquina
    if not red_activa(nombre):
        fallar(45, "La red '%s' existe pero está inactiva.\n"
                   "Actívala con:            virsh net-start %s\n"
                   "Para que arranque sola:  virsh net-autostart %s" % (nombre, nombre, nombre))
    return nombre


def cargar_red(nombre):
    """Los datos reales de la red (virsh net-dumpxml), en lugar de dar por
    supuesta la configuración del manual (192.168.X.0/24, pasarela en .1 y
    DHCP en .128-.254): así funciona igual con redes de otra topología."""
    pista = ("\nRevisa su definición con: virsh net-dumpxml %s\n"
             "Si no ves el problema, avisa a tu profesor con esa salida." % nombre)
    codigo, xml, _ = virsh("net-dumpxml", nombre)
    if codigo != 0:
        fallar(40, "La red '%s' no existe.\n"
                   "Consulta las redes disponibles con: virsh net-list --all" % nombre)
    datos = analizar_xml_red(xml)
    if datos is None:
        fallar(43, "No se ha podido determinar la configuración IPv4 de la red '%s'.%s"
               % (nombre, pista))
    pasarela = datos["address"]
    prefijo = None
    if datos["netmask"]:
        prefijo = mascara_a_prefijo(datos["netmask"])
        if prefijo is None:
            fallar(43, "La máscara '%s' de la red '%s' no es válida.%s"
                   % (datos["netmask"], nombre, pista))
    elif datos["prefix"]:
        prefijo = int(datos["prefix"], 10)
    elif ipv4_valida(pasarela):
        prefijo = prefijo_por_clase(pasarela)
    if not ipv4_valida(pasarela):
        fallar(43, "La pasarela '%s' de la red '%s' no es una IPv4 válida.%s"
               % (pasarela, nombre, pista))
    # Rangos DHCP (puede haber varios) y reservas estáticas por MAC, que pueden
    # estar fuera del rango DHCP
    rangos = [(a, b) for a, b in datos["rangos"] if ipv4_valida(a) and ipv4_valida(b)]
    reservas = [r for r in datos["reservas"] if ipv4_valida(r)]
    return RedIPv4(nombre, pasarela, prefijo, rangos, reservas)


def ips_libres(o):
    return "\n".join(o.red.bloques_libres())


def remedio_ip(o):
    """Final de los mensajes de IP: qué puede hacer el alumno."""
    if not o.cluster:
        return "También puedes omitir el parámetro IP para que la máquina use DHCP."
    n = o.red.primer_hueco(len(CLUSTER_NODOS))
    if n is not None:
        return ("Para el clúster hacen falta %d IPs fijas seguidas. Hay hueco a partir de la "
                ".%d:\n  %s --gluster-cluster --ip-inicial %d"
                % (len(CLUSTER_NODOS), n, orden_provision(), n))
    return ("Para el clúster hacen falta %d IPs fijas seguidas y tu red no tiene ningún hueco "
            "así.\nReduce el rango DHCP de tu red (virsh net-edit %s; p.ej. que empiece en la "
            ".128)." % (len(CLUSTER_NODOS), o.red.nombre))


def validar_ip_fija(o, ip):
    """Valida una IP fija contra la configuración real de la red."""
    red = o.red
    if not ipv4_valida(ip):
        fallar(41, "La IP '%s' no es una dirección IPv4 válida (cuatro números de 0 a 255 "
                   "separados por puntos).\nPasarela : %s\nIPs libres para asignación fija:\n"
                   "%s\n\n%s" % (ip, red.pasarela, ips_libres(o), remedio_ip(o)))
    n = ip_a_entero(ip)
    if n & red.mascara_entera != red.red_entera:
        fallar(41, "La IP '%s' no pertenece a la red '%s'.\nRed      : %s/%d\n"
                   "Pasarela : %s\nIPs libres para asignación fija:\n%s"
               % (ip, red.nombre, entero_a_ip(red.red_entera), red.prefijo, red.pasarela,
                  ips_libres(o)))
    if n in (red.red_entera, red.difusion_entera):
        fallar(41, "La IP '%s' es la dirección de red o la de difusión de '%s'. No se puede "
                   "asignar a una máquina." % (ip, red.nombre))
    if n == ip_a_entero(red.pasarela):
        fallar(41, "La IP '%s' es la pasarela de la red '%s'. Elige otra." % (ip, red.nombre))
    for inicio, fin in red.rangos:
        if ip_a_entero(inicio) <= n <= ip_a_entero(fin):
            fallar(42, "La IP '%s' está dentro del rango DHCP de la red '%s' (%s - %s).\n"
                       "Si se la asignas de forma fija, el servidor DHCP puede entregársela a "
                       "otra máquina.\nPasarela : %s\nIPs libres para asignación fija:\n%s\n\n%s"
                   % (ip, red.nombre, inicio, fin, red.pasarela, ips_libres(o), remedio_ip(o)))
    for reserva in red.reservas:
        if n == ip_a_entero(reserva):
            fallar(42, "La IP '%s' ya está reservada por MAC en la red '%s'.\n"
                       "IPs libres para asignación fija:\n%s\n\n%s"
                   % (ip, red.nombre, ips_libres(o), remedio_ip(o)))


def comprobar_ip_en_uso(o, ip, vm):
    """¿Usa ya otra máquina esta IP? Se mira en los ficheros cloud-init del silo
    (las máquinas creadas con el script, aunque estén apagadas) y, si hay ping,
    si algo responde en ella. No cuenta la máquina que se va a rehacer con
    --limpiar, que es la que tiene esa IP."""
    propia = False
    patron = re.compile(r"- %s/[0-9]+$" % re.escape(ip), re.M)
    for f in sorted(glob.glob(os.path.join(glob.escape(o.silo), "cloudinit-*", "cip-net.yaml"))):
        if not os.path.isfile(f):
            continue
        directorio = os.path.dirname(f)
        if directorio.endswith(".dry-run"):
            continue
        dominio = os.path.basename(directorio)[len("cloudinit-"):]
        datos = leer_bytes(f) or b""
        if not patron.search(datos.decode("utf-8", "surrogateescape")):
            continue
        if dominio in o.obj_dominios:
            propia = True
        elif virsh_ok("dominfo", dominio):
            if dominio.startswith(o.usuario + "-"):
                orden = "%s --eliminar %s" % (orden_provision(), dominio[len(o.usuario) + 1:])
            else:
                orden = "%s --prefijo %s --eliminar %s" % (
                    orden_provision(), dominio.split("-", 1)[0], dominio.split("-", 1)[-1])
            fallar(42, "La IP '%s' ya la tiene asignada tu máquina '%s'. Dos máquinas con la "
                       "misma IP no se pueden comunicar.\n"
                       "Elige otra IP, o elimina antes esa máquina: %s\n"
                       "IPs libres para asignación fija:\n%s" % (ip, dominio, orden, ips_libres(o)))
    if (not propia and shutil.which("ping")
            and ejecutar(["ping", "-c1", "-W1", ip])[0] == 0):
        fallar(42, "Algo responde ya en la IP '%s' (otra máquina de tu red virtual, o creada a "
                   "mano).\nSi se la asignas también a '%s', ninguna de las dos funcionará "
                   "bien. Elige otra IP.\nIPs libres para asignación fija:\n%s\n\n%s"
               % (ip, vm, ips_libres(o), remedio_ip(o)))


# --- Deshacer lo creado si la ejecución se interrumpe a medias ----------------------
#
# Solo se eliminan los elementos creados por ESTA ejecución: los dominios y los
# discos que el propio script acaba de crear. Nada preexistente se toca.

def revertir_cambios(o):
    if not o.dominios_creados and not o.discos_creados:
        return
    err = sys.stderr
    print(file=err)
    print("Deshaciendo lo que se había creado en esta ejecución:", file=err)
    for dominio in o.dominios_creados:
        # Se registra antes de lanzar virt-install: puede que no llegara a definirlo
        if not virsh_ok("dominfo", dominio):
            continue
        virsh("destroy", dominio)
        if virsh_ok("undefine", dominio, "--snapshots-metadata"):
            print("  - dominio '%s' eliminado" % dominio, file=err)
        else:
            print("  - dominio '%s': no se ha podido eliminar. Hazlo tú: virsh undefine %s "
                  "--snapshots-metadata" % (dominio, dominio), file=err)
    for disco in o.discos_creados:
        if not os.path.exists(disco):
            continue
        borrar_si_existe(disco)
        print("  - disco '%s' eliminado" % disco, file=err)
    for directorio in o.dirs_creados:
        if os.path.isdir(directorio):
            borrar_ruta(directorio)
            print("  - ficheros cloud-init '%s' eliminados" % directorio, file=err)
    if o.base_conservada and os.path.exists(o.base_conservada):
        nombre = os.path.basename(o.base_conservada)
        print("  - la imagen base %s ya estaba terminada y se conserva:" % nombre, file=err)
        print("    puedes reutilizarla con --base %s" % nombre, file=err)
    print("  (nada que existiera antes de ejecutar el script se ha tocado)", file=err)


def al_salir(o, codigo, interrumpido=False, inesperado=False):
    """Lo que hace el «trap al_salir EXIT» de ci-provision.sh."""
    if codigo == 0:
        return
    err = sys.stderr
    if interrumpido:
        print(file=err)
        print("Interrumpido por el usuario.", file=err)
    elif inesperado:
        print(file=err)
        print("ERROR: el script ha terminado de forma inesperada (código %d)." % codigo, file=err)
        print("       Si el problema persiste, avisa a tu profesor indicando el comando usado.",
              file=err)
    if o.creacion_completa:
        print("Lo creado se conserva: no se deshace nada. Comprueba su estado con:", file=err)
        print("  virsh list --all", file=err)
        if interrumpido:
            print("OJO: no se ha expulsado el medio de cloud-init y la máquina se apagará en su "
                  "primer", file=err)
            print("     reinicio. Cuando termine de configurarse, apágala y arráncala desde fuera",
                  file=err)
            print("     (virsh shutdown NOMBRE; virsh start NOMBRE) antes de tomar instantáneas.",
                  file=err)
    else:
        revertir_cambios(o)


def senal_recibida(numero, marco):
    raise Interrumpido()


# --- Flujo de provision -----------------------------------------------------------

def provision(argv):
    o = Opciones()
    # Como «trap 'INTERRUMPIDO=true; exit 130' INT TERM HUP»
    for senal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(senal, senal_recibida)
    try:
        codigo = ejecutar_provision(o, argv)
    except NoImplementado:
        return no_implementado("provision")
    except FinProvision as e:
        return e.codigo
    except ErrorProvision as e:
        print("ERROR [%d] %s" % (e.codigo, e.mensaje), file=sys.stderr)
        al_salir(o, e.codigo)
        return e.codigo
    except FalloInesperado as e:
        al_salir(o, e.codigo, inesperado=True)
        return e.codigo
    except (Interrumpido, KeyboardInterrupt):
        al_salir(o, 130, interrumpido=True)
        return 130
    except Exception as e:   # un error de programación: se deshace igual
        print("(%s: %s)" % (type(e).__name__, e), file=sys.stderr)
        al_salir(o, 1, inesperado=True)
        return 1
    return codigo


def ejecutar_provision(o, argv):
    """El flujo de main() en ci-provision.sh. Devuelve el código de salida."""
    # Sin argumentos y desde una terminal: el asistente con menús
    if not argv and sys.stdin.isatty() and sys.stdout.isatty() and shutil.which("whiptail"):
        argv = ["--menu"]
    analizar_opciones(o, argv)
    validar_opciones(o)
    calcular_derivados(o)
    validar_entorno(o)
    if o.menu:
        asistente(o)
    elif o.listar:
        listar_maquinas(o)
    elif o.eliminar:
        eliminar_maquinas(o, o.nombres)
    elif o.eliminar_todo:
        eliminar_todo(o)
    elif o.cluster:
        ejecutar_cluster(o)
    else:
        ejecutar_maquina(o)
    return 0
