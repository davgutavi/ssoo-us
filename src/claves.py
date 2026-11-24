# --- Clave pública del alumno ------------------------------------------------------

# Espacios de [[:space:]] con LC_ALL=C (str.strip() quitaría además los de Unicode)
ESPACIOS_C = " \t\n\v\f\r"
TIPO_CLAVE_RE = re.compile(r"(ssh-(rsa|ed25519|dss)|ecdsa-sha2-nistp[0-9]+"
                           r"|sk-(ssh-ed25519|ecdsa-sha2-nistp256))(@openssh\.com)? ")


def lineas_con_texto(texto):
    """Las líneas con algo que no sea espacio (grep '[^[:space:]]')."""
    return [l for l in texto.split("\n") if l.strip(ESPACIOS_C)]


def comprobar_clave_publica(o):
    """La clave pública existe y tiene una sola clave: va tal cual dentro del
    user-data, y una segunda línea (o un fichero vacío) lo dejaría inválido.
    Deja en o.pubkey la línea, sin los espacios del final."""
    ruta = o.pubkey_path
    if not os.path.isfile(ruta):
        privada = ruta[:-len(".pub")] if ruta.endswith(".pub") else ""
        if privada and os.path.isfile(privada):
            # ssh-keygen le preguntaría si sobrescribe la privada y, si dijera
            # que sí, perdería el acceso a las máquinas hechas con ella
            fallar(31, "No existe la clave pública %s, pero sí la privada %s.\n"
                       "No generes otra: perderías el acceso a las máquinas que ya tengas. "
                       "Recupera la\npública a partir de la privada con:\n"
                       "  ssh-keygen -y -f %s > %s" % (ruta, privada, privada, ruta))
        fallar(31, "No existe la clave pública en %s. Genera una con: ssh-keygen" % ruta)
    datos = leer_bytes(ruta) or b""
    lineas = lineas_con_texto(datos.decode("utf-8", "surrogateescape"))
    o.pubkey = lineas[0].rstrip(ESPACIOS_C) if lineas else ""
    if not lineas:
        fallar(31, "El fichero %s está vacío. Genera una pareja de claves nueva con: ssh-keygen"
               % ruta)
    if len(lineas) > 1:
        fallar(31, "El fichero %s tiene %d líneas y debe contener una sola clave pública.\n"
                   "Deja solo la tuya (una línea que empiece por ssh-rsa, ssh-ed25519 o "
                   "ecdsa-sha2-…)." % (ruta, len(lineas)))
    if TIPO_CLAVE_RE.match(o.pubkey) is None:
        fallar(31, "El fichero %s no contiene una clave pública: debe ser una línea que empiece\n"
                   "por ssh-rsa, ssh-ed25519 o ecdsa-sha2-… (¿has copiado ahí la clave privada u "
                   "otro fichero?).\n"
                   "Si no la tienes, genera una pareja de claves nueva con: ssh-keygen" % ruta)


# --- Crear la clave si no tiene ninguna ---------------------------------------------
#
# Hay alumnos que usan la herramienta sin haber visto qué es una clave SSH: si no
# tienen ninguna (ni la pública ni la privada) en ~/.ssh/id_rsa, se les ofrece
# crearla. Sin contraseña: quien no sabe de claves no sabría qué hacer cuando
# ssh se la pidiera. Si existe la privada, nunca: se perdería el acceso a sus
# máquinas (comprobar_clave_publica le dice cómo recuperar la pública).

PREGUNTA_CREAR_CLAVE = ("No tienes clave SSH (%s). Es la que te permite entrar en tus "
                        "máquinas sin contraseña.\n¿La creo ahora?")


def se_puede_crear_la_clave(o):
    """La de siempre (~/.ssh/id_rsa), sin pública ni privada, y con ssh-keygen."""
    ruta = o.home + "/.ssh/id_rsa"
    return (o.pubkey_path == ruta + ".pub" and not os.path.lexists(ruta + ".pub")
            and not os.path.lexists(ruta) and shutil.which("ssh-keygen") is not None)


def crear_clave(o):
    """ssh-keygen -t rsa sin contraseña en ~/.ssh/id_rsa. Devuelve las líneas
    que se le enseñan al alumno."""
    directorio = o.home + "/.ssh"
    os.makedirs(directorio, mode=0o700, exist_ok=True)
    ruta = directorio + "/id_rsa"
    codigo, _, errores = ejecutar(["ssh-keygen", "-q", "-t", "rsa", "-N", "", "-f", ruta],
                                  timeout=60)
    if codigo != 0 or not os.path.isfile(ruta + ".pub"):
        fallar(31, "No se ha podido crear la clave con ssh-keygen%s.\nCréala tú con: ssh-keygen"
               % (": " + errores.strip() if errores.strip() else ""))
    return ["✔ Clave SSH creada: %s (privada) y %s.pub (pública)." % (ruta, ruta),
            "  Es la que usará ssh para entrar en tus máquinas. No la borres ni se la des a nadie."]


def ofrecer_crear_clave(o):
    """Si no tiene ninguna clave, la crea tras preguntar (con --si, sin
    preguntar). Sin terminal, o con --dry-run, no hace nada: lo dirá
    comprobar_clave_publica con el error 31."""
    if o.dry_run or not se_puede_crear_la_clave(o):
        return
    if not o.si and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    if confirmar(o, PREGUNTA_CREAR_CLAVE % (o.home + "/.ssh/id_rsa")):
        for linea in crear_clave(o):
            print(linea)
        print()
