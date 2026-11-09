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
