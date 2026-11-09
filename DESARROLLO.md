# Desarrollo de ssoo-us

Esta guía es para quien modifique la herramienta. Si eres alumno de la
asignatura, no necesitas nada de esto: lee el [README](README.md).

`ssoo-us` sustituirá a `ci-provision.sh` (subcomando `provision`) y a
`ci-diagnosis` (subcomando `diagnosis`), con la misma interfaz, los mismos
mensajes y los mismos códigos de salida que cada uno. Mientras se porta, lo que
falta responde «todavía no está implementado» con el código 69, que no usa
ninguna de las dos herramientas: `diagnosis` entero y, en `provision`,
`--glusterfs`, `--gluster-cluster`, `--listar`, `--eliminar`, `--eliminar-todo`
y `--menu` (fases 4 a 6 del port). Ya están las validaciones, `--dry-run` y la
creación de una máquina suelta (fases 1 a 3).

## Estructura

El programa que se distribuye (`ssoo-us`) **se genera**, no se edita a mano. El
código vive en `src/`, en fragmentos de un único programa:

```
src/base.py       Importaciones, versión, ejecutar() (órdenes externas) y leer_bytes()
src/red.py        Red virtual: XML de libvirt y aritmética de IPv4 (se compartirá
                  con diagnosis)
src/claves.py     provision: la clave pública del alumno
src/imagenes.py   provision: imágenes de partida (y su descarga), qemu-img,
                  --base, tamaño y creación de discos
src/cloudinit.py  provision: user-data, meta-data y network-config
src/virsh.py      provision: llamadas a virsh y análisis de su salida
src/limpieza.py   provision: quién usa cada disco, qué se puede borrar,
                  conflictos con lo que ya existe y --limpiar (con confirmación)
src/espera.py     provision: espera a cloud-init por el agente, apagado y
                  reinicio en frío
src/maquina.py    provision: orden de virt-install, plan, creación y resumen de
                  una máquina suelta
src/cluster.py    provision: --gluster-cluster
src/provision.py  provision: configuración, opciones, validaciones (también las
                  del entorno: libvirt, silo, red, IPs), flujo y marcha atrás
src/main.py       Despachador de subcomandos, --version y -h
```

Tras modificar cualquiera de ellos, regenera el programa:

```bash
python3 tools/build.py
```

`tools/build.py` concatena los fragmentos en el orden de su lista `ORDEN`: todos
comparten el espacio de nombres, así que no se importan entre sí, y las
importaciones de la biblioteca estándar van todas en `base.py` (el primero;
`main.py` va el último). Un test comprueba que `ssoo-us` está al día respecto a
los fuentes, y otro que todo fuente de `src/` está en `ORDEN`.

Solo biblioteca estándar, más lo que ya está en los servidores: PyYAML 5.4.1 y
el módulo `libvirt` (`python3-libvirt`). Los servidores tienen Python 3.10; el
código tiene que ser válido en 3.8 (un test lo comprueba con
`ast.parse(..., feature_version=(3, 8))`, pero no detecta funciones nuevas de la
biblioteca, como `str.removeprefix`: no las uses). La primera línea es
`#!/usr/bin/python3`, el del sistema, que es el que tiene esos módulos.

## Tests locales

### Tests unitarios (`unittest`)

Sobre el programa generado, que es lo que usará el alumnado:

```bash
python3 -m unittest discover -s tests
```

Para tener PyYAML, como en `ci-diagnosis` (en macOS, PyYAML 5.4.1 no se compila
con los Python recientes; PyYAML 6 tiene la misma interfaz para lo que se usa):

```bash
python3.11 -m venv .venv && .venv/bin/pip install pyyaml==6.0.2
.venv/bin/python -m unittest discover -s tests
```

Ningún test ni ejemplo puede llevar un UVUS real: el alumno de prueba es
`alu0000`.

### Tests de aceptación de `provision` (bats)

Son los 153 tests de bats de `ci-provision`, sin tocar ni una línea de lo que
comprueban: `ssoo-us provision` tiene que pasar los mismos que `ci-provision.sh`.

