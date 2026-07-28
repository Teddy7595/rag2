# Técnicas de Diseño: Sistema de Engramas de Personalidad

> Documento de referencia arquitectónica — consolidación de las técnicas discutidas para dotar de persistencia, coherencia narrativa y "presencia" a un sistema local de engramas conversacionales sobre hardware restringido (RX 7800 XT 16GB / 32GB RAM).

---

## 1. Arquitectura de memoria y persistencia (el "engrama" en sí)

Basado en *Generative Agents: Interactive Simulacra of Human Behavior* (Park et al., Stanford/Google, 2023).

### 1.1 Memory Stream con scoring triple

Cada recuerdo/observación se recupera ponderando tres factores, no solo similitud coseno:

```
score = α·recency(t) + β·importance(obs) + γ·relevance(query, obs)
```

- **Recency**: decaimiento exponencial desde el *último acceso* (no desde la creación — cada recuperación "refresca" el recuerdo).
- **Importance**: score 1-10 asignado por el LLM al insertar la observación ("¿qué tan significativo es esto para la identidad del engrama?"). Se guarda como metadata.
- **Relevance**: similitud coseno estándar contra el embedding de la query/contexto actual.

### 1.2 Reflection Layer

Cuando la suma de importancia de observaciones recientes supera un umbral, se dispara una síntesis: el LLM lee esas observaciones y genera una reflexión de nivel superior, que se reinserta en el memory stream con más peso, referenciando los nodos que la originaron. Esto crea jerarquía de memoria — sin esto, el engrama solo acumula logs planos y nunca "aprende sobre sí mismo".

### 1.3 Motor de estado afectivo — modelo PAD

Reemplazo estructurado de atributos sueltos ad-hoc (líbido, humor, empatía como variables inconexas):

- **PAD (Pleasure-Arousal-Dominance)**: vector de 3 floats, estándar en psicología afectiva computacional.
- Se actualiza tras cada interacción (delta pequeño, por regla determinista o scoring del LLM).
- Decae hacia una baseline homeostática con el tiempo (personalidad "por defecto" si no pasa nada).
- Se inyecta en **cada** llamada de generación como contexto explícito (`P=0.3, A=0.7, D=-0.2` → el system prompt traduce esto a tono/comportamiento).
- Ventaja sobre atributos sueltos: es auditable — se puede graficar la trayectoria emocional en el tiempo y verificar coherencia.

### 1.4 Loop autónomo (el engrama "vive" sin que le hables)

- Proceso demonio independiente por engrama (systemd timer o `asyncio.sleep` en loop), desacoplado del ciclo request-response del chat.
- En cada tick: **heurística barata primero** (tiempo desde última interacción, estado afectivo actual, probabilidad ponderada) decide si vale la pena invocar al LLM grande.
- Si la heurística aprueba → llamada real: "dado tu memory stream + estado actual, ¿qué piensas/haces ahora?" → resultado se escribe de vuelta al memory stream y opcionalmente dispara mensaje proactivo al usuario.

### 1.5 Orquestador multi-engrama

- Cada engrama = namespace aislado (colección propia en vector DB, estado PAD propio, persona config propio).
- **Cuello de botella real**: una sola GPU de 16GB no soporta N engramas con loops autónomos disparando inferencia en paralelo sin contención.
- Solución: cola de inferencia centralizada (semáforo asyncio o worker queue) — todos los engramas piden turno al mismo servidor de inferencia en vez de lanzar procesos propios.

---

## 2. Coherencia narrativa-espacial (evitar alucinación de estado del mundo)

### 2.1 Objeto de estado explícito en vez de prosa cruda

No se inyecta el historial narrativo completo como contexto. Se mantiene un objeto de estado del mundo, actualizado de forma determinista o vía llamadas con salida estructurada forzada:

