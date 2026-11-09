# --- provision: ver y eliminar lo que ya existe (--listar, --eliminar, --eliminar-todo)
#
# Todo parte de libvirt, no de los nombres: los discos de una máquina son los
# que dice «virsh domblklist» (solo los que están en el silo). Nunca se borra
# un disco que use otra máquina ni una imagen de la que dependan otras copias
# (ver filtrar_borrables en limpieza.py).
#
# Las llamadas a virsh y a qemu-img se hacen en el mismo orden que en
# ci-provision.sh: los tests de aceptación cuentan algunas, y la herramienta de
# equivalencia compara el registro entero.


def dominios_propios(o):
    """Dominios del usuario (o del prefijo): los que empiezan por PREFIJO- y
    tienen sus discos en el silo. Los nombres de dominio son de todo el
    servidor: con --prefijo, otro usuario podría tener uno que empiece igual."""
    propios = [d for d in dominios_del_servidor()
               if d.startswith(o.prefijo_dominio + "-") and dominio_en_silo(o, d)]
    return sorted(propios)


def discos_de_dominio(o, dominio):
    """Discos de un dominio que están en el silo (según su definición persistente)."""
    return [f for f in discos_persistentes(dominio, admitir_guion=True)
            if f.startswith(o.silo + "/")]


ESTADOS_DOMINIO = {"running": "en ejecución", "shut off": "apagada", "paused": "pausada",
                   "": "?"}


def estado_dominio(dominio):
    estado = virsh_salida("domstate", dominio).rstrip("\n")
    return ESTADOS_DOMINIO.get(estado, estado)


def ip_dominio(dominio):
    """IP de una máquina en ejecución: la que reporta el agente o, si no, la del
    DHCP. «-» si no hay ninguna."""
    ip = obtener_ip_agente(dominio)
    if not ip:
        for linea in virsh_salida("domifaddr", dominio, "--source", "lease").split("\n"):
            campos = linea.split()
            if len(campos) >= 3 and campos[2] == "ipv4":
                ip = campos[3].split("/")[0] if len(campos) >= 4 else ""
                break
    return ip or "-"


def respaldo_de(o, ruta):
    """Imagen de la que es copia un fichero (solo el nombre), o ""."""
    base = cargar_respaldos(o).get(ruta, "")
    return os.path.basename(base) if base else ""


def copias_de(o, ruta):
    """Copias del silo que dependen de un fichero: «a.qcow2, b.qcow2»."""
    return ", ".join(os.path.basename(c) for c in copias_directas(o, ruta))


def discos_sin_maquina(o):
    """Discos del silo (los qcow2 y la imagen cloud de Ubuntu, que es un .img)
    que no usa ninguna de las máquinas del usuario."""
    usados = set()
    for d in dominios_propios(o):
        usados.update(discos_de_dominio(o, d))
    candidatos = ficheros_del_silo(o, "*.qcow2")
    noble = o.silo + "/" + IMAGEN_NOBLE
    if os.path.isfile(noble):
        candidatos.append(noble)
    return [f for f in candidatos if f not in usados]


def rellenar(texto, ancho):
    """Rellena con espacios hasta ANCHO caracteres (no bytes: por las tildes)."""
    return texto + " " * (ancho - len(texto)) if len(texto) < ancho else texto


def descripcion_discos(o, discos):
    """«server1.qcow2 (copia de X) + N discos extra»."""
    if not discos:
        return "sin discos en el silo"
    desc = os.path.basename(discos[0])
    respaldo = respaldo_de(o, discos[0])
    if respaldo:
        desc += " (copia de %s)" % respaldo
    if len(discos) > 1:
        desc += " + %d discos extra" % (len(discos) - 1)
    return desc


def descripcion_disco_suelto(o, ruta):
    """Qué es un disco del silo que no usa ninguna máquina."""
    if ruta == o.silo + "/" + IMAGEN_NOBLE:
        return "imagen cloud de Ubuntu 24.04: de ella salen las máquinas (no la borres)"
    if ruta == o.silo + "/" + IMAGEN_DEBIAN:
        return "imagen cloud de Debian 12: de ella salen las máquinas (no la borres)"
    partes = []
    respaldo = respaldo_de(o, ruta)
    if respaldo:
        partes.append("copia de %s" % respaldo)
    dependientes = copias_de(o, ruta)
    if dependientes:
        partes.append("imagen base de: %s" % dependientes)
    return "; ".join(partes) or "disco suelto"


