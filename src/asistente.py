# --- provision: el asistente con menús (--menu, o sin argumentos desde una terminal)
#
# Para quien no se sabe las opciones: unas pantallas (pantallas.py) construyen
# el comando equivalente, lo enseñan y lo ejecutan. Toda la lógica sigue en el
# mismo sitio: el asistente solo elige los argumentos, enseña el comando
# equivalente y lo lanza en otro proceso.
#
# Cada caso es una serie de pasos: «Siguiente» avanza, «Atrás» vuelve al paso
# anterior (con lo que ya se había escrito) y, desde el primero, al menú
# principal. Ctrl+C sale del asistente.

SIGUIENTE = "<siguiente>"
REPETIR = "<repetir>"
OMITIR = "<omitir>"
ANCHO_LISTA = 72


def opciones_maquina():
    return [("extra-disks", "Seis discos extra vdb..vdg de %s" % TAM_DISCO_EXTRA),
            ("ssh-pass", "Contraseña para administrador y SSH por contraseña"),
            ("no-root", "No habilitar al usuario root"),
            ("no-virt-viewer", "Sin consola gráfica (virt-viewer)"),
            ("limpiar", "Eliminar antes lo que ya exista con esos nombres")]


def opciones_cluster():
    return [("limpiar", "Eliminar antes los nodos y la imagen base si ya existen"),
            ("discos-crea-entorno", "%d discos por nodo (vdb..vdh), como crea-entorno.sh"
             % len(UNIDADES_POSIBLES_NODO)),
            ("ssh-pass", "Contraseña para administrador y SSH por contraseña"),
            ("no-root", "No habilitar al usuario root"),
            ("no-virt-viewer", "Sin consola gráfica (virt-viewer)")]


IMAGENES_MAQUINA = (
    ("noble", "Ubuntu 24.04 (la imagen por defecto)"),
    ("debian12", "Debian 12"),
)
IMAGENES_GLUSTER = (
    ("noble", "Imagen cloud de Ubuntu 24.04, la misma que SERVER1 (recomendada)"),
    ("ubuntu-base", "ubuntu-base.qcow2 del boletín 1, como la construcción manual"),
    ("debian12", "Imagen cloud de Debian 12"),
)


def red_del_usuario(o):
    """La red virtual del usuario (RedIPv4), o None si no se encuentra: el
    asistente sigue sin ella (ya lo dirá el programa al ejecutar)."""
    try:
        return cargar_red(detectar_red(o))
    except ErrorProvision:
        return None


def ip_sugerida(red, n=None):
    """La IP que se propone: la .N si se puede asignar (la .2 de SERVER1), y si
    no, la primera libre de la red. "" si no hay red o no queda ninguna."""
    if red is None:
        return ""
    if n is not None and red.asignable(red.red_entera + n):
        return entero_a_ip(red.red_entera + n)
    primera = red.primer_hueco(1)
    return entero_a_ip(red.red_entera + primera) if primera is not None else ""


def problema_de_la_ip(o, red, ip, maquina):
    """Por qué no vale esta IP fija (el mismo mensaje que daría provision al
    ejecutarse), o None si vale: dentro de la red y fuera del DHCP y de las
    reservas, y que no la tenga otra máquina suya ni responda nada en ella."""
    class Datos:
        pass
    d = Datos()
    d.__dict__.update(vars(o))
    d.red, d.cluster, d.obj_dominios = red, False, []
    try:
        validar_ip_fija(d, ip)
        comprobar_ip_en_uso(d, ip, "%s-%s" % (o.prefijo_dominio, maquina))
    except ErrorProvision as e:
        return e.mensaje.replace("También puedes omitir el parámetro IP para que la máquina use "
                                 "DHCP.", "También puedes volver atrás y elegir DHCP.")
    return None


def salir_asistente():
    print("Sin cambios.")
    raise FinProvision(0)


def recorrer(pasos):
    """Los pasos de un caso, cada uno una función que devuelve SIGUIENTE, ATRAS,
    REPETIR (el mismo paso otra vez), OMITIR (no hace falta: se pasa en el
    sentido en que se iba) o SALIR. True si se llega al final; False si se
    vuelve atrás desde el primero."""
    i, adelante = 0, True
    while 0 <= i < len(pasos):
        r = pasos[i]()
        if r == SALIR:
            salir_asistente()
        elif r == ATRAS:
            i, adelante = i - 1, False
        elif r == OMITIR:
            i += 1 if adelante else -1
        elif r != REPETIR:
            i, adelante = i + 1, True
    return i >= len(pasos)


