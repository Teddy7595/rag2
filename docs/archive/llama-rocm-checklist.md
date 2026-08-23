# Checklist llama.cpp + ROCm (AMD)

## 1) Entorno base

- Kernel Linux actualizado y GPU AMD visible con `rocminfo`.
- ROCm instalado y `hipcc` disponible en `PATH`.
- Variables mínimas:
  - `HSA_OVERRIDE_GFX_VERSION` (si tu GPU lo requiere)
  - `HIP_VISIBLE_DEVICES` (opcional, para fijar dispositivo)

## 2) Build del binding

- Ejecutar `./installer.sh` para compilar `llama-cpp-python` con backend HIP.
- Verificar que el build detecta HIP/ROCm sin fallback silencioso a CPU.

## 3) Validación runtime

- API de estado: `GET /api/models/runtime/status`
- Smokes:
  - `POST /api/models/runtime/text`
  - `POST /api/models/runtime/vision`
- Confirmar en respuesta:
  - `runtime_adapter_status = wired`
  - `provider = local`

## 4) Validación de modelos

- Colocar bundles en `ai_models/` (texto y, para visión, `mmproj`).
- Cambiar selección activa en `PATCH /api/models/selection`.
- Revalidar smokes de texto/visión.

## 5) Diagnóstico web

- Revisar:
  - `/admin/runtime-ai`
  - `/admin/models`
  - `/chat`

## 6) Criterio de aceptación

- El sistema responde en local para texto y visión.
- No hay error de binding en `/api/models/runtime/status`.
- Chat y rutas de ingestión pueden usar runtime local sin configuración manual extra.
