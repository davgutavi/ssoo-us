# --- acceso: por qué no puede entrar por ssh en su máquina (ssoo-us acceso) ------
#
# Para cualquier máquina suya (creada a mano, con ssoo-us provision o con
# ci-provision), encendida: su estado, su IP, el puerto 22, lo que dice ssh y,
# sin apagarla, qué clave tiene administrador (se lee por su agente QEMU, con
# las órdenes de leer archivos del agente: nada de guest-exec). Solo lee, como
# diagnosis: no cambia nada en la máquina ni en la cuenta.

USO_ACCESO = """\
Uso: ssoo-us acceso MAQUINA [--ip IP]

Dice por qué no puede entrar por ssh en una de sus máquinas virtuales (creada
a mano, con ssoo-us provision o con ci-provision) y cómo arreglarlo: si está
encendida, su IP, el puerto 22, lo que dice ssh y, sin apagarla, qué clave
tiene su usuario administrador.

  MAQUINA     la máquina: control2, server1, 1 o <uvus>-server1.
  --ip IP     la IP de la máquina, si no la encuentra sola.
  -h          muestra esta ayuda.
  --version   muestra la versión.

Solo lee: no cambia nada en la máquina ni en su cuenta, y no muestra nunca
su clave privada. Código de salida: 0 si no hay ningún ERROR, 1 si hay
alguno, 2 si no se ha podido hacer la revisión.
"""

FUENTE_LEASE = 0   # VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE
CLAVES_EN_LA_MAQUINA = "/home/%s/.ssh/authorized_keys" % USUARIO_VM
SIN_AGENTE = ("not responding", "not connected", "not configured", "agent is not",
              "Guest agent", "guest agent")


