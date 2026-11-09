# --- provision: una máquina suelta ---------------------------------------------------


def construir_comando(o, nombre, ram, vcpus, discos):
    """La orden de virt-install, como lista para poder ejecutarla y mostrarla
    tal cual. Usa los ficheros cloud-init generados justo antes. Los discos se
    conectan en el orden dado: el primero es vda."""
    orden = ["virt-install", "--quiet", "--name", nombre, "--ram", str(ram),
             "--vcpus", str(vcpus), "--import"]
    for disco in discos:
        orden += ["--disk", "path=%s,format=qcow2,bus=virtio" % disco]
    cloud_init = "user-data=%s,meta-data=%s" % (o.user_data, o.meta_data)
    if o.network_data:
        cloud_init += ",network-config=%s" % o.network_data
    orden += ["--os-variant", o.os_variant, "--network", "network=%s" % o.red.nombre,
              "--cloud-init", cloud_init,
              "--graphics", "none" if o.no_graficos else "spice", "--noautoconsole"]
    o.virt_install_cmd = orden


def texto_comando(o):
    """La orden de virt-install, legible: una opción por línea."""
    orden = o.virt_install_cmd
    lineas, i = ["  virt-install \\"], 1
    while i < len(orden):
        arg = orden[i]
        siguiente = orden[i + 1] if i + 1 < len(orden) else ""
        if arg.startswith("--") and siguiente and not siguiente.startswith("--"):
            linea, i = "    %s %s" % (arg, siguiente), i + 2
        else:
            linea, i = "    %s" % arg, i + 1
        lineas.append(linea + (" \\" if i < len(orden) else ""))
    return lineas


def calcular_objetivos(o):
    """Qué va a crear esta ejecución (dominios y ficheros). Se calcula antes de la
    validación que cuesta tiempo (la descarga de la imagen), para avisar de un
    conflicto cuanto antes."""
    if o.cluster:
        objetivos_cluster(o)
        return
    o.extras = discos_extra(o, o.maquina, UNIDADES_EXTRA) if o.extra_disks else []
    if o.disco_main in o.extras:
        fallar(16, "El nombre de disco '%s' coincide con uno de los discos extra que se "
                   "crearían.\nElige otro nombre para el disco principal."
               % os.path.basename(o.disco_main))
    o.obj_dominios = [o.vm_name]
    o.obj_ficheros = [o.disco_main] + o.extras


def avisar_imagen_falta(o):
    """En --dry-run, si la imagen de partida no está en el silo."""
    if not o.base_img_falta:
        return
    compartida = imagen_compartida(o)
    if compartida:
        print("    Imagen  : %s no está en el silo; se copiará de %s"
              % (os.path.basename(o.base_img), compartida))
    else:
        print("    Imagen  : %s no está en el silo; se descargará de"
              % os.path.basename(o.base_img))
        print("              %s" % o.base_img_url)


def mostrar_plan_maquina(o):
    """Plan de --dry-run de una máquina suelta: genera los ficheros (en el
    directorio .dry-run) y enseña lo que se haría."""
    generar_cloudinit(o, o.vm_name, o.host_name, o.ip, "gluster" if o.glusterfs else "normal")
    construir_comando(o, o.vm_name, o.ram_mb, o.vcpus, [o.disco_main] + o.extras)

    print("→ MODO SIMULACIÓN (--dry-run): no se creará ninguna máquina.")
    print()
    print("✔ Validaciones superadas.")
    print("    Usuario : %s" % o.usuario)
    if o.prefijo_opt:
        print("    Prefijo : %s (sustituye al usuario en los dominios y en los discos)"
              % o.prefijo_opt)
    print("    Máquina : %s  (hostname: %s)" % (o.vm_name, o.host_name))
    print("    Sistema : %s; variante %s" % (descripcion_imagen(o.imagen), o.os_variant))
    print("    Red     : %s (pasarela %s, prefijo /%d)" % (o.red.nombre, o.red.pasarela,
                                                         o.red.prefijo))
    if o.ip:
        print("    IP      : %s, disponible para asignación fija" % o.ip)
    else:
        print("    IP      : por DHCP")
    print("    Recursos: %d MB y %d vCPU" % (o.ram_mb, o.vcpus))
    avisar_imagen_falta(o)
    print()
    print("✔ Ficheros cloud-init generados en %s/" % o.workdir)
    print()
    print("Discos que se crearían en %s:" % o.silo)
    print("    %s  (%s, %s)" % (os.path.basename(o.disco_main),
                                origen_disco_principal(o, o.base_img), o.tam_disco))
    for disco in o.extras:
        print("    %s  (%s)" % (os.path.basename(disco), TAM_DISCO_EXTRA))
    print()
    print("Comando que se ejecutaría:")
    print()
    for linea in texto_comando(o):
        print(linea)
    print()
    if o.glusterfs:
        print("Al terminar cloud-init, la máquina se apagaría y se eliminaría el dominio,")
        print("dejando solo %s como imagen base." % os.path.basename(o.disco_main))
    else:
        print("Al terminar cloud-init, se expulsaría su medio y la máquina se apagaría y se")
        print("volvería a arrancar, para que se ejecute con su configuración definitiva.")
    print()
    print("No se ha creado ni modificado ninguna máquina, disco ni red.")


def ejecutar_maquina(o):
    # Conflictos con lo que ya exista (y --limpiar, si se pidió)
    comprobar_conflictos(o)
    if o.dry_run:
        mostrar_plan_maquina(o)
        return
    raise NoImplementado("crear la máquina")   # fase 3