```json
{
  "personajes": {
    "engrama_A": {
      "ubicacion": "taller",
      "estado_emocional": "irritado",
      "ultima_accion": "reparando el motor"
    }
  },
  "timeline_reciente": ["evento_1", "evento_2"],
  "relaciones": {"engrama_A->usuario": "confianza_media"}
}
```

- Se posiciona **al final del prompt**, justo antes de la generación — zona de mejor atención del modelo (recency bias, mitiga "lost in the middle").
- El historial de prosa completo vive en la vector DB para retrieval bajo demanda, no se recarga entero cada turno.

### 2.2 Por qué falla el enfoque ingenuo

- **Lost in the middle**: modelos 7-24B tienen atención mucho más débil hacia el centro de contextos largos que hacia el inicio/final — explica por qué "no sacan nada" de un PDF largo aunque esté completo en el contexto.
- **Chunking a ciegas**: cortar texto en bloques de tamaño fijo rompe unidades semánticas (relaciones causales quedan partidas a la mitad), y el retrieval por similitud recupera lo que "suena" parecido, no lo que tiene contexto completo de la entidad.

---

## 3. GraphRAG con resúmenes jerárquicos (resuelve la saturación del grafo)

Aplicable directamente al problema reportado: grafo funcional pero saturante en inyección directa.

### 3.1 Construcción offline (una vez, o al actualizar lore)

1. Extracción de grafo de entidades/relaciones (ya implementado).
2. Detección de comunidades vía **algoritmo Leiden** — agrupa el grafo en clusters temáticos (ej. "facción X + su territorio").
3. Por cada comunidad: resumen en prosa generado vía LLM (puede delegarse a modelo cloud aquí, porque es data ya consolidada y no en vivo) que condensa decenas de triples en pocos párrafos coherentes.
4. Los resúmenes se guardan como nodos adicionales con embedding propio.

### 3.2 Retrieval en vivo

1. Query → embedding → match primero contra **resúmenes de comunidad**, no contra triples crudos.
2. Solo si se necesita el detalle puntual (ej. "¿qué arma exacta usa X?") se hace traversal de 1 hop sobre el nodo específico — nunca sobre la comunidad entera.
3. Resultado: 2-3 resúmenes densos + triples puntuales en vez de 40-60 triples sueltos — mismo contenido informacional, fracción del tamaño en tokens.

### 3.3 Parent Document Retrieval (small-to-big)

Para contenido no grafado (diálogos, descripciones):

- Se indexan chunks pequeños (100-200 tokens) para matching semántico preciso.
- Cada chunk pequeño referencia su **chunk padre** (párrafo/escena completa, 800-1500 tokens).
- Retrieval: se busca con el chunk pequeño (precisión), se inyecta el chunk padre (completitud).

### 3.4 Stack de base de datos unificado

- **pgvector** (embeddings de chunks + resúmenes de comunidad) + **Apache AGE** (grafo de entidades, sintaxis openCypher) — ambos como extensiones sobre el mismo Postgres ya en uso para el thesis stack.
- Evita fragmentar infra con un Neo4j aparte — un solo backup, una sola conexión.

---

## 4. Cómputo en tiempo de inferencia (subir el "IQ efectivo" sin cambiar de modelo)

Principio central: el techo de una sola pasada de un modelo de 12-24B es fijo por VRAM — no se supera con mejor prompting. Pero el techo del **sistema** depende de cuánto se orquesta alrededor de esa llamada.

### 4.1 Descomposición map-reduce

En vez de una pasada sobre el documento completo, se divide en secciones, se corre extracción local por sección (contexto pequeño, atención efectiva alta), y una llamada de síntesis final reduce los resultados parciales. Es el mismo mecanismo que genera los resúmenes de comunidad en GraphRAG.

### 4.2 Self-consistency / voto por mayoría

Para tareas con respuesta verificable (extracción de hechos, scoring de importancia, decisiones del loop autónomo): correr la misma llamada 3-5 veces a temperatura moderada, quedarse con la mayoría o promediar el score. Reduce varianza de modelos pequeños a costo de 3-5x en inferencia.

