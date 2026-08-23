# Comparativa tecnica: rag (referencia) vs rag2 (actual)

## Resumen ejecutivo

rag2 ya tiene base modular fuerte (event bus, saga CRUD, engramas, contexto, chat realtime, runtime local texto/vision).
La brecha principal con el proyecto de referencia no esta en "tener endpoints", sino en capacidades de orquestacion avanzada para conversaciones largas y narrativa compleja multi-hilo.

## Estado actual de rag2

- Sagas:
  - Crear, listar, filtrar por estado, consultar detalle, actualizar, borrar.
  - Extender sagas completadas con nuevos comandos.
  - Debatir elementos de saga y persistir memoria inspiracional enlazada a saga+engrama.
- RAG/contexto:
  - Routing por intencion y armado de context pack.
  - Prompt contextual con identidad activa (engrama).
  - Nuevo endpoint de grafo de contexto para panorama de nodos/relaciones.
- Engrama:
  - Personalidad, reglas y parametros de generacion.
  - Resolucion por handle tipo @Nombre.
- Runtime local:
  - Texto y vision con llama.cpp opcional.
  - Admin smoke tests y chat con analisis de imagen.

## Diferencias clave frente a rag (referencia)

1. Memoria jerarquica de largo alcance
- rag referencia tiene capas y estrategias de recuperacion mas maduras para separar fuentes conversacionales/documentales.
- rag2 necesita resumido incremental de sesiones para reducir degradacion en chats largos.

2. Orquestacion narrativa avanzada
- rag referencia tiene flujo de saga mas orientado a modos narrativos y continuidad por actos.
- rag2 tiene base CRUD+timeline, pero requiere motor de consistencia narrativa (arcos, objetivos, restricciones de continuidad) para calidad sostenida.

3. Estrategias de retrieval mas ricas
- rag referencia contempla estrategias mixtas especializadas.
- rag2 ya tiene pipeline funcional, pero le falta:
  - re-rank semantico mas robusto,
  - politicas de fallback por precision/recall,
  - trazabilidad explicita de por que una pieza fue elegida sobre otra.

4. Experiencia multi-sesion/multi-room
- rag referencia tiene patron de servicios de conversacion mas orientado a rooms/hilos.
- rag2 hoy es funcional pero necesita modelado explicito de "thread/topic" para tipo ChatGPT/Gemini con varios temas simultaneos.

5. Gobernanza de coherencia
- rag2 mejoro estructura de respuesta (idea principal/secundarias), pero aun falta un evaluador automatico de coherencia que mida deriva y fuerce correcciones.

## Necesidades prioritarias (roadmap sugerido)

### Prioridad alta
- Memoria deslizante + resumen jerarquico por sesion:
  - ventana corta para inmediatez,
  - resumen persistente por bloques,
  - recall fuera de ventana con scoring.
- Topic graph persistente por sesion:
  - topico principal,
  - topicos secundarios,
  - estado (abierto/cerrado),
  - enlaces a sagas y knowledge items.

### Prioridad media
- Saga consistency engine:
  - reglas de continuidad,
  - detector de contradicciones entre actos,
  - propuesta de retcon controlado.
- Debate asistido por engrama:
  - posturas pro/contra,
  - decision rationale,
  - guardado de "insights" para reutilizacion.

### Prioridad media-baja
- Panel admin de trazabilidad:
  - vista de por que se recupero cada contexto,
  - comparativa de respuestas con/sin contexto,
  - score de coherencia por turno.

## Criterios de exito para acercarse a nivel ChatGPT/Gemini

- Chats de +100 turnos sin perdida de hilo principal.
- Capacidad de retomar un topico antiguo sin reinyectar todo el historial manualmente.
- Sagas largas con continuidad verificable entre actos.
- Respuestas consistentes con personalidad del engrama y con memoria contextual recuperada.
- Transparencia de contexto (grafo + trazas) para depuracion operativa.
