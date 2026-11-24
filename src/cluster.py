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


def quitar_dominio_creado(o, dominio):
    """Quita un dominio del registro de creados (cuando se elimina a propósito)."""
    o.dominios_creados = [d for d in o.dominios_creados if d != dominio]


def crear_base_gluster(o, vm, host, disco):
    """Base GlusterFS: crea la máquina, espera a que cloud-init termine, la
    apaga y elimina el dominio. Queda solo el disco, listo para hacer copias
    COW. Es lo que describen los apartados 2.4 a) y b) del boletín 2, y lo usan
    tanto --glusterfs como la fase 1 de --gluster-cluster."""
    crear_maquina(o, vm, host, "", "gluster", disco, o.base_img)

    # Para una base no vale «se da por terminada»: si no se puede consultar
    # cloud-init, se sigue esperando hasta agotar el tiempo
    o.exigir_estado_ci = True
    lista = esperar_maquinas(o, [vm])
    o.exigir_estado_ci = False
    if not lista:
        fallar(70, "No se ha podido confirmar que cloud-init haya terminado en '%s' en %ds.\n"
                   "Sin esa confirmación no puede servir de base. Comprueba la carga del servidor "
                   "y vuelve a intentarlo." % (vm, o.esperas["WAIT_TIMEOUT"]))

    if o.estado_ci.get(vm) != "done":
        # Se conserva la máquina para poder examinarla
        o.creacion_completa = True
        if o.no_root:
            acceso = "ssh administrador@%s    (con tu clave)" % o.ips_detectadas.get(vm, "IP")
        else:
            acceso = "virsh console %s    (root, contraseña %s)" % (vm, PASS_CONSOLA)
        fallar(71, "cloud-init ha terminado con errores en '%s' (probablemente al instalar\n"
                   "glusterfs-server). Las copias heredarían el problema, así que se detiene "
                   "aquí.\nLa máquina se conserva para que puedas examinarla:\n"
                   "  %s\n  y dentro: cloud-init status --long\n"
                   "Cuando termines, repite el comando añadiendo --limpiar, o elimínala tú:\n"
                   "  virsh destroy %s; virsh undefine %s --snapshots-metadata; rm %s"
               % (vm, acceso, vm, vm, disco))

    print("→ Apagando '%s'…" % vm)
    if not apagar_maquina(o, vm):
        fallar(70, "La máquina '%s' no se ha apagado en %ds.\n"
                   "Se deshace lo creado en esta ejecución. Comprueba la carga del servidor "
                   "(virsh list --all, uptime)\ny vuelve a intentarlo. Si el dominio siguiera "
                   "ahí: virsh destroy %s; virsh undefine %s --snapshots-metadata"
               % (vm, o.esperas["SHUTDOWN_TIMEOUT"], vm, vm))

    # El dominio sobra: el disco se queda como respaldo de las copias
    codigo, _, errores = virsh("undefine", vm, "--snapshots-metadata")
    if codigo != 0:
        sys.stderr.write(errores)
        raise FalloInesperado(codigo)
    quitar_dominio_creado(o, vm)
    # A partir de aquí la base ya vale: si falla lo siguiente, se conserva
    quitar_disco_creado(o, disco)
    o.base_conservada = disco
    print("✔ Base lista: %s (el dominio '%s' se ha eliminado; el disco se conserva)."
          % (os.path.basename(disco), vm))


