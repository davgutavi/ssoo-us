# --- provision: el asistente con menús (--menu, o sin argumentos desde una terminal)
#
# Para quien no se sabe las opciones: unos diálogos de whiptail (el programa de
# menús de texto que trae Ubuntu) construyen el comando equivalente, lo enseñan y
# lo ejecutan. Toda la lógica sigue en el mismo sitio: el asistente solo elige
# los argumentos, enseña el comando equivalente y lo lanza en otro proceso.

# Colores de los diálogos: la paleta clásica de newt (fondo azul, ventanas
# grises). Si el usuario tiene NEWT_COLORS definida, se respeta la suya.
PALETA_ASISTENTE = """
root=white,blue
roottext=white,blue
helpline=white,blue
window=black,lightgray
border=black,lightgray
shadow=black,black
title=blue,lightgray
textbox=black,lightgray
label=black,lightgray
listbox=black,lightgray
actlistbox=white,blue
sellistbox=black,cyan
actsellistbox=white,blue
checkbox=black,lightgray
actcheckbox=white,blue
entry=black,cyan
button=black,cyan
actbutton=white,blue
compactbutton=black,lightgray
"""


def locale_utf8():
    """Los diálogos de whiptail necesitan una locale UTF-8 (si no, cortan los
    textos en la primera tilde): la del usuario si lo es, o C.UTF-8."""
    loc = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    if "utf-8" in loc.lower() or "utf8" in loc.lower():
        return loc
    return "C.UTF-8"


def wt(*argumentos):
    """whiptail con estos argumentos: (código, selección). Código 0 aceptar, 1
    cancelar, 255 Esc. whiptail dibuja por su salida estándar (aquí, la de
    errores, que es la terminal) y escribe la selección por la de errores."""
    entorno = dict(os.environ, NEWT_COLORS=os.environ.get("NEWT_COLORS") or PALETA_ASISTENTE,
                   LC_ALL=locale_utf8())
    sys.stdout.flush()
    sys.stderr.flush()
    p = subprocess.run(["whiptail", "--title", "%s %s" % (PROGRAMA, VERSION)]
                       + [str(a) for a in argumentos],
                       stdout=sys.stderr.fileno(), stderr=subprocess.PIPE, env=entorno)
    # Como $(...): sin los saltos de línea del final
    return p.returncode, p.stderr.decode("utf-8", "replace").rstrip("\n")


def wt_aviso(*argumentos):
    """whiptail fuera de $(...) en ci-provision.sh (--msgbox, --yesno): lo que
    devuelva va a la salida. True si se ha aceptado."""
    codigo, salida = wt(*argumentos)
    if salida:
        sys.stdout.write(salida)
    return codigo == 0


def etiquetas(salida):
    """La salida de un --checklist («"a" "b"») → etiquetas sueltas."""
    return salida.replace('"', "").split()


def ips_libres_texto(o):
    """IPs libres de la red del usuario, para mostrarlas. Si la red no se
    encuentra, el asistente sigue (ya lo dirá el programa al ejecutar)."""
    try:
        return "\n".join(cargar_red(detectar_red(o)).bloques_libres())
    except ErrorProvision:
        return ""


def ip_de_la_red(o, n):
    """La IP número N de la red del usuario (la .2 de SERVER1), o ""."""
    try:
        return entero_a_ip(cargar_red(detectar_red(o)).red_entera + n)
    except ErrorProvision:
        return ""


def salir_asistente():
    print("Sin cambios.")
    raise FinProvision(0)


