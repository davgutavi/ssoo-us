#!/bin/bash
# Instala ssoo-us en un servidor de la asignatura, para todos los usuarios:
#
#   sudo bash tools/instalar.sh            instala (o actualiza)
#   sudo bash tools/instalar.sh --quitar   lo quita
#
# Instala el ssoo-us del directorio de arriba en /usr/local/bin/ssoo-us (lo usan
# los alumnos: «ssoo-us provision ...», «ssoo-us diagnosis») y tools/ssoo-us-admin
# en /usr/local/sbin/ssoo-us-admin (para el profesorado). Cada archivo se copia
# con otro nombre y después se renombra (mv): quien esté usando ssoo-us en ese
# momento sigue con la versión anterior, y nadie ve nunca un archivo a medias.
#
# DESTINO=RUTA instala en RUTA/bin y RUTA/sbin en lugar de /usr/local (lo usan
# los tests).

set -euo pipefail
export LC_ALL=C
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSOO_US="$AQUI/../ssoo-us"
ADMIN="$AQUI/ssoo-us-admin"
DESTINO="${DESTINO:-/usr/local}"
PY=/usr/bin/python3

instalar_archivo() {   # ORIGEN DESTINO
    local temporal
    temporal="$(dirname "$2")/.$(basename "$2").nuevo.$$"
    install -m 755 "$1" "$temporal"
    mv -f "$temporal" "$2"
}

version() {   # ARCHIVO
    if [[ -f "$1" ]]; then "$PY" "$1" --version 2>/dev/null || echo "(no se puede ejecutar)"
    else echo "(no estaba)"; fi
}

for d in "$DESTINO/bin" "$DESTINO/sbin"; do
    if [[ ! -d "$d" || ! -w "$d" ]]; then
        echo "No puedo escribir en $d: lánzalo con sudo." >&2
        exit 1
    fi
done

if [[ "${1:-}" == "--quitar" ]]; then
    for f in "$DESTINO/bin/ssoo-us" "$DESTINO/sbin/ssoo-us-admin"; do
        if [[ -e "$f" ]]; then rm -f "$f"; echo "Quitado: $f"; else echo "No estaba: $f"; fi
    done
    exit 0
elif [[ -n "${1:-}" ]]; then
    echo "Uso: sudo bash $0 [--quitar]" >&2
    exit 2
fi

[[ -f "$SSOO_US" ]] || { echo "No encuentro $SSOO_US" >&2; exit 1; }
[[ -f "$ADMIN" ]] || { echo "No encuentro $ADMIN" >&2; exit 1; }

# Lo que necesita, en el python3 del sistema (el del #!)
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
    || { echo "$PY es anterior a Python 3.8." >&2; exit 1; }
"$PY" "$SSOO_US" --version >/dev/null || { echo "$SSOO_US no arranca con $PY." >&2; exit 1; }
for modulo in yaml libvirt; do
    if ! "$PY" -c "import $modulo" 2>/dev/null; then
        echo "AVISO: $PY no tiene el módulo $modulo: diagnosis no podrá hacer toda la revisión."
    fi
done

antes="$(version "$DESTINO/bin/ssoo-us")"
instalar_archivo "$SSOO_US" "$DESTINO/bin/ssoo-us"
instalar_archivo "$ADMIN" "$DESTINO/sbin/ssoo-us-admin"
echo "ssoo-us: $antes → $(version "$DESTINO/bin/ssoo-us")"
ls -l "$DESTINO/bin/ssoo-us" "$DESTINO/sbin/ssoo-us-admin"