def print_summary_cluster(o):
    base_disco = disco_base_cluster(o)
    print("-------------------------------------------")
    print("Infraestructura GlusterFS creada (boletín 2, epígrafe 2.4)")
    print()
    print("Red          : %s" % o.red.nombre)
    print("Nodos        :")
    for host, ip_fija in zip(CLUSTER_NODOS, o.cluster_ips):
        vm = "%s-%s" % (o.prefijo_dominio, host)
        print("  %-28s %-16s hostname %s" % (vm, o.ips_detectadas.get(vm) or ip_fija, host))
    print("RAM / vCPUs  : %d MB / %d por nodo" % (o.ram_mb, o.vcpus))
    print("Sistema      : %s" % descripcion_imagen(o.imagen))
    print("Discos       : %s..%s (%d × %s) en cada nodo" % (
        o.unidades_cluster[0], o.unidades_cluster[-1], len(o.unidades_cluster), TAM_DISCO_EXTRA))
    print("               %s%s" % (texto_discos_montados(o), texto_discos_sin_formatear(o)))
    print("GlusterFS    : glusterfs-server instalado y glusterd habilitado en todos")
    print("/etc/hosts   : con los %d nombres, en todos" % len(CLUSTER_NODOS))
    print()
    print("Acceso (igual en todos los nodos, con la IP de cada uno):")
    vm = "%s-%s" % (o.prefijo_dominio, CLUSTER_NODOS[0])
    bloque_acceso(o, vm, o.ips_detectadas.get(vm) or o.cluster_ips[0])
    print()
    print("IMPORTANTE: no borres %s." % base_disco)
    print("            Los discos de los %d nodos dependen de él." % len(CLUSTER_NODOS))
    print()
    # Con --base, la imagen no es de esta infraestructura: solo los nodos
    print("Para eliminar la infraestructura entera (nodos%s):"
          % ("" if o.base_opt else " e imagen base"))
    print("  %s %s--eliminar %s%s" % (orden_provision(), prefijo_en_orden(o), " ".join(CLUSTER_NODOS),
                                     "" if o.base_opt else " " + CLUSTER_BASE))
    print("-------------------------------------------")


def ejecutar_cluster(o):
    base_vm = "%s-%s" % (o.prefijo_dominio, CLUSTER_BASE)
    base_disco = disco_base_cluster(o)

    comprobar_conflictos(o)
    if o.dry_run:
        mostrar_plan_cluster(o)
        return

    # Fase 1: base
    if o.base_opt:
        print("═══ Fase 1 de 2: se omite; los nodos parten de %s ═══" % os.path.basename(base_disco))
    else:
        print("═══ Fase 1 de 2: base GlusterFS (%s) ═══" % base_vm)
        crear_base_gluster(o, base_vm, CLUSTER_BASE, base_disco)
    print()

    # Fase 2: nodos
    print("═══ Fase 2 de 2: %d nodos ═══" % len(CLUSTER_NODOS))
    nodos = []
    for host, ip in zip(CLUSTER_NODOS, o.cluster_ips):
        vm = "%s-%s" % (o.prefijo_dominio, host)
        print("── %s (%s)" % (vm, ip))
        crear_maquina(o, vm, host, ip, "nodo", o.silo + "/" + disco_de(o, host), base_disco,
                      discos_extra_nodo(o, host))
        nodos.append(vm)
    o.creacion_completa = True
    print("✔ Los %d nodos están creados y arrancando." % len(nodos))
    print("-------------------------------------------")

    if o.no_wait:
        print("Omitiendo la espera (--no-wait activo).")
        print("NOTA: los nodos siguen configurándose por dentro (discos xfs, /etc/hosts...).")
        print("      No se expulsa el medio de cloud-init ni se reinician en frío.")
        aviso_on_reboot(nodos)
    else:
        esperar_maquinas(o, nodos)
        listos = [vm for vm in nodos if o.estado_ci.get(vm)]
        sin_terminar = [vm for vm in nodos if not o.estado_ci.get(vm)]
        for vm in listos:
            eject_cloudinit_media(vm)
        if listos:
            reiniciar_en_frio(o, listos)
        if sin_terminar:
            aviso_on_reboot(sin_terminar)

    con_ficha(o, [(ruta_ficha(o, host), "del nodo %s-%s de la infraestructura GlusterFS"
                   % (o.prefijo_dominio, host)) for host in CLUSTER_NODOS],
              print_summary_cluster)
    avisar_known_hosts(o, o.cluster_ips)
