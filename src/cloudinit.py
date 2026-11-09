# --- provision: ficheros de cloud-init ---------------------------------------------
#
#   generar_cloudinit(o, DOMINIO, HOSTNAME, IP, MODO)
#
#   MODO:
#     normal   máquina corriente
#     gluster  nodo GlusterFS suelto, o base del clúster: instala
#              glusterfs-server y xfsprogs, habilita glusterd y resetea el
#              machine-id para que las copias sean máquinas distintas
#     nodo     nodo del clúster, creado a partir de la base: ya tiene todo
#              instalado; solo se personaliza (IP, /etc/hosts, discos xfs)
#
# Deja las rutas en o.workdir, o.user_data, o.meta_data y o.network_data (""
# si DHCP).
#
# Solo se usan claves vigentes en el cloud-init de Ubuntu 24.04: con una
# obsoleta (p.ej. 'chpasswd: list:' o 'ssh-authorized-keys') termina en
# 'degraded done', que el script trata como error.

# DNS_DE_LA_US e INTERFAZ_VM están en base.py: diagnosis comprueba lo mismo


def yaml_comillas(texto):
    """Escalar YAML entre comillas simples (dentro, la comilla se duplica): así
    una contraseña con ':', '#' o espacios no rompe el user-data."""
    return "'%s'" % texto.replace("'", "''")


def escribir_privado(ruta, texto):
    """Un fichero que solo puede leer su dueño desde el primer instante (en el
    servidor, multiusuario, estos ficheros llevan contraseñas)."""
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(texto.encode("utf-8", "surrogateescape"))
    os.chmod(ruta, 0o600)


def borrar_ruta(ruta):
    """rm -rf RUTA (un enlace simbólico se borra él, no lo que señala)."""
    if os.path.islink(ruta) or os.path.isfile(ruta):
        os.remove(ruta)
    elif os.path.isdir(ruta):
        shutil.rmtree(ruta)


def preparar_workdir(o, dominio):
    """Directorio de los ficheros. En --dry-run es otro, para no sobrescribir los
    de una máquina que ya exista."""
    if o.dry_run:
        o.workdir = "%s/cloudinit-%s.dry-run" % (o.silo, dominio)
    else:
        o.workdir = "%s/cloudinit-%s" % (o.silo, dominio)
        # Si algo falla después, el rollback lo quita junto a los discos
        o.dirs_creados.append(o.workdir)
    # Solo su propietario debe poder leerlos, ni siquiera un instante: por eso
    # el umask, y no un chmod después
    borrar_ruta(o.workdir)
    antes = os.umask(0o077)
    try:
        os.makedirs(o.workdir, exist_ok=True)
    finally:
        os.umask(antes)
    os.chmod(o.workdir, 0o700)
    o.user_data = o.workdir + "/cip-user.yaml"
    o.meta_data = o.workdir + "/cip-meta.yaml"
    o.network_data = ""


def generar_cloudinit(o, dominio, host, ip, modo):
    preparar_workdir(o, dominio)
    # El instance-id importa: cloud-init vuelve a configurar una máquina cuando
    # ve uno distinto del que tenía. Así se personalizan los nodos del clúster,
    # que parten de un disco ya configurado. Lleva la fecha para que sea nuevo
    # aunque el disco de partida ya hubiera sido una máquina con el mismo nombre.
    escribir_privado(o.meta_data, "instance-id: %s-%s\nlocal-hostname: %s\n"
                     % (dominio, time.strftime("%Y%m%d%H%M%S"), host))
    lineas = ["#cloud-config"] + yaml_usuarios(o) + yaml_paquetes_y_ficheros(o, modo, host) \
        + yaml_runcmd(o, modo)
    escribir_privado(o.user_data, "".join(l + "\n" for l in lineas))
    if ip:
        o.network_data = o.workdir + "/cip-net.yaml"
        escribir_privado(o.network_data, texto_network_config(o, ip))


