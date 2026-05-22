# Eventos

## Proposito

El sistema de eventos existe para comunicar modulos sin imports directos entre sus capas internas. Debe ser la herramienta principal para coordinacion cross-module y el punto natural de evolucion hacia auditoria, integracion externa y tiempo real.

## Piezas del sistema

- `EventSpec`: contrato estable del evento
- `EventEnvelope`: contexto runtime con metadata
- `EventRegistry`: registro de handlers
- `EventRouter`: despacho interno
- `EventBus`: entrada unica del sistema
- `EventPublisher`: wrapper ligado a un modulo productor

## Tipos de evento

### REQUEST

Se usa cuando un modulo necesita una respuesta canonicamente controlada por otro modulo.

Ejemplos:

- buscar un dataset por ID
- validar una anotacion externa
- exportar un reporte a storage

Reglas:

- un solo handler canonico
- input y output tipados
- errores de contrato claros

### PUBLISH

Se usa cuando un modulo publica un hecho consumado.

Ejemplos:

- archivo almacenado
- archivo eliminado
- proceso actualizado
- notificacion emitida

Reglas:

- puede haber multiples listeners
- el productor no conoce a los consumidores

## Canales recomendados

- `DOMAIN` para hechos de negocio internos
- `AUDIT` para trazabilidad y cumplimiento
- `INTEGRATION` para conectores externos
- `NOTIFICATION` para correo, push, sockets o alertas

No multiplicar canales si solo cambia el consumidor. El canal expresa intencion, no tecnologia.

## Reglas de naming

- request: `<module>.<action>`
- publish: `<module>.<aggregate>.<past_tense_action>`

Ejemplos:

- `files.get_by_id`
- `files.store_content`
- `reports.report.exported`
- `training.process.updated`

## Reglas de handlers

- reciben `EventEnvelope` con payload tipado
- delegan al composite del modulo
- no mezclan logica HTTP
- no conocen repositorios ajenos
- deben ser delgados

## Reglas de composites

Los composites deciden cuando pedir o publicar eventos. Eso mantiene la separacion correcta:

- handler: adapter
- composite: orquestacion
- bus: infraestructura

## Trazabilidad

Todo evento relevante debe soportar:

- `correlation_id`
- `causation_id`
- `tenant_id`
- `aggregate_type`
- `aggregate_id`
- `metadata`

Esto prepara al sistema para debugging, auditoria y procesamiento distribuido.

## Idempotencia y reintentos

Cuando una operacion pueda repetirse por retry o reenvio:

- definir una clave idempotente
- registrar correlacion
- evitar efectos duplicados en handlers de integracion

## Evolucion recomendada

### Fase 1

EventBus en memoria para request y publish internos.

### Fase 2

Outbox persistente para eventos que deban sobrevivir reinicios.

### Fase 3

Bridge hacia workers, sockets, colas o integraciones externas sin cambiar el contrato del modulo productor.

## Regla final

Un modulo puede exponer capacidad al sistema, pero no debe exponer sus internals por costumbre. El evento es el contrato, no el repositorio del vecino.