# 🛠️ ssoo-us provision — referencia completa

Todo sobre `ssoo-us provision`. Para empezar basta con el [README](../README.md).

## Índice

1. [Requisitos previos](#requisitos)
2. [Funcionamiento](#funcionamiento): parámetros, opciones, asistente, `--limpiar`, ver y eliminar
3. [Casos de uso](#casos-de-uso)
4. [Accesos configurados](#accesos)
5. [Archivos generados](#archivos)
6. [Códigos de error](#codigos)
7. [Opciones avanzadas](#opciones-avanzadas)

---

<a id="requisitos"></a>
# 1. 📌 Requisitos previos

## **1. Tener el silo creado**
Debe estar configurado en el trayecto:

```
$HOME/imagenesMV/
```

## **2. Tener una red virtual creada**
Con el nombre `TU_USUARIO-red`. Compruébalo con:

```bash
virsh net-list
```

Si tu red se llama de otra forma, `ssoo-us provision` la encontrará igualmente
siempre que empiece por tu nombre de usuario. Si tienes varias, o se llama de
otro modo, indícala con `--red NOMBRE` (ver [opciones avanzadas](#opciones-avanzadas)).

## **3. Imagen cloud de Ubuntu 24.04**

Debe estar ubicada en el silo con el nombre que le da el boletín 2,
**noble-server-cloudimg-amd64.img**:

```
$HOME/imagenesMV/noble-server-cloudimg-amd64.img
```

**Si no está, `ssoo-us provision` la descarga** (unos 600 MB) la primera vez
que lo ejecutes. Solo la guarda con ese nombre si la descarga termina bien,
coincide con la suma que publica Ubuntu y es una imagen válida. Si los
profesores han dejado una copia en `/home/ssoo-shared`, la copia de allí en
lugar de descargarla.

Si usas `--imagen debian12`, la imagen es
**debian12.qcow2** (unos 430 MB), y también la descarga si falta.

### Para obtenerlas tú mismo, si lo prefieres:

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img \
     -O $HOME/imagenesMV/noble-server-cloudimg-amd64.img
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2 \
     -O $HOME/imagenesMV/debian12.qcow2
```

(con `curl`, cambia `wget … -O FICHERO` por `curl -L … -o FICHERO`)

## **4. Tu clave pública SSH**
En `$HOME/.ssh/id_rsa.pub`. Si no la tienes, créala con `ssh-keygen`.

---

<a id="funcionamiento"></a>
# 2. ⚙️ Funcionamiento

`ssoo-us provision` trabaja siempre en tu silo, `$HOME/imagenesMV`, estés en el
directorio que estés: allí crea los discos y los ficheros cloud-init, y allí
busca la imagen de partida (también la de `--base`).

```bash
ssoo-us provision [opciones] MAQUINA [IP]
ssoo-us provision [opciones] --gluster-cluster
ssoo-us provision --listar
ssoo-us provision --eliminar MAQUINA [MAQUINA...]
ssoo-us provision --eliminar-todo
ssoo-us provision                       (asistente con menús)
```

De `MAQUINA` (por ejemplo `server1`) salen el nombre del dominio en libvirt
(`TU_USUARIO-server1`), el nombre de host (`server1`) y el disco principal
(`server1.qcow2`), que se crea en el silo como copia COW de la imagen cloud
(`noble-server-cloudimg-amd64.img`, o `debian12.qcow2` con `--imagen debian12`).

### Parámetros

| Parámetro | Descripción | Por defecto |
|-----------|-------------|-------------|
| `MAQUINA` | Nombre corto de la máquina: `server1`, `server2`, `gluster-base`... Solo letras, números y guiones | obligatorio |
| `IP` | IP fija dentro de tu red virtual | DHCP |

### Opciones

| Opción | Descripción |
|--------|-------------|
| `--imagen IMAGEN` | Imagen de partida: `noble` (Ubuntu 24.04, por defecto) o `debian12` (Debian 12). Para la base GlusterFS hay además `ubuntu-base`, ver [infraestructura GlusterFS](#caso-cluster) |
| `--extra-disks` | Crea y conecta 6 discos extra de 40G (`vdb`..`vdg`). Ver [SERVER1 del boletín 2](#caso-server1) |
| `--glusterfs` | Construye una imagen base GlusterFS y deja solo el disco. Ver [solo la imagen base](#caso-imagen-base) |
| `--gluster-cluster` | Construye la infraestructura completa del boletín 2, epígrafe 2.4. Ver [infraestructura GlusterFS](#caso-cluster) |
| `--base FICHERO` | Imagen del silo de la que hacer la copia, en lugar de la imagen cloud. Con `--gluster-cluster`, los nodos parten de ella y no se construye la base. Se deduce de qué sistema es; si no se sabe, te avisa y puedes indicarlo con `--imagen`. Ver [si ya tienes tu imagen base](#caso-base-propia) |
| `--ssh-pass -` | Te pide una contraseña para `administrador` y permite entrar por SSH escribiéndola. Solo caracteres ASCII. También se puede escribir en la orden (`--ssh-pass CONTRASEÑA`), pero entonces la ven los demás usuarios del servidor mientras se ejecuta y queda en tu historial |
| `--no-root` | No habilita al usuario `root` |
| `--no-virt-viewer` | No habilita la consola gráfica. La consola de texto (`virsh console`) sigue funcionando |
| `--limpiar` | Si ya existen los dominios o discos que se van a crear, los elimina antes, previa confirmación. **Solo esos** |
| `--si` | Da por contestadas que sí las confirmaciones de `--limpiar`, `--eliminar` y `--eliminar-todo`. Solo hace falta si lo lanzas sin terminal (desde otro script): entonces, sin `--si`, no elimina nada |
| `--listar` | Muestra tus máquinas (estado, IP, discos) y los discos del silo que no usa ninguna |
| `--eliminar MAQUINA...` | Elimina esas máquinas con sus discos y sus ficheros cloud-init, previa confirmación |
| `--eliminar-todo` | Elimina todas tus máquinas con sus discos y ofrece borrar los discos que queden sin máquina |
| `--menu` | Asistente con menús. Es lo que se abre al ejecutar `ssoo-us provision` sin argumentos |
| `-h` | Ayuda |

Hay más opciones para casos particulares en [opciones avanzadas](#opciones-avanzadas).

### 🧭 Asistente con menús

Si ejecutas `ssoo-us provision` **sin argumentos** desde el servidor (o con
`--menu`), se abre un asistente con menús: eliges qué quieres hacer (una
máquina, SERVER1 del boletín 2, la infraestructura GlusterFS, solo la imagen
base, ver o eliminar lo que tienes), rellenas el nombre, la red (DHCP, o una IP
fija: te propone la primera libre de tu red y te avisa enseguida si la que
escribes no vale) y las opciones, y antes de ejecutar te muestra **el comando
equivalente**, que es el que aprenderás a escribir. Todo lo que hace el
asistente se puede hacer con las opciones de la tabla anterior.

Se maneja con el teclado o con el **ratón**:

| Tecla | Qué hace |
|-------|----------|
| `↑` `↓` | Moverse por la lista |
| `Espacio` (o un clic) | Marcar una opción |
| `Intro` | Seguir |
| `Tab` | Pasar a los botones |
| `Esc` | Volver atrás |
| `Ctrl+C` | Salir del asistente |

Cada paso tiene los botones **«Atrás»** y **«Siguiente»**. «Atrás» vuelve al
paso anterior sin perder lo que ya habías escrito y, desde el primero, al menú
principal. Mientras se crea una máquina, `Ctrl+C` la interrumpe y deshace lo
creado.

### ⏳ Qué pasa al ejecutarlo

Tras crear la máquina, `ssoo-us provision` **espera a que termine de
configurarse por dentro** (instalación de paquetes y ajustes iniciales). Suele
tardar entre uno y tres minutos; mientras tanto verás un contador. Después **la
apaga y la vuelve a arrancar**: así se reinicia con normalidad cuando la
reinicies desde dentro, y las instantáneas que tomes después conservan ese
comportamiento. Al terminar muestra un resumen con los datos de la máquina y su
IP.

> ⚠️ Con `--no-wait` (o si la espera se agota) ese último paso no se hace, y la
> máquina **se apagaría en su primer reinicio**. Cuando termine de configurarse,
> apágala y arráncala tú: `virsh shutdown NOMBRE` y, ya apagada, `virsh start NOMBRE`.

### 🧹 Sobre `--limpiar`

`ssoo-us provision` siempre crea máquinas y discos **nuevos**. Si ya existe
alguno de los que va a crear, se detiene y te dice cuáles son y cómo
eliminarlos. Con `--limpiar` los elimina él, pero **únicamente esos**: nunca
toca otro dominio ni otro fichero de tu silo. Antes de hacerlo te enseña la
lista y te pide confirmación por teclado. Y si uno de esos discos lo está usando
cualquier otra máquina del servidor, o es la imagen base de otras copias, no lo
borra: se detiene y te lo explica. Tampoco toca una máquina que se llame como
las tuyas pero tenga sus discos fuera de tu silo (puede ser de otro usuario).

Con una IP fija, comprueba también que no la tenga ya otra de tus máquinas y que
no responda nada en ella.

### 🗂️ Ver y eliminar lo que ya tienes

```bash
ssoo-us provision --listar
```

Muestra tus máquinas (las que empiezan por `TU_USUARIO-`), con su estado, su IP y
sus discos, y después los discos del silo que no usa ninguna máquina (por ejemplo
`gluster-base.qcow2`, que es la imagen de la que son copia los nodos, o las
imágenes cloud).

```bash
ssoo-us provision --eliminar server1
```

Elimina `TU_USUARIO-server1` con **todos** sus discos (los que tenga conectados,
según libvirt) y sus ficheros cloud-init, tras enseñarte la lista y pedir
confirmación. Puedes indicar varias máquinas a la vez; para deshacer la
infraestructura GlusterFS entera:

```bash
ssoo-us provision --eliminar server1 server2 server3 server4 gluster-base
```

Nunca borra un disco que esté usando otra máquina (tuya o no), ni una imagen de la
que dependan otras copias que se conservan, aunque sea a través de otra copia: en
ese caso lo conserva y te dice por qué.

```bash
ssoo-us provision --eliminar-todo
```

Elimina todas tus máquinas con sus discos y, en una segunda pregunta, los discos del
silo que queden sin máquina. Las imágenes cloud (`noble-server-cloudimg-amd64.img` y
`debian12.qcow2`) no se tocan nunca. Con `--dry-run`, las tres opciones solo enseñan
lo que harían.

---

# 📘 Notas sobre los ejemplos

- **usuario** = tu usuario en el servidor  
- **192.168.XXX.Y** = una IP de tu red virtual privada  
- **soserver** = avantasia / warcry / megadeth  

---

<a id="casos-de-uso"></a>
# 3. 🧪 Casos de uso

---

## 🟦 **1️⃣ Máquina básica**

### **Ubuntu 24.04 con DHCP**

```bash
ssoo-us provision server1
```

### **Con IP fija**

```bash
ssoo-us provision server1 192.168.XXX.2
```

### **Debian 12**

```bash
ssoo-us provision --imagen debian12 server1 192.168.XXX.2
```

### **Permitiendo además entrar por SSH con contraseña**

```bash
ssoo-us provision --ssh-pass - server1
```

Te pide la contraseña (no se ve al escribirla).

---

<a id="caso-server1"></a>
## 🟩 **2️⃣ SERVER1 del boletín 2 — Epígrafe 2.1**

### **Máquina con IP fija y seis discos extra**

```bash
ssoo-us provision --extra-disks server1 192.168.XXX.2
```

Crea `usuario-server1`, con Ubuntu 24.04, hostname `server1`, la IP `.2` de tu red
y seis discos de 40G en el silo, `server1-vdb.qcow2`..`server1-vdg.qcow2`,
conectados como `vdb`..`vdg`. Queda lista para todo el resto del bloque:

- puedes tomar y revertir **instantáneas** (`virsh snapshot-create-as … --atomic`)
  en cuanto termina, encendida o apagada;
- `root` tiene la contraseña `s1st3mas` en la consola, que es la que te pedirá la
  máquina si arranca en **modo de emergencia** (epígrafe 2.3);
- `apt` funciona, para instalar lo que pidan los ejercicios (por ejemplo, `lvm2`).

### **Si `server1` ya existía y quieres rehacerla desde cero**

```bash
ssoo-us provision --limpiar --extra-disks server1 192.168.XXX.2
```

---

<a id="caso-cluster"></a>
## 🟥 **3️⃣ Infraestructura GlusterFS del boletín 2 — Epígrafe 2.4**

### **Todo en un comando**

```bash
ssoo-us provision --gluster-cluster
```

Crea, en dos fases:

1. **Una imagen base** `gluster-base.qcow2` (Ubuntu 24.04, copia COW de la misma
   imagen cloud que SERVER1), con `glusterfs-server` instalado, `glusterd`
   habilitado, la zona horaria `Europe/Madrid` y el `machine-id` vacío. Se
   construye en una máquina provisional (`usuario-gluster-base`) que, al terminar,
   se apaga y se elimina; el disco **se conserva**, porque los nodos son copias
   COW de él.
2. **Cuatro nodos** `usuario-server1`..`usuario-server4`, cada uno con:
   - IP fija `192.168.XXX.10`, `.11`, `.12` y `.13`
   - `/etc/hosts` con los cuatro nombres
   - 3 discos extra de 40G (`vdb`, `vdc` y `vdd`), formateados en xfs y montados
     en `/gluster1`, `/gluster2` y `/gluster3` desde `/etc/fstab`
   - `glusterd` en marcha, su propio `machine-id` y el cliente de Gluster
   - 1 vCPU y 1 GB de RAM

Los cuatro nodos arrancan en paralelo y se espera a que todos terminen. En total
tarda unos tres minutos.

> ⚠️ **No borres `gluster-base.qcow2`** mientras existan los nodos.

### **Variantes**

```bash
ssoo-us provision --gluster-cluster --discos-nodo 7          # 7 discos por nodo (vdb..vdh), como crea-entorno.sh
ssoo-us provision --gluster-cluster --imagen ubuntu-base     # base hecha como en la construcción manual del boletín
```

Con `--imagen ubuntu-base`, la base es una **copia completa** (64G) de
`/home/ssoo-shared/ubuntu-base.qcow2`, la imagen del boletín 1, y en los nodos
`administrador` conserva la contraseña de esa imagen (que `sudo` pide); solo se
le añade tu clave pública. Con `--discos-nodo`, solo los tres primeros discos se
formatean y se montan.

### **Si ya tenías máquinas de otros ejercicios**

Si existen `usuario-server1`..`4` o sus discos, `ssoo-us provision` se detendrá
y te lo dirá. Para que los elimine él:

```bash
ssoo-us provision --limpiar --gluster-cluster
```

<a id="caso-base-propia"></a>
### **Si ya tienes tu imagen base y solo quieres los nodos**

Con `--base` no se construye la base: los cuatro nodos se crean directamente
como copias de la imagen que indiques, que **no se toca** (ni siquiera con
`--limpiar`). Tarda alrededor de un minuto.

```bash
ssoo-us provision --gluster-cluster --base gluster-base.qcow2
```

<a id="caso-imagen-base"></a>
### **Solo la imagen base**

```bash
ssoo-us provision --glusterfs gluster-base
```

Deja `gluster-base.qcow2` en el silo, sin máquina. Después puedes crear los
nodos con el comando anterior, o hacerlo tú siguiendo el epígrafe 2.4 del
boletín 2. Para crear una máquina suelta a partir de esa imagen también sirve
`--base`:

```bash
ssoo-us provision --base gluster-base.qcow2 server1 192.168.XXX.10
```

---

<a id="accesos"></a>
# 4. 🔐 Accesos configurados

## Usuario `administrador`

| Acceso | Requisitos | Estado |
|--------|------------|--------|
| SSH con tu clave pública | Ninguno | ✔ Siempre |
| SSH escribiendo contraseña | `--ssh-pass` | ✔ con la contraseña que elijas |
| Consola (`virsh console` / virt-viewer) | `--ssh-pass` | ✔ con la contraseña que elijas |

## Usuario `root`

| Acceso | Requisitos | Estado |
|--------|------------|--------|
| SSH | – | ❌ Prohibido |
| Consola (`virsh console` / virt-viewer) | Ninguno | ✔ contraseña `s1st3mas` |

Con `--no-root`, el usuario `root` queda sin contraseña y no se puede entrar con
él por ningún medio.

En las máquinas hechas con `--imagen ubuntu-base`, `administrador` tiene además la
contraseña de esa imagen (la del boletín 1), con la que puede entrar por SSH y por
consola, y que `sudo` le pide. Con `--no-virt-viewer`, la máquina no tiene consola gráfica;
`virsh console` sigue funcionando.

### Ejemplos

```bash
ssh administrador@192.168.XXX.Y
virsh console usuario-server1
virt-viewer --connect qemu+ssh://usuario@soserver.lsi.us.es/system usuario-server1
```

> 💡 Si al conectar por SSH ves un aviso `REMOTE HOST IDENTIFICATION HAS CHANGED`,
> es que esa IP la tuvo antes otra máquina tuya. `ssoo-us provision` te avisa al
> terminar y te da el comando `ssh-keygen -R` para resolverlo.

> 💡 De `virsh console` se sale con `Ctrl+]`. En un teclado de Mac esa tecla es
> `⌥ Option + Shift + 9`, lo que resulta incómodo; puedes cambiar el carácter de
> escape al entrar, y salir entonces con `Ctrl+X`:
> ```bash
> virsh -e '^X' console usuario-server1
> ```

---

<a id="archivos"></a>
# 5. 🧩 Archivos generados

En el silo:

```
noble-server-cloudimg-amd64.img   imagen cloud de Ubuntu 24.04 (la descarga ssoo-us)
debian12.qcow2                    imagen cloud de Debian 12 (solo con --imagen debian12)
server1.qcow2                     disco principal (copia COW de la imagen cloud)
server1-vdb.qcow2 … server1-vdg.qcow2   discos extra, si se pidieron
cloudinit-usuario-server1/
 ├── cip-user.yaml
 ├── cip-meta.yaml
 └── cip-net.yaml                 solo si hay IP estática
```

Los discos extra se llaman siempre `MAQUINA-vdX.qcow2`, que es el nombre que
usan los ejercicios del boletín (por ejemplo, `virsh detach-disk usuario-server1
$PWD/server1-vdb.qcow2`).

Con `--gluster-cluster` se genera un directorio `cloudinit-*` por máquina (la
base y cada nodo), los discos `server1.qcow2`..`server4.qcow2` con sus
`serverN-vdb.qcow2`..`serverN-vdd.qcow2`, y queda además `gluster-base.qcow2`, la
imagen de la que son copia los cuatro nodos. Con `--dry-run`, los ficheros van a `cloudinit-*.dry-run/`;
esos directorios los puedes borrar cuando quieras.

> ⚠️ Los ficheros `cloudinit-*` contienen las contraseñas en texto plano, así que
> el directorio se crea con permisos `700` (solo tú puedes leerlo). Recuerda que
> el servidor de la asignatura es compartido con el resto de la clase.

---

<a id="codigos"></a>
# 6. 🧨 Códigos de error

| Código | Descripción | Solución |
|--------|-------------|-----------|
| **2** | `ssoo-us` sin subcomando, o con uno que no existe | `ssoo-us provision …` o `ssoo-us diagnosis …`; consulta `ssoo-us -h` |
| **10** | Faltan o sobran parámetros, opciones incompatibles, una `--imagen` que no existe o una máquina llamada como una imagen cloud | Revisa la sintaxis: `MAQUINA [IP]` |
| **11** | Falta el valor de una opción, o está vacío | Escríbelo después de la opción, separado por un espacio |
| **12** | Opción desconocida, obsoleta o escrita con `=` | Consulta `-h`; las opciones van separadas de su valor por un espacio |
| **13** | RAM, vCPUs, `--discos-nodo` o `--ip-inicial` no válidos | Números; mínimo 512 MB y 1 vCPU; de 3 a 7 discos por nodo; IP inicial de 2 a 250 |
| **14** | Contraseña con caracteres no ASCII | Sin tildes ni `ñ`: no podrías teclearla en la consola |
| **15** | Tamaño de disco no válido, o menor que la imagen de partida | Formato `40G`, `20G`, `512M`; nunca menor que la imagen |
| **16** | Nombre de disco o de imagen no válido | Solo el nombre del fichero, sin rutas |
| **20** | Nombre de máquina o prefijo (`--prefijo`) no válido | Solo letras, números y guiones; sin tu usuario delante |
| **21** | Ya existe el dominio o algún disco, o un disco lo usa otra máquina | El mensaje indica cómo eliminarlos, o usa `--limpiar` |
| **22** | No hay nada que eliminar, o no se ha podido eliminar | Comprueba el nombre con `--listar` |
| **23** | Había que confirmar y no hay terminal para preguntar | Ejecútalo desde una terminal, o añade `--si` si de verdad quieres hacerlo sin preguntas |
| **30** | No existe el silo | Crear `$HOME/imagenesMV` y mapearlo en el hipervisor |
| **31** | No existe la clave pública, o el fichero no contiene una sola clave | `ssh-keygen` |
| **37** | No se ha podido descargar la imagen base, no coincide con su suma publicada, o la que hay está corrupta | El mensaje indica el `wget` manual, o el `rm` para que se vuelva a descargar |
| **38** | Faltan herramientas (incluido `wget`/`curl` para descargar la imagen, o `prompt_toolkit` para el asistente) o no hay conexión con libvirt | Avisar al profesor |
| **39** | La imagen indicada con `--base` no existe, no es un `qcow2`, le falta la imagen de la que es copia o es el disco de una máquina; o no está `/home/ssoo-shared/ubuntu-base.qcow2` (con `--imagen ubuntu-base`) | Revisa el nombre; debe estar en el silo. Sin ubuntu-base, usa la imagen por defecto |
| **40** | No se encuentra tu red virtual, o el nombre dado a `--red` no es válido | Créala con el nombre `TU_USUARIO-red`, o usa `--red` |
| **41** | IP no válida o fuera de tu red | El mensaje indica las IPs libres de tu red |
| **42** | IP ocupada: por el DHCP, por una reserva, por otra de tus máquinas o por algo que ya responde en ella | El mensaje indica las IPs libres de tu red (y, en el clúster, qué `--ip-inicial` usar) |
| **43** | No se puede interpretar la red | Revisar `virsh net-dumpxml TU_RED` |
| **44** | Tienes varias redes virtuales | Indica cuál con `--red` |
| **45** | Tu red virtual está inactiva | `virsh net-start TU_RED` |
| **70** | No se ha podido confirmar que la imagen base GlusterFS haya terminado, o no se ha apagado | Reintentar; revisar la carga del servidor |
| **71** | cloud-init ha fallado en la imagen base GlusterFS | La máquina se conserva: revísala con `virsh console`; después repite con `--limpiar` |

Los de `ssoo-us diagnosis` son otros: ver [su referencia](diagnosis.md#resultado).

---

<a id="opciones-avanzadas"></a>
# 7. 🔧 Opciones avanzadas

No las necesitas en los [casos de uso](#casos-de-uso).

| Opción | Descripción |
|--------|-------------|
| `--dry-run` | Comprueba los datos y muestra lo que se haría, **sin crear nada** |
| `--no-wait` | No espera a que la máquina termine de configurarse (no válida con `--glusterfs`; con `--gluster-cluster` solo afecta a los nodos: la imagen base se espera siempre) |
| `--red NOMBRE` | Red virtual a usar, si no se llama `TU_USUARIO-red` o tienes varias |
| `--prefijo PREFIJO` | Sustituye a tu usuario en los nombres de todo lo que se crea (dominios y discos). Ver abajo |
| `--disco NOMBRE` | Nombre del disco principal (por defecto `MAQUINA.qcow2`) |
| `--tam TAMAÑO` | Tamaño del disco principal (por defecto `40G`, o el de la imagen de partida si es mayor) |
| `--discos-nodo N` | Discos extra por nodo del clúster, de 3 a 7 (por defecto 3; con 7, como `crea-entorno.sh`) |
| `--ip-inicial N` | IP del primer nodo del clúster: `.N`, `.N+1`… (por defecto 10). Solo si el DHCP de tu red ocupa las `.10`–`.13`; se te dice qué número usar |
| `--ram MB` | Memoria (por defecto 2048; en el clúster, 1024 por nodo) |
| `--vcpus N` | vCPUs (por defecto 2; en el clúster, 1 por nodo) |

### `--dry-run`

Ejecuta todas las comprobaciones, genera los ficheros cloud-init y muestra el
comando `virt-install` exacto que se lanzaría, pero **no crea la máquina, ni los
discos, ni modifica nada**. Sirve para comprobar que los datos son correctos
antes de invertir un par de minutos, y para ver el comando que hay detrás.

```bash
ssoo-us provision --dry-run --extra-disks server1 192.168.XXX.2
ssoo-us provision --dry-run --gluster-cluster
```

Los ficheros de la simulación se escriben en `cloudinit-DOMINIO.dry-run/`, así
que nunca sobrescriben los de una máquina que ya exista. Combinado con
`--limpiar`, solo enumera lo que se eliminaría.

### `--no-wait`

Devuelve el control en cuanto la máquina está creada. Ten en cuenta que entonces
la máquina **seguirá configurándose por dentro** durante un rato: si entras
enseguida, puede que los paquetes instalados por cloud-init todavía no estén
disponibles.

### `--prefijo`

Por defecto las máquinas se llaman `TU_USUARIO-MAQUINA` y los discos `MAQUINA.qcow2`.
Con `--prefijo PREFIJO`, el prefijo sustituye a tu usuario en **todo lo que se
crea**: dominios `PREFIJO-MAQUINA`, discos `PREFIJO-MAQUINA.qcow2` y
`PREFIJO-MAQUINA-vdb.qcow2`, imagen base `PREFIJO-gluster-base.qcow2` y directorios
`cloudinit-PREFIJO-*`. Así puedes tener dos juegos de máquinas en el mismo silo sin
que se pisen, y `--limpiar` nunca toca los del otro prefijo. El hostname (`server1`) y
la red no cambian. Si además usas `--disco`, ese nombre manda tal cual, sin prefijo.

```bash
ssoo-us provision --prefijo demo --gluster-cluster
```

crea `demo-gluster-base.qcow2` y `demo-server1`..`demo-server4` (con `demo-server1.qcow2`,
`demo-server1-vdb.qcow2`, etc.) dejando intactos tus `TU_USUARIO-server1`..`4`.