def yaml_usuarios(o):
    """Usuarios, contraseñas y acceso por SSH."""
    l = ["users:", "  - name: administrador"]
    if o.imagen == "ubuntu-base":
        # En ubuntu-base 'administrador' ya existe, con la contraseña del
        # boletín 1, y sudo se la pide: se deja como está (lock_passwd: false
        # para que cloud-init no la bloquee) y solo se añade la clave
        l.append("    lock_passwd: false")
    else:
        l += ["    groups: [sudo]", "    shell: /bin/bash",
              "    sudo: ['ALL=(ALL) NOPASSWD:ALL']"]
    l.append("    ssh_authorized_keys:")
    # Entre comillas: el comentario de la clave puede llevar ': ' o '#'
    l.append("      - %s" % yaml_comillas(o.pubkey))

    # root tiene contraseña para poder entrar por consola (por SSH no entra:
    # el sshd de Debian y el de Ubuntu traen PermitRootLogin prohibit-password).
    # Hace falta, p.ej., en el modo de emergencia del epígrafe 2.3 del boletín 2.
    # 'administrador' solo la tiene si se pide --ssh-pass; si no, entra
    # únicamente por SSH con su clave, igual que en las máquinas que se crean a
    # mano siguiendo el boletín.
    if o.ssh_pass or not o.no_root:
        l += ["chpasswd:", "  expire: false", "  users:"]
        if o.ssh_pass:
            l += ["    - name: administrador",
                  "      password: %s" % yaml_comillas(o.ssh_pass),
                  "      type: text"]
        if not o.no_root:
            l += ["    - name: root", "      password: %s" % PASS_CONSOLA, "      type: text"]

    # SSH por contraseña solo si el alumno lo pide explícitamente. Se fija
    # también el 'false' para no depender del valor por defecto de la imagen,
    # salvo en ubuntu-base, que lo trae activado y se respeta.
    if o.ssh_pass:
        l.append("ssh_pwauth: true")
    elif o.imagen != "ubuntu-base":
        l.append("ssh_pwauth: false")
    return l


def yaml_paquetes_y_ficheros(o, modo, host):
    """Paquetes y, en los nodos, /etc/hosts y discos xfs."""
    if modo in ("normal", "gluster"):
        l = ["package_update: true", "packages:", "  - qemu-guest-agent"]
        if modo == "gluster":
            l.append("  - glusterfs-server")
            # Necesario para que los nodos del clúster puedan formatear sus
            # discos en xfs en el primer arranque
            l.append("  - xfsprogs")
        return l
    if modo != "nodo":
        return []
    # La base ya tiene todo instalado: no hace falta tocar apt
    l = ["package_update: false",
         # Resolución por nombre entre los nodos (epígrafe 2.4 c). Se fija
         # manage_etc_hosts a false para que cloud-init no regenere /etc/hosts
         # en cada arranque y pise lo escrito aquí.
         "manage_etc_hosts: false", "write_files:", "  - path: /etc/hosts",
         "    content: |", "      127.0.0.1 localhost", "      127.0.1.1 %s" % host]
    l += ["      %s %s" % (ip, nodo) for ip, nodo in zip(o.cluster_ips, CLUSTER_NODOS)]
    l += ["      ::1 localhost ip6-localhost ip6-loopback", "      ff02::1 ip6-allnodes",
          "      ff02::2 ip6-allrouters"]
    # Discos vdb, vdc y vdd formateados en xfs. Deben estar conectados desde el
    # primer arranque: por eso se pasan a virt-install en vez de añadirlos
    # después. El montaje va en runcmd (ver yaml_runcmd) para que las líneas de
    # /etc/fstab sean las mismas que escribe crea-entorno.sh; el módulo
    # 'mounts' de cloud-init las escribiría a su manera.
    l.append("fs_setup:")
    for unidad, _ in zip(o.unidades_cluster, CLUSTER_MONTAJES):
        l += ["  - device: /dev/%s" % unidad, "    filesystem: xfs", "    partition: none",
              "    overwrite: false"]
    return l


def yaml_runcmd(o, modo):
    l = ["runcmd:"]
    if modo == "nodo":
        l.append("  - mkdir -p %s" % " ".join(CLUSTER_MONTAJES))
        for unidad, montaje in zip(o.unidades_cluster, CLUSTER_MONTAJES):
            l.append("  - echo '/dev/%s %s xfs %s 0 0' >> /etc/fstab"
                     % (unidad, montaje, OPCIONES_FSTAB_CLUSTER))
        l.append("  - mount -a")
    if o.imagen == "ubuntu-base" and o.no_root:
        # ubuntu-base trae root con contraseña: --no-root la bloquea
        l.append("  - passwd -l root")
    l.append("  - timedatectl set-timezone Europe/Madrid")
    if modo == "gluster":
        # Solo se habilita glusterd, no se arranca: así no genera su UUID en la
        # base, y cada copia tendrá el suyo cuando arranque
        l.append("  - systemctl enable glusterd")
    l.append("  - systemctl start qemu-guest-agent")
    if modo == "gluster":
        # machine-id vacío: cada copia de este disco generará el suyo
        l.append("  - truncate -s 0 /etc/machine-id")
    return l


def texto_network_config(o, ip):
    """network-config, solo si la IP es fija. La pasarela y el prefijo son los de
    la red real. Con 'routes:' en lugar de la obsoleta 'gateway4:', como el
    capítulo 6 del manual."""
    return ("version: 2\n"
            "ethernets:\n"
            "  %s:\n"
            "    addresses:\n"
            "      - %s/%d\n"
            "    routes:\n"
            "      - to: default\n"
            "        via: %s\n"
            "    nameservers:\n"
            "      addresses:\n"
            "        - %s\n"
            "        - %s\n" % ((INTERFAZ_VM, ip, o.red.prefijo, o.red.pasarela) + DNS_DE_LA_US))