class Asistente:
    """Lo que el asistente recuerda entre diálogos."""

    def __init__(self, o):
        self.o = o
        self.pass_asistente = ""   # la contraseña elegida, para el proceso hijo
        self.opciones_args = []
        self.imagen_args = []

    def ejecutar(self):
        while True:
            codigo, sel = wt("--notags", "--menu",
                             "¿Qué quieres hacer?\n(muévete con las flechas y elige con Enter)",
                             20, 78, 8,
                             "basica", "Crear una máquina básica (boletín 1; Debian 12 propuesta)",
                             "extra", "Crear una máquina con IP .2 y 6 discos extra (boletín 2, "
                                      "epígrafe 2.1)",
                             "cluster", "Crear la infraestructura GlusterFS (boletín 2, epígrafe 2.4)",
                             "base", "Crear solo la imagen base GlusterFS",
                             "listar", "Mostrar mis máquinas virtuales",
                             "eliminar", "Eliminar una máquina virtual (y su almacenamiento)",
                             "todo", "Eliminar todas mis máquinas virtuales (y su almacenamiento)",
                             "salir", "Salir")
            if codigo != 0:
                salir_asistente()
            if sel in ("basica", "extra"):
                self.maquina(sel)
            elif sel == "cluster":
                self.cluster()
            elif sel == "base":
                self.base()
            elif sel == "listar":
                self.listar()
            elif sel == "eliminar":
                self.eliminar()
            elif sel == "todo":
                self.lanzar(["--eliminar-todo"])
            else:
                salir_asistente()

    # --- Piezas comunes ---

    def opciones_a_argumentos(self, salida):
        """Opciones marcadas en un checklist → argumentos (la contraseña se pide
        aparte). False si se cancela. La contraseña no va en los argumentos
        (cualquier usuario del servidor la vería con 'ps'): se guarda para el
        hijo y la orden lleva «--ssh-pass -»."""
        self.opciones_args, self.pass_asistente = [], ""
        for opcion in etiquetas(salida):
            if opcion == "ssh-pass":
                codigo, contrasena = wt("--passwordbox",
                                        "Contraseña para administrador\n(solo letras sin tilde, "
                                        "números y signos básicos):", 10, 70)
                if codigo != 0 or not contrasena:
                    return False
                self.pass_asistente = contrasena
                self.opciones_args += ["--ssh-pass", "-"]
            elif opcion == "discos-crea-entorno":
                self.opciones_args += ["--discos-nodo", str(len(UNIDADES_POSIBLES_NODO))]
            else:
                self.opciones_args.append("--" + opcion)
        return True

    def elegir_imagen_maquina(self, preseleccionada):
        """Imagen de una máquina suelta: deja --imagen en imagen_args (nada si es
        la de por defecto). False si se cancela."""
        def marca(opcion):
            return "on" if opcion == preseleccionada else "off"
        self.imagen_args = []
        codigo, img = wt("--notags", "--radiolist",
                         "Sistema de la máquina (marca con la barra espaciadora):", 11, 76, 2,
                         "noble", "Ubuntu 24.04 (boletín 2)", marca("noble"),
                         "debian12", "Debian 12 (boletín 1)", marca("debian12"))
        if codigo != 0:
            return False
        if img and img != IMAGEN_DEFECTO:
            self.imagen_args = ["--imagen", img]
        return True

    def elegir_imagen_gluster(self):
        """De qué imagen sale la base GlusterFS (mismo convenio que la anterior)."""
        self.imagen_args = []
        codigo, img = wt("--notags", "--radiolist",
                         "¿De qué imagen sale la base GlusterFS?\n(marca con la barra espaciadora)",
                         13, 78, 3,
                         "noble", "Imagen cloud de Ubuntu 24.04, la misma que SERVER1 (recomendada)",
                         "on",
                         "ubuntu-base", "ubuntu-base.qcow2 del boletín 1, como la construcción manual",
                         "off",
                         "debian12", "Imagen cloud de Debian 12", "off")
        if codigo != 0:
            return False
        if img and img != IMAGEN_DEFECTO_GLUSTER:
            self.imagen_args = ["--imagen", img]
        return True

    @staticmethod
    def nombre_valido(nombre):
        """Nombre corto válido; si no lo es, lo dice (un nombre que empezara por
        '-' se tomaría además por una opción)."""
        if re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?", nombre) and len(nombre) <= 63:
            return True
        wt_aviso("--msgbox", "El nombre '%s' no es válido: solo letras, números y guiones, "
                             "empezando\npor letra o número (p.ej. server1)." % nombre, 9, 72)
        return False

    # --- Cada entrada del menú ---

    def maquina(self, modo):
        """basica | extra (IP .2 sugerida y discos extra marcados)."""
        o = self.o
        codigo, nombre = wt("--inputbox", "Nombre corto de la máquina (letras, números y "
                                          "guiones).\nEl dominio será %s-NOMBRE y el disco "
                                          "NOMBRE.qcow2." % o.prefijo_dominio, 11, 70, "server1")
        if codigo != 0 or not nombre or not self.nombre_valido(nombre):
            return

        sugerida = ip_de_la_red(o, 2) if modo == "extra" else ""
        libres = ips_libres_texto(o)
        texto = "IP fija dentro de tu red virtual. Déjala vacía para usar DHCP."
        if libres:
            texto += "\nIPs libres de tu red:\n" + libres
        codigo, ip = wt("--inputbox", texto, 16, 70, sugerida)
        if codigo != 0:
            return

        # El boletín 1 usa Debian 12; el 2, Ubuntu 24.04
        if not self.elegir_imagen_maquina("debian12" if modo == "basica" else "noble"):
            return

        marcado = "on" if modo == "extra" else "off"
        codigo, sel = wt("--checklist", "Opciones (marca con la barra espaciadora):", 16, 76, 5,
                         "extra-disks", "Seis discos extra vdb..vdg de %s" % TAM_DISCO_EXTRA, marcado,
                         "ssh-pass", "Contraseña para administrador y SSH por contraseña", "off",
                         "no-root", "No habilitar al usuario root", "off",
                         "no-virt-viewer", "Sin consola gráfica (virt-viewer)", "off",
                         "limpiar", "Eliminar antes lo que ya exista con esos nombres", "off")
        if codigo != 0 or not self.opciones_a_argumentos(sel):
            return

        argumentos = self.imagen_args + self.opciones_args + [nombre]
        if ip:
            argumentos.append(ip)
        self.lanzar(argumentos)

    def cluster(self):
        o = self.o
        argumentos = ["--gluster-cluster"]
        usar_base = False
        base = disco_base_cluster(o)
        if os.path.isfile(base):
            if wt_aviso("--yesno", "Ya tienes %s en el silo.\n¿Quieres usarla como imagen base, "
                                   "sin volver a construirla?" % os.path.basename(base), 10, 70):
                argumentos += ["--base", os.path.basename(base)]
                usar_base = True
        if not usar_base:
            if not self.elegir_imagen_gluster():
                return
            argumentos += self.imagen_args

        codigo, sel = wt("--checklist", "Opciones (marca con la barra espaciadora):", 15, 78, 5,
                         "limpiar", "Eliminar antes los nodos y la imagen base si ya existen", "off",
                         "discos-crea-entorno", "%d discos por nodo (vdb..vdh), como crea-entorno.sh"
                         % len(UNIDADES_POSIBLES_NODO), "off",
                         "ssh-pass", "Contraseña para administrador y SSH por contraseña", "off",
                         "no-root", "No habilitar al usuario root", "off",
                         "no-virt-viewer", "Sin consola gráfica (virt-viewer)", "off")
        if codigo != 0 or not self.opciones_a_argumentos(sel):
            return
        self.lanzar(argumentos + self.opciones_args)

    def base(self):
        codigo, nombre = wt("--inputbox", "Nombre de la imagen base.\nQuedará NOMBRE.qcow2 en el "
                                          "silo, sin máquina, lista para hacer copias.", 11, 70,
                            CLUSTER_BASE)
        if codigo != 0 or not nombre or not self.nombre_valido(nombre):
            return
        if not self.elegir_imagen_gluster():
            return
        argumentos = ["--glusterfs"] + self.imagen_args
        if wt_aviso("--defaultno", "--yesno", "Si ya existe una máquina o un disco con ese "
                                              "nombre,\n¿eliminarlos antes (--limpiar)?", 9, 70):
            argumentos.append("--limpiar")
        self.lanzar(argumentos + [nombre])

    def listar(self):
        """Lista de máquinas y discos sueltos; al elegir uno se abre su ficha."""
        o = self.o
        # Las imágenes base se vuelven a leer cada vez: tras crear o eliminar
        # algo desde el asistente, la lista tiene que verlo (ci-provision lo
        # corrigió en la 3.0.3)
        o.respaldos = None
        cargar_respaldos(o)

        items = []
        for d in dominios_propios(o):
            estado = estado_dominio(d)
            ip = ip_dominio(d) if estado == "en ejecución" else "-"
            n = len(discos_de_dominio(o, d))
            items += ["m:" + d, "%s %s %s %d disco(s)" % (
                rellenar(d[len(o.prefijo_dominio) + 1:], 14), rellenar(estado, 12),
                rellenar(ip, 15), n)]
        for f in discos_sin_maquina(o):
            tipo = "imagen cloud" if imagen_protegida(o, f) else "sin máquina"
            items += ["d:" + f, "%s %s %s" % (rellenar(os.path.basename(f), 14), rellenar(tipo, 12),
                                              descripcion_disco_suelto(o, f))]

        if not items:
            wt_aviso("--msgbox", "No tienes máquinas ni discos en el silo.", 8, 60)
            return

        while True:
            codigo, sel = wt("--notags", "--menu", "Mis máquinas virtuales y los discos del "
                                                   "silo.\nElige una entrada para ver su ficha; "
                                                   "Cancelar para volver.", 22, 78, 12, *items)
            if codigo != 0:
                return
            if sel.startswith("m:"):
                self.ficha_maquina(sel[2:])
            elif sel.startswith("d:"):
                self.ficha_disco(sel[2:])

    def ficha_maquina(self, d):
        o = self.o
        corto = d[len(o.prefijo_dominio) + 1:] if d.startswith(o.prefijo_dominio + "-") else d
        estado = estado_dominio(d)
        ip = ip_dominio(d) if estado == "en ejecución" else "-"
        texto = ("Máquina : %s   (hostname: %s)\nEstado  : %s\nIP      : %s\nDiscos  :"
                 % (d, corto, estado, ip))
        n = 4
        discos = discos_de_dominio(o, d)
        if not discos:
            texto += " (ninguno en el silo)"
        for f in discos:
            respaldo = respaldo_de(o, f)
            texto += "\n          %s%s" % (os.path.basename(f),
                                           " (copia de %s)" % respaldo if respaldo else "")
            n += 1
        if ip != "-":
            texto += "\nAcceso  : ssh administrador@%s" % ip
            n += 1
        texto += "\nConsola : virsh console %s" % d
        texto += "\n\nPara eliminarla con sus discos: %s %s--eliminar %s" % (
            orden_provision(), prefijo_en_orden(o), corto)
        n += 3
        wt_aviso("--msgbox", texto, n + 6, 78)

    def ficha_disco(self, f):
        vs = tam_virtual(f)
        texto = "Disco   : %s\nRuta    : %s" % (os.path.basename(f), f)
        if re.fullmatch(r"[0-9]+", vs):
            texto += "\nTamaño  : %d GiB (virtual)" % bytes_a_gib(int(vs))
        texto += "\nQué es  : %s" % descripcion_disco_suelto(self.o, f)
        wt_aviso("--msgbox", texto, 11, 78)

    def eliminar(self):
        o = self.o
        items = []
        for d in dominios_propios(o):
            items += [d[len(o.prefijo_dominio) + 1:], estado_dominio(d), "off"]
        if not items:
            wt_aviso("--msgbox", "No tienes máquinas (dominios %s-*).\nLos discos sueltos del silo "
                                 "se ven en \"Mostrar mis máquinas virtuales\"\ny se eliminan con "
                                 "\"Eliminar todas mis máquinas virtuales\"." % o.prefijo_dominio,
                     11, 76)
            return
        codigo, sel = wt("--checklist", "Marca las máquinas a eliminar (con sus discos y sus "
                                        "ficheros cloud-init):", 18, 72, 8, *items)
        if codigo != 0:
            return
        nombres = etiquetas(sel)
        if nombres:
            self.lanzar(["--eliminar"] + nombres)

    # --- Ejecución del comando elegido ---

    def lanzar(self, argumentos):
        """Enseña el comando equivalente, pide confirmación y lo ejecuta en un
        proceso aparte (este mismo programa con esos argumentos)."""
        o = self.o
        if o.prefijo_opt:
            argumentos = ["--prefijo", o.prefijo_opt] + argumentos
        # Con --menu --dry-run, todo lo que se lance es también una simulación;
        # con --menu --si, sin preguntas
        if o.si:
            argumentos = ["--si"] + argumentos
        if o.dry_run:
            argumentos = ["--dry-run"] + argumentos

        mostrar, anterior = orden_provision(), ""
        for a in argumentos:
            mostrar += " ••••••" if anterior == "--ssh-pass" else " " + a
            anterior = a

        if not wt_aviso("--yesno", "Se va a ejecutar:\n\n  %s\n\n¿Adelante?" % mostrar, 12, 76):
            return

        sys.stdout.flush()
        try:
            subprocess.call(["clear"], stderr=subprocess.DEVNULL)
        except OSError:
            pass
        print("→ %s" % mostrar)
        print()
        entorno = dict(os.environ)
        if self.pass_asistente:
            entorno["CI_PROVISION_SSH_PASS"] = self.pass_asistente
        # Ctrl+C lo atiende el proceso hijo, que deshace lo suyo; aquí no hace
        # nada. Con un manejador que no hace nada y no con SIG_IGN, que el hijo
        # heredaría: con la señal ignorada, el hijo no podría atrapar Ctrl+C y
        # la creación lanzada desde el menú no se podría parar (como en
        # ci-provision hasta la 3.0.2, con «trap '' INT»; la 3.0.3 usa «trap ':' INT»).
        anterior_int = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            codigo = subprocess.call([sys.executable, ruta_del_programa(), "provision"] + argumentos,
                                     env=entorno)
        finally:
            signal.signal(signal.SIGINT, anterior_int)
        self.pass_asistente = ""
        if codigo < 0:
            codigo = 128 - codigo
        print()
        if codigo != 0:
            print("(el comando ha terminado con el código %d)" % codigo)
        pausa()


def pausa():
    """«read -r -p "Pulsa Enter…"»: el texto por la salida de errores, solo si la
    entrada es una terminal; se lee byte a byte, como bash, para no quitarle al
    siguiente proceso lo que venga después en la entrada."""
    if sys.stdin.isatty():
        sys.stderr.write("Pulsa Enter para volver al menú… ")
        sys.stderr.flush()
    try:
        while os.read(0, 1) not in (b"", b"\n"):
            pass
    except OSError:
        pass


def asistente(o):
    if not shutil.which("whiptail"):
        fallar(38, "El asistente (--menu) necesita el programa 'whiptail', que no está en este "
                   "equipo\n(en los servidores de la asignatura sí está). Usa las opciones de la "
                   "línea de comandos: %s -h" % orden_provision())
    Asistente(o).ejecutar()
