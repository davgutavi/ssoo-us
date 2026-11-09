# --- Imágenes de partida (--imagen) ------------------------------------------

# Las dos imágenes cloud se descargan al silo si faltan, con el nombre y desde
# la URL que dan los boletines.
#   noble        Ubuntu 24.04: SERVER1 y nodos GlusterFS del boletín 2
#   debian12     Debian 12: SERVER1 del boletín 1
#   ubuntu-base  la imagen del boletín 1 que dejan los profesores en
#                /home/ssoo-shared; solo para la base GlusterFS, si se quiere
#                hacer como la construcción manual del boletín (epígrafe 2.4),
#                sobre una copia suya en el silo
IMAGEN_NOBLE = "noble-server-cloudimg-amd64.img"
URL_NOBLE = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
IMAGEN_DEBIAN = "debian12.qcow2"
URL_DEBIAN = ("https://cloud.debian.org/images/cloud/bookworm/latest/"
              "debian-12-generic-amd64.qcow2")
# Sumas publicadas junto a cada imagen, para comprobar la descarga
SUMAS_NOBLE = "https://cloud-images.ubuntu.com/noble/current/SHA256SUMS"
SUMAS_DEBIAN = "https://cloud.debian.org/images/cloud/bookworm/latest/SHA512SUMS"
IMAGEN_DEFECTO = "noble"                # máquinas sueltas
IMAGEN_DEFECTO_GLUSTER = "noble"        # --glusterfs y --gluster-cluster


def variante_de_imagen(imagen):
    """Variante de SO que se declara a virt-install para cada imagen."""
    return "debian12" if imagen == "debian12" else "ubuntu24.04"


def descripcion_imagen(imagen):
    """Nombre legible de cada imagen, para los mensajes."""
    return {"noble": "Ubuntu 24.04 (imagen cloud)",
            "debian12": "Debian 12 (imagen cloud)",
            "ubuntu-base": "Ubuntu 24.04 (ubuntu-base.qcow2 del boletín 1)"}.get(imagen, "")


def elegir_imagen(o):
    """Fija o.imagen, o.base_img, o.base_img_url, o.base_img_sumas y o.os_variant
    a partir de --imagen. Con --base, el fichero es ese; su tipo lo da --imagen
    si se indica y, si no, se deduce más tarde del propio fichero."""
    gluster = o.glusterfs or o.cluster

    if o.base_opt:
        o.base_img = os.path.join(o.silo, o.base_opt)
        o.base_img_url = ""
        o.base_img_sumas = ""
        if o.imagen_opt:
            if o.imagen_opt not in ("noble", "debian12", "ubuntu-base"):
                fallar(10, "La imagen '%s' (--imagen) no existe. Con --base, indica de cuál sale\n"
                           "el fichero: noble (Ubuntu 24.04), debian12 o ubuntu-base."
                       % o.imagen_opt)
            o.imagen = o.imagen_opt
            o.os_variant = variante_de_imagen(o.imagen)
        return

    o.imagen = o.imagen_opt or (IMAGEN_DEFECTO_GLUSTER if gluster else IMAGEN_DEFECTO)
    if o.imagen == "noble":
        o.base_img = os.path.join(o.silo, IMAGEN_NOBLE)
        o.base_img_url, o.base_img_sumas = URL_NOBLE, SUMAS_NOBLE
    elif o.imagen == "debian12":
        o.base_img = os.path.join(o.silo, IMAGEN_DEBIAN)
        o.base_img_url, o.base_img_sumas = URL_DEBIAN, SUMAS_DEBIAN
    elif o.imagen == "ubuntu-base":
        if not gluster:
            fallar(10, "--imagen ubuntu-base solo sirve para la imagen base GlusterFS (--glusterfs o\n"
                       "--gluster-cluster). Para una máquina suelta usa noble (Ubuntu 24.04) o debian12.")
        o.base_img = o.ubuntu_base_compartida
        o.base_img_url = o.base_img_sumas = ""
    else:
        fallar(10, "La imagen '%s' (--imagen) no existe. Elige una de estas:\n"
                   "  noble        Ubuntu 24.04 (por defecto)\n"
                   "  debian12     Debian 12\n"
                   "  ubuntu-base  la del boletín 1, solo para la base GlusterFS" % o.imagen)
    o.os_variant = variante_de_imagen(o.imagen)


# --- qemu-img ------------------------------------------------------------------

def qemu_info(ruta, forzar=True, cadena=False):
    """«qemu-img info --output=json» ya leído (un diccionario o, con cadena, una
    lista), o None si falla. forzar: con -U (force-share), para poder leer la
    imagen aunque una máquina en ejecución la tenga abierta."""
    orden = ["qemu-img", "info"] + (["-U"] if forzar else [])
    orden += (["--backing-chain"] if cadena else []) + ["--output=json", ruta]
    codigo, salida, _ = ejecutar(orden)
    if codigo != 0:
        return None
    try:
        return json.loads(salida)
    except ValueError:
        return None


