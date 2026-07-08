#!/usr/bin/env bash
# Installer for openSUSE (zypper). AMD GPU only.
#
# ROCm on openSUSE ships under /usr (FHS layout), not /opt/rocm like Arch,
# and does not package hipBLAS/rocBLAS. Because of that:
#   - torch/torchvision/sentence-transformers use prebuilt ROCm wheels from
#     PyPI (self-contained, don't need system hipBLAS).
#   - llama-cpp-python is compiled with the Vulkan backend (GGML_VULKAN),
#     not HIP, since HIP compilation needs hipBLAS which isn't packaged here.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
ROCM_TORCH_BACKEND="${ROCM_TORCH_BACKEND:-rocm7.2}"
HSA_GFX_OVERRIDE="${HSA_OVERRIDE_GFX_VERSION:-11.0.0}"
ROCM_PATH_RESOLVED="/usr"
ROCM_LIB_DIR="/usr/lib64"

SHELL_ENV_DIR="${HOME}/.config/rag2"
SHELL_ENV_FILE="${SHELL_ENV_DIR}/amd-rocm.sh"
FISH_ENV_DIR="${HOME}/.config/fish/conf.d"
FISH_ENV_FILE="${FISH_ENV_DIR}/rag2-amd-rocm.fish"

log_step() { echo -e "${GREEN}$1${NC}"; }
log_warn() { echo -e "${YELLOW}$1${NC}"; }
log_error() { echo -e "${RED}$1${NC}" >&2; }

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_error "[ERROR] Falta el comando requerido: $1"
        exit 1
    fi
}

detect_amd_gpu_target() {
    if ! command -v rocminfo >/dev/null 2>&1; then
        return 1
    fi
    rocminfo 2>/dev/null | awk '/^[[:space:]]*Name:[[:space:]]*gfx[0-9]+/ { print $2; exit }'
}

resolve_amd_gpu_target() {
    if [ -n "${AMD_GPU_TARGET:-}" ]; then
        printf '%s' "$AMD_GPU_TARGET"
        return 0
    fi

    local detected_target
    detected_target="$(detect_amd_gpu_target || true)"
    if [ -n "$detected_target" ]; then
        printf '%s' "$detected_target"
        return 0
    fi

    log_error "[ERROR] No se pudo detectar AMD_GPU_TARGET con rocminfo. Exporta AMD_GPU_TARGET manualmente y reintenta."
    exit 1
}

persist_rocm_env() {
    mkdir -p "$SHELL_ENV_DIR" "$FISH_ENV_DIR"

    cat > "$SHELL_ENV_FILE" <<EOF
export ROCM_PATH=${ROCM_PATH_RESOLVED}
export HIP_PATH=${ROCM_PATH_RESOLVED}
export HSA_OVERRIDE_GFX_VERSION=${HSA_GFX_OVERRIDE}
export LD_LIBRARY_PATH="\${LD_LIBRARY_PATH:+\$LD_LIBRARY_PATH:}${ROCM_LIB_DIR}"
EOF

    cat > "$FISH_ENV_FILE" <<EOF
set -gx ROCM_PATH ${ROCM_PATH_RESOLVED}
set -gx HIP_PATH ${ROCM_PATH_RESOLVED}
set -gx HSA_OVERRIDE_GFX_VERSION ${HSA_GFX_OVERRIDE}
if set -q LD_LIBRARY_PATH
    set -gx LD_LIBRARY_PATH "\$LD_LIBRARY_PATH:${ROCM_LIB_DIR}"
else
    set -gx LD_LIBRARY_PATH ${ROCM_LIB_DIR}
end
EOF

    if ! grep -Fq "$SHELL_ENV_FILE" "${HOME}/.bashrc" 2>/dev/null; then
        {
            echo ""
            echo "# Configuracion AMD ROCm para rag2"
            echo "[ -f \"$SHELL_ENV_FILE\" ] && source \"$SHELL_ENV_FILE\""
        } >> "${HOME}/.bashrc"
    fi

    # shellcheck disable=SC1090
    source "$SHELL_ENV_FILE"
}