Los tests de `ci-provision` lanzan el script siempre como `bash "$SCRIPT" ...`,
y `test/helpers.bash` fija `SCRIPT="$REPO_DIR/ci-provision.sh"`. Aquí `SCRIPT`
es un envoltorio, `tests/aceptacion/ssoo-us-provision`, que hace
`exec python3 ssoo-us provision "$@"`. Los mocks (`virsh`, `virt-install`,
`wget`, `curl`, `ping`, `whiptail`) se copian tal cual: `ssoo-us provision`
tiene que llamar a las mismas órdenes externas que `ci-provision.sh` para que
sirvan.

```
tests/aceptacion/
  ci-provision.bats    importado (no se edita)
  helpers.bash         importado (no se edita)
  mocks/               importados (no se editan)
  ORIGEN               de qué commit de ci-provision salen
  fases.txt            en qué fase del port tiene que pasar cada test
  ssoo-us-provision    el envoltorio
  bats/                bats-core, bats-support y bats-assert (submódulos, en
                       los mismos commits que en ci-provision)
```

Se importan, no se copian a mano, con:

```bash
python3 tools/importar_aceptacion.py            # de ../ci-provision
python3 tools/importar_aceptacion.py RUTA       # de otra copia de ci-provision
```

El importador aplica una lista corta de sustituciones (`SUSTITUCIONES_HELPERS`
y `SUSTITUCIONES_BATS`), cada una con el número de apariciones que espera; si
los tests de `ci-provision` cambian y alguna no cuadra, no escribe nada y dice
cuál. Las sustituciones son:

- `SCRIPT` es el envoltorio; `REPO_DIR` es la raíz de este repositorio y los
  mocks están en `$MOCKS_DIR`.
- Las cargas de `bats-support` y `bats-assert` apuntan a `tests/aceptacion/bats`.
- El asistente (`--menu`) muestra la orden que lanza: `ci-provision.sh` escribe
  su `$0`; `ssoo-us provision` escribirá `ssoo-us provision`, que en los tests es
  `$ORDEN`.
- `--version` escribe `ssoo-us X.Y.Z` en vez de `ci-provision.sh X.Y.Z`.
- Dos tests se conservan con `skip` (para que la numeración y los nombres sigan
  siendo los de `ci-provision`): el que comprueba que `ci-provision.sh` está al
  día respecto a sus fuentes en bash y el que ejecuta `src/main.sh`.

Para lanzarlos (hacen falta `qemu-img` y `jq`; en macOS:
`brew install qemu jq`; y los submódulos, con `git submodule update --init`):

```bash
bash tools/aceptacion.sh                         # todos
bash tools/aceptacion.sh --fase 2                # los de las fases 0, 1 y 2
bash tools/aceptacion.sh -f 'error 1[0-9]'       # los que coincidan con el filtro
bash tools/aceptacion.sh --tap > /tmp/a.tap      # en formato TAP, para contarlos
```

Usa el Python de `.venv` si existe y, si no, el `python3` del `PATH`
(`SSOO_US_PYTHON` lo cambia). Tarda alrededor de un minuto.

`tests/aceptacion/fases.txt` reparte los 153 tests entre las fases del port
(una línea por test: la fase y su nombre exacto); las fases son acumulativas y
`--fase N` lanza los de las fases 0 a N. Un test unitario comprueba que cada
test de `ci-provision.bats` está en una fase y solo en una: si se reimportan
tests nuevos, hay que asignarles fase.

Hoy pasan los de las fases 1 a 3 y fallan los demás (por «todavía no está
implementado»). Para comprobar el propio arnés se puede lanzar contra
`ci-provision.sh` con un envoltorio que quite la palabra `provision`
(`SSOO_US=envoltorio SSOO_US_PYTHON=$(command -v bash)`): entonces pasan todos
menos los seis que dependen de las sustituciones de `$ORDEN` y de `--version`.

Los tests de `ci-provision` leen variables de entorno con el prefijo
`CI_PROVISION_` (tiempos de espera, directorio compartido, clave pública, URI de
libvirt); `ssoo-us provision` las lee con los mismos nombres.

### Pruebas de equivalencia con `ci-provision.sh`

