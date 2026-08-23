# Brief: Corrección de Chat Template en Modelos Locales (RAG / Engramas)

> Documento de handoff para agente de código. Contiene síntoma, diagnóstico y tarea a ejecutar. No implementar nada fuera de lo descrito en la sección 4 sin confirmar con el usuario.

---

## 1. Síntoma observado

Al conversar con modelos locales servidos vía llama.cpp/koboldcpp, el modelo responde correctamente a la pregunta del usuario pero **no se detiene al terminar su turno** — continúa generando texto adicional que simula un intercambio completo, incluyendo líneas con prefijo tipo `- usuario pregunta...` que inventan preguntas y respuestas no formuladas por el usuario real. El contenido generado en ese "auto-diálogo" es inconsistente con lo que el usuario preguntó (ej. usuario pregunta por categorías de historias, modelo continúa generando turnos de usuario no relacionados).

## 2. Diagnóstico técnico (causa raíz)

**No es un problema de capacidad del modelo ni de calidad del RAG.** Es un desajuste entre el **chat template** con el que el server ensambla el prompt y el chat template con el que el modelo fue efectivamente fine-tuneado.

Cada modelo instruct-tuned aprende, durante su fine-tuning, a asociar tokens especiales específicos (ej. `<|im_start|>` / `<|im_end|>` en ChatML, `<|start_header_id|>...<|end_header_id|>` en Llama-3, `[INST]...[/INST]` en Mistral) con el concepto "aquí termina mi turno". Si el server aplica un template distinto al que el checkpoint espera, el modelo nunca recibe la señal de stop que reconoce y continúa generando — estadísticamente, lo más probable después de "fin de turno de asistente" en su data de entrenamiento es el inicio de un turno de usuario, de ahí el patrón observado.

Causas posibles a verificar, en orden de probabilidad:
1. Chat template embebido en el GGUF no coincide con el fine-tune real (conversión GGUF de comunidad mal empaquetada, o metadata desactualizada).
2. `stop` sequences no configuradas explícitamente si se usa el endpoint `/completion` en vez de `/chat/completions`.
3. Contenido inyectado por el RAG (chunks recuperados, ejemplos de engramas en formato pregunta-respuesta) sin delimitadores claros, tratado por el modelo como continuación literal de la conversación en vez de material de referencia.
4. `max_tokens`/`n_predict` sin límite razonable, amplificando el síntoma aunque no sea la causa raíz.

## 3. Objetivo de la tarea

Para cada modelo GGUF presente en la carpeta local de modelos, determinar el chat template correcto, dejar constancia en un perfil de modelo versionado, y usar esa información para: (a) forzar el template correcto en la llamada al server, y (b) envolver el contenido inyectado por el RAG con delimitadores explícitos que eviten que el modelo lo trate como turno de conversación real.

## 4. Pasos a ejecutar

### 4.1 Inventario de modelos

- Escanear la carpeta de modelos locales (ruta a confirmar con el usuario — típicamente algo como `~/ai_models` o `/vault/ai_models`) y listar todos los archivos `.gguf`.
- Para cada archivo, registrar: nombre de archivo, tamaño, cuantización (extraíble del nombre, ej. `Q4_K_M`).

### 4.2 Extracción de metadata embebida

Antes de buscar en internet, leer la metadata que el propio GGUF ya trae — muchas veces el chat template correcto (o al menos el nombre exacto del modelo base/fine-tune) ya está embebido:

```bash
# Opción 1: usando el script de llama.cpp
python3 llama.cpp/gguf-py/scripts/gguf_dump.py --no-tensors modelo.gguf | grep -i "tokenizer.chat_template\|general.name\|general.basename"

# Opción 2: usando la librería gguf de Python directamente
uv run --with gguf python3 -c "
import gguf
reader = gguf.GGUFReader('modelo.gguf')
for field in reader.fields.values():
    if 'chat_template' in field.name or 'general.name' in field.name or 'general.basename' in field.name:
        print(field.name, '->', field.parts[field.data[0]] if field.data else None)
"
```

Si el campo `tokenizer.chat_template` existe y no está vacío, ese es el template autoritativo — no hace falta adivinar.

### 4.3 Investigación online (solo si la metadata embebida falta o es ambigua)

- A partir del `general.name` / `general.basename` extraído, buscar el modelo original en HuggingFace (el repo del fine-tune, no de la cuantización GGUF de terceros si es posible identificarlo).
- Confirmar en `tokenizer_config.json` del repo original el campo `chat_template` (formato Jinja2).
- Confirmar también en la tarjeta del modelo (README) si el autor especifica explícitamente el formato de prompt recomendado (a veces difiere de lo técnicamente embebido si el autor documentó un formato "probado" alternativo).
- Registrar la fuente (URL del repo consultado) junto con el template encontrado, para trazabilidad.

### 4.4 Esquema de perfil de modelo

Crear (o extender si ya existe) un archivo de configuración por modelo — sugerido en JSON o YAML, uno por modelo, o un único archivo con un registro por modelo:

