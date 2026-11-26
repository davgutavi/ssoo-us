#!/usr/bin/env bats
# Tests de aceptación de ssoo-us (no se importan de ci-provision): si el alumno
# no tiene silo o red virtual, provision ofrece crearlos. Con el entorno de
# ci-provision.bats y un virsh que, además, sabe de silos y crea redes
# (mocks-ssoo-us/virsh). Sin terminal, no se puede preguntar: con --si.

setup() {
    load 'helpers'
    load 'bats/bats-support/load'
    load 'bats/bats-assert/load'
    preparar_entorno
    export PATH="$ACEPTACION_DIR/mocks-ssoo-us:$PATH"
}

@test "ssoo-us sin silo ni red, con --si: crea el silo, la red y la máquina" {
    rm -rf "$SILO"
    quitar_red "${USUARIO}-red"
    definir_red "otro-red" 192.168.1.1 255.255.255.0 192.168.1.128 192.168.1.254
    echo "192.168.2.0/24 dev eth1 proto kernel scope link src 192.168.2.5" > "$MOCK_STATE/rutas"
    # Con la umask de una cuenta con grupo propio (002), como en los servidores
    umask 002
    run bash "$SCRIPT" --si --no-wait server1 </dev/null
    assert_success
    assert_output --partial "No tienes silo: el directorio $SILO"
    assert_output --partial "✔ Silo creado: $SILO"
    assert_output --partial "✔ Registrado en libvirt como '${USUARIO}-imagenesMV'"
    assert_output --partial "No tienes red virtual. Se creará '${USUARIO}-red': NAT, 192.168.3.0/24"
    assert_output --partial "✔ Red virtual creada: ${USUARIO}-red (192.168.3.0/24"
    [ "$(llamadas "^virsh pool-define-as ${USUARIO}-imagenesMV dir --target $SILO\$")" -eq 1 ]
    [ "$(cat "$MOCK_STATE/silo-${USUARIO}-imagenesMV")" = "$SILO" ]
    [ -f "$MOCK_STATE/silo-${USUARIO}-imagenesMV.activo" ]
    grep -qF "<ip address='192.168.3.1' netmask='255.255.255.0'>" "$MOCK_STATE/red-${USUARIO}-red.xml"
    [ ! -f "$MOCK_STATE/red-${USUARIO}-red.inactiva" ]
    [ -f "$MOCK_STATE/red-${USUARIO}-red.autostart" ]
    # Y la máquina, en la red nueva y en el silo nuevo
    dominio_existe "${USUARIO}-server1"
    [ -e "$SILO/server1.qcow2" ]
    # La imagen descargada, en 0644 aunque la umask sea 002 (no la puede
    # escribir el grupo kvm cuando libvirt se la asigna)
    local imagen="$SILO/noble-server-cloudimg-amd64.img"
    [ "$(stat -f %Lp "$imagen" 2>/dev/null || stat -c %a "$imagen")" = "644" ]
    grep -q "network=${USUARIO}-red" "$MOCK_STATE/log"
}

@test "ssoo-us sin silo y sin terminal: error 30, sin crear nada" {
    rm -rf "$SILO"
    run bash "$SCRIPT" server1 </dev/null
    assert_failure 30
    [ ! -e "$SILO" ]
    [ "$(llamadas '^virsh pool-')" -eq 0 ]
}

@test "ssoo-us sin red y sin terminal: error 40, sin crear nada" {
    quitar_red "${USUARIO}-red"
    run bash "$SCRIPT" server1 </dev/null
    assert_failure 40
    [ "$(llamadas '^virsh net-define')" -eq 0 ]
}

@test "ssoo-us sin red, con --si y --dry-run: no la crea (error 40)" {
    quitar_red "${USUARIO}-red"
    run bash "$SCRIPT" --si --dry-run server1 </dev/null
    assert_failure 40
    [ "$(llamadas '^virsh net-define')" -eq 0 ]
}

@test "ssoo-us --listar sin silo: error 30, también con --si" {
    rm -rf "$SILO"
    run bash "$SCRIPT" --si --listar </dev/null
    assert_failure 30
    [ ! -e "$SILO" ]
}

@test "ssoo-us sin red, si ninguna arranca: prueba cinco, se deshace y error 40" {
    quitar_red "${USUARIO}-red"
    MOCK_FALLA="net-start" run bash "$SCRIPT" --si --no-wait server1 </dev/null
    assert_failure 40
    assert_output --partial "Se ha deshecho. Se ha probado con: 192.168.1.0/24, 192.168.2.0/24,"
    [ "$(llamadas "^virsh net-start ${USUARIO}-red\$")" -eq 5 ]
    [ "$(llamadas "^virsh net-undefine ${USUARIO}-red\$")" -eq 5 ]
    [ ! -f "$MOCK_STATE/red-${USUARIO}-red.xml" ]
}

@test "ssoo-us sin silo, si libvirt no deja registrarlo: avisa y sigue con el directorio" {
    rm -rf "$SILO"
    MOCK_FALLA="pool-define-as" run bash "$SCRIPT" --si --no-wait server1 </dev/null
    assert_success
    assert_output --partial "AVISO: no se ha podido registrar el silo en libvirt"
    [ -e "$SILO/server1.qcow2" ]
}
