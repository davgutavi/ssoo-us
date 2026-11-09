# --- provision: conflictos con lo que ya existe, y --limpiar -----------------------
#
# El script siempre crea dominios y discos nuevos. Si alguno de los que va a
# crear ya existe, se detiene y lo dice; con --limpiar los elimina antes, pero
# solo exactamente esos: nunca otro dominio ni otro fichero del silo.
#
# Aquí están también las comprobaciones que comparten --limpiar, --eliminar y
# --eliminar-todo para no borrar nunca lo que no se debe:
#   - un disco que use cualquier máquina del servidor que no se vaya a eliminar;
#   - una imagen de la que dependa (directa o indirectamente) una copia que se
#     conserva;
#   - las imágenes cloud de partida;
#   - un dominio cuyos discos no están en el silo (no lo ha creado el alumno
#     con este script, aunque su nombre lo parezca: p.ej. con --prefijo).


def cargar_dominios_vecinos(o):
    """Dominios «vecinos»: TODOS los del servidor que no son objetivo de esta
    ejecución. Cualquiera de ellos podría estar usando un fichero de este silo.
    Deja en o.disco_usado_por, para cada fichero, el primer vecino que lo usa."""
    o.disco_usado_por = {}
    for d in dominios_del_servidor():
        if d in o.obj_dominios:
            continue
        for f in discos_persistentes(d):
            o.disco_usado_por.setdefault(f, d)


def dominio_en_silo(o, dominio):
    """¿Es el dominio de este silo? Todos sus discos tienen que estar en el silo
    (salvo el CD-ROM de cloud-init que deja virt-install), y al menos uno."""
    n = 0
    for f in discos_persistentes(dominio, admitir_guion=True):
        if f.startswith(o.silo + "/"):
            n += 1
        elif not f.endswith("cloudinit.iso"):
            return False
    return n > 0


def ficheros_del_silo(o, *patrones):
    """Los ficheros del silo que casan con cada patrón, en el orden de bash
    (cada patrón ordenado por separado)."""
    ficheros = []
    for patron in patrones:
        ficheros += sorted(glob.glob(os.path.join(glob.escape(o.silo), patron)))
    return [f for f in ficheros if os.path.isfile(f)]


def cargar_respaldos(o):
    """Imagen base de cada qcow2 (y .img) del silo, leída una sola vez: un
    qemu-img por fichero, y todo lo demás se calcula sobre ese mapa."""
    if o.respaldos is None:
        o.respaldos = {}
        for f in ficheros_del_silo(o, "*.qcow2", "*.img"):
            o.respaldos[f] = leer_respaldo(f)
    return o.respaldos


def copias_directas(o, ruta):
    """Copias del silo cuya imagen base es este fichero."""
    return sorted(c for c, b in cargar_respaldos(o).items() if b == ruta)


def filtrar_borrables(o, ficheros):
    """Decide cuáles de estos ficheros se pueden eliminar. Se conservan:
      - las imágenes cloud de partida;
      - los que use una máquina que no se va a eliminar;
      - aquellos de los que dependa una copia que se conserva, aunque sea a
        través de otra (si una copia se queda, se queda toda su cadena).
    Devuelve (borrables, conservados), con «nombre: motivo» en conservados.
    Antes hay que llamar a cargar_dominios_vecinos.

    El orden de los motivos de «imagen base de» puede no ser el de bash, que
    recorre sus tablas en el orden de su hash; aquí se recorren ordenadas."""
    respaldos = cargar_respaldos(o)
    candidatos, conservados = [], []
    for f in ficheros:
        if imagen_protegida(o, f):
            conservados.append("%s: es una imagen cloud de partida (nunca se borra)"
                               % os.path.basename(f))
        elif f in o.disco_usado_por:
            conservados.append("%s: lo usa la máquina '%s'"
                               % (os.path.basename(f), o.disco_usado_por[f]))
        else:
            candidatos.append(f)
    # Lo que se conserva por depender de ello una copia que se queda. Se repite
    # hasta que no cambia nada, para recorrer cadenas de cualquier longitud.
    cambio = True
    while cambio:
        cambio = False
        for f in sorted(candidatos):
            for c in sorted(respaldos):
                if respaldos[c] == f and c not in candidatos:
                    candidatos.remove(f)
                    conservados.append("%s: es la imagen base de %s, que se conserva"
                                       % (os.path.basename(f), os.path.basename(c)))
                    cambio = True
                    break
    return [f for f in ficheros if f in candidatos], conservados