# --- --listar --------------------------------------------------------------------

def listar_maquinas(o):
    cargar_respaldos(o)
    dominios = dominios_propios(o)
    if not dominios:
        print("No tienes máquinas (dominios que empiecen por %s-)." % o.prefijo_dominio)
    else:
        print("Máquinas %s-* (%d):" % (o.prefijo_dominio, len(dominios)))
        for d in dominios:
            estado = estado_dominio(d)
            ip = ip_dominio(d) if estado == "en ejecución" else "-"
            print("  %s %s %s %s" % (rellenar(d, 26), rellenar(estado, 13), rellenar(ip, 16),
                                     descripcion_discos(o, discos_de_dominio(o, d))))

    sueltos = discos_sin_maquina(o)
    if sueltos:
        print()
        print("Discos del silo sin máquina:")
        for f in sueltos:
            print("  %s %s" % (rellenar(os.path.basename(f), 26),
                              descripcion_disco_suelto(o, f)))


# --- --eliminar y --eliminar-todo -------------------------------------------------

class PlanEliminacion:
    """Lo que se eliminaría y lo que se conserva (con el motivo)."""

    def __init__(self):
        self.dominios = []
        self.ficheros = []
        self.dirs = []
        self.conservados = []
        self.sin_nada = []

    def hay_algo(self):
        return bool(self.dominios or self.ficheros or self.dirs)


def planificar_eliminacion(o, nombres):
    """El plan para eliminar las máquinas indicadas por su nombre corto."""
    plan = PlanEliminacion()
    ficheros = []
    for m in nombres:
        vm = "%s-%s" % (o.prefijo_dominio, m)
        habia = False
        if virsh_ok("dominfo", vm) and not dominio_en_silo(o, vm):
            # Se llama como las tuyas, pero sus discos no están en tu silo
            plan.conservados.append("máquina %s: sus discos no están en tu silo (no la ha "
                                    "creado este script para ti)" % vm)
            habia = True
        elif virsh_ok("dominfo", vm):
            plan.dominios.append(vm)
            habia = True
            for f in discos_de_dominio(o, vm):
                if f not in ficheros:
                    ficheros.append(f)
        # También los discos que llevan su nombre aunque no estén conectados
        # (una imagen base hecha con --glusterfs, restos de otra ejecución)
        principal = o.silo + "/" + disco_de(o, m)
        extra = ficheros_del_silo(o, glob.escape("%s%s" % (o.prefijo_fichero, m)) + "-vd?.qcow2")
        for f in [principal] + extra:
            if os.path.isfile(f) and f not in ficheros:
                ficheros.append(f)
                habia = True
        for d in ("%s/cloudinit-%s" % (o.silo, vm), "%s/cloudinit-%s.dry-run" % (o.silo, vm)):
            if os.path.isdir(d):
                plan.dirs.append(d)
                habia = True
        if not habia:
            plan.sin_nada.append(m)

    # Lo que use otra máquina, o de lo que dependan copias que se conservan,
    # se conserva
    o.obj_dominios = list(plan.dominios)
    o.obj_ficheros = list(ficheros)
    cargar_dominios_vecinos(o)
    if ficheros:
        plan.ficheros, conservados = filtrar_borrables(o, ficheros)
        plan.conservados += conservados
    return plan


def mostrar_plan_eliminacion(o, plan):
    if plan.hay_algo():
        print("Se va a eliminar:")
        for d in plan.dominios:
            print("  máquina  %s (%s)" % (d, estado_dominio(d)))
        for f in plan.ficheros:
            print("  disco    %s" % f)
        for x in plan.dirs:
            print("  ficheros %s/" % x)
    if plan.conservados:
        print("Se conserva:")
        for x in plan.conservados:
            print("  %s" % x)
    for x in plan.sin_nada:
        print("  (de '%s' no hay nada: ni la máquina %s-%s ni discos con ese nombre)"
              % (x, o.prefijo_dominio, x))


