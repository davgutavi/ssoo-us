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


def crear_dominio(o, nombre):
    """Ejecuta virt-install y registra el dominio para poder deshacerlo. Se
    registra ANTES de lanzarlo: si virt-install define el dominio y luego falla
    (o llega un Ctrl+C), el rollback tiene que eliminarlo."""
    o.dominios_creados.append(nombre)
    codigo = ejecutar_visible(o.virt_install_cmd)
    if codigo != 0:
        raise FalloInesperado(codigo)


def crear_maquina(o, vm, host, ip, modo, disco, base, extras=()):
    """Una máquina: cloud-init, discos y dominio, registrándolo todo para el
    rollback. Lo usan la máquina suelta, la base GlusterFS y cada nodo."""
    generar_cloudinit(o, vm, host, ip, modo)
    construir_comando(o, vm, o.ram_mb, o.vcpus, [disco] + list(extras))

    print("→ Creando el disco %s (%s, %s)…" % (os.path.basename(disco),
                                             origen_disco_principal(o, base), o.tam_disco))
    crear_disco_principal(o, disco, base, o.tam_disco)
    if extras:
        print("→ Creando %d discos extra de %s (%s … %s)…" % (
            len(extras), TAM_DISCO_EXTRA, os.path.basename(extras[0]),
            os.path.basename(extras[-1])))
        for d in extras:
            crear_disco_vacio(o, d, TAM_DISCO_EXTRA)

    print("→ Creando la máquina '%s' con cloud-init…" % vm)
    crear_dominio(o, vm)
    if ip:
        o.ip_esperada[vm] = ip


def ejecutar_maquina(o):
    if o.glusterfs and not o.dry_run:
        raise NoImplementado("--glusterfs")   # fase 4
    # Conflictos con lo que ya exista (y --limpiar, si se pidió)
    comprobar_conflictos(o)
    if o.dry_run:
        mostrar_plan_maquina(o)
        return

    crear_maquina(o, o.vm_name, o.host_name, o.ip, "normal", o.disco_main, o.base_img, o.extras)
    o.creacion_completa = True
    print("✔ Máquina creada y arrancada.")
    print("-------------------------------------------")

    if o.no_wait:
        print("Omitiendo la espera (--no-wait activo).")
        print("NOTA: la máquina sigue configurándose por dentro. No se expulsa el medio de")
        print("      cloud-init ni se reinicia en frío.")
        aviso_on_reboot([o.vm_name])
    # Solo se expulsa el medio de cloud-init, y se reinicia, si consta que la
    # máquina ya terminó de configurarse: antes interrumpiría a cloud-init
    elif esperar_maquinas(o, [o.vm_name]):
        eject_cloudinit_media(o.vm_name)
        reiniciar_en_frio(o, [o.vm_name])
    else:
        aviso_on_reboot([o.vm_name])

    print_summary(o)
    avisar_known_hosts(o, [o.ip or o.ips_detectadas.get(o.vm_name, "")])


def servidor_fqdn():
    nombre = socket.gethostname() or "SERVIDOR"
    return nombre if "." in nombre else nombre + ".lsi.us.es"