def comprobar_conflictos(o, solo_detectar=False):
    """¿Choca lo que se va a crear (o.obj_dominios, o.obj_ficheros) con lo que
    ya existe? Sin --limpiar, error 21 con las opciones; con --limpiar, lo
    enumera y (salvo en --dry-run) lo elimina, previa confirmación. Con
    solo_detectar (la pasada previa a la descarga), --limpiar solo avisa."""
    dominios, ficheros = [], []
    for d in o.obj_dominios:
        if virsh_ok("dominfo", d):
            # Un dominio que se llama como los que crea el script pero tiene
            # sus discos fuera del silo es de otra persona (o hecho a mano):
            # ni se elimina ni se aconseja eliminarlo
            if not dominio_en_silo(o, d):
                fallar(21, "Ya existe una máquina llamada '%s', pero sus discos no están en tu "
                           "silo:\nno la ha creado este script para ti (puede ser de otro usuario "
                           "del servidor), así que no se toca.\n"
                           "Elige otro nombre de máquina, u otro --prefijo." % d)
            dominios.append(d)
    ficheros = [f for f in o.obj_ficheros if os.path.exists(f)]
    if not dominios and not ficheros:
        return

    # Un fichero que ya existe puede ser el disco de otra máquina (hecha a mano
    # con otro nombre, o de otro prefijo) o el respaldo de otras copias.
    # Entonces ni se elimina ni se aconseja eliminarlo.
    if ficheros:
        cargar_dominios_vecinos(o)
        _, conservados = filtrar_borrables(o, ficheros)
        if conservados:
            fallar(21, "Algunos de los discos que este script tendría que crear ya existen y no "
                       "se pueden eliminar:\n" + "".join("  %s\n" % x for x in conservados)
                   + "Elige otro nombre de máquina (o de disco, con --disco), u otro --prefijo.")

    # En la pasada previa a la descarga solo se avisa; con --limpiar, la
    # eliminación se hace en la pasada definitiva
    if solo_detectar and o.limpiar:
        return

    if not o.limpiar:
        msg = "Ya existen elementos que este script tendría que crear:"
        msg += "".join("\n  dominio  %s" % d for d in dominios)
        msg += "".join("\n  disco    %s" % f for f in ficheros)
        msg += "\n\nEl script siempre crea máquinas y discos nuevos. Tienes estas opciones:"
        msg += "\n  a) Eliminarlos tú:"
        msg += "".join("\n       virsh destroy %s; virsh undefine %s --snapshots-metadata" % (d, d)
                       for d in dominios)
        if dominios:
            msg += ("\n       (si la máquina ya está apagada, 'virsh destroy' dará un error; "
                    "es normal)")
        msg += "".join("\n       rm %s" % f for f in ficheros)
        msg += ("\n  b) Repetir el comando añadiendo --limpiar, que elimina exactamente eso y "
                "nada más.")
        if o.cluster and not o.base_opt and disco_base_cluster(o) in ficheros:
            msg += "\n  c) Reutilizar la imagen base que ya tienes, sin volver a construirla:"
            msg += "\n       %s %s--gluster-cluster --base %s" % (
                orden_provision(), prefijo_en_orden(o), os.path.basename(disco_base_cluster(o)))
            msg += "\n     (añade --limpiar si además existen los nodos)"
        fallar(21, msg)

    print("--limpiar: se van a eliminar estos elementos (y solo estos):")
    for d in dominios:
        print("  dominio  %s" % d)
    for f in ficheros:
        print("  disco    %s" % f)
    if o.dry_run:
        print("  (--dry-run: no se elimina nada)")
        print()
        return

    if not confirmar(o, "¿Eliminar estos elementos?"):
        print("Cancelado: no se ha eliminado nada.")
        print("No se ha creado nada. Usa otro nombre de máquina (o --prefijo) para no pisar lo "
              "que ya tienes.")
        raise FinProvision(0)

    for d in dominios:
        virsh("destroy", d)
        if not virsh_ok("undefine", d, "--snapshots-metadata"):
            fallar(21, "No se ha podido eliminar el dominio '%s'. Inténtalo a mano:\n"
                       "  virsh destroy %s; virsh undefine %s --snapshots-metadata" % (d, d, d))
        print("  ✔ dominio %s eliminado" % d)
    for f in ficheros:
        borrar_si_existe(f)
        print("  ✔ disco %s eliminado" % f)
    print()


RESPUESTAS_SI = ("s", "S", "si", "sí", "Si", "Sí", "SI", "SÍ")


def confirmar(o, pregunta):
    """Pregunta sí/no por teclado. Con --si se da por contestada que sí. Sin
    terminal y sin --si no se puede preguntar, y eliminar sin confirmación sería
    peligroso (p.ej. desde un ssh sin sesión): se detiene con el error 23."""
    if o.si:
        print("%s [s/N] s   (--si)" % pregunta)
        return True
    if not sys.stdin.isatty():
        fallar(23, "Hace falta confirmar («%s») y no hay terminal para preguntarte.\n"
                   "No se ha eliminado nada. Si de verdad quieres hacerlo sin preguntas (p.ej. "
                   "desde\notro script), repite el comando añadiendo --si." % pregunta)
    # Como «read -r -p»: la pregunta por stderr; sin respuesta (fin de la
    # entrada), un salto de línea por stdout
    sys.stderr.write("%s [s/N] " % pregunta)
    sys.stderr.flush()
    linea = sys.stdin.readline()
    if not linea.endswith("\n"):
        respuesta = ""
        print()
    else:
        respuesta = linea[:-1].strip(" \t")
    return respuesta in RESPUESTAS_SI


def prefijo_en_orden(o):
    """«--prefijo PREFIJO » en las órdenes que se sugieren, si se usó."""
    return "--prefijo %s " % o.prefijo_opt if o.prefijo_opt else ""
