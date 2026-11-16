# 👨‍🏫 ssoo-us — Para el profesorado

Esta página es para el profesorado de la asignatura. Si eres alumno, lo que
necesitas está en el [README](README.md).

---

# 1. 🔍 Revisar la cuenta de un alumno: `ssoo-us-admin`

`ssoo-us-admin` lanza `ssoo-us diagnosis` sobre la cuenta de un alumno, **como
si la ejecutara él**: revisa sus archivos, sus claves y su acceso por ssh tal y
como los vería él. Necesita `sudo`, así que solo sirve al profesorado. Está
instalado en `/usr/local/sbin`, en los tres servidores.

```bash
ssoo-us-admin UVUS            # la máquina de su meta-data
ssoo-us-admin UVUS server2    # otra máquina
ssoo-us-admin UVUS server1 --acceso
```

Muestra sus silos y sus máquinas, elige el directorio en el que trabaja (su silo
`UVUS-imagenesMV`, o `~/imagenesMV`; `--dir DIRECTORIO` para indicar otro) y
ejecuta `ssoo-us diagnosis` como el alumno con `sudo`, que pide tu contraseña.
Las opciones `--antes`, `--acceso` e `--ip IP` se le pasan tal cual.

**Solo lee:** no cambia nada en la cuenta del alumno, y libvirt se abre en solo
lectura.

---

# 2. 📦 Instalar o actualizar `ssoo-us` en un servidor

`ssoo-us` está instalado en cada servidor como una orden para todos los
usuarios, así que todos usan la misma versión. Se ejecuta con los permisos de
quien la lanza. Necesita:

| Qué | Paquete | Para qué |
|-----|---------|----------|
| `/usr/bin/python3` (3.8 o posterior) | `python3` | todo |
| PyYAML | `python3-yaml` | `diagnosis` (estructura de los archivos de cloud-init) |
| `libvirt` de Python | `python3-libvirt` | `diagnosis` |
| `prompt_toolkit` | `python3-prompt-toolkit` | el asistente (`ssoo-us provision --menu`) |

Se copian `ssoo-us`, `tools/instalar.sh` y `tools/ssoo-us-admin` al servidor
(en `DIR/` y `DIR/tools/`) y, con la cuenta de un profesor:

```bash
sudo bash DIR/tools/instalar.sh            # instala o actualiza
sudo bash DIR/tools/instalar.sh --quitar   # lo quita
```

Instala `/usr/local/bin/ssoo-us` y `/usr/local/sbin/ssoo-us-admin`:

- Antes comprueba que el `python3` del sistema puede con él, y avisa si le falta
  alguno de los módulos de la tabla.
- Dice qué versión había y cuál queda.
- Copia cada archivo con otro nombre y luego lo renombra: quien lo esté usando
  en ese momento sigue con la versión anterior y nadie ve un archivo a medias.

**Cada instalación lleva su versión** (`ssoo-us --version`). El instalador no
instala un `ssoo-us` distinto con la misma versión que el que ya está: antes hay
que subirla (ver [DESARROLLO.md](DESARROLLO.md)). Si es exactamente el mismo,
dice que no hay nada que hacer.

---

[README](README.md) · [Desarrollo](DESARROLLO.md)
