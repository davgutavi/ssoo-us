# --- provision: espera a que cloud-init termine, apagado y reinicio en frío -----------
#
# Una espera de duración fija no sirve: las medidas en los tres servidores
# mostraron que cloud-init tarda entre 60 y 140 segundos según lo que instale y
# la carga del servidor. En su lugar se consulta al guest agent:
#
#   1. Que el agente responda con la IP de la máquina ya dice que ha arrancado
#      y, en una máquina recién creada, que apt ha terminado (el agente se
#      instala con cloud-init).
#   2. Además, a través del propio agente se ejecuta 'cloud-init status' dentro
#      de la máquina, que dice exactamente si ha terminado. Esto es
#      imprescindible en los nodos del clúster, donde el agente ya está
#      instalado de antes y responde mucho antes de que cloud-init acabe.
#
# Si el agente no permite ejecutar órdenes, se recurre solo al punto 1 con un
# pequeño margen, y se avisa.

ORDEN_CLOUDINIT_STATUS = ('{"execute":"guest-exec","arguments":{"path":"/usr/bin/cloud-init",'
                          '"arg":["status"],"capture-output":true}}')


def ahora():
    """Segundos enteros, como $SECONDS en bash."""
    return int(time.monotonic())


def limpiar_linea():
    if sys.stdout.isatty():
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def json_o_nada(texto):
    try:
        return json.loads(texto)
    except ValueError:
        return None


def campo_return(datos, campo):
    """jq -r '.return.CAMPO // empty'."""
    if isinstance(datos, dict) and isinstance(datos.get("return"), dict):
        valor = datos["return"].get(campo)
        if valor is not None and valor is not False:
            return valor
    return None


def cloudinit_status(vm):
    """Ejecuta 'cloud-init status' dentro de la máquina a través del guest agent
    y devuelve su estado (done, running, error...), o None si no se ha podido
    consultar. Desde cloud-init 23.4 (Ubuntu 24.04), 'cloud-init status' escribe
    "done" aunque haya terminado con avisos; lo que lo distingue es el código de
    salida: 0 bien, 1 error, 2 terminado con avisos ("degraded")."""
    _, r, _ = virsh("qemu-agent-command", vm, "--timeout", "5", ORDEN_CLOUDINIT_STATUS)
    pid = campo_return(json_o_nada(r), "pid")
    if pid is None:
        return None
    pid = pid if isinstance(pid, str) else json.dumps(pid)
    for _ in range(10):
        time.sleep(1)
        _, s, _ = virsh("qemu-agent-command", vm, "--timeout", "5",
                        '{"execute":"guest-exec-status","arguments":{"pid":%s}}' % pid)
        datos = json_o_nada(s)
        if campo_return(datos, "exited") is not True:
            continue
        try:
            salida = base64.b64decode(campo_return(datos, "out-data") or "").decode("utf-8", "replace")
        except (ValueError, TypeError):
            salida = ""
        codigo = campo_return(datos, "exitcode")
        estado = ""
        for linea in salida.split("\n"):
            if linea.startswith("status:"):
                estado = linea[len("status:"):].lstrip(" ")
                break
        if estado == "done" and codigo in (2, "2"):
            estado = "degraded done"
        return estado
    return None


def maquina_lista(o, vm):
    """¿Está la máquina lista? Deja la IP en o.ips_detectadas y el estado en
    o.estado_ci."""
    ip = obtener_ip_agente(vm)
    if not ip:
        return False
    o.ip_vista[vm] = ip
    # Si se pidió IP fija, se exige esa IP concreta
    if o.ip_esperada.get(vm) and ip != o.ip_esperada[vm]:
        return False

    estado = cloudinit_status(vm)
    if estado is not None:
        o.fallos_consulta[vm] = 0
        o.asumido_desde.pop(vm, None)
        if estado == "done":
            o.ips_detectadas[vm], o.estado_ci[vm] = ip, "done"
            return True
        if estado in ("error", "degraded done"):
            o.ips_detectadas[vm], o.estado_ci[vm] = ip, "error"
            return True
        return False   # running, not run, disabled...

    # No se ha podido consultar cloud-init. Si pasa varias veces seguidas, se da
    # la máquina por lista en cuanto lleve GRACE_SECS respondiendo.
    o.fallos_consulta[vm] = o.fallos_consulta.get(vm, 0) + 1
    if o.fallos_consulta[vm] >= 3 and not o.exigir_estado_ci:
        if vm not in o.asumido_desde:
            o.asumido_desde[vm] = ahora()
        elif ahora() - o.asumido_desde[vm] >= o.esperas["GRACE_SECS"]:
            o.ips_detectadas[vm], o.estado_ci[vm] = ip, "asumido"
            return True
    return False