main() {
    cd "$PROJECT_DIR"

    if ! command -v zypper >/dev/null 2>&1; then
        log_error "[ERROR] Este instalador esta preparado para openSUSE / zypper."
        log_error "[ERROR] En Arch o derivados usa ./installer-arch.sh"
        exit 1
    fi

    # /tmp puede tener cuota por usuario (tmpfs con usrquota) demasiado chica
    # para compilar llama-cpp-python (cientos de objetos + shaders Vulkan).
    # Se usa un directorio propio del proyecto en vez de /tmp para builds.
    export TMPDIR="${PROJECT_DIR}/.build-tmp"
    mkdir -p "$TMPDIR"
    trap 'rm -rf "$TMPDIR"' EXIT

    log_step "[1/6] Instalando dependencias del sistema (build toolchain, ROCm runtime, Vulkan)..."
    sudo zypper --non-interactive install --no-confirm -t pattern devel_basis
    sudo zypper --non-interactive install --no-confirm \
        cmake \
        rocm-hip \
        rocminfo \
        rocm-smi \
        vulkan-devel \
        shaderc \
        shaderc-devel \
        spirv-headers \
        spirv-tools-devel

    export PATH="${HOME}/.local/bin:${PATH}"
    if ! command -v uv >/dev/null 2>&1; then
        sudo zypper --non-interactive install --no-confirm uv || curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    require_command uv
    require_command glslc

    AMD_GPU_TARGET="$(resolve_amd_gpu_target)"
    log_step "[info] AMD_GPU_TARGET resuelto: ${AMD_GPU_TARGET}"

    log_step "[2/6] Persistiendo variables ROCm para bash y fish..."
    persist_rocm_env

    log_step "[3/6] Preparando Python ${PYTHON_VERSION} y entorno UV..."
    uv python install "$PYTHON_VERSION"
    uv venv --python "$PYTHON_VERSION" --allow-existing .venv

    VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
    require_command "$VENV_PYTHON"

    log_step "[4/6] Sincronizando dependencias del proyecto..."
    uv sync --dev

    log_step "[5/6] Instalando stack AMD para embeddings (opcional pero recomendado para RAG avanzado)..."
    uv pip install \
        --python "$VENV_PYTHON" \
        --torch-backend "$ROCM_TORCH_BACKEND" \
        torch \
        torchvision \
        sentence-transformers

    log_step "[6/6] Compilando llama-cpp-python para Vulkan..."
    export FORCE_CMAKE=1
    export CMAKE_ARGS="-DGGML_VULKAN=ON"
    uv pip install \
        --python "$VENV_PYTHON" \
        --reinstall \
        --no-cache \
        --no-binary llama-cpp-python \
        llama-cpp-python

    if ! find "${PROJECT_DIR}/.venv" -iname 'libggml-vulkan.so' 2>/dev/null | grep -q .; then
        log_error "[ERROR] libggml-vulkan.so no aparece en .venv tras la compilacion."
        log_error "[ERROR] llama-cpp-python quedo CPU-only pese a CMAKE_ARGS=-DGGML_VULKAN=ON."
        exit 1
    fi

    log_step "--- VERIFICACION FINAL ---"
    "$VENV_PYTHON" <<'END'
import importlib.util
import json

payload = {
    "llama_cpp_installed": importlib.util.find_spec("llama_cpp") is not None,
    "sentence_transformers_installed": importlib.util.find_spec("sentence_transformers") is not None,
}
if payload["llama_cpp_installed"]:
    from llama_cpp import llama_cpp

    payload["gpu_offload_supported"] = bool(llama_cpp.llama_supports_gpu_offload())

print(json.dumps(payload, ensure_ascii=True))
if payload.get("llama_cpp_installed") and not payload.get("gpu_offload_supported"):
    raise SystemExit("[ERROR] llama-cpp-python quedo compilado sin offload GPU. Revisa CMAKE_ARGS/Vulkan.")
END

    log_warn "Instalacion completada. Abre una terminal nueva para heredar las variables persistidas en bash/fish."
}

main "$@"
