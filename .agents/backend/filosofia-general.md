# Filosofia General

## Proposito

El proyecto estandar debe permitir construir software util desde el dia uno sin sacrificar capacidad de crecimiento. La regla central es simple: el sistema debe poder empezar pequeno, mantenerse entendible y escalar por extensiones, no por reconstrucciones.

## Principios rectores

1. La unidad real de diseno es el modulo, no el endpoint.
2. El dominio manda sobre la infraestructura.
3. La composicion de dependencias debe ser explicita.
4. El desacoplamiento entre modulos se protege con contratos y eventos.
5. Cada decision debe servir tanto en local como en servidor.
6. El proyecto debe aceptar nuevas capacidades sin deformar la base.

## Decisiones de alto nivel

### Monolito modular primero

La base recomendada es un monolito modular. Esto reduce friccion de arranque, acelera desarrollo y permite evolucionar luego hacia workers, colas, outbox o microservicios solo si el problema real lo exige.

### Clean Architecture por modulo

Cada modulo tiene capas claras:

- `domain/` para reglas e invariantes
- `application/` para casos de uso y contratos
- `adapters/` para HTTP, DB, storage, eventos o integraciones

### Wiring explicito

La dependencia entre piezas se construye en `*_module.py` y en el `bootstrap` global. No se oculta detras de magia de framework.

### Desacoplamiento por eventos

Cuando un modulo necesita informacion o una accion de otro, la primera opcion no debe ser importar su repositorio. Debe pasar por contratos de aplicacion y, preferentemente, por el sistema de eventos interno.

## Matriz de decision

- mismo modulo: llamada directa a composite o use case
- modulos del mismo grupo: preferir eventos o composite solo si el acoplamiento es justificable
- modulos de grupos distintos: eventos por defecto
- salida a servicios externos: adapters dedicados, nunca desde dominio

## Capacidad de crecimiento sin rehacer todo

El proyecto estandar debe poder absorber:

- autenticacion real con tokens y sesiones
- storage local o remoto
- notificaciones y sockets
- tareas asincronas y workers
- observabilidad, auditoria y metricas
- despliegue local, containerizado y servidor

Todo eso debe entrar como extension de interfaces, modulos o adapters. No debe exigir redisenar dominio, routers o base de datos desde cero.

## Criterios de calidad

- si un modulo no puede explicarse con su propia carpeta, esta mal delimitado
- si un endpoint contiene logica de negocio, el borde HTTP esta contaminado
- si un modulo conoce el repositorio interno de otro, el desacoplamiento fallo
- si una capacidad nueva requiere tocar archivos por todo el repo, falta una frontera correcta

## Resultado esperado

Un proyecto basado en esta filosofia debe ser:

- facil de arrancar en local
- facil de empaquetar en Docker
- apto para servidores y despliegues posteriores
- legible para un desarrollador nuevo
- resistente a crecimiento funcional y tecnico