class Asistente:
    """Lo que el asistente recuerda entre pantallas."""

    def __init__(self, o, pantallas=None):
        self.o = o
        self.p = pantallas or pantallas_del_asistente()
        self.pass_asistente = ""   # la contraseña elegida, para el proceso hijo

    def ejecutar(self):
        ultima = None
        while True:
            sel = self.p.menu(
                "¿Qué quieres hacer?",
                [("basica", "Crear una máquina (Ubuntu 24.04 o Debian 12)"),
                 ("extra", "Crear SERVER1 del boletín 2: IP .2 y 6 discos extra (2.1)"),
                 ("cluster", "Crear la infraestructura GlusterFS (boletín 2, 2.4)"),
                 ("base", "Crear solo la imagen base GlusterFS"),
                 ("listar", "Ver mis máquinas virtuales y los discos del silo"),
                 ("eliminar", "Eliminar máquinas virtuales (con sus discos)"),
                 ("todo", "Eliminar todas mis máquinas virtuales (con sus discos)"),
                 ("salir", "Salir")],
                inicial=ultima, atras="Salir", seguir="Aceptar")
            if sel in (ATRAS, SALIR, "salir"):
                salir_asistente()
            ultima = sel
            if sel in ("basica", "extra", "cluster", "base") and not self.clave_lista():
                continue
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
                recorrer([lambda: self.lanzar(["--eliminar-todo"])])

    def clave_lista(self):
        """Antes de las pantallas de crear algo: sin una clave pública válida,
        provision fallaría con el error 31 al final, con todo ya rellenado. Ver
        y eliminar máquinas no la necesitan."""
        try:
            comprobar_clave_publica(self.o)
        except ErrorProvision as e:
            self.p.aviso(e.mensaje + "\n\nCuando la tengas, vuelve a elegir esta opción.")
            return False
        return True

    # --- Pasos comunes ---

    def paso_nombre(self, s, pregunta):
        def paso():
            r = self.p.texto(pregunta, s["nombre"])
            if r == ATRAS:
                self.conservar(s, "nombre")
            if r in (ATRAS, SALIR):
                return r
            r = r.strip()
            if not self.nombre_valido(r):
                return REPETIR
            s["nombre"] = r
            return SIGUIENTE
        return paso

    def paso_imagen(self, s, imagenes, texto):
        def paso():
            if s.get("usar_base"):
                return OMITIR
            r = self.p.elegir_uno(texto, list(imagenes), s["imagen"])
            if r in (ATRAS, SALIR):
                return r
            s["imagen"] = r
            return SIGUIENTE
        return paso

    def paso_opciones(self, s, opciones):
        def paso():
            r = self.p.elegir_varios("Opciones (márcalas con Espacio o con el ratón):",
                                     list(opciones), s["opciones"])
            if r in (ATRAS, SALIR):
                return r
            s["opciones"] = r
            return SIGUIENTE
        return paso

    def paso_contrasena(self, s):
        """Solo si se ha marcado ssh-pass. La contraseña no va en la orden
        (cualquier usuario del servidor la vería con 'ps'): se le pasa al proceso
        hijo, y la orden lleva «--ssh-pass -»."""
        def paso():
            if "ssh-pass" not in s["opciones"]:
                return OMITIR
            r = self.p.texto("Contraseña para administrador (solo letras sin tilde, números y "
                             "signos básicos):", s["contrasena"], oculto=True)
            if r in (ATRAS, SALIR):
                return r
            if not r:
                self.p.aviso("Escribe una contraseña, o vuelve atrás y desmarca la opción.")
                return REPETIR
            s["contrasena"] = r
            return SIGUIENTE
        return paso

    def conservar(self, s, clave):
        """Al volver atrás desde un campo, lo que tenía escrito se guarda: al
        volver a ese paso, sigue ahí."""
        escrito = getattr(self.p, "texto_al_volver", None)
        if escrito is not None:
            s[clave] = escrito.strip()

    def nombre_valido(self, nombre):
        """Nombre corto válido; si no lo es, lo dice (un nombre que empezara por
        '-' se tomaría además por una opción)."""
        if re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?", nombre) and len(nombre) <= 63:
            return True
        self.p.aviso("El nombre '%s' no es válido: solo letras, números y guiones, empezando "
                     "por letra o número (p.ej. server1)." % nombre)
        return False

    @staticmethod
    def argumentos_de(s, imagen_defecto):
        """Las opciones elegidas, como argumentos de provision."""
        argumentos = []
        if s.get("imagen") and s["imagen"] != imagen_defecto and not s.get("usar_base"):
            argumentos += ["--imagen", s["imagen"]]
        for opcion in s.get("opciones", []):
            if opcion == "ssh-pass":
                argumentos += ["--ssh-pass", "-"]
            elif opcion == "discos-crea-entorno":
                argumentos += ["--discos-nodo", str(len(UNIDADES_POSIBLES_NODO))]
            else:
                argumentos.append("--" + opcion)
        return argumentos

    # --- Cada entrada del menú ---

    def maquina(self, modo):
        """basica | extra (IP .2 sugerida y discos extra marcados)."""
        o = self.o
        s = {"nombre": "server1", "red": "fija" if modo == "extra" else "dhcp", "ip": None,
             "imagen": IMAGEN_DEFECTO, "opciones": ["extra-disks"] if modo == "extra" else [],
             "contrasena": ""}

        def paso_red():
            r = self.p.elegir_uno("Red de la máquina:",
                                  [("dhcp", "DHCP (la red le da una IP)"),
                                   ("fija", "IP fija")], s["red"])
            if r in (ATRAS, SALIR):
                return r
            s["red"] = r
            return SIGUIENTE

        def paso_ip():
            """Solo con IP fija: las libres de su red y, en el campo, la primera
            (la .2 en SERVER1); si la escrita no vale, se dice aquí mismo."""
            if s["red"] != "fija":
                return OMITIR
            red = red_del_usuario(o)
            if s["ip"] is None:
                s["ip"] = ip_sugerida(red, 2 if modo == "extra" else None)
            texto = "IP fija de la máquina, dentro de tu red virtual."
            if red is not None:
                texto += "\nIPs libres de tu red:\n" + "\n".join(red.bloques_libres())
            r = self.p.texto(texto, s["ip"])
            if r == ATRAS:
                self.conservar(s, "ip")
            if r in (ATRAS, SALIR):
                return r
            s["ip"] = r.strip()
            if not s["ip"]:
                self.p.aviso("Escribe una IP, o vuelve atrás y elige DHCP.")
                return REPETIR
            problema = problema_de_la_ip(o, red, s["ip"], s["nombre"]) if red else None
            if problema:
                self.p.aviso(problema)
                return REPETIR
            return SIGUIENTE

        def paso_lanzar():
            argumentos = self.argumentos_de(s, IMAGEN_DEFECTO) + [s["nombre"]]
            if s["red"] == "fija" and s["ip"]:
                argumentos.append(s["ip"])
            return self.lanzar(argumentos, s["contrasena"] if "ssh-pass" in s["opciones"] else "")

        recorrer([
            self.paso_nombre(s, "Nombre corto de la máquina (letras, números y guiones).\n"
                                "El dominio será %s-NOMBRE y el disco NOMBRE.qcow2."
                                % o.prefijo_dominio),
            paso_red,
            paso_ip,
            self.paso_imagen(s, IMAGENES_MAQUINA, "Sistema de la máquina:"),
            self.paso_opciones(s, opciones_maquina()),
            self.paso_contrasena(s),
            paso_lanzar,
        ])

    def cluster(self):
        o = self.o
        base = disco_base_cluster(o)
        hay_base = os.path.isfile(base)
        s = {"usar_base": hay_base, "imagen": IMAGEN_DEFECTO_GLUSTER, "opciones": [],
             "contrasena": ""}

        def paso_base():
            if not hay_base:
                return OMITIR
            r = self.p.elegir_uno("Ya tienes %s en el silo." % os.path.basename(base),
                                  [("usar", "Usarla como imagen base, sin volver a construirla"),
                                   ("nueva", "Construir la imagen base de nuevo")],
                                  "usar" if s["usar_base"] else "nueva")
            if r in (ATRAS, SALIR):
                return r
            s["usar_base"] = r == "usar"
            return SIGUIENTE

        def paso_lanzar():
            argumentos = ["--gluster-cluster"]
            if s["usar_base"]:
                argumentos += ["--base", os.path.basename(base)]
            argumentos += self.argumentos_de(s, IMAGEN_DEFECTO_GLUSTER)
            return self.lanzar(argumentos, s["contrasena"] if "ssh-pass" in s["opciones"] else "")

        recorrer([
            paso_base,
            self.paso_imagen(s, IMAGENES_GLUSTER, "¿De qué imagen sale la base GlusterFS?"),
            self.paso_opciones(s, opciones_cluster()),
            self.paso_contrasena(s),
            paso_lanzar,
        ])

    def base(self):
        s = {"nombre": CLUSTER_BASE, "imagen": IMAGEN_DEFECTO_GLUSTER, "opciones": []}

        def paso_lanzar():
            argumentos = ["--glusterfs"] + self.argumentos_de(s, IMAGEN_DEFECTO_GLUSTER)
            return self.lanzar(argumentos + [s["nombre"]])

        recorrer([
            self.paso_nombre(s, "Nombre de la imagen base.\nQuedará NOMBRE.qcow2 en el silo, "
                                "sin máquina, lista para hacer copias."),
            self.paso_imagen(s, IMAGENES_GLUSTER, "¿De qué imagen sale la base GlusterFS?"),
            self.paso_opciones(s, [("limpiar", "Eliminar antes la máquina o el disco que ya se "
                                               "llamen así")]),
            paso_lanzar,
        ])

    def filas_de_la_lista(self):
        """[(clave, fila)] de «Ver mis máquinas»: m:DOMINIO o d:RUTA, con filas que
        caben en el cuadro."""
        o = self.o
        filas = []
        for d in dominios_propios(o):
            estado = estado_dominio(d)
            ip = ip_dominio(d) if estado == "en ejecución" else "-"
            n = len(discos_de_dominio(o, d))
            filas.append(("m:" + d, "%s %s %s %d disco(s)" % (
                rellenar(d[len(o.prefijo_dominio) + 1:], 16), rellenar(estado, 12),
                rellenar(ip, 15), n)))
        for f in discos_sin_maquina(o):
            if imagen_protegida(o, f):
                # La explicación entera («no la borres»), en su ficha
                sistema = "Debian 12" if f.endswith("/" + IMAGEN_DEBIAN) else "Ubuntu 24.04"
                fila = "%s  [imagen cloud] %s" % (os.path.basename(f), sistema)
            else:
                fila = "%s  [sin máquina] %s" % (os.path.basename(f),
                                                 descripcion_disco_suelto(o, f))
            filas.append(("d:" + f, fila))
        return [(clave, recortar(fila, ANCHO_LISTA)) for clave, fila in filas]

    def listar(self):
        """Lista de máquinas y discos sueltos; al elegir uno se abre su ficha."""
        o = self.o
        # Las imágenes base se vuelven a leer cada vez: tras crear o eliminar
        # algo desde el asistente, la lista tiene que verlo
        o.respaldos = None
        cargar_respaldos(o)
        filas = self.filas_de_la_lista()
        if not filas:
            self.p.aviso("No tienes máquinas ni discos en el silo.")
            return
        ultima = None
        while True:
            sel = self.p.menu("Tus máquinas virtuales y los discos del silo. Elige una para ver "
                              "su ficha.", filas, inicial=ultima, atras="Volver", seguir="Ver ficha")
            if sel == SALIR:
                salir_asistente()
            if sel == ATRAS:
                return
            ultima = sel
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
        discos = discos_de_dominio(o, d)
        if not discos:
            texto += " (ninguno en el silo)"
        for f in discos:
            respaldo = respaldo_de(o, f)
            texto += "\n          %s%s" % (os.path.basename(f),
                                           " (copia de %s)" % respaldo if respaldo else "")
        if ip != "-":
            texto += "\nAcceso  : ssh administrador@%s" % ip
        texto += "\nConsola : virsh console %s" % d
        texto += "\n\nPara eliminarla con sus discos:\n  %s %s--eliminar %s" % (
            orden_provision(), prefijo_en_orden(o), corto)
        self.p.aviso(texto, boton="Volver")

    def ficha_disco(self, f):
        vs = tam_virtual(f)
        texto = "Disco   : %s\nRuta    : %s" % (os.path.basename(f), f)
        if re.fullmatch(r"[0-9]+", vs):
            texto += "\nTamaño  : %d GiB (virtual)" % bytes_a_gib(int(vs))
        texto += "\nQué es  : %s" % descripcion_disco_suelto(self.o, f)
        self.p.aviso(texto, boton="Volver")

    def eliminar(self):
        o = self.o
        maquinas = [(d[len(o.prefijo_dominio) + 1:], estado_dominio(d))
                    for d in dominios_propios(o)]
        if not maquinas:
            self.p.aviso("No tienes máquinas (dominios %s-*). Los discos sueltos del silo se "
                         "ven en «Ver mis máquinas virtuales» y se eliminan con «Eliminar todas "
                         "mis máquinas virtuales»." % o.prefijo_dominio)
            return
        s = {"nombres": []}

        def paso_elegir():
            r = self.p.elegir_varios("Marca las máquinas a eliminar (con sus discos y sus "
                                     "ficheros cloud-init):",
                                     [(n, "%s  (%s)" % (n, e)) for n, e in maquinas], s["nombres"])
            if r in (ATRAS, SALIR):
                return r
            if not r:
                self.p.aviso("No has marcado ninguna máquina.")
                return REPETIR
            s["nombres"] = r
            return SIGUIENTE

        recorrer([paso_elegir, lambda: self.lanzar(["--eliminar"] + s["nombres"])])

    # --- Ejecución del comando elegido ---

    def lanzar(self, argumentos, contrasena=""):
        """Enseña el comando equivalente, pide confirmación y lo ejecuta en un
        proceso aparte (este mismo programa con esos argumentos). Devuelve ATRAS
        o SALIR si no se confirma; SIGUIENTE, una vez ejecutado."""
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

        r = self.p.confirmar("Se va a ejecutar:\n\n%s\n\n¿Adelante?" % mostrar)
        if r is not True:
            return r

        sys.stdout.flush()
        try:
            subprocess.call(["clear"], stderr=subprocess.DEVNULL)
        except OSError:
            pass
        print("→ %s" % mostrar)
        print()
        entorno = dict(os.environ)
        if contrasena:
            entorno["CI_PROVISION_SSH_PASS"] = contrasena
        # Ctrl+C lo atiende el proceso hijo, que deshace lo suyo; aquí no hace
        # nada. Con un manejador que no hace nada y no con SIG_IGN, que el hijo
        # heredaría: con la señal ignorada, el hijo no podría atrapar Ctrl+C y
        # la creación lanzada desde el menú no se podría parar.
        anterior_int = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            codigo = subprocess.call([sys.executable, ruta_del_programa(), "provision"] + argumentos,
                                     env=entorno)
        finally:
            signal.signal(signal.SIGINT, anterior_int)
        if codigo < 0:
            codigo = 128 - codigo
        print()
        if codigo != 0:
            print("(el comando ha terminado con el código %d)" % codigo)
        pausa()
        return SIGUIENTE


def pausa():
    """«Pulsa Enter…»: el texto por la salida de errores, solo si la entrada es
    una terminal; se lee byte a byte, para no quitarle al siguiente proceso lo
    que venga después en la entrada."""
    if sys.stdin.isatty():
        sys.stderr.write("Pulsa Enter para volver al menú… ")
        sys.stderr.flush()
    try:
        while os.read(0, 1) not in (b"", b"\n"):
            pass
    except OSError:
        pass


def asistente(o):
    if not os.environ.get("SSOO_US_ASISTENTE_GUION") and not prompt_toolkit_disponible():
        fallar(38, "El asistente (--menu) necesita el módulo prompt_toolkit de Python (el paquete "
                   "python3-prompt-toolkit),\nque no está en este equipo (en los servidores de la "
                   "asignatura sí está). Usa las opciones\nde la línea de comandos: %s -h"
                   % orden_provision())
    Asistente(o).ejecutar()