def esperar_maquinas(o, vms):
    """Espera hasta que todas las máquinas estén operativas o se agote
    WAIT_TIMEOUT. True si todas terminaron."""
    pendientes = list(vms)
    inicio = ahora()
    print("Esperando a que cloud-init termine de configurar %d máquina(s)." % len(pendientes))
    print("Puede tardar entre uno y tres minutos, según lo que haya que instalar.")
    while True:
        restantes = []
        for vm in pendientes:
            if maquina_lista(o, vm):
                transcurrido = ahora() - inicio
                limpiar_linea()
                estado, ip = o.estado_ci[vm], o.ips_detectadas[vm]
                if estado == "done":
                    print("✔ %s operativa tras %ds. IP: %s" % (vm, transcurrido, ip))
                elif estado == "error":
                    print("⚠ %s ha arrancado (IP %s), pero cloud-init informa de errores tras %ds."
                          % (vm, ip, transcurrido))
                    print("  Entra en la máquina y revisa: sudo cloud-init status --long")
                else:
                    print("✔ %s responde tras %ds. IP: %s" % (vm, transcurrido, ip))
                    print("  (no se ha podido consultar el estado de cloud-init; se da por "
                          "terminado)")
            else:
                restantes.append(vm)
        pendientes = restantes
        if not pendientes:
            return True

        transcurrido = ahora() - inicio
        if transcurrido >= o.esperas["WAIT_TIMEOUT"]:
            limpiar_linea()
            err = sys.stderr
            print("AVISO: no ha(n) terminado en %ds: %s" % (o.esperas["WAIT_TIMEOUT"],
                                                         " ".join(pendientes)), file=err)
            print("       Puede que siga(n) instalando paquetes. Comprueba su estado con:", file=err)
            for vm in pendientes:
                print("         virsh domifaddr %s --source agent" % vm, file=err)
                vista = o.ip_vista.get(vm)
                if vista:
                    esperada = o.ip_esperada.get(vm)
                    if esperada and vista != esperada:
                        print("         (%s responde en %s y no en la IP fija %s: la configuración "
                              "de red no se ha aplicado)" % (vm, vista, esperada), file=err)
                    else:
                        print("         (%s ya responde en %s; cloud-init sigue trabajando)"
                              % (vm, vista), file=err)
            print("       Si no responde, entra por consola: virsh console NOMBRE", file=err)
            return False

        if sys.stdout.isatty():
            sys.stdout.write("\r  … %ds  (esperando: %s)" % (transcurrido, " ".join(pendientes)))
            sys.stdout.flush()
        time.sleep(o.esperas["POLL_SECS"])


def apagar_maquina(o, vm):
    """Apaga una máquina de forma limpia y espera a que esté parada. False si no
    se ha apagado en SHUTDOWN_TIMEOUT."""
    virsh("shutdown", vm)
    return esperar_apagada(o, vm)


def esperar_apagada(o, vm):
    """Espera a que una máquina esté parada (a quien ya se le ha pedido apagarse)."""
    inicio = ahora()
    while True:
        if virsh_salida("domstate", vm).rstrip("\n") == "shut off":
            return True
        if ahora() - inicio >= o.esperas["SHUTDOWN_TIMEOUT"]:
            return False
        time.sleep(2)


# Reinicio en frío al terminar
#
# Con --cloud-init, virt-install arranca la máquina con una definición "de
# instalación" que tiene on_reboot=destroy: cuenta con estar él presente en el
# primer reinicio para volver a arrancarla con la definición definitiva
# (on_reboot=restart). Como se lanza con --noautoconsole, termina enseguida y
# nadie hace ese segundo arranque: el primer 'reboot' dentro de la máquina la
# apagaría. Y una instantánea tomada en caliente guardaría ese on_reboot=destroy,
# así que el problema volvería al revertirla.
#
# Apagándola y arrancándola desde fuera, pasa a ejecutarse con la definición
# persistente, que es la buena. Solo se hace cuando cloud-init ya ha terminado:
# antes lo interrumpiría.

def aviso_on_reboot(vms):
    """Aviso para cuando no se ha podido (o no se debía) reiniciar."""
    err = sys.stderr
    print("AVISO: tras crearlas, estas máquinas se apagan en su primer reinicio: %s"
          % " ".join(vms), file=err)
    print("       Cuando terminen de configurarse, apágalas y arráncalas desde fuera:", file=err)
    print("         virsh shutdown NOMBRE   (y, cuando esté apagada)   virsh start NOMBRE", file=err)
    print("       Hazlo antes de tomar instantáneas.", file=err)


def reiniciar_en_frio(o, vms):
    print("→ Apagando y volviendo a arrancar %d máquina(s), para que usen su configuración "
          "definitiva…" % len(vms))
    for vm in vms:
        virsh("shutdown", vm)
    arrancadas, fallidas = [], []
    for vm in vms:
        if esperar_apagada(o, vm) and virsh_ok("start", vm):
            arrancadas.append(vm)
        else:
            fallidas.append(vm)

    # Que vuelvan a responder (con su IP fija, si la tienen)
    inicio = ahora()
    pendientes = list(arrancadas)
    while pendientes:
        restantes = []
        for vm in pendientes:
            ip = obtener_ip_agente(vm)
            if ip and (not o.ip_esperada.get(vm) or ip == o.ip_esperada[vm]):
                o.ips_detectadas[vm] = ip
            else:
                restantes.append(vm)
        pendientes = restantes
        if not pendientes:
            break
        if ahora() - inicio >= o.esperas["WAIT_TIMEOUT"]:
            print("AVISO: no han vuelto a responder en %ds: %s"
                  % (o.esperas["WAIT_TIMEOUT"], " ".join(pendientes)), file=sys.stderr)
            print("       Comprueba su estado con: virsh list --all", file=sys.stderr)
            break
        time.sleep(o.esperas["POLL_SECS"])

    for vm in arrancadas:
        if on_reboot_vivo(vm) == "restart":
            print("✔ %s reiniciada: ya puedes reiniciarla desde dentro y tomar instantáneas." % vm)
        else:
            fallidas.append(vm)
    if fallidas:
        aviso_on_reboot(fallidas)