```yaml
# model_profiles.yaml
- filename: "modelo-ejemplo-Q4_K_M.gguf"
  display_name: "Nombre legible"
  base_model: "org/nombre-repo-original-hf"
  chat_template_format: "chatml"   # chatml | llama3 | mistral-instruct | vicuna | alpaca | otro
  llamacpp_chat_format: "chatml"   # string exacto a pasar como chat_format=... si está en la lista built-in; "custom_jinja2" si requiere Jinja2ChatFormatter manual
  stop_tokens: ["<|im_end|>"]
  chat_template_source: "embedded_gguf"   # embedded_gguf | huggingface_tokenizer_config | model_card
  chat_template_verified_url: "https://huggingface.co/org/repo"
  notes: ""
```

Este perfil es lo que el orquestador RAG debe leer al momento de armar la llamada al server — nunca asumir un template por defecto.

### 4.5 Reconfiguración del RAG

Dos cambios independientes, ambos necesarios:

**a) Aplicación forzada del template correcto por modelo (llama-cpp-python):**

El stack usa la librería `llama-cpp-python`, no el binario `llama-server` standalone — el mecanismo de template se controla en la instanciación de la clase `Llama`, no por flag de CLI. Hay tres rutas posibles, en orden de preferencia:

1. **Auto-detección desde metadata embebida.** Si no se pasa `chat_format` ni `chat_handler` al constructor, versiones recientes de `llama-cpp-python` intentan leer `tokenizer.chat_template` directamente del GGUF (vía `Jinja2ChatFormatter` interno) y renderizarlo automáticamente. Esto solo funciona si 4.2 confirmó que el campo viene bien poblado en el GGUF — **no asumir que funciona, verificar explícitamente** loggeando el prompt final ensamblado (`Llama(..., verbose=True)` expone esto).

2. **`chat_format` con string de la lista soportada.** Si el template del modelo coincide con uno de los formatos built-in de la librería (`"chatml"`, `"llama-3"`, `"mistral-instruct"`, `"vicuna"`, `"alpaca"`, `"zephyr"`, `"gemma"`, `"openchat"`, entre otros — la lista exacta depende de la versión instalada, revisar `llama_cpp.llama_chat_format`), forzarlo explícitamente en la instanciación:
   ```python
   llm = Llama(model_path="modelo.gguf", chat_format="chatml", verbose=True)
   ```
   Este es el camino preferido cuando aplica — es explícito, no depende de que la metadata del GGUF esté bien empaquetada.

3. **`chat_handler` custom vía Jinja2 cuando el template no está en la lista soportada.** Construir el formatter manualmente a partir del `chat_template` (Jinja2) extraído del `tokenizer_config.json` del repo HF original (paso 4.3):
   ```python
   from llama_cpp.llama_chat_format import Jinja2ChatFormatter

   formatter = Jinja2ChatFormatter(
       template=jinja_template_string,  # extraído de tokenizer_config.json
       eos_token="<|im_end|>",          # confirmar contra el modelo específico
       bos_token="<|im_start|>",
   )
   llm = Llama(model_path="modelo.gguf", chat_handler=formatter.to_chat_handler(), verbose=True)
   ```

**Stop tokens:** al usar `create_chat_completion()` (no `create_completion()` crudo), el formatter resuelto por cualquiera de las tres rutas ya inyecta los stop tokens correctos como parte de su `ChatFormatterResponse` — no hace falta pasarlos a mano salvo que se detecte que el modelo sigue sin cortar, en cuyo caso pasar `stop=[...]` explícito en la llamada como override usando el/los `stop_tokens` registrados en el perfil (4.4) es el fallback correcto. Si el orquestador RAG usa `create_completion()` con prompt ensamblado a mano en vez de `create_chat_completion()`, los `stop_tokens` del perfil son obligatorios en cada llamada, no opcionales.

**b) Delimitación explícita del contexto inyectado por el RAG:**
Envolver cualquier contenido recuperado (chunks, ejemplos de engramas) con marcadores estructurales explícitos dentro del prompt, separados de la conversación real, de forma que el modelo no lo interprete como turnos de diálogo a continuar:

```
<contexto_referencia>
{chunks recuperados}
</contexto_referencia>

<conversacion_actual>
usuario: {mensaje real}
</conversacion_actual>
```

## 5. Criterios de aceptación

- Cada modelo en la carpeta de modelos tiene una entrada en `model_profiles.yaml` con `chat_template_format`, `stop_tokens` y `chat_template_source` completos (no vacíos, no placeholder).
- El orquestador del RAG lee el perfil correspondiente al modelo activo antes de armar cada request — cero templates hardcodeados a nivel global.
- Prueba de humo: enviar una pregunta simple a cada modelo configurado (vía `create_chat_completion()`) y confirmar que la respuesta termina limpiamente sin generar turnos de usuario adicionales.
- El prompt final ensamblado, inspeccionado con `Llama(..., verbose=True)`, muestra los tokens especiales correctos del template aplicado y los delimitadores de contexto de la sección 4.5b presentes en la posición esperada.

## 6. Fuera de alcance

- No modificar el schema de columnas del CSV de engramas (`name,color_hex,avatar,perfil,prompt,regla,ejemplos,historia`) — es un tema independiente ya cerrado.
- No re-cuantizar ni re-descargar modelos — esta tarea es de configuración de serving, no de gestión de artefactos de modelo.