def bloque_acceso(o, vm, ip):
    """Líneas de «Acceso» del resumen, iguales para una máquina suelta y para el
    clúster."""
    print("  %-42s %s" % ("ssh administrador@%s" % ip, "con tu clave pública"))
    if o.ssh_pass:
        print("  %-42s %s" % ("", "(o con la contraseña: %s)" % o.ssh_pass))
    elif o.imagen == "ubuntu-base":
        print("  %-42s %s" % ("", "(o con la contraseña de ubuntu-base del boletín 1; sudo la pide)"))
    consola = "virsh console %s" % vm
    if o.no_root and not o.ssh_pass and o.imagen == "ubuntu-base":
        print("  %-42s %s" % (consola, "administrador, con la contraseña de ubuntu-base"))
    elif o.no_root and not o.ssh_pass:
        print("  %-42s %s" % (consola, "(con --no-root y sin --ssh-pass nadie entra por consola: "
                                       "usa SSH)"))
    elif o.no_root:
        print("  %-42s %s" % (consola, "administrador, contraseña: %s" % o.ssh_pass))
    else:
        print("  %-42s %s" % (consola, "root, contraseña: %s" % PASS_CONSOLA))
    if not o.no_graficos:
        print("  virt-viewer --connect qemu+ssh://%s@%s/system %s" % (o.usuario, servidor_fqdn(), vm))
    if o.imagen == "ubuntu-base" and not o.ssh_pass:
        print()
        print("AVISO: 'administrador' conserva la contraseña de ubuntu-base, que es la misma para "
              "toda")
        print("       la clase, y entra por SSH con ella (y con sudo). Cualquier usuario del "
              "servidor")
        print("       podría entrar en esta máquina. Cámbiala dentro con: passwd")


def print_summary(o):
    """Resumen final de una máquina suelta."""
    vm_ip = o.ips_detectadas.get(o.vm_name) or o.ip_vista.get(o.vm_name, "")
    if o.ip and vm_ip and vm_ip != o.ip:
        ip_mostrar = ("%s (fija)  AVISO: la máquina ha respondido en %s; la configuración de red "
                      "no se ha aplicado" % (o.ip, vm_ip))
    elif o.ip:
        ip_mostrar = "%s (fija)" % o.ip
    elif vm_ip:
        ip_mostrar = "%s (DHCP)" % vm_ip
    else:
        ip_mostrar = "(DHCP; consúltala con: virsh domifaddr %s --source agent)" % o.vm_name

    print("-------------------------------------------")
    print("Máquina      : %s  (hostname: %s)" % (o.vm_name, o.host_name))
    print("Sistema      : %s" % descripcion_imagen(o.imagen))
    print("Disco        : %s (%s, copia COW de %s)" % (o.disco_main, o.tam_disco,
                                                       os.path.basename(o.base_img)))
    print("Red          : %s" % o.red.nombre)
    print("IP           : %s" % ip_mostrar)
    print("RAM / vCPUs  : %d MB / %d" % (o.ram_mb, o.vcpus))
    if o.extra_disks:
        print("Discos extra : %s..%s (%d × %s), ver: virsh domblklist %s" % (
            UNIDADES_EXTRA[0], UNIDADES_EXTRA[-1], len(UNIDADES_EXTRA), TAM_DISCO_EXTRA,
            o.vm_name))
    else:
        print("Discos extra : NO")
    if o.glusterfs:
        print("GlusterFS    : glusterfs-server instalado, glusterd habilitado, machine-id reseteado")
    else:
        print("GlusterFS    : NO")
    print()
    print("Acceso:")
    bloque_acceso(o, o.vm_name, vm_ip or o.ip or "IP")
    print()
    print("Para eliminarla con sus discos:  %s %s--eliminar %s"
          % (orden_provision(), prefijo_en_orden(o), o.maquina))
    print("-------------------------------------------")


def avisar_known_hosts(o, ips):
    """El DHCP reutiliza direcciones, así que es habitual que la IP de una
    máquina nueva ya figure en known_hosts con la clave de una máquina anterior:
    el aviso alarmante del apartado B.2 del manual. Aquí solo se avisa y se da
    la orden: no se toca el known_hosts del usuario."""
    kh = o.home + "/.ssh/known_hosts"
    if not os.path.isfile(kh) or not shutil.which("ssh-keygen"):
        return
    avisado = False
    for ip in ips:
        if not ip:
            continue
        if ejecutar(["ssh-keygen", "-F", ip, "-f", kh])[0] == 0:
            if not avisado:
                print()
                print("AVISO: estas IPs ya figuran en tu known_hosts con la clave de otra máquina.")
                print("       Al conectar por SSH verás un aviso de seguridad. Para resolverlo:")
                avisado = True
            print('         ssh-keygen -f "%s" -R "%s"' % (kh, ip))
