# Docker y Despliegue

## Principio

El proyecto estandar debe ser facil de levantar en local y predecible en servidor. Docker no debe complicar el sistema; debe encapsularlo.

## Perfil minimo de contenedores

### Local simple

- `api`
- volumen para storage local
- base de datos local o SQLite montada en volumen

### Servidor

- `api`
- `worker` si existen jobs o outbox
- `db` o servicio gestionado externo
- `reverse-proxy` cuando haga falta TLS, compresion o routing
- `redis` si hay rate limiting distribuido o realtime con backplane

## Reglas del Dockerfile

- imagen pequena y reproducible
- variables por entorno
- usuario no root cuando sea viable
- healthcheck util
- comando claro de arranque

## Docker Compose esperado

Todo proyecto basado en este estandar deberia poder ofrecer:

```bash
docker compose up --build
```

Y definir, como minimo:

- variables del app
- puertos expuestos
- volumenes de archivos
- readiness de la API

## Diferencia local vs servidor

### Local

- `reload` activado
- volumenes bind para codigo
- logs faciles de leer
- dependencias minimizadas

### Servidor

- `reload` desactivado
- secretos via variables seguras o secret manager
- replicas o proceso worker separado
- proxy y TLS delante de la API

## Compatibilidad con tiempo real

Si el proyecto usa WebSockets o SSE, Docker debe contemplar:

- proxy compatible
- timeouts correctos
- escalado con backplane si hay varias replicas

## Estrategia de arranque

- aplicar migraciones antes del modo estable cuando existan
- preparar storage o volumenes
- exponer health endpoint
- fallar rapido si faltan variables criticas

## Resultado esperado

Un desarrollador nuevo debe poder levantar el sistema sin instalar todo manualmente y un servidor debe poder correrlo sin hacks adicionales.