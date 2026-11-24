#!/usr/bin/env bats
# Tests de aceptación del asistente de «ssoo-us provision» (--menu).
#
# No se importan de ci-provision: su asistente usa whiptail y el de ssoo-us,
# prompt_toolkit. Son los mismos casos que los de ci-provision.bats (que allí
# se quedan con skip), con el mismo entorno y los mismos mocks, pero las
# respuestas salen de un guion (SSOO_US_ASISTENTE_GUION: una línea por pantalla)
# y cada pantalla se anota en un registro (SSOO_US_ASISTENTE_REGISTRO), en lugar
# del whiptail simulado. Ver PantallasGuion en src/pantallas.py.

setup() {
    load 'helpers'
    load 'bats/bats-support/load'
    load 'bats/bats-assert/load'
    preparar_entorno
    export SSOO_US_ASISTENTE_GUION="$BATS_TEST_TMPDIR/guion"
    export SSOO_US_ASISTENTE_REGISTRO="$BATS_TEST_TMPDIR/pantallas"
}

qinfo() {
    qemu-img info --output=json "$1" | jq -r "$2"
}

guion() {
    printf '%s\n' "$@" > "$SSOO_US_ASISTENTE_GUION"
}

pantalla() {   # pantalla TEXTO: alguna pantalla lo ha mostrado
    grep -qF -- "$1" "$SSOO_US_ASISTENTE_REGISTRO"
}

@test "ssoo-us asistente: construye el comando, lo ejecuta y vuelve al menú" {
    guion basica server1 "" "" "extra-disks no-root" si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    # La máquina básica parte de Ubuntu 24.04, la imagen por defecto
    pantalla "elegir_uno: Sistema de la máquina: | *noble=Ubuntu 24.04 (la imagen por defecto) ; debian12="
    assert_output --partial "→ $ORDEN --extra-disks --no-root server1"
    assert_output --partial "Sin cambios."
    dominio_existe "${USUARIO}-server1"
    [ -e "$SILO/server1-vdg.qcow2" ]
    [ "$(qinfo "$SILO/server1.qcow2" '."backing-filename"')" = "noble-server-cloudimg-amd64.img" ]
    [ "$(grep -c '^menu: ¿Qué quieres hacer?' "$SSOO_US_ASISTENTE_REGISTRO")" -eq 2 ]
    # El resumen queda en la ficha, que solo puede leer su dueño
    local ficha="$SILO/server1-ficha.txt"
    assert_output --partial "Estos datos quedan guardados en $ficha"
    [ "$(head -1 "$ficha")" = "Ficha de la máquina ${USUARIO}-server1 (la escribe ssoo-us provision)" ]
    grep -qF "  $ORDEN --extra-disks --no-root server1" "$ficha"
    grep -q "^Máquina      : ${USUARIO}-server1" "$ficha"
    grep -q "^Acceso:" "$ficha"
    [ "$(stat -f %Lp "$ficha" 2>/dev/null || stat -c %a "$ficha")" = "600" ]
}

@test "ssoo-us asistente: el clúster deja elegir la imagen de la base y los discos de crea-entorno.sh" {
    guion cluster debian12 discos-crea-entorno si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "*noble=Imagen cloud de Ubuntu 24.04, la misma que SERVER1 (recomendada) ; ubuntu-base="
    assert_output --partial "→ $ORDEN --gluster-cluster --imagen debian12 --discos-nodo 7"
    [ "$(qinfo "$SILO/gluster-base.qcow2" '."backing-filename"')" = "debian12.qcow2" ]
    [ -e "$SILO/server4-vdh.qcow2" ]
    # Una ficha por nodo, cada una con el resumen de la infraestructura
    assert_output --partial "Estos datos quedan guardados en una ficha por nodo"
    for n in server1 server2 server3 server4; do
        [ "$(head -1 "$SILO/$n-ficha.txt")" = "Ficha del nodo ${USUARIO}-$n de la infraestructura GlusterFS (la escribe ssoo-us provision)" ]
        grep -q "^Infraestructura GlusterFS creada" "$SILO/$n-ficha.txt"
    done

    # Con la base ya hecha, ofrece reutilizarla y no pregunta la imagen
    guion cluster "" limpiar si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "elegir_uno: Ya tienes gluster-base.qcow2 en el silo. | *usar="
    assert_output --partial "→ $ORDEN --gluster-cluster --base gluster-base.qcow2 --limpiar"
}

