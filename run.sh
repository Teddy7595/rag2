#!/usr/bin/env bash
# Lanza rag2 sin pasar por `uv sync` / `uv run` directamente.
#
# `llama-cpp-python` esta listado en pyproject.toml como dependencia normal,
# sin flags de build. Eso significa que cualquier `uv sync` (o `uv run`, que
# sincroniza por defecto) reinstala silenciosamente una build CPU-only y
# pisa el backend GPU (Vulkan en openSUSE, HIP en Arch) compilado por el
# instalador, sin ningun error visible.
#
# Este script arranca la app directamente con el Python del venv (nunca via
# `uv run`), y si detecta que el .so del backend GPU desaparecio, lo
# recompila antes de levantar el servidor.

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

log_step() { echo -e "${GREEN}$1${NC}"; }
log_warn() { echo -e "${YELLOW}$1${NC}"; }
log_error() { echo -e "${RED}$1${NC}" >&2; }

VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    log_error "[ERROR] No existe .venv. Corre primero el instalador de tu distro:"
    log_error "  ./installer-arch.sh       (Arch y derivados)"
    log_error "  ./installer-opensuse.sh   (openSUSE Tumbleweed)"
    exit 1
fi

detect_expected_gpu_backend() {
    if command -v pacman >/dev/null 2>&1; then
        printf '%s' "hip"
    elif command -v zypper >/dev/null 2>&1; then
        printf '%s' "vulkan"
    else
        printf '%s' ""
    fi
}

gpu_backend_so_name() {
    case "$1" in
        hip) printf '%s' "libggml-hip.so" ;;
        vulkan) printf '%s' "libggml-vulkan.so" ;;
    esac
}

resolve_amd_gpu_target() {
    if [ -n "${AMD_GPU_TARGET:-}" ]; then
        printf '%s' "$AMD_GPU_TARGET"
        return 0
    fi
    if command -v rocminfo >/dev/null 2>&1; then
        rocminfo 2>/dev/null | awk '/^[[:space:]]*Name:[[:space:]]*gfx[0-9]+/ { print $2; exit }'
    fi
}

repair_gpu_backend() {
    local backend="$1"
    log_warn "[run] llama-cpp-python no tiene el backend GPU (${backend}). Recompilando..."

    local build_tmp="${PROJECT_DIR}/.build-tmp"
    mkdir -p "$build_tmp"
    export TMPDIR="$build_tmp"
    export FORCE_CMAKE=1

    case "$backend" in
        hip)
            local target
            target="$(resolve_amd_gpu_target)"
            if [ -z "$target" ]; then
                log_error "[ERROR] No se pudo resolver AMD_GPU_TARGET para recompilar HIP."
                rm -rf "$build_tmp"
                exit 1
            fi
            export CMAKE_ARGS="-DGGML_HIP=ON -DGPU_TARGETS=${target}"
            ;;
        vulkan)
            export CMAKE_ARGS="-DGGML_VULKAN=ON"
            ;;
        *)
            log_error "[ERROR] Backend GPU desconocido: ${backend}"
            rm -rf "$build_tmp"
            exit 1
            ;;
    esac

    uv pip install \
        --python "$VENV_PYTHON" \
        --reinstall \
        --no-cache \
        --no-binary llama-cpp-python \
        llama-cpp-python

    rm -rf "$build_tmp"

    if ! find "${PROJECT_DIR}/.venv" -iname "$(gpu_backend_so_name "$backend")" 2>/dev/null | grep -q .; then
        log_error "[ERROR] La recompilacion no produjo $(gpu_backend_so_name "$backend"). Revisa manualmente."
        exit 1
    fi

    log_step "[run] Backend GPU (${backend}) restaurado."
}

sync_firewall_port() {
    if ! command -v firewall-cmd >/dev/null 2>&1; then
        return 0
    fi
    if [ ! -f "${PROJECT_DIR}/.env" ]; then
        return 0
    fi

    local zone="${FIREWALL_ZONE:-public}"
    local state_dir="${HOME}/.config/rag2"
    local state_file="${state_dir}/last-port"
    mkdir -p "$state_dir"

    local current_port
    current_port="$(grep -E '^APP_PORT=' "${PROJECT_DIR}/.env" | tail -1 | cut -d= -f2 | tr -d '"'"'"' \r')"
    if [ -z "$current_port" ]; then
        return 0
    fi

    local last_port=""
    [ -f "$state_file" ] && last_port="$(cat "$state_file")"

    if [ "$current_port" = "$last_port" ]; then
        return 0
    fi

    log_warn "[run] Puerto cambio (${last_port:-ninguno} -> ${current_port}). Sincronizando firewall (zona: ${zone})..."

    if [ -n "$last_port" ]; then
        sudo firewall-cmd --zone="$zone" --remove-port="${last_port}/tcp" --permanent >/dev/null 2>&1 || true
    fi
    sudo firewall-cmd --zone="$zone" --add-port="${current_port}/tcp" --permanent
    sudo firewall-cmd --reload

    printf '%s' "$current_port" > "$state_file"
    log_step "[run] Firewall sincronizado: ${current_port}/tcp abierto en zona '${zone}'."
}

sync_firewall_port

BACKEND="$(detect_expected_gpu_backend)"
if [ -n "$BACKEND" ]; then
    SO_NAME="$(gpu_backend_so_name "$BACKEND")"
    if ! find "${PROJECT_DIR}/.venv" -iname "$SO_NAME" 2>/dev/null | grep -q .; then
        repair_gpu_backend "$BACKEND"
    fi
fi

log_step "[run] Iniciando rag2 (sin uv sync / uv run)..."
exec "$VENV_PYTHON" main.py
