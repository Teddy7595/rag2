#!/usr/bin/env bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_DIR="${VAULT_DIR:-${PROJECT_DIR}/.vault}"
RUNTIME_CONFIG="${VAULT_DIR}/model-runtime-config.json"

log_step() { echo -e "${GREEN}$1${NC}"; }
log_warn()  { echo -e "${YELLOW}$1${NC}"; }

ensure_runtime_config() {
    mkdir -p "$VAULT_DIR"

    if [ -f "$RUNTIME_CONFIG" ]; then
        log_step "[config] model-runtime-config.json encontrado."
        return
    fi

    log_warn "[config] model-runtime-config.json no existe — generando valores por defecto..."

    cat > "$RUNTIME_CONFIG" <<'EOF'
{
  "text_generation_temperature": 0.55,
  "text_generation_top_p": 0.97,
  "text_generation_max_tokens": 3072,
  "text_generation_min_p": 0.03,
  "text_generation_repeat_penalty": 1.08,
  "text_generation_presence_penalty": 0.0,
  "text_generation_frequency_penalty": 0.0,
  "text_generation_seed": -1
}
EOF

    log_step "[config] model-runtime-config.json creado en: ${RUNTIME_CONFIG}"
}

main() {
    cd "$PROJECT_DIR"

    ensure_runtime_config

    log_step "[start] Iniciando RAG2..."
    exec uv run python main.py "$@"
}

main "$@"