@test "ssoo-us asistente: sin clave SSH ofrece crearla antes de las pantallas de crear" {
    rm -f "$HOME/.ssh/id_rsa.pub"
    # Si no la quiere, vuelve al menú sin preguntar nada más
    guion basica "<atrás>" cluster "<atrás>" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    [ "$(grep -c "^confirmar: No tienes clave SSH ($HOME/.ssh/id_rsa)" "$SSOO_US_ASISTENTE_REGISTRO")" -eq 2 ]
    ! pantalla "Nombre corto de la máquina"
    [ ! -e "$HOME/.ssh/id_rsa" ]
    [ "$(llamadas '^virt-install')" -eq 0 ]

    # Si la quiere, la crea (sin contraseña) y sigue con las pantallas
    : > "$SSOO_US_ASISTENTE_REGISTRO"
    guion basica si "" server1 "" "" "" si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "aviso: ✔ Clave SSH creada: $HOME/.ssh/id_rsa (privada)"
    assert_output --partial "→ $ORDEN server1"
    ssh-keygen -y -P "" -f "$HOME/.ssh/id_rsa" >/dev/null
    grep -qF "$(cut -d' ' -f2 "$HOME/.ssh/id_rsa.pub")" "$SILO/cloudinit-${USUARIO}-server1/cip-user.yaml"

    # Con la privada y sin la pública, no la ofrece: dice cómo recuperarla
    rm "$HOME/.ssh/id_rsa.pub"
    : > "$SSOO_US_ASISTENTE_REGISTRO"
    guion basica "" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    ! pantalla "confirmar: No tienes clave SSH"
    pantalla "ssh-keygen -y -f $HOME/.ssh/id_rsa > $HOME/.ssh/id_rsa.pub"
}

@test "ssoo-us asistente: salir del menú principal no hace nada" {
    for salida in "<atrás>" "<salir>" salir; do
        guion "$salida"
        run bash "$SCRIPT" --menu </dev/null
        assert_success
        assert_output --partial "Sin cambios."
    done
    [ "$(llamadas '^virt-install')" -eq 0 ]
}

@test "ssoo-us asistente: almacenamiento extra pide el nombre, sugiere la IP .2 y marca los discos; eliminar elige de la lista" {
    guion extra server1 "" 192.168.7.2 "" extra-disks si eliminar server1 si salir
    run bash "$SCRIPT" --menu --si </dev/null
    assert_success
    pantalla "elegir_uno: Red de la máquina: | dhcp=DHCP (la red le da una IP) ; *fija=IP fija"
    pantalla "| inicial=192.168.7.2"
    pantalla "elegir_uno: Sistema de la máquina: | *noble="
    pantalla "| *extra-disks=Seis discos extra vdb..vdg de 40G ; ssh-pass="
    assert_output --partial "→ $ORDEN --si --extra-disks server1 192.168.7.2"
    assert_output --partial "→ $ORDEN --si --eliminar server1"
    pantalla "elegir_varios: Marca las máquinas a eliminar (con sus discos y sus ficheros cloud-init): | server1=server1  (en ejecución)"
    ! dominio_existe "${USUARIO}-server1"
    [ ! -e "$SILO/server1-vdb.qcow2" ]
    # Y su ficha, con ella
    assert_output --partial "✔ ficha $SILO/server1-ficha.txt eliminada"
    [ ! -e "$SILO/server1-ficha.txt" ]
}

@test "ssoo-us asistente: DHCP o IP fija; con IP fija, la primera libre y los avisos en el mismo paso" {
    # La máquina básica, con DHCP por defecto: sin paso de IP
    guion basica server1 "" "" "" si salir
    run bash "$SCRIPT" --menu --dry-run </dev/null
    assert_success
    pantalla "elegir_uno: Red de la máquina: | *dhcp=DHCP (la red le da una IP) ; fija=IP fija"
    ! pantalla "texto: IP fija"
    assert_output --partial "→ $ORDEN --dry-run server1"$'\n'

    # IP fija: propone la primera libre (.2); una del DHCP y otra que ya responde
    # se avisan en el mismo paso, que conserva lo escrito
    echo 192.168.7.5 > "$MOCK_STATE/ping_responde"
    guion basica server1 fija 192.168.7.200 "" 192.168.7.5 "" 192.168.7.6 "" "" si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "texto: IP fija de la máquina, dentro de tu red virtual. / IPs libres de tu red: /   192.168.7.2 - 192.168.7.127 | inicial=192.168.7.2"
    pantalla "aviso: La IP '192.168.7.200' está dentro del rango DHCP"
    pantalla "También puedes volver atrás y elegir DHCP."
    pantalla "| inicial=192.168.7.200"
    pantalla "aviso: Algo responde ya en la IP '192.168.7.5'"
    assert_output --partial "→ $ORDEN server1 192.168.7.6"
    dominio_existe "${USUARIO}-server1"
}