Los tests de bats solo miran trozos de la salida. `tools/equivalencia.py` lanza
las mismas órdenes con `ci-provision.sh` y con `ssoo-us provision`, cada una en
el entorno de los tests de aceptación (`preparar_entorno` de `helpers.bash`, con
los mocks) más una preparación propia del caso (que puede llamar a `programa`,
la implementación que se está probando, para los casos de varios pasos), y
compara la salida, los errores, el código, los ficheros que quedan en el `HOME`
(con sus permisos), las máquinas del libvirt simulado y el registro de llamadas
a los mocks. Algunos casos mandan una señal a mitad (Ctrl+C, SIGTERM). Se
normalizan la orden (`$0`), la línea de la versión, la fecha del `instance-id`,
los segundos de «tras Ns» y el PID del fichero temporal de la descarga; en los
casos cuya espera se agota, el número de consultas al agente depende del reloj y
su registro no se compara. Tarda unos 5 minutos:

```bash
python3 tools/equivalencia.py --fase 1        # con ../ci-provision/ci-provision.sh
python3 tools/equivalencia.py RUTA/ci-provision.sh
```

Necesita un bash 4 o posterior en el `PATH` (en macOS, el de Homebrew). Cada caso
lleva la fase a partir de la cual tiene que coincidir; al portar una fase se
añaden sus casos.

## Lo que conviene saber antes de tocar el código

- **Órdenes externas, solo con `ejecutar()`** (`base.py`): sin teclado (la
  entrada es `/dev/null` salvo que se le pase texto), con `LC_ALL=C` (warcry y
  megadeth responden en español) y con `LIBVIRT_DEFAULT_URI=qemu:///system`
  (sin sesión de login, o con la variable heredada, `virsh` se conectaría a
  `qemu:///session` y no vería ninguna máquina).
- **Errores de `provision`:** `fallar(código, mensaje)` lanza `ErrorProvision`,
  que `provision()` convierte en «ERROR [código] mensaje» por la salida de
  errores y en el código de salida, como `error` en `ci-provision.sh`. La ayuda
  y `--version` terminan con `FinProvision(0)`. En los mensajes, la orden es
  `orden_provision()` («./ssoo-us provision»), donde `ci-provision.sh` ponía `$0`.
- **Salida por líneas:** `main()` pone la salida y los errores en modo
  `line_buffering`, para que se mezclen en el mismo orden que en bash.
- **Como bash con `LC_ALL=C`:** los nombres, el tamaño y los números se validan
  solo con caracteres ASCII (`re.fullmatch` con clases `[A-Za-z0-9]`, nunca
  `\w` ni `str.isdigit`), y `decimal()` solo admite cifras (`int()` aceptaría
  espacios, `+` o `1_0`).
- **Órdenes que escriben en la terminal** (`virt-install`, `qemu-img create`,
  `wget`, `curl`, `cp`): con `ejecutar_visible()`, que no captura sus errores
  (ni su salida, si se pide), como hace `ci-provision.sh`.
- **`set -e` y la marcha atrás:** si falla una orden de la que no se espera que
  falle, `FalloInesperado(código)`; Ctrl+C, SIGTERM y SIGHUP, `Interrumpido`.
  `provision()` los convierte, como el `trap al_salir EXIT` de bash, en el
  mensaje que toque y deshace lo creado en esta ejecución (los dominios se
  registran antes de lanzar `virt-install`; los discos, antes de crearlos),
  salvo que la creación ya esté completa.
- **Lo que aún no está portado** lanza `NoImplementado`, que `provision()`
  convierte en el aviso y el código 69. Así una fase se puede cerrar sin dejar
  a medias lo que viene detrás (por ejemplo, con `--limpiar` sin `--dry-run`
  no se borra nada hasta la fase 3).
- **Orden de recorrido:** bash recorre sus tablas asociativas en el orden de su
  hash; aquí se recorren ordenadas. Solo se nota en el orden de varios motivos
  de «es la imagen base de…» en un mismo mensaje (`filtrar_borrables`).
- **Códigos de salida.** Los de `provision` son los de `ci-provision.sh` (10 a
  45, 70 y 71); los de `diagnosis`, los de `ci-diagnosis` (0, 1 y 2). `ssoo-us`
  sin subcomando, o con uno que no existe, sale con 2.