def analizar_argumentos_acceso(argv):
    opciones = {"maquina": None, "ip": None, "ayuda": False, "version": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help", "--ayuda"):
            opciones["ayuda"] = True
        elif a == "--version":
            opciones["version"] = True
        elif a == "--ip" or a.startswith("--ip="):
            if a == "--ip":
                i += 1
                if i == len(argv):
                    raise ErrorDeUso("falta la IP después de --ip.")
                valor = argv[i]
            else:
                valor = a[len("--ip="):]
            try:
                opciones["ip"] = ipaddress.ip_address(valor)
            except ValueError:
                raise ErrorDeUso("«%s» no es una dirección IP." % valor)
        elif a.startswith("-"):
            raise ErrorDeUso("opción desconocida: %s." % a)
        elif opciones["maquina"] is None:
            opciones["maquina"] = a
        else:
            raise ErrorDeUso("sobra «%s»: indique una sola máquina." % a)
        i += 1
    return opciones


def buscar_maquina_suya(conn, nombre, uvus):
    """El dominio que el alumno llama así: tal cual (con un prefijo propio,
    p.ej. demo-server1) o <uvus>-NOMBRE. None si no existe."""
    for candidato in (nombre, "%s-%s" % (uvus, normalizar_maquina(nombre, uvus))):
        dominio = buscar_dominio(conn, candidato)
        if dominio is not None:
            return dominio
    return None


# --- El agente QEMU ---------------------------------------------------------------

def preguntar_al_agente(dominio, orden, espera=5):
    """(respuesta, problema) de una orden al agente QEMU de la máquina."""
    argv = ["virsh", "-c", URI, "qemu-agent-command", dominio, "--timeout", str(espera),
            json.dumps(orden)]
    codigo, salida, err = ejecutar_lectura(argv, timeout=espera + 15)
    if codigo is None:
        return None, "virsh no ha terminado a tiempo"
    if codigo != 0:
        lineas = [l.strip() for l in err.splitlines() if l.strip()]
        return None, lineas[-1] if lineas else "virsh ha fallado (código %d)" % codigo
    try:
        return json.loads(salida).get("return"), None
    except (ValueError, AttributeError):
        return None, "el agente ha devuelto algo que no se entiende"


def sin_agente(problema):
    return any(s in (problema or "") for s in SIN_AGENTE)


def leer_por_agente(dominio, ruta):
    """(texto, problema) de un archivo de la máquina encendida, leído por su
    agente. problema es «no existe», «sin agente» u otro texto."""
    handle, problema = preguntar_al_agente(
        dominio, {"execute": "guest-file-open", "arguments": {"path": ruta, "mode": "r"}})
    if handle is None:
        if problema and "No such file" in problema:
            return None, "no existe"
        return None, "sin agente" if sin_agente(problema) else problema
    datos = b""
    try:
        while len(datos) < 4 * 1024 * 1024:     # authorized_keys es pequeño
            r, problema = preguntar_al_agente(
                dominio, {"execute": "guest-file-read",
                          "arguments": {"handle": handle, "count": 65536}})
            if r is None:
                return None, problema
            datos += base64.b64decode(r.get("buf-b64") or "")
            if r.get("eof") or not r.get("count"):
                break
    finally:
        preguntar_al_agente(dominio, {"execute": "guest-file-close",
                                      "arguments": {"handle": handle}})
    return datos.decode("utf-8", "replace"), None


def ip_por_agente(dominio):
    r, _ = preguntar_al_agente(dominio, {"execute": "guest-network-get-interfaces"})
    for interfaz in r or []:
        if interfaz.get("name") == "lo":
            continue
        for d in interfaz.get("ip-addresses") or []:
            if d.get("ip-address-type") == "ipv4":
                try:
                    return ipaddress.ip_address(d.get("ip-address"))
                except ValueError:
                    continue
    return None


def ip_por_lease(dominio):
    """IPv4 que el DHCP de su red le ha dado, o None."""
    try:
        datos = dominio.interfaceAddresses(FUENTE_LEASE, 0)
    except Exception:
        return None
    for interfaz in (datos or {}).values():
        for direccion in interfaz.get("addrs") or []:
            if direccion.get("type") == 0:
                try:
                    return ipaddress.ip_address(direccion.get("addr"))
                except ValueError:
                    continue
    return None


# --- Claves ----------------------------------------------------------------------

def claves_del_usuario(home):
    """[(archivo, ClavePublica)] de sus ~/.ssh/*.pub, con id_rsa.pub la primera."""
    directorio = os.path.join(home, ".ssh")
    try:
        nombres = sorted(n for n in os.listdir(directorio) if n.endswith(".pub"))
    except OSError:
        return []
    if "id_rsa.pub" in nombres:
        nombres.remove("id_rsa.pub")
        nombres.insert(0, "id_rsa.pub")
    claves = []
    for n in nombres:
        datos = leer_bytes(os.path.join(directorio, n))
        clave = analizar_clave_publica(datos.decode("utf-8", "replace")) if datos else None
        if clave is not None:
            claves.append((n, clave))
    return claves


def claves_del_texto(texto):
    """Las claves públicas de un authorized_keys (las líneas que lo son)."""
    claves = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave = analizar_clave_publica(linea)
        if clave is None:
            # Con opciones delante (from=..., command=...): la clave va después
            partes = linea.split()
            for i in range(1, len(partes) - 1):
                clave = analizar_clave_publica(" ".join(partes[i:]))
                if clave is not None:
                    break
        if clave is not None:
            claves.append(clave)
    return claves


def linea_de_la_clave(clave):
    """«tipo blob», sin el comentario (así no hay comillas que escapar)."""
    return "%s %s" % (clave.tipo, base64.b64encode(clave.blob).decode())


def pasos_anadir_clave(dominio, clave, ip):
    return ["Añada su clave a la máquina desde su consola:",
            "1. Entre en la consola, pulse Intro e inicie sesión como root (si la creó con "
            "ssoo-us provision o con ci-provision, la contraseña es %s):" % PASS_CONSOLA,
            "$ virsh console %s" % dominio,
            "2. Dentro de la máquina, añada su clave (es una sola línea):",
            "$ echo '%s' >> %s" % (linea_de_la_clave(clave), CLAVES_EN_LA_MAQUINA),
            "3. Salga con exit y luego Ctrl+], y vuelva a entrar:",
            "$ ssh %s@%s" % (USUARIO_VM, ip or "IP")]


def comprobar_clave_de_la_maquina(dominio, home, ip, rechazada):
    """La clave que tiene administrador en la máquina, comparada con las suyas."""
    texto, problema = leer_por_agente(dominio, CLAVES_EN_LA_MAQUINA)
    suyas = claves_del_usuario(home)
    actual = suyas[0][1] if suyas and suyas[0][0] == "id_rsa.pub" else None
    if texto is None:
        if problema == "no existe":
            rs = [error("En la máquina, %s no tiene authorized_keys" % USUARIO_VM,
                        efecto="no se puede entrar por ssh con ninguna clave.",
                        arreglo=pasos_anadir_clave(dominio, actual, ip) if actual else
                        "cree su pareja de claves (ssh-keygen) y añada la pública a la "
                        "máquina desde su consola.")]
            return rs
        if problema == "sin agente":
            return [omitida("La clave de la máquina: no se puede ver sin apagarla, porque no "
                            "responde su agente QEMU (las máquinas creadas a mano no suelen "
                            "tenerlo). Con la máquina apagada, ssoo-us diagnosis %s --acceso "
                            "la lee en su disco" % dominio)]
        return [omitida("La clave de la máquina: no se ha podido leer (%s)" % problema)]

    en_la_maquina = claves_del_texto(texto)
    huellas = {c.huella for c in en_la_maquina}
    if actual is not None and actual.huella in huellas:
        rs = [ok("La máquina tiene su clave de ~/.ssh/id_rsa.pub")]
        if rechazada:
            rs.append(aviso("La máquina tiene su clave, pero ssh la rechaza",
                            efecto="puede que los permisos de /home/%s/.ssh en la máquina "
                                   "no sean los que exige ssh." % USUARIO_VM,
                            arreglo=["Desde su consola, como root:",
                                     "$ virsh console %s" % dominio,
                                     "$ chown -R %s: /home/%s/.ssh && chmod 700 /home/%s/.ssh "
                                     "&& chmod 600 %s" % (USUARIO_VM, USUARIO_VM, USUARIO_VM,
                                                          CLAVES_EN_LA_MAQUINA)]))
        return rs
    otras = [(n, c) for n, c in suyas if c.huella in huellas and n != "id_rsa.pub"]
    detalle = ["En la máquina: %s" % c.describir() for c in en_la_maquina] or \
              ["En la máquina: ninguna clave"]
    detalle += ["Suya: %s (~/.ssh/%s)" % (c.huella, n) for n, c in suyas] or \
               ["Suya: ninguna (~/.ssh no tiene claves públicas)"]
    if otras:
        nombre = otras[0][0]
        privada = os.path.join(home, ".ssh", nombre[:-len(".pub")])
        pasos = []
        if os.path.exists(privada):
            pasos = ["Entre con esa clave:",
                     "$ ssh -i ~/.ssh/%s %s@%s" % (nombre[:-len(".pub")], USUARIO_VM, ip or "IP")]
        if actual is not None:
            pasos += ["O, para entrar con la actual, " + pasos_anadir_clave(dominio, actual, ip)[0]
                      .lower()] + pasos_anadir_clave(dominio, actual, ip)[1:]
        return [error("La máquina tiene otra clave suya (~/.ssh/%s), no la de ~/.ssh/id_rsa.pub"
                      % nombre, fallo="B5", detalle=detalle,
                      efecto="ssh entra con ~/.ssh/id_rsa: la máquina se creó con otra clave y "
                             "después cambió la de id_rsa.",
                      arreglo=pasos or None)]
    if actual is None:
        return [error("No tiene la clave ~/.ssh/id_rsa.pub", fallo="B5", detalle=detalle,
                      arreglo="cree su pareja de claves con ssh-keygen; después tendrá que "
                              "añadir la pública a la máquina desde su consola.")]
    return [error("La máquina no tiene ninguna de sus claves", fallo="B5", detalle=detalle,
                  efecto="ssh contesta «Permission denied (publickey)». Lo más probable: "
                         "cambió su clave (ssh-keygen) después de crear la máquina.",
                  arreglo=pasos_anadir_clave(dominio, actual, ip))]


# --- La revisión ------------------------------------------------------------------

def comprobar_puerto(dominio, ip):
    """(resultados, el puerto 22 está abierto)."""
    rs = []
    if responde_ping(ip):
        rs.append(ok("La máquina responde en %s" % ip))
    puerto = probar_puerto(ip)
    if puerto == "abierto":
        return rs + [ok("El puerto 22 (ssh) está abierto")], True
    if puerto == "rechazado":
        rs.append(error("La máquina rechaza la conexión al puerto 22",
                        detalle=["ssh dice «Connection refused»."],
                        efecto="ssh no está en marcha en la máquina: todavía arranca, o ha "
                               "arrancado en modo de emergencia.",
                        arreglo=["Espere un minuto y repita.",
                                 "Si sigue igual, mire en su consola qué pasa (si pide «Give "
                                 "root password for maintenance», está en modo de emergencia):",
                                 "$ virsh console %s" % dominio]))
    else:
        rs.append(error("Nada responde en el puerto 22 de %s" % ip,
                        detalle=["ssh dice «Connection timed out» o «No route to host»."],
                        efecto="o la máquina todavía arranca, o esa no es su IP.",
                        arreglo=["Espere un minuto y repita.",
                                 "Si sigue igual, compruebe su IP:",
                                 "$ virsh domifaddr %s --source lease" % dominio]))
    return rs, False


def comprobar_entrada(dominio, ip, home, esperado):
    """(resultados, entra, la máquina rechaza la clave)."""
    cifrada, en_agente = estado_de_la_clave(home)
    known_hosts = os.path.join(home, ".ssh", "known_hosts")
    codigo, _, _ = ejecutar_lectura(["ssh-keygen", "-F", str(ip), "-f", known_hosts])
    conocida = codigo == 0
    codigo, salida, err = _ssh(ip, home, known_hosts if conocida else "/dev/null", conocida)
    rs = []
    if codigo == 0:
        otra = _otra_maquina(salida, esperado)
        if otra:
            return [aviso("En %s ha contestado una máquina que se llama %s, no %s"
                          % (ip, otra, esperado),
                          efecto="otra máquina suya tiene la misma IP.",
                          arreglo="apague una de las dos (virsh list --all le dice cuáles "
                                  "tiene encendidas).")], False, False
        return [ok("Puede entrar: ssh %s@%s funciona" % (USUARIO_VM, ip),
                   detalle=["Si a usted no le deja, compruebe que lo ejecuta en el servidor (no "
                            "en su ordenador) y que escribe exactamente ssh %s@%s."
                            % (USUARIO_VM, ip)])], True, False
    if codigo is None:
        return [aviso("ssh no ha terminado a tiempo",
                      arreglo="repita dentro de un minuto, o pruébelo a mano: ssh %s@%s"
                              % (USUARIO_VM, ip))], False, False
    if "REMOTE HOST IDENTIFICATION HAS CHANGED" in err:
        rs.append(error("known_hosts tiene otra clave para %s" % ip, fallo="D4",
                        efecto="ssh se niega a conectar («REMOTE HOST IDENTIFICATION HAS "
                               "CHANGED»). Pasa al volver a crear una máquina con la misma IP.",
                        arreglo=["$ ssh-keygen -f \"%s\" -R \"%s\"" % (known_hosts, ip)]))
        codigo, _, err = _ssh(ip, home, "/dev/null", False)
        if codigo == 0:
            # No hace falta mirar su clave: es lo único que falla
            rs.append(ok("Quitando esa línea de known_hosts, podrá entrar"))
            return rs, True, False
    if "UNPROTECTED PRIVATE KEY FILE" in err:
        rs.append(error("ssh no usa ~/.ssh/id_rsa: tiene permisos demasiado abiertos",
                        fallo="B10", arreglo=["$ chmod 600 ~/.ssh/id_rsa"]))
        return rs, False, False
    if "Permission denied" in err:
        if cifrada and not en_agente:
            rs.append(omitida("Acceso por ssh: no concluyente. Su clave tiene contraseña y no "
                              "está en el agente, así que esta prueba no puede usarla. "
                              "Cárguela con ssh-add y repita"))
            return rs, False, False
        rs.append(error("La máquina rechaza su clave: «Permission denied (publickey)»",
                        fallo="B5", efecto="su clave no es la que tiene la máquina.",
                        arreglo="en el bloque siguiente, «La clave de la máquina», se ve qué "
                                "clave tiene y cómo añadirle la suya."))
        return rs, False, True
    lineas = [l for l in err.strip().splitlines() if l.strip()]
    rs.append(error("ssh no ha podido entrar",
                    detalle=["ssh dice: %s" % (lineas[-1] if lineas else "(nada)")],
                    arreglo=["Pruébelo a mano y fíjese en las últimas líneas:",
                             "$ ssh -v %s@%s" % (USUARIO_VM, ip)]))
    return rs, False, False


def revisar_acceso(conn, uvus, home, nombre, ip_forzada=None):
    """El informe de «ssoo-us acceso NOMBRE»."""
    informe = Informe()
    dominio = buscar_maquina_suya(conn, nombre, uvus)
    if dominio is None:
        suyas = sorted(d.name() for d in conn.listAllDomains(0)
                       if d.name().startswith(uvus + "-"))
        informe.bloque("Máquina", [error(
            "No existe la máquina %s" % nombre,
            detalle=["Sus máquinas: %s." % ", ".join(suyas) if suyas
                     else "No tiene ninguna máquina."],
            arreglo="escriba el nombre de una de sus máquinas (vale sin su usuario delante: "
                    "server1 en lugar de %s-server1)." % uvus)])
        return informe, None
    m = Maquina(dominio)
    corto = m.nombre[len(uvus) + 1:] if m.nombre.startswith(uvus + "-") else m.nombre
    if m.apagada:
        informe.bloque("Máquina", [error(
            "La máquina %s está apagada" % m.nombre,
            arreglo=["Arránquela, espere un minuto y vuelva a probar:",
                     "$ virsh start %s" % m.nombre])])
        return informe, m.nombre
    if not m.encendida:
        estado = NOMBRES_ESTADO.get(m.estado, str(m.estado))
        informe.bloque("Máquina", [error(
            "La máquina %s está %s" % (m.nombre, estado),
            arreglo=["$ virsh resume %s" % m.nombre] if m.estado == ESTADO_PAUSADA else
            ["Apáguela y arránquela:", "$ virsh destroy %s" % m.nombre,
             "$ virsh start %s" % m.nombre])])
        return informe, m.nombre
    informe.bloque("Máquina", [ok("La máquina %s está encendida" % m.nombre)])

    # La IP: la indicada, la del DHCP, la de las tablas ARP o la que diga su agente
    ip, origen = ip_forzada, "de --ip"
    for buscar, de_donde in ((ip_por_lease, "del DHCP de su red"),
                             (ip_por_arp, "de las tablas ARP del servidor"),
                             (lambda d: ip_por_agente(m.nombre), "de su agente QEMU")):
        if ip is None:
            ip, origen = buscar(dominio), de_donde
    rechazada = False
    if ip is None:
        informe.bloque("Red", [error(
            "No se encuentra la IP de la máquina",
            efecto="o todavía arranca, o no ha conseguido red.",
            arreglo=["Espere un minuto y repita. Si sigue sin IP, mire en su consola si ha "
                     "arrancado bien:", "$ virsh console %s" % m.nombre,
                     "Si sabe su IP, indíquela: ssoo-us acceso %s --ip IP" % corto])])
    else:
        rs, abierto = comprobar_puerto(m.nombre, ip)
        informe.bloque("Red", [ok("IP %s (%s)" % (ip, origen))] + rs)
        if abierto:
            rs, entra, rechazada = comprobar_entrada(m.nombre, ip, home, corto)
            informe.bloque("Entrar por ssh", rs)
            if entra:
                return informe, m.nombre
    informe.bloque("La clave de la máquina",
                   comprobar_clave_de_la_maquina(m.nombre, home, ip, rechazada))
    return informe, m.nombre


def acceso(argv=None):
    """ssoo-us acceso ARGUMENTOS. Devuelve el código de salida."""
    argv = sys.argv[2:] if argv is None else argv
    try:
        opciones = analizar_argumentos_acceso(argv)
    except ErrorDeUso as e:
        print("ssoo-us acceso: %s" % e, file=sys.stderr)
        print("Consulte la ayuda con: ssoo-us acceso -h", file=sys.stderr)
        return 2
    if opciones["ayuda"]:
        print(USO_ACCESO, end="")
        return 0
    if opciones["version"]:
        print("%s %s" % (PROGRAMA, VERSION))
        return 0
    if opciones["maquina"] is None:
        print("ssoo-us acceso: indique la máquina (por ejemplo: ssoo-us acceso server1).",
              file=sys.stderr)
        return 2
    uvus = (os.environ.get("CI_DIAGNOSIS_USUARIO") or pwd.getpwuid(os.getuid()).pw_name)
    home = os.path.expanduser("~")
    try:
        conn = abrir_conexion()
    except SinLibvirt as e:
        print("ssoo-us acceso: %s." % e, file=sys.stderr)
        print("Sin libvirt no se puede hacer la revisión: avise al profesor.", file=sys.stderr)
        return 2
    try:
        informe, nombre = revisar_acceso(conn, uvus, home, opciones["maquina"],
                                         opciones["ip"])
    finally:
        try:
            conn.close()
        except Exception:
            pass
    servidor = os.uname().nodename.split(".")[0]
    print("ssoo-us acceso %s · %s · usuario: %s · máquina: %s" % (
        VERSION, servidor, uvus, nombre or opciones["maquina"]))
    print()
    for linea in formatear_informe(informe, usar_color(sys.stdout)):
        print(linea)
    return informe.codigo_salida()
