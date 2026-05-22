# Componentes Frontend

## Objetivo

Definir reglas para que cada componente haga una sola cosa, conserve su contexto y siga siendo entendible cuando el sistema crezca.

## Regla principal

Cada componente debe existir para una funcion especifica y reconocible.

Si una pieza no puede nombrarse por la funcion que cumple, probablemente esta resolviendo varias cosas a la vez.

## Contrato de un componente

Todo componente debe poder describirse con estas preguntas:

- que entrada recibe
- que proceso ejecuta
- que salida produce
- que estado local necesita
- de que dependencias externas depende

## Responsabilidad unica real

Un componente sano:

- renderiza una sola capacidad visual o interactiva
- mantiene su propio contexto inmediato
- delega transporte y persistencia a servicios o capas superiores cuando corresponde

Un componente enfermo:

- mezcla varias areas funcionales
- conoce demasiados detalles del sistema
- modifica estado global sin contrato claro
- usa nombres genericos que obligan a adivinar el contexto

## Nombres auditables

Las variables deben expresar dominio, intencion y alcance.

Preferir:

- `chatMessageInput`
- `securityBanForm`
- `activeRateLimitRules`
- `engramEditorModal`
- `pendingUploadRequest`

Evitar:

- `data`
- `item`
- `temp`
- `thing`
- `handleStuff`
- `value2`

## Contexto propio del componente

Cada componente debe mantener su propio contexto y funcionalidad mientras ese contexto no sea compartido por varias piezas.

Ejemplos de contexto local valido:

- si un modal esta abierto o cerrado
- el texto actual de un input
- el estado de carga de una accion local
- la fila seleccionada en una tabla local

Ejemplos de contexto que podria subir de nivel:

- la sesion de usuario en toda la app
- la configuracion global del chat
- reglas compartidas por varias pantallas

## Plantilla sugerida por componente

```text
# Componente X

## Proposito
## Entrada
## Estado local
## Proceso
## Salida
## Dependencias
## Errores esperados
## Extension points
```

## Anti patrones a evitar

- componentes dios
- helpers globales con efectos secundarios opacos
- estado compartido por comodidad y no por necesidad
- handlers que mezclan validacion, render y persistencia en un solo bloque
- nombres que no permiten auditar el codigo rapidamente

## Resultado esperado

Al leer un componente, otro desarrollador deberia identificar en pocos segundos:

- que resuelve
- que datos recibe
- que estado mantiene
- que produce al final