def ejecutar_eliminacion(plan):
    for d in plan.dominios:
        virsh("destroy", d)
        if not virsh_ok("undefine", d, "--snapshots-metadata"):
            fallar(22, "No se ha podido eliminar la máquina '%s'. Inténtalo a mano:\n"
                       "  virsh destroy %s; virsh undefine %s --snapshots-metadata" % (d, d, d))
        print("  ✔ máquina %s eliminada" % d)
    for f in plan.ficheros:
        borrar_si_existe(f)
        print("  ✔ disco %s eliminado" % f)
    for x in plan.dirs:
        borrar_ruta(x)
        print("  ✔ ficheros %s eliminados" % x)


def cancelar_eliminacion():
    print("Cancelado: no se ha eliminado nada.")
    raise FinProvision(0)


def eliminar_maquinas(o, nombres):
    plan = planificar_eliminacion(o, nombres)

    if not plan.hay_algo():
        msg = "No hay nada que eliminar."
        for x in plan.sin_nada:
            msg += "\n  '%s': no existe la máquina %s-%s ni discos con ese nombre." % (
                x, o.prefijo_dominio, x)
        for x in plan.conservados:
            msg += "\n  %s (se conserva)." % x
        msg += "\nPara ver lo que tienes: %s --listar" % orden_provision()
        fallar(22, msg)

    mostrar_plan_eliminacion(o, plan)
    if o.dry_run:
        print("  (--dry-run: no se elimina nada)")
        return
    if not confirmar(o, "¿Eliminar?"):
        cancelar_eliminacion()
    ejecutar_eliminacion(plan)


def eliminar_todo(o):
    nombres = [d[len(o.prefijo_dominio) + 1:] for d in dominios_propios(o)]
    plan = planificar_eliminacion(o, nombres) if nombres else PlanEliminacion()

    # Directorios cloud-init que quedaran de máquinas que ya no existen
    patron = glob.escape("%s/cloudinit-%s" % (o.silo, o.prefijo_dominio)) + "-*"
    for d in sorted(glob.glob(patron)):
        if os.path.isdir(d) and d not in plan.dirs:
            plan.dirs.append(d)

    # Discos del silo que quedarían sin máquina, salvo las imágenes cloud. Se
    # comprueba contra todos los dominios del servidor y contra todas las copias
    # del silo. Los discos de las máquinas ya están decididos (si el alumno dice
    # que no a estos, sus copias se quedan y no pueden perder su imagen base);
    # aquí solo se decide qué otros se pueden ofrecer.
    candidatos = []
    for f in ficheros_del_silo(o, "*.qcow2"):
        if imagen_protegida(o, f) or f in plan.ficheros:
            continue
        if o.prefijo_opt and not os.path.basename(f).startswith(o.prefijo_opt + "-"):
            continue
        candidatos.append(f)
    sueltos = []
    if candidatos:
        print("Comprobando qué discos del silo usa alguna máquina…")
        o.obj_dominios = list(plan.dominios)
        cargar_dominios_vecinos(o)
        borrables, conservados = filtrar_borrables(o, plan.ficheros + candidatos)
        sueltos = [f for f in borrables if f in candidatos]
        plan.conservados += conservados

    if not plan.hay_algo() and not sueltos:
        fallar(22, "No hay nada que eliminar: ni máquinas %s-* ni discos sin máquina en %s\n"
                   "(aparte de las imágenes cloud %s y %s, que se conservan siempre)."
               % (o.prefijo_dominio, o.silo, IMAGEN_NOBLE, IMAGEN_DEBIAN))

    mostrar_plan_eliminacion(o, plan)
    if sueltos:
        print("Discos del silo sin máquina (se preguntará aparte):")
        for f in sueltos:
            print("  disco    %s" % f)
    if o.dry_run:
        print("  (--dry-run: no se elimina nada)")
        return

    if plan.hay_algo():
        if not confirmar(o, "¿Eliminar las máquinas con sus discos?"):
            cancelar_eliminacion()
        ejecutar_eliminacion(plan)
    if sueltos:
        if confirmar(o, "¿Eliminar también los %d discos sin máquina?" % len(sueltos)):
            for f in sueltos:
                borrar_si_existe(f)
                print("  ✔ disco %s eliminado" % f)
        else:
            print("Los discos sin máquina se conservan.")
