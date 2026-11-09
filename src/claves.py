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
