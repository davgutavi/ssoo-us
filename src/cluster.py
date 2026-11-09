# --- provision: infraestructura GlusterFS (boletín 2, epígrafe 2.4) -----------------
#
# Dos fases, las mismas que describe el boletín, pero todo con cloud-init:
#
#   Fase 1  Base gluster-base.qcow2: por defecto, una copia COW de la imagen
#           cloud de Ubuntu (la misma que SERVER1); con --imagen ubuntu-base,
#           una copia de ubuntu-base.qcow2, como en la construcción manual
#           (apartado 2.4 b). Se arranca con glusterfs-server instalado,
#           glusterd habilitado y el machine-id vacío; se espera a que termine,
#           se apaga y se elimina su dominio conservando el disco.
#   Fase 2  Cada nodo es una copia COW de ese disco con sus discos extra
#           conectados desde el primer arranque. Un instance-id nuevo hace que
#           cloud-init lo personalice: IP fija, /etc/hosts, discos xfs
#           montados. Los nodos arrancan en paralelo y se espera a todos.


def disco_base_cluster(o):
    """Disco de la imagen base del clúster: la que se construye en la fase 1 o,
    con --base, una que ya existe en el silo."""
    if o.base_opt:
        return o.silo + "/" + o.base_opt
    return o.silo + "/" + disco_de(o, CLUSTER_BASE)


def discos_extra_nodo(o, host):
    return discos_extra(o, host, o.unidades_cluster)


def texto_discos_montados(o):
    """«vdb, vdc y vdd en xfs, montados en /gluster1 /gluster2 /gluster3»."""
    n = len(CLUSTER_MONTAJES)
    u = o.unidades_cluster[:n]
    return "%s y %s en xfs, montados en %s" % (", ".join(u[:-1]), u[-1],
                                                " ".join(CLUSTER_MONTAJES))


def texto_discos_sin_formatear(o):
    """«; vde..vdh sin formatear» (nada si solo están los que se montan)."""
    n = len(CLUSTER_MONTAJES)
    u = o.unidades_cluster
    if len(u) == n + 1:
        return "; %s sin formatear" % u[n]
    if len(u) > n + 1:
        return "; %s..%s sin formatear" % (u[n], u[-1])
    return ""


def calcular_ips_cluster(o):
    """IPs de los nodos (.10, .11, ...) dentro de la red."""
    o.cluster_ips = [entero_a_ip(o.red.red_entera + o.cluster_ip_inicial + i)
                     for i in range(len(CLUSTER_NODOS))]


def objetivos_cluster(o):
    """Todo lo que crea el clúster."""
    o.obj_dominios, o.obj_ficheros = [], []
    if not o.base_opt:
        o.obj_dominios.append("%s-%s" % (o.prefijo_dominio, CLUSTER_BASE))
        o.obj_ficheros.append(o.silo + "/" + disco_de(o, CLUSTER_BASE))
    for host in CLUSTER_NODOS:
        o.obj_dominios.append("%s-%s" % (o.prefijo_dominio, host))
        o.obj_ficheros.append(o.silo + "/" + disco_de(o, host))
        o.obj_ficheros += discos_extra_nodo(o, host)


def mostrar_plan_cluster(o):
    base_vm = "%s-%s" % (o.prefijo_dominio, CLUSTER_BASE)
    base_disco = disco_base_cluster(o)

    print("→ MODO SIMULACIÓN (--dry-run): no se creará nada.")
    print()
    print("✔ Validaciones superadas.")
    print("    Usuario : %s" % o.usuario)
    if o.prefijo_opt:
        print("    Prefijo : %s (sustituye al usuario en los dominios y en los discos)"
              % o.prefijo_opt)
    print("    Red     : %s (pasarela %s, prefijo /%d)" % (o.red.nombre, o.red.pasarela,
                                                         o.red.prefijo))
    print("    Nodos   :")
    for nodo, ip in zip(CLUSTER_NODOS, o.cluster_ips):
        print("      %s-%s  →  %s" % (o.prefijo_dominio, nodo, ip))
    print("    Sistema : %s; variante %s" % (descripcion_imagen(o.imagen), o.os_variant))
    print("    Recursos: %d MB y %d vCPU por máquina" % (o.ram_mb, o.vcpus))
    avisar_imagen_falta(o)
    print()

    if o.base_opt:
        print("Fase 1: se omite. Los nodos partirán de la imagen que ya existe: %s"
              % os.path.basename(base_disco))
    else:
        print("Fase 1: base GlusterFS")
        print("    Máquina %s con disco %s (%s, %s)." % (
            base_vm, os.path.basename(base_disco), origen_disco_principal(o, o.base_img),
            o.tam_disco))
        print("    Instala glusterfs-server (y las herramientas para formatear en xfs), "
              "habilita glusterd, vacía el machine-id.")
        print("    Al terminar se apaga y se elimina el dominio; el disco se conserva como "
              "respaldo.")
        generar_cloudinit(o, base_vm, CLUSTER_BASE, "", "gluster")
        construir_comando(o, base_vm, o.ram_mb, o.vcpus, [base_disco])
        print("    Ficheros cloud-init en %s/" % o.workdir)
        print("    Comando:")
        for linea in texto_comando(o):
            print("    " + linea)
    print()

    print("Fase 2: %d nodos, cada uno con %d discos extra de %s"
          % (len(CLUSTER_NODOS), len(o.unidades_cluster), TAM_DISCO_EXTRA))
    print("    %s%s." % (texto_discos_montados(o), texto_discos_sin_formatear(o)))
    comando_primero = []
    for i, (host, ip) in enumerate(zip(CLUSTER_NODOS, o.cluster_ips)):
        vm = "%s-%s" % (o.prefijo_dominio, host)
        generar_cloudinit(o, vm, host, ip, "nodo")
        print("    %s: disco %s (COW de %s), IP %s, cloud-init en %s/"
              % (vm, disco_de(o, host), os.path.basename(base_disco), ip, o.workdir))
        if i == 0:
            construir_comando(o, vm, o.ram_mb, o.vcpus,
                              [o.silo + "/" + disco_de(o, host)] + discos_extra_nodo(o, host))
            comando_primero = texto_comando(o)
    print()
    print("    Comando del primer nodo (los demás son iguales, con su nombre, IP y discos):")
    for linea in comando_primero:
        print("    " + linea)
    print()
    print("Al terminar cloud-init en los nodos, se expulsaría su medio y se apagarían y se")
    print("volverían a arrancar, para que se ejecuten con su configuración definitiva.")
    print()
    print("No se ha creado ni modificado ninguna máquina, disco ni red.")


def ejecutar_cluster(o):
    comprobar_conflictos(o)
    if o.dry_run:
        mostrar_plan_cluster(o)
        return
    raise NoImplementado("crear el clúster")   # fase 4
