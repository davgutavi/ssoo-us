# 🚀 ssoo-us
### Máquinas virtuales con cloud-init en los servidores de la asignatura
**Asignatura: Sistemas Operativos — Universidad de Sevilla**

> ℹ️ Este curso, las herramientas de referencia del manual y de los boletines
> siguen siendo `ci-provision.sh` y `ci-diagnosis`. `ssoo-us` hace lo mismo que
> ellas, con las mismas opciones, y ya está instalado en avantasia, warcry y
> megadeth: puedes usar la que prefieras.

`ssoo-us` tiene tres herramientas, para tres situaciones distintas:

| ¿Qué quieres? | Orden |
|---|---|
| 🛠️ **Crear** máquinas virtuales con un solo comando (SERVER1, GlusterFS…) | `ssoo-us provision` |
| 🩺 **Revisar** una máquina que has construido **a mano** y saber qué falla | `ssoo-us diagnosis` |
| 🔑 **Entrar**: saber por qué no puedes entrar por `ssh` en una de tus máquinas | `ssoo-us acceso` |

Todas tienen su ayuda con `-h` (por ejemplo, `ssoo-us acceso -h`).

## 📑 Índice

- [🛠️ `ssoo-us provision`: crear máquinas](#provision)
  - [Antes de empezar](#antes)
  - [Uso](#uso)
  - [Casos de uso del boletín 2](#casos)
  - [Asistente con menús](#asistente)
  - [Ver y eliminar tus máquinas](#ver-eliminar)
  - [Cómo entrar en las máquinas](#entrar)
- [🩺 `ssoo-us diagnosis`: revisar una máquina hecha a mano](#diagnosis)
  - [Uso](#uso-diagnosis)
  - [Cómo leer el resultado](#resultado)
- [🔑 `ssoo-us acceso`: por qué no puedes entrar en tu máquina](#acceso)
- [📚 Referencia completa](#referencia)

---

<a id="provision"></a>
# 🛠️ `ssoo-us provision`: crear máquinas

Crea máquinas virtuales completas con `virt-install` y `cloud-init`, a partir
de la imagen cloud de **Ubuntu 24.04** (o de **Debian 12**, si la pides). Todas
tienen:

- usuario `administrador` con tu clave pública SSH y `sudo` sin contraseña;
- usuario `root` con contraseña `s1st3mas`, **solo para la consola**;
- consola gráfica, `qemu-guest-agent` y zona horaria `Europe/Madrid`.

<a id="antes"></a>
## 📌 Antes de empezar

Necesitas lo que se monta en el manual (secciones 5.2 y 5.3):

- tu **silo** en `$HOME/imagenesMV`;
- tu **red virtual** `TU_USUARIO-red` (compruébalo con `virsh net-list`);
- tu **clave pública** en `$HOME/.ssh/id_rsa.pub` (si no la tienes: `ssh-keygen`).

La imagen cloud de Ubuntu 24.04 la descarga sola la primera vez. Trabaja
siempre en tu silo, estés en el directorio que estés.

<a id="uso"></a>
## ⚙️ Uso

```bash
ssoo-us provision [opciones] MAQUINA [IP]     # una máquina (sin IP: DHCP)
ssoo-us provision [opciones] --gluster-cluster
ssoo-us provision                             # asistente con menús
```

De `MAQUINA` (por ejemplo, `server1`) salen el nombre de la máquina en libvirt
(`TU_USUARIO-server1`), su nombre de host (`server1`) y su disco
(`server1.qcow2`). Al terminar, espera a que la máquina esté configurada y te
enseña su IP y cómo entrar.

Las opciones más usadas:

| Opción | Qué hace |
|--------|----------|
| `--imagen debian12` | Debian 12 en lugar de Ubuntu 24.04 |
| `--extra-disks` | Seis discos extra de 40G (`vdb`..`vdg`) |
| `--ssh-pass -` | Pide una contraseña para entrar también por SSH escribiéndola |
| `--limpiar` | Si ya existe lo que se va a crear, lo elimina antes (te pregunta) |
| `--dry-run` | Comprueba todo y enseña lo que haría, **sin crear nada** |

Todas las demás, en la [referencia completa](docs/provision.md#funcionamiento).

<a id="casos"></a>
## 🧪 Casos de uso del boletín 2

### 🟦 Una máquina

```bash
ssoo-us provision server1                       # Ubuntu 24.04, con DHCP
ssoo-us provision server1 192.168.XXX.2         # con IP fija
ssoo-us provision --imagen debian12 server1     # Debian 12
```

### 🟩 SERVER1 (epígrafe 2.1)

```bash
ssoo-us provision --extra-disks server1 192.168.XXX.2
```

Con la IP `.2` de tu red y seis discos de 40G. Lista para tomar y revertir
instantáneas en cuanto termina; `root` (contraseña `s1st3mas`) es el que te
pedirá la máquina si arranca en **modo de emergencia** (epígrafe 2.3).

### 🟥 Infraestructura GlusterFS (epígrafe 2.4)

```bash
ssoo-us provision --gluster-cluster
```

Crea la imagen base `gluster-base.qcow2` y los cuatro nodos `server1`..`server4`
(IPs `.10` a `.13`), con `glusterd` en marcha y tres discos en xfs montados en
`/gluster1`..`/gluster3`. Tarda unos tres minutos.

> ⚠️ **No borres `gluster-base.qcow2`** mientras existan los nodos: son copias suyas.

Si ya tenías máquinas con esos nombres, añade `--limpiar` para que las elimine
antes. Más variantes en la [referencia completa](docs/provision.md#casos-de-uso).

<a id="asistente"></a>
## 🧭 Asistente con menús

```bash
ssoo-us provision
```

Sin argumentos se abre un asistente que te guía por los mismos casos: eliges qué
hacer, el nombre, la red (DHCP o una IP fija, de la que te propone la primera
libre) y las opciones, y antes de ejecutar te enseña **el comando equivalente**.
Se maneja con el teclado o con el **ratón**:

| Tecla | Qué hace |
|-------|----------|
| `↑` `↓` | Moverse |
| `Espacio` (o un clic) | Marcar una opción |
| `Intro` | Seguir |
| `Tab` | Pasar a los botones «Atrás» y «Siguiente» |
| `Esc` | Volver atrás sin perder lo escrito |
| `Ctrl+C` | Salir |

<a id="ver-eliminar"></a>
## 🗂️ Ver y eliminar tus máquinas

```bash
ssoo-us provision --listar                     # tus máquinas, su estado, su IP y sus discos
ssoo-us provision --eliminar server1           # una máquina, con sus discos
ssoo-us provision --eliminar server1 server2 server3 server4 gluster-base   # el clúster entero
ssoo-us provision --eliminar-todo              # todas
```

Siempre te enseña lo que va a eliminar y te pide confirmación. Nunca borra un
disco que use otra máquina ni las imágenes cloud.

<a id="entrar"></a>
## 🔐 Cómo entrar en las máquinas

```bash
ssh administrador@192.168.XXX.Y          # con tu clave
virsh console TU_USUARIO-server1         # consola: root / s1st3mas (sal con Ctrl+])
```

> 💡 Si `ssh` avisa de `REMOTE HOST IDENTIFICATION HAS CHANGED`, esa IP la tuvo
> antes otra máquina tuya: `provision` te da al terminar la orden `ssh-keygen -R`
> que lo resuelve.

---

<a id="diagnosis"></a>
# 🩺 `ssoo-us diagnosis`: revisar una máquina hecha a mano

Si construyes una máquina **a mano**, siguiendo el manual (sección 5.4), y algo
no funciona, `diagnosis` revisa tu trabajo y te dice **qué falla, por qué, cómo
arreglarlo y en qué sección del manual se explica**. No hace falta para las
máquinas creadas con `provision`.

**Solo lee:** no cambia ningún archivo, no arranca ni apaga máquinas y no
muestra nunca tu clave privada.

<a id="uso-diagnosis"></a>
## ▶️ Uso

Desde tu silo, porque revisa los archivos del directorio en que estás:

```bash
cd $HOME/imagenesMV
ssoo-us diagnosis server1
```

- **Si la máquina aún no existe**, revisa lo que necesita `virt-install`: tu
  silo, tu red, la imagen y el disco, `user-data`, `meta-data` y
  `network-config`, tus claves y, si ya lo intentaste, qué dijo `virt-install`.
- **Si ya existe y no puedes entrar**, revisa la máquina, su red, su disco, tus
  claves, la orden con la que la creaste y tus archivos. Si está encendida, te
  pedirá que la apagues (`virsh shutdown`) para poder leer su disco.

<a id="resultado"></a>
## 📋 Cómo leer el resultado

| | |
|---|---|
| `OK` | Está bien. |
| `AVISO` | Se aparta del manual o puede dar problemas, pero no impide seguir. |
| `ERROR` | Está mal: hay que arreglarlo. |
| `--` | No se ha podido comprobar, porque falla algo de lo que depende. |

Cada AVISO y cada ERROR dice qué efecto tiene, **cómo arreglarlo** (con las
órdenes listas para copiar) y la sección del manual.

> 💡 Empieza siempre por el **primer ERROR**: los demás pueden ser consecuencia suya.

```
ARCHIVOS DE CLOUD-INIT
  OK     Existe user-data
  ERROR  user-data tiene comillas curvas (línea 4) [B1]
         Caracteres: U+2018, U+2019; la comilla es «'».
         Cómo arreglarlo: suele pasar al copiar del PDF o de la web. Escriba
         esa parte a mano con nano.
         Manual: sección 5.4.1 (Pasos preliminares)
```

Si te dice «avise al profesor», el problema no es tuyo: comunícaselo tal cual.

---

<a id="acceso"></a>
# 🔑 `ssoo-us acceso`: por qué no puedes entrar en tu máquina

Si `ssh administrador@IP` no te deja entrar en una de tus máquinas (la hayas
creado a mano, con `ssoo-us provision` o con `ci-provision.sh`), `acceso` te
dice por qué y cómo arreglarlo, **sin apagarla**:

```bash
ssoo-us acceso control2
```

Con la máquina encendida, mira por orden:

1. **La máquina y su red:** si está encendida, su IP, si responde y si el
   puerto 22 está abierto.
2. **Lo que dice `ssh`** al entrar con tu clave, y qué significa:
   `REMOTE HOST IDENTIFICATION HAS CHANGED`, la clave privada con permisos
   demasiado abiertos, o `Permission denied (publickey)`.
3. **Qué clave tiene la máquina**, comparada con las tuyas. Si cambiaste tu
   clave después de crear la máquina, te lo dice y te explica cómo añadirle la
   nueva: si la creaste con `provision` o con `ci-provision.sh`, con la orden
   exacta para hacerlo desde su consola (como `root`); si la hiciste a mano,
   con el procedimiento del manual (FAQ B.3). Si la máquina tiene una clave
   tuya antigua que conservas, te dice cómo entrar con ella.

Se lee igual que `diagnosis` (`OK`, `AVISO`, `ERROR`, con «Cómo arreglarlo» y
la sección del manual) y
**solo lee**: no cambia nada en la máquina ni en tu cuenta. Para ver la clave
sin apagarla usa el agente QEMU de la máquina, que tienen las creadas con
`ssoo-us provision` y con `ci-provision.sh`; si no lo tiene, te dice cómo
revisarla con `ssoo-us diagnosis`.

---

<a id="referencia"></a>
# 📚 Referencia completa

- [🛠️ `ssoo-us provision`](docs/provision.md): todas las opciones, el asistente,
  `--limpiar`, los casos de uso con sus variantes, los accesos, los archivos que
  crea, los códigos de error y las opciones avanzadas.
- [🩺 `ssoo-us diagnosis`](docs/diagnosis.md): qué revisa en cada caso, lo que no
  revisa y sus códigos de salida.

---

**David Gutiérrez Avilés** · Profesor Titular de Universidad · Departamento de
Lenguajes y Sistemas Informáticos · Universidad de Sevilla

<sub>[Para el profesorado](PROFESORADO.md) · [Desarrollo](DESARROLLO.md) · [Licencia MIT](LICENSE)</sub>