@test "ssoo-us asistente: la lista muestra máquinas y discos sueltos, con ficha al elegir" {
    run bash "$SCRIPT" --extra-disks server1
    assert_success
    run bash "$SCRIPT" --imagen debian12 --glusterfs glusterbase
    assert_success
    guion listar "m:${USUARIO}-server1" "" "d:$SILO/glusterbase.qcow2" "" "<atrás>" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "menu: Tus máquinas virtuales y los discos del silo."
    grep -qE -- "m:${USUARIO}-server1=server1 +en ejecución +192\.168\.7\.[0-9]+ +7 disco\(s\)" "$SSOO_US_ASISTENTE_REGISTRO"
    pantalla "d:$SILO/glusterbase.qcow2=glusterbase.qcow2  [sin máquina] copia de debian12.qcow2"
    pantalla "Máquina : ${USUARIO}-server1   (hostname: server1)"
    pantalla "          server1-vdg.qcow2"
    pantalla "Disco   : glusterbase.qcow2"
    pantalla "Tamaño  : 40 GiB (virtual)"
    assert_output --partial "Sin cambios."
}

@test "ssoo-us asistente: la lista no se sale del cuadro ni repite «imagen cloud»" {
    run bash "$SCRIPT" server1
    assert_success
    guion listar "<atrás>" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "=noble-server-cloudimg-amd64.img  [imagen cloud] Ubuntu 24.04"
    ! pantalla "imagen cloud imagen cloud"
}

@test "ssoo-us asistente: Ctrl+C en lo que lanza lo interrumpe y lo deshace" {
    export MOCK_VIRT_INSTALL_CTRL_C=1
    guion basica server1 "" debian12 no-root si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    assert_output --partial "Interrumpido por el usuario."
    assert_output --partial "(el comando ha terminado con el código 130)"
    ! dominio_existe "${USUARIO}-server1"
    [ ! -e "$SILO/server1.qcow2" ]
}

@test "ssoo-us asistente: la lista ve lo creado desde el propio menú" {
    run bash "$SCRIPT" --imagen debian12 --glusterfs glusterbase
    assert_success
    # Se lista (se carga el mapa), se crea server1 desde el menú y se vuelve a listar
    guion listar "<atrás>" basica server1 "" debian12 no-root si \
        listar "m:${USUARIO}-server1" "" "<atrás>" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    dominio_existe "${USUARIO}-server1"
    pantalla "          server1.qcow2 (copia de debian12.qcow2)"
}

@test "ssoo-us asistente: la contraseña no se muestra en el comando; sin prompt_toolkit, error 38; sin más opciones" {
    guion basica web "" "" ssh-pass Secreta1 si salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    assert_output --partial "→ $ORDEN --ssh-pass •••••• web"
    refute_output --partial "--ssh-pass Secreta1"
    ! pantalla "Secreta1"
    grep -q "password: 'Secreta1'" "$SILO/cloudinit-${USUARIO}-web/cip-user.yaml"

    # Sin el módulo (y sin guion), el asistente no puede abrirse
    local py="$BATS_TEST_TMPDIR/py/prompt_toolkit"
    mkdir -p "$py"
    echo "raise ImportError('simulado')" > "$py/__init__.py"
    SSOO_US_ASISTENTE_GUION= PYTHONPATH="${py%/*}" run bash "$SCRIPT" --menu
    assert_failure 38
    assert_output --partial "python3-prompt-toolkit"
    run bash "$SCRIPT" --menu server1
    assert_failure 10
    run bash "$SCRIPT" --menu --extra-disks
    assert_failure 10
}

@test "ssoo-us asistente: --menu --dry-run no crea nada; la contraseña no va en la línea de órdenes" {
    guion basica web "" "" ssh-pass Secreta1 si salir
    # Un sitecustomize que anota los argumentos de cada python: así se ve qué
    # recibe el proceso hijo
    local bin="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$bin"
    printf 'import sys\nwith open("%s/argv", "a") as f:\n    f.write(" ".join(sys.argv) + "\\n")\n' "$MOCK_STATE" > "$bin/sitecustomize.py"
    PYTHONPATH="$bin" run bash "$SCRIPT" --menu --dry-run </dev/null
    assert_success
    assert_output --partial "→ $ORDEN --dry-run --ssh-pass •••••• web"
    assert_output --partial "MODO SIMULACIÓN"
    ! dominio_existe "${USUARIO}-web"
    grep -q -- "provision --dry-run --ssh-pass - web" "$MOCK_STATE/argv"
    ! grep -q "Secreta1" "$MOCK_STATE/argv"
}

@test "ssoo-us asistente: rechaza nombres que empiezan por '-' y la ficha respeta --prefijo" {
    guion basica -h "" "<atrás>" salir
    run bash "$SCRIPT" --menu </dev/null
    assert_success
    pantalla "El nombre '-h' no es válido"
    [ "$(llamadas '^virt-install')" -eq 0 ]
    run bash "$SCRIPT" --prefijo demo server1
    assert_success
    guion listar "m:demo-server1" "" "<atrás>" salir
    run bash "$SCRIPT" --prefijo demo --menu </dev/null
    assert_success
    pantalla "--prefijo demo --eliminar server1"
}