def campo_json(datos, campo):
    """jq -r '.CAMPO // empty': el valor como texto, o "" si falta, es null o false."""
    if not isinstance(datos, dict):
        return ""
    valor = datos.get(campo)
    if valor is None or valor is False:
        return ""
    return str(valor)


def tam_a_bytes(tam):
    """40G, 512M o 1T → bytes."""
    return int(tam[:-1], 10) * {"M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}[tam[-1]]


def bytes_a_gib(n):
    """Bytes → GiB, redondeando hacia arriba."""
    return (n + 1073741823) // 1073741824


def tam_virtual(ruta):
    """Tamaño virtual de una imagen en bytes (como texto), o "" si no se puede leer."""
    return campo_json(qemu_info(ruta), "virtual-size")


def formato_de(ruta, forzar=True):
    return campo_json(qemu_info(ruta, forzar), "format")


def leer_respaldo(ruta):
    """Imagen base de un fichero (ruta completa), o "". Las rutas relativas son
    relativas al directorio del propio fichero, como las interpreta qemu."""
    b = campo_json(qemu_info(ruta), "backing-filename")
    if b and not b.startswith("/"):
        b = os.path.dirname(ruta) + "/" + b
    return b


# --- La imagen de partida en el silo -----------------------------------------------

def imagen_protegida(o, ruta):
    """¿Es una de las imágenes cloud que descarga el script? Nunca se borran."""
    return ruta in (o.silo + "/" + IMAGEN_NOBLE, o.silo + "/" + IMAGEN_DEBIAN)


def imagen_compartida(o):
    """Copia de la imagen cloud en el directorio compartido de los profesores, si
    la han dejado allí (evita que cada alumno descargue cientos de MB), o ""."""
    ruta = o.dir_compartido + "/" + os.path.basename(o.base_img)
    return ruta if os.access(ruta, os.R_OK) else ""


def origen_disco_principal(o, imagen):
    """Cómo se hace el disco principal a partir de una imagen, para los mensajes."""
    if os.path.dirname(imagen) == o.silo:
        return "copia COW de %s" % os.path.basename(imagen)
    return "copia completa de %s" % imagen


def discos_extra(o, host, unidades):
    """Rutas de los discos extra de una máquina."""
    return ["%s/%s%s-%s.qcow2" % (o.silo, o.prefijo_fichero, host, u) for u in unidades]


def deducir_imagen_de_base(o):
    """Con --base: comprueba que la cadena de respaldo está completa y, si no se
    ha dicho con --imagen, deduce de qué imagen sale el fichero por el nombre de
    la última de la cadena:
      *debian*                     Debian 12
      noble*, *cloudimg*           Ubuntu 24.04 (imagen cloud)
      *ubuntu-base*, *gluster*     ubuntu-base (la base GlusterFS del boletín es
                                   una copia completa suya)
    Si no se reconoce, se trata como imagen cloud de Ubuntu y se avisa: así
    'administrador' siempre tiene sudo."""
    cadena = qemu_info(o.base_img, cadena=True)
    if cadena is None:
        fallar(39, "No se puede leer la imagen %s ni la cadena de imágenes de la que es copia.\n"
                   "Lo más probable es que falte (o se haya movido) la imagen de la que se hizo "
                   "la copia; compruébalo con:\n"
                   "  qemu-img info --backing-chain %s" % (o.base_img, o.base_img))
    if o.imagen_opt:
        return
    ultima = cadena[-1] if isinstance(cadena, list) and cadena else cadena
    raiz = os.path.basename(campo_json(ultima, "filename") or o.base_img)
    # ${raiz,,} con LC_ALL=C: solo las letras ASCII
    nombre = "".join(c.lower() if "A" <= c <= "Z" else c for c in raiz)
    if "debian" in nombre:
        o.imagen = "debian12"
    elif nombre.startswith("noble") or "cloudimg" in nombre:
        o.imagen = "noble"
    elif "ubuntu-base" in nombre or "gluster" in nombre:
        o.imagen = "ubuntu-base"
    else:
        o.imagen = "noble"
        base = os.path.basename(o.base_img)
        print("AVISO: no sé de qué imagen sale %s (no es copia de ninguna imagen conocida)." % base,
              file=sys.stderr)
        print("       Se trata como imagen cloud de Ubuntu 24.04 ('administrador' con sudo sin "
              "contraseña).", file=sys.stderr)
        print("       Si sale de ubuntu-base o de Debian, indícalo: --imagen ubuntu-base, o "
              "--imagen debian12.", file=sys.stderr)
    o.os_variant = variante_de_imagen(o.imagen)


def comprobar_base_no_objetivo(o):
    """La imagen de partida no puede ser uno de los discos que se van a crear
    (con --limpiar se borraría antes de usarla)."""
    for f in o.obj_ficheros:
        if f == o.base_img:
            if o.base_opt:
                fallar(10, "La imagen indicada con --base (%s) es uno de los discos que se "
                           "crearían.\nElige otra imagen o cambia el nombre de la máquina."
                       % os.path.basename(o.base_img))
            fallar(10, "El disco que se crearía se llama %s, que es la imagen de la que\n"
                       "salen todas las máquinas. Ponle otro nombre a la máquina (p.ej. server1)."
                   % os.path.basename(o.base_img))
        if imagen_protegida(o, f):
            fallar(10, "El disco que se crearía se llama %s, que es una de las imágenes cloud de\n"
                       "las que salen las máquinas. Ponle otro nombre a la máquina (p.ej. "
                       "server1)." % os.path.basename(f))


def comprobar_tam_disco(o):
    """--tam no puede ser menor que la imagen de la que se hace la copia: qemu-img
    lo admite, pero la máquina arrancaría con el sistema de ficheros truncado."""
    if not os.path.isfile(o.base_img):
        return
    vs = tam_virtual(o.base_img)
    if re.fullmatch(r"[0-9]+", vs) is None:
        return
    vs = int(vs)
    if tam_a_bytes(o.tam_disco) < vs:
        # Sin --tam, el disco toma el tamaño de la imagen (ubuntu-base tiene 64G)
        if not o.tam_explicito:
            o.tam_disco = "%dG" % bytes_a_gib(vs)
            return
        fallar(15, "El tamaño --tam %s es menor que el de la imagen %s (%d GiB):\n"
                   "la copia quedaría truncada y la máquina no arrancaría bien. Indica un tamaño "
                   "igual o mayor." % (o.tam_disco, os.path.basename(o.base_img), bytes_a_gib(vs)))


def comprobar_imagen_base(o):
    """La imagen de partida: con --base, que exista y sirva; ubuntu-base, que
    esté; las imágenes cloud, que estén (si no, se descargan) y sean qcow2."""
    if o.base_opt:
        if not os.path.isfile(o.base_img):
            fallar(39, "La imagen indicada con --base no está en el silo: %s\n"
                       "Mira qué imágenes tienes con: ls %s/*.qcow2" % (o.base_img, o.silo))
        formato = formato_de(o.base_img)
        if formato != "qcow2":
            fallar(39, "La imagen indicada con --base no es un qcow2 válido: %s (formato: %s).\n"
                       "Mira qué imágenes tienes con: ls %s/*.qcow2"
                   % (o.base_img, formato or "desconocido", o.silo))
        # Una imagen base no puede ser el disco de ninguna máquina, ni siquiera
        # apagada: en cuanto arrancara, escribiría en ella y las copias que
        # dependen de ella quedarían corruptas
        cargar_dominios_vecinos(o)
        otro = o.disco_usado_por.get(o.base_img)
        if otro:
            fallar(39, "La imagen %s es el disco de la máquina '%s' (aunque esté apagada).\n"
                       "Si la usas como imagen base, al arrancar '%s' las copias se "
                       "corromperían.\n"
                       "Elimina antes esa máquina, o haz una copia completa del disco y usa la "
                       "copia:\n  cp %s %s/mi-base.qcow2" % (o.base_img, otro, otro, o.base_img,
                                                            o.silo))
        # Sin -U, qemu-img se niega si otro proceso (p.ej. una máquina de otro
        # usuario) tiene la imagen abierta para escribir
        if qemu_info(o.base_img, forzar=False) is None:
            _, salida, errores = ejecutar(["qemu-img", "info", o.base_img])
            if "lock" in (salida + errores).lower():
                fallar(39, "La imagen %s la tiene abierta para escribir una máquina en "
                           "ejecución.\nApágala (o elimina su dominio) antes de usarla como "
                           "imagen base: las copias de un disco\nque se está escribiendo "
                           "quedarían corruptas." % o.base_img)
        deducir_imagen_de_base(o)
        return

    # ubuntu-base: la dejan los profesores en el servidor; no se descarga
    if o.imagen == "ubuntu-base":
        if not os.access(o.base_img, os.R_OK) or formato_de(o.base_img) != "qcow2":
            fallar(39, "No encuentro la imagen ubuntu-base del boletín 1 en %s\n"
                       "(o no se puede leer, o no es un qcow2). En los servidores de la "
                       "asignatura está ahí.\n"
                       "Si no la tienes, construye la base a partir de una imagen cloud: "
                       "--imagen noble" % o.base_img)
        return

    if not os.path.isfile(o.base_img):
        if o.dry_run:
            # Se avisa dentro del plan, no aquí, para que salga en orden
            o.base_img_falta = True
            return
        raise NoImplementado("descarga de la imagen base")   # fase 3

    formato = formato_de(o.base_img)
    if formato != "qcow2":
        fallar(37, "La imagen base '%s' no es un qcow2 válido (formato: %s).\n"
                   "Probablemente la descarga falló. Bórrala y vuelve a ejecutar el script, que "
                   "la descargará:\n  rm %s" % (o.base_img, formato or "desconocido", o.base_img))
