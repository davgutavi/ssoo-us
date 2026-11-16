# 🩺 ssoo-us diagnosis — referencia completa

Todo sobre `ssoo-us diagnosis`. Para empezar basta con el [README](../README.md).

`ssoo-us diagnosis` revisa la construcción **a mano** de una máquina virtual con
cloud-init, siguiendo el manual (sección 5.4), y te dice qué falla, por qué,
cómo arreglarlo y en qué sección del manual se explica. No revisa las máquinas
creadas con `ssoo-us provision`, que no lo necesitan.

**Solo lee.** No cambia ningún archivo, no arranca ni apaga máquinas, no toca
silos ni redes y no muestra nunca tu clave privada.

### ▶️ Cómo se usa

**Desde tu silo**: revisa los archivos del directorio en que estás (si no es tu
silo, te lo dice):

```bash
cd $HOME/imagenesMV
ssoo-us diagnosis server1
```

Cambia `server1` por la máquina que quieres revisar (también vale `1` o
`usuario-server1`). Si no indicas ninguna, se toma del `local-hostname` de tu
archivo `meta-data`.

Según la situación, hace una de dos revisiones:

- **Antes de `virt-install`** (la máquina todavía no existe): tu silo, tu red,
  la imagen base y el disco, los archivos `user-data`, `meta-data` y
  `network-config`, tus claves SSH, que el nombre y la IP estén libres, los
  permisos de tu directorio personal y, si ya intentaste crear la máquina, qué
  dijo `virt-install`.
- **Con la máquina ya creada**, en cinco bloques:
  1. **Máquina y red:** si está encendida, si está conectada a tu red, cómo es
     tu red, su IP y si responde en ella (ping y puerto 22).
  2. **Disco:** su formato, su tamaño y la imagen de la que depende y, con la
     máquina apagada, lo que cloud-init dejó escrito en él: el usuario, la clave
     y la red que configuró, y sus errores.
  3. **Claves SSH y acceso:** tus claves y si `ssh` puede entrar, y por qué no.
  4. **Orden de virt-install:** la orden con la que creaste la máquina, tal como
     la escribiste (la toma de tu registro), comparada opción por opción con la
     del manual.
  5. **Archivos de cloud-init:** `user-data`, `meta-data` y `network-config`.

Elige sola: si la máquina existe, la segunda; si no, la primera. Puedes forzarla
con `--antes` o con `--acceso`.

Si la máquina está encendida y no puedes entrar, te pedirá que la apagues
(`virsh shutdown`) y que la vuelvas a ejecutar: así puede revisar su disco.
Nunca la apaga ella.

```bash
ssoo-us diagnosis server1 --ip 192.168.XXX.YYY   # si la IP no es la de tu network-config
ssoo-us diagnosis -h
```

### 🚫 Lo que no revisa

La conexión desde tu ordenador hasta el servidor: tus claves y tu agente en el
ordenador, `virt-manager` o un bloqueo del servidor por demasiados intentos
fallidos. Si no puedes conectarte al servidor, consulta la sección 4.5 del
manual y la FAQ.

`ssoo-us diagnosis` tampoco cuenta nunca como un intento fallido: para
comprobar si puedes entrar en tu máquina usa solo tu clave, nunca una
contraseña.

<a id="resultado"></a>
### 📋 Cómo leer el resultado

Cada comprobación da una de estas respuestas:

| | |
|---|---|
| `OK` | Está bien. |
| `AVISO` | Se aparta del manual o puede dar problemas, pero no impide seguir. |
| `ERROR` | Está mal: hay que arreglarlo. |
| `--` | No se ha podido comprobar, porque falla algo de lo que depende. |

Los avisos y errores llevan, debajo, el efecto, cómo arreglarlo y la sección del
manual. Las soluciones llevan tus nombres reales (tu usuario, tu máquina, tu IP)
y las órdenes completas, cada una en su línea, listas para copiar. Cuando la
única solución es volver a crear la máquina, se dan todos los pasos: eliminarla
con su disco, crear un disco nuevo, la orden de `virt-install` del manual y
olvidar la huella antigua de `ssh`. Algunos llevan también, entre corchetes, el
código del fallo (`[B5]`): indícalo si preguntas en el chat de dudas.

> 💡 Empieza siempre por el **primer ERROR**: los demás pueden ser consecuencia suya.

Un ejemplo:

```
ARCHIVOS DE CLOUD-INIT
  OK     Existe user-data
  ERROR  user-data tiene comillas curvas (línea 4) [B1]
         Caracteres: U+2018, U+2019; la comilla es «'».
         Cómo arreglarlo: suele pasar al copiar del PDF o de la web. Escriba
         esa parte a mano con nano.
         Manual: sección 5.4.1 (Pasos preliminares)
```

Si la salida te dice «avise al profesor», el problema no es tuyo (por ejemplo, un
silo de otro usuario que hace fallar `virt-install` a todos): comunícaselo a tu
profesor tal cual.

| Código de salida | Significado |
|------------------|-------------|
| **0** | Ningún ERROR |
| **1** | Algún ERROR |
| **2** | No se ha podido hacer la revisión |