### 4.3 Generador-crítico (mitigación directa de alucinación)

Dos llamadas en cadena:
1. Generación narrativa normal.
2. Auditoría: prompt distinto que pregunta si la afirmación generada es consistente con los hechos recuperados — respuesta binaria + señalamiento de contradicción.
3. Si falla, se regenera con el error inyectado como corrección.

### 4.4 Destilación offline

Usar un modelo grande **una sola vez, fuera de línea**, para producir artefactos estáticos que después consume el modelo chico en producción (ej. "biblia de personaje" condensada por engrama, generada a partir del Obsidian completo). El modelo en caliente nunca razona sobre el lore crudo — consume el resumen ya destilado. Se compra inteligencia una vez, se amortiza indefinidamente.

### 4.5 Decoding forzado (GBNF grammar / JSON schema)

Para tareas estructuradas (extracción de entidades, actualización del objeto de estado del mundo, scoring PAD): forzar el output con gramática en llama.cpp. No aumenta la inteligencia del modelo, pero elimina divagación y formato inconsistente — la tarea puntual sale con precisión superior a lo que sugeriría su prosa libre.

### 4.6 Asignación de presupuesto por contexto de uso

- **Loop autónomo (background, no interactivo)**: presupuesto de tiempo alto → permite cadenas de 5-10 llamadas generador-crítico-reductor sin impacto perceptible.
- **Chat en vivo (latencia baja requerida)**: presupuesto bajo → aquí se siente más el techo real de una sola pasada; es donde más pesa la restricción de hardware.

---

## 5. Sampling para prosa narrativa no genérica

Configuración de muestreo — causa raíz frecuente de "modelo local suena plano/repetitivo" antes de descartar el modelo mismo.

| Técnica | Función | Config de referencia |
|---|---|---|
| **DRY** (Don't Repeat Yourself) | Penaliza n-gramas repetidos completos, no tokens individuales — mata loops de frase sin destruir vocabulario recurrente (nombres propios, términos técnicos) | `--dry-multiplier 0.8 --dry-base 1.75 --dry-allowed-length 2 --dry-penalty-last-n 512` |
| **min_p** (en vez de top_p) | Más estable en generación larga; no colapsa la distribución cuando el modelo está "seguro" de un token | `--min-p 0.05` |
| **XTC** (Exclude Top Choices) | Excluye probabilísticamente los tokens top-1/2 cuando su probabilidad combinada supera umbral — rompe el sesgo hacia la continuación más "segura"/clichée | `--xtc-probability 0.5 --xtc-threshold 0.1` |
| **temp** | Punto de partida narrativo | `0.8–0.85` |

Nota: koboldcpp expone estos samplers de forma más directa en su API/UI que llama-server puro; vale la pena evaluarlo como frontend de inferencia manteniendo el orquestador propio.

---

## 6. Resumen de mapeo problema → técnica

| Síntoma reportado | Técnica que lo ataca |
|---|---|
| Chatbot sin continuidad, "operación → respuesta" | Memory Stream + Reflection Layer + loop autónomo |
| Atributos emocionales ad-hoc sin coherencia | Modelo PAD |
| No "vive" cuando no se le habla | Loop autónomo con heurística de decisión |
| No saca todo del PDF | Map-reduce + reposicionamiento de contexto (recency bias) |
| Alucinación por chunks incompletos | Parent Document Retrieval (small-to-big) |
| Grafo funcional pero satura el modelo | GraphRAG con resúmenes de comunidad (Leiden) |
| Modelo "tonto" por restricción de VRAM | Test-time compute scaling (4.1–4.5) |
| Prosa genérica/repetitiva | DRY + min_p + XTC |

---

*Documento vivo — actualizar conforme se implementen y validen los componentes contra hardware real (RX 7800 XT / 32GB RAM).*
