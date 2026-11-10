# Desarrollo de ssoo-us

Esta guía es para quien modifique la herramienta. Si eres alumno de la
asignatura, no necesitas nada de esto: lee el [README](README.md).

`ssoo-us` sustituirá a `ci-provision.sh` (subcomando `provision`) y a
`ci-diagnosis` (subcomando `diagnosis`), con la misma interfaz, los mismos
mensajes y los mismos códigos de salida que cada uno. Están los dos
subcomandos: `provision` (fases 1 a 6 del port: validaciones, `--dry-run`,
máquina suelta, GlusterFS, `--listar`, `--eliminar`, `--eliminar-todo` y el
asistente `--menu`) y `diagnosis` (fase 8: `--antes` y `--acceso`, como
`ci-diagnosis` 1.1.0). Los dos han pasado sus baterías de pruebas en avantasia,
warcry y megadeth (fase 7).

## Estructura

El programa que se distribuye (`ssoo-us`) **se genera**, no se edita a mano. El
código vive en `src/`, en fragmentos de un único programa:

```
src/base.py       Importaciones, versión, lo que comparten provision y diagnosis
                  (imagen de Ubuntu, interfaz y DNS de las máquinas), ejecutar()
                  (órdenes externas de provision) y leer_bytes()
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
src/cluster.py    provision: base GlusterFS (--glusterfs y fase 1 del clúster)
                  y --gluster-cluster
src/gestion.py    provision: --listar, --eliminar y --eliminar-todo
src/pantallas.py  provision: las pantallas del asistente (prompt_toolkit), y las
                  de los tests (un guion de respuestas)
src/asistente.py  provision: el asistente (--menu): los pasos de cada caso
src/provision.py  provision: configuración, opciones, validaciones (también las
                  del entorno: libvirt, silo, red, IPs), flujo y marcha atrás
src/diagnosis_base.py      diagnosis: Resultado (OK, AVISO, ERROR, --), Informe,
                           formato de la salida y ejecutar_lectura() (órdenes
                           externas, con lista blanca)
src/diagnosis_textos.py    diagnosis: secciones del manual y lo que espera
src/diagnosis_claves.py    diagnosis: claves SSH (B5, B7, B10, D6)
src/diagnosis_archivos.py  diagnosis: user-data, meta-data y network-config
src/diagnosis_servidor.py  diagnosis: libvirt (solo lectura), silos, red,
                           imagen y disco, nombres libres y permisos
src/diagnosis_acceso.py    diagnosis: --acceso (estado, conectividad, ssh) y la
                           orden de virt-install de su registro
src/diagnosis_disco.py     diagnosis: el disco de una máquina apagada (guestfish)
src/diagnosis.py           diagnosis: opciones y flujo
src/main.py       Despachador de subcomandos, --version y -h

tools/ssoo-us-admin   Para el profesor: diagnosis sobre la cuenta de un alumno,
                      como él (con sudo)
tools/instalar.sh     Instala ssoo-us y ssoo-us-admin en un servidor (con sudo)
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

Solo biblioteca estándar, más lo que está en los servidores: PyYAML 5.4.1, el
módulo `libvirt` (`python3-libvirt`) y, solo para el asistente,
`prompt_toolkit` 3.0.28 (`python3-prompt-toolkit`, que se instala con `apt`; se
importa al abrir el asistente, no antes, y sin él `--menu` da el error 38). En
el `.venv`: `pip install pyyaml==6.0.2 prompt_toolkit==3.0.28`. Los servidores tienen Python 3.10; el
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

`diagnosis` necesita PyYAML para revisar la estructura de los archivos de
cloud-init: sin él, esos tests se omiten (unos 60). Para tenerlo (en macOS,
PyYAML 5.4.1 no se compila con los Python recientes; PyYAML 6 tiene la misma
interfaz para lo que se usa):

```bash
python3.11 -m venv .venv && .venv/bin/pip install pyyaml==6.0.2
.venv/bin/python -m unittest discover -s tests
```

Los de `diagnosis` son `tests/test_diagnosis_*.py`, con `comun_diagnosis.py` y
`falso_libvirt.py` (una conexión de libvirt simulada que falla si se le pide
algo que no sea de lectura). Vienen de los de `ci-diagnosis` 1.1.0; además:

- `test_diagnosis_solo_lee.py`: `diagnosis` solo lee, aunque viva en un
  programa que escribe. Revisa los fuentes `src/diagnosis*.py` (no el programa
  entero, como hacía `ci-diagnosis`): ni llamadas de `os` que escriban, ni
  `open` para escribir, ni `shutil` o `tempfile`, ni `subprocess` fuera de
  `ejecutar_lectura()`, que solo admite las órdenes de su lista. Y no usan nada
  de `provision` (ni `ejecutar()`, ni `virsh()`, ni `fallar()`...): solo lo
  suyo, lo que `base.py` comparte a propósito (lista `COMPARTIDO`) y Python.
- `test_diagnosis_cruzado.py`: lo que genera `provision` (máquina suelta, con
  `--ssh-pass`, con `--extra-disks`, GlusterFS y nodo del clúster) no da ningún
  ERROR en `diagnosis`. No es que `diagnosis` revise máquinas de `provision`:
  `diagnosis` es para la creación manual (manual, sección 5.4), y busca los
  archivos en el silo (`user-data`, `meta-data`, `network-config`), no en el
  `cloudinit-<máquina>/` de `provision`. El test comprueba que los dos siguen
  las mismas convenciones (usuario, clave, interfaz, DNS, `routes:`).

Ningún test ni ejemplo puede llevar un UVUS real: el alumno de prueba es
`alu0000`.

### Tests de aceptación de `provision` (bats)

Son los 156 tests de bats de `ci-provision` 3.0.4, sin tocar ni una línea de lo
que comprueban: `ssoo-us provision` tiene que pasar los mismos que
`ci-provision.sh`. Salvo los del asistente: el de `ci-provision` usa `whiptail`
y el de `ssoo-us`, `prompt_toolkit`, así que sus 11 tests se quedan con `skip` y
los mismos casos están en `tests/aceptacion/asistente.bats` (más abajo).

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
  asistente.bats       los del asistente de ssoo-us (estos sí se editan)
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
- El test de la auditoría 5 y 6 anotaba los argumentos del proceso hijo del
  asistente con un `bash` falso en el `PATH`; `ssoo-us` lanza el hijo con su
  mismo intérprete de Python, así que los anota un `sitecustomize.py` (en
  `PYTHONPATH`).
- `--version` escribe `ssoo-us X.Y.Z` en vez de `ci-provision.sh X.Y.Z`.
- Trece tests se conservan con `skip` (para que la numeración y los nombres
  sigan siendo los de `ci-provision`; lista `OMITIDOS`): el que comprueba que
  `ci-provision.sh` está al día respecto a sus fuentes en bash, el que ejecuta
  `src/main.sh` y los 11 del asistente.

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

`tests/aceptacion/fases.txt` reparte los 156 tests (y los 11 de `asistente.bats`) entre las fases del port
(una línea por test: la fase y su nombre exacto); las fases son acumulativas y
`--fase N` lanza los de las fases 0 a N. Un test unitario comprueba que cada
test de `ci-provision.bats` está en una fase y solo en una: si se reimportan
tests nuevos, hay que asignarles fase.

Hoy pasan todos: 143 de `ci-provision.bats` (y los 13 omitidos) y los 11 de
`asistente.bats`. Para comprobar el propio arnés se puede lanzar contra
`ci-provision.sh` con un envoltorio que quite la palabra `provision`
(`SSOO_US=envoltorio SSOO_US_PYTHON=$(command -v bash)`): entonces pasan todos
menos los seis que dependen de las sustituciones de `$ORDEN` y de `--version`.

### Tests de aceptación del asistente (`asistente.bats`)

Los mismos casos que los 11 del asistente de `ci-provision.bats`, con el mismo
entorno y los mismos mocks, pero sin `whiptail`: el asistente toma las
respuestas de un guion y anota cada pantalla en un registro.

- `SSOO_US_ASISTENTE_GUION=FICHERO`: una línea por pantalla. La clave elegida
  (en el menú y en «elegir una»; vacía, la marcada), las claves marcadas
  separadas por espacios, el texto escrito, `si` para confirmar, o `<atrás>`
  o `<salir>`. Sin más líneas, `<salir>`.
- `SSOO_US_ASISTENTE_REGISTRO=FICHERO`: cada pantalla, en una línea
  (`TIPO: texto | opciones`, con `*` en la marcada).

Lo hace `PantallasGuion` (`src/pantallas.py`), que tiene las mismas operaciones
que las pantallas de verdad (`PantallasPT`). Esas, con `prompt_toolkit`, las
prueban los tests unitarios con una entrada de teclado simulada
(`TestPantallas`, en `tests/test_provision_asistente.py`), junto con el flujo de
cada caso (qué orden construye, que Atrás conserva lo escrito...).

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
su registro no se compara. Los casos marcados con `conocida` son diferencias
deliberadas: se muestran (con «≈») pero no cuentan como fallo. Tarda unos 10
minutos:

```bash
python3 tools/equivalencia.py --fase 1        # con ../ci-provision/ci-provision.sh
python3 tools/equivalencia.py RUTA/ci-provision.sh
```

Necesita un bash 4 o posterior en el `PATH` (en macOS, el de Homebrew). Cada caso
lleva la fase a partir de la cual tiene que coincidir; al portar una fase se
añaden sus casos. El asistente (fase 6) no se compara: es distinto a propósito
(ver abajo).

### Diferencias deliberadas con `ci-provision`

La referencia es `ci-provision` 3.0.4. Los fallos que salieron al portarlo se
corrigieron allí (el resumen de `--gluster-cluster --base`, en la 3.0.2; Ctrl+C
y la lista del asistente, en la 3.0.3; la imagen por defecto de «máquina básica»
y la lista que se salía del cuadro, en la 3.0.4). En la herramienta de
equivalencia, un caso con una diferencia deliberada lleva la opción `conocida`
con el motivo: se muestra con «≈» y no cuenta como fallo. La única diferencia es
el asistente:

- **El asistente (`--menu`) usa `prompt_toolkit`, no `whiptail`** (decidido por
  David el 10-nov): botones «Atrás» y «Siguiente» (Atrás vuelve al paso anterior
  con lo que ya se había escrito; desde el primero, al menú), ratón y `Esc`
  para volver. Hace los mismos casos y lanza las mismas órdenes; los textos de
  sus pantallas no son los mismos. Ctrl+C en una pantalla sale del asistente;
  en lo que lanza, lo interrumpe y lo deshace (mientras trabaja el proceso hijo,
  el padre atiende SIGINT con un manejador que no hace nada; no lo ignora,
  porque el hijo heredaría la señal ignorada y ya no podría atraparla).

### Pruebas de equivalencia con `ci-diagnosis`

`tools/equivalencia_diagnosis.py` carga `ci-diagnosis` (el archivo generado de
`../ci-diagnosis`) y `ssoo-us` en el mismo proceso y ejecuta las dos en 52
situaciones (opciones, `--antes` con todo bien y con distintos fallos,
`--acceso` encendida y apagada, la orden de `virt-install` de su registro...),
con libvirt, ping, el puerto 22, ssh y
guestfish simulados como en `test_diagnosis_salida.py`, y compara la salida,
los errores y el código. Se normalizan el nombre (`./ci-diagnosis` es
`./ssoo-us diagnosis`), la versión, la línea «(Versión en desarrollo.)» y los
saltos de línea (el nombre nuevo es más largo y los párrafos se parten en otro
sitio). Tarda unos segundos; con PyYAML:

```bash
.venv/bin/python tools/equivalencia_diagnosis.py
```

Hoy son iguales las 52, frente a `ci-diagnosis` 1.1.0. Los fuentes de
`diagnosis` son de `ssoo-us`. Si cambia algo en `ci-diagnosis` mientras los
alumnos lo usan, se trae aquí, y esta herramienta dice si las dos siguen
diciendo lo mismo.

## Pruebas en un servidor de la asignatura

Dos baterías, que ejecutan `ssoo-us` de verdad contra libvirt. Son las de
`ci-provision` 3.0.3 y `ci-diagnosis` 1.1.0, con `ssoo-us`. Esperan el programa
en el directorio de arriba (`../ssoo-us`; `SSOO_US=RUTA` lo cambia), así que en
el servidor se copian juntos, en un directorio que pueda leer la cuenta de
prueba:

```
DIR/ssoo-us
DIR/tools/pruebas-servidor-provision.sh
DIR/tools/pruebas-servidor-diagnosis.sh
DIR/tools/preparar-cuenta-prueba.sh
```

**`provision`**, con la cuenta de un profesor (crea máquinas en su silo):

```bash
bash DIR/tools/pruebas-servidor-provision.sh a    # validaciones: no crea nada
bash DIR/tools/pruebas-servidor-provision.sh b    # máquinas sueltas, comprobadas por SSH
PREFIJO=pruebas bash DIR/tools/pruebas-servidor-provision.sh c   # el clúster GlusterFS
```

- **A**: códigos de error y `--dry-run`.
- **B**: SERVER1 de Ubuntu con DHCP y con IP fija y seis discos, con las
  instantáneas del boletín; Debian 12 con `--ssh-pass` y `--no-root`;
  `--glusterfs` desde Noble y desde ubuntu-base; `--listar` y `--eliminar`.
  Crea `pruebas1`, `pruebasgluster` y `pruebasnoble`.
- **C**: el clúster, comprobado nodo a nodo, con MySQL en Podman sobre el
  volumen disperso (`SIN_MYSQL=1` lo omite; se le dan hasta 5 minutos para
  aceptar conexiones: en megadeth tardó unos 130 s), y los nodos rehechos con
  `--base`. Con `PREFIJO=xxx` el clúster es `xxx-server1`..`4`, para no tocar
  los `server1`..`4` de la cuenta.

Para entrar en las máquinas usa una clave de usar y tirar (en
`~/.ssoo-us-pruebas.XXXXXX`, sin frase), que borra al terminar; al terminar
elimina todo lo que ha creado (`CONSERVAR=1` lo deja). El registro queda en el
silo (`pruebas-servidor-FECHA.log`).

**`diagnosis`**, con una **cuenta de alumno de prueba** (sin `sudo`, con los
grupos de un alumno: `kvm`, `libvirt`), desde la de un profesor:

```bash
sudo -iu CUENTA bash DIR/tools/preparar-cuenta-prueba.sh     # una vez: silo, red e imagen
sudo -iu CUENTA bash DIR/tools/pruebas-servidor-diagnosis.sh a
```

- **a**: `--antes`, provocando cada fallo en el silo de la cuenta. No crea
  máquinas.
- **b**: `--acceso`, con la máquina `CUENTA-server1` encendida y apagada (de 10
  a 15 minutos).
- **c**: B8, C2, B10 y C1 con máquinas de verdad (unos 5 minutos).
- **d**: A1 y A2, dentro de una máquina Ubuntu 22.04 con su propio libvirt, para
  no afectar a nadie (de 5 a 10 minutos; la primera vez descarga la imagen).
- **e**: B9, B3 con máquina, D5 y D6 (unos 10 minutos).

Al terminar deja el silo de la cuenta como estaba y elimina sus máquinas. El
registro queda en `/tmp/pruebas-ssoo-us-diagnosis-CUENTA-FECHA.log`.
`preparar-cuenta-prueba.sh --quitar` quita el silo y la red de la cuenta (sin
borrar archivos).

## Instalación en los servidores

`ssoo-us` se instala en cada servidor como una orden para todos los usuarios:
los alumnos escriben `ssoo-us provision …` o `ssoo-us diagnosis` desde su silo,
y todos usan la misma versión. Se ejecuta con los permisos de quien la lanza,
como antes `ci-provision.sh` y `ci-diagnosis`. Solo necesita lo que ya tienen
los servidores: `/usr/bin/python3` (3.8 o posterior), PyYAML y `python3-libvirt`.

Se copian `ssoo-us`, `tools/instalar.sh` y `tools/ssoo-us-admin` al servidor
(en `DIR/` y `DIR/tools/`) y, con la cuenta de un profesor:

```bash
sudo bash DIR/tools/instalar.sh            # instala o actualiza
sudo bash DIR/tools/instalar.sh --quitar   # lo quita
```

Instala `/usr/local/bin/ssoo-us` y `/usr/local/sbin/ssoo-us-admin`. Comprueba
antes que el `python3` del sistema puede con él (y avisa si le falta PyYAML o
`libvirt`, que necesita `diagnosis`), y dice qué versión había y cuál queda.
Cada archivo se copia con otro nombre y luego se renombra: quien lo esté usando
en ese momento sigue con la versión anterior y nadie ve un archivo a medias.
Sus tests (`tests/test_instalar.py`) instalan en un directorio temporal
(`DESTINO=RUTA`).

## Para el profesor: `ssoo-us-admin`

Lanza `ssoo-us diagnosis` sobre la cuenta de un alumno, como él (con `sudo`),
desde el directorio en que trabaja (su silo `<uvus>-imagenesMV`, o
`~/imagenesMV`): así revisa sus archivos, sus claves y su acceso por ssh tal y
como los vería él. Usa el `ssoo-us` instalado (el del `PATH`, o
`/usr/local/bin/ssoo-us`; `SSOO_US=RUTA` usa otro, que el alumno tiene que
poder leer). Es el `ci-diagnosis-admin` de `ci-diagnosis` 1.1.0, sin
`--actualizar` (ya no se descarga de GitHub):

```bash
ssoo-us-admin alu0000 server1 --acceso
```

Sus tests son `tests/test_diagnosis_admin.py`.

## Lo que conviene saber antes de tocar el código

- **`diagnosis` solo lee.** Sus órdenes externas, solo con
  `ejecutar_lectura()` (lista blanca: `qemu-img`, `ssh-keygen`, `ssh`,
  `ssh-add`, `ping`, `guestfish`, `virt-cat`, `virt-ls`), y libvirt con
  `openReadOnly`. Lo comprueban los tests de `test_diagnosis_solo_lee.py`: un
  fuente de `diagnosis` no puede llamar a nada de `provision`; lo que tengan que
  compartir (como `IMAGEN_NOBLE`) va en `base.py`.
- **Cómo se nombra a sí mismo.** `provision` escribe la orden como la llamaron
  (`orden_provision()`, el `$0` de `ci-provision.sh`), salvo si se encontró en
  el `PATH`: entonces sin la ruta, `ssoo-us provision`, aunque Python reciba
  `/usr/local/bin/ssoo-us` (`nombre_programa()`). `diagnosis` escribe siempre
  `ssoo-us diagnosis`, que es como se usa instalado (como `ci-diagnosis`
  escribía siempre `./ci-diagnosis`, que se descargaba en el silo). Para volver
  a lanzarse (el asistente), `ruta_del_programa()`.
- **Órdenes externas de `provision`, solo con `ejecutar()`** (`base.py`): sin teclado (la
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
- **Orden de recorrido:** bash recorre sus tablas asociativas en el orden de su
  hash; aquí se recorren ordenadas. Solo se nota en el orden de varios motivos
  de «es la imagen base de…» en un mismo mensaje (`filtrar_borrables`).
- **Códigos de salida.** Los de `provision` son los de `ci-provision.sh` (10 a
  45, 70 y 71); los de `diagnosis`, los de `ci-diagnosis` (0, 1 y 2). `ssoo-us`
  sin subcomando, o con uno que no existe, sale con 2.
