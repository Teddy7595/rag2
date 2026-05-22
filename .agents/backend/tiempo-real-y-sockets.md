# Tiempo Real y Sockets

## Estado observado

El repo actual no implementa WebSockets ni SSE, pero la arquitectura ya tiene un punto de apoyo correcto: eventos internos con metadata, desacoplamiento entre modulos y capacidad de publicar hechos.

## Objetivo del estandar

La capacidad de tiempo real debe agregarse sin invadir dominio ni repositorios. El sistema debe poder emitir estados, notificaciones y progreso de procesos en vivo usando una capa dedicada.

## Cuando usar cada mecanismo

### WebSocket

Usar cuando se necesita comunicacion bidireccional o alta frecuencia:

- progreso de entrenamiento
- consola en vivo
- estado de jobs largos
- notificaciones interactivas

### SSE

Usar cuando el servidor solo necesita empujar eventos al cliente:

- timeline de estados
- notificaciones ligeras
- monitoreo de procesos

### Polling

Aceptar solo como compatibilidad o fallback.

## Patron recomendado

```text
Composite -> EventBus -> Notification Bridge -> WebSocket/SSE Gateway -> Cliente
```

Opcionalmente:

```text
Composite -> Outbox -> Worker -> Gateway
```

## Tipos de eventos en tiempo real

- `process.started`
- `process.progress.updated`
- `process.finished`
- `process.failed`
- `notification.created`
- `resource.changed`

## Reglas de diseno

- no emitir desde el router si el estado nace del negocio
- emitir desde composite o desde un bridge suscrito a eventos de dominio
- separar transporte realtime del contrato de negocio
- soportar autenticacion y tenant en cada conexion

## Autenticacion en sockets

- token al abrir conexion
- validacion de tenant y permisos
- cierre inmediato de conexiones invalidas
- canales o rooms por tenant, usuario o recurso

## Escalado

Si hay multiples instancias del servidor, el realtime necesita un backplane compartido:

- Redis pub/sub
- broker de mensajes
- outbox + dispatcher

## Casos de uso recomendados

- progreso de entrenamiento de modelos
- exportacion de reportes o archivos largos
- estados de pipelines
- notificaciones administrativas

## Pruebas y observabilidad

- probar conexion, autenticacion y recepcion de eventos
- medir conexiones activas, latencia y eventos perdidos
- registrar correlation id cuando un stream venga de un proceso de negocio