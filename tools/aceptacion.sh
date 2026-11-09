#!/bin/bash
# Tests de aceptación de «ssoo-us provision»: los de bats de ci-provision,
# importados en tests/aceptacion/ (ver DESARROLLO.md).
#
#   bash tools/aceptacion.sh                    todos
#   bash tools/aceptacion.sh --fase 2           los de las fases 0, 1 y 2 del port
#                                               (tests/aceptacion/fases.txt)
#   bash tools/aceptacion.sh -f 'error 1[0-9]'  los que coincidan (opciones de bats)
#
# --fase va la primera; detrás se pueden añadir opciones de bats (--tap...).
# Con el Python de .venv si existe (tiene PyYAML); si no, el python3 del PATH.
# Se puede fijar otro con SSOO_US_PYTHON.
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BATS="$RAIZ/tests/aceptacion/bats/bats-core/bin/bats"
if [[ ! -x "$BATS" ]]; then
    echo "Falta bats: git submodule update --init" >&2
    exit 1
fi
if [[ -z "${SSOO_US_PYTHON:-}" ]]; then
    if [[ -x "$RAIZ/.venv/bin/python" ]]; then
        SSOO_US_PYTHON="$RAIZ/.venv/bin/python"
    else
        SSOO_US_PYTHON="$(command -v python3)"
    fi
fi
export SSOO_US_PYTHON

# --fase N: los tests de las fases 0..N, por su nombre exacto
if [[ "${1:-}" == --fase ]]; then
    fase="${2:-}"
    if ! [[ "$fase" =~ ^[0-6]$ ]]; then
        echo "Uso: bash tools/aceptacion.sh --fase N [opciones de bats]   (N de 0 a 6)" >&2
        exit 1
    fi
    shift 2
    filtro="$(awk -F'\t' -v f="$fase" '/^[0-9]\t/ && $1 <= f { print $2 }' \
                  "$RAIZ/tests/aceptacion/fases.txt" \
              | sed 's/[][\.*^$(){}?+|/]/\\&/g' | paste -s -d '|' -)"
    set -- -f "^($filtro)\$" "$@"
fi

exec "$BATS" "$@" "$RAIZ/tests/aceptacion/ci-provision.bats"
