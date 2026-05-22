# Documentacion Modular

## Objetivo

Cada modulo debe tener suficiente documentacion para explicar que hace, como lo hace y como puede extenderse. La documentacion no es un anexo; es parte del contrato del modulo.

## Capas de documentacion

### README raiz

Debe explicar:

- que resuelve el proyecto
- como instalarlo
- como arrancarlo
- como correr pruebas
- como ver Swagger
- como usar Docker

### `docs/`

Debe narrar capacidades funcionales y tecnicas por area importante.

### README por modulo o documento equivalente

Cada modulo importante debe documentar:

- proposito
- lenguaje del dominio
- endpoints
- DTOs
- casos de uso
- eventos expuestos y consumidos
- reglas de seguridad
- pruebas minimas

## Plantilla sugerida por modulo

```text
# Modulo X

## Proposito
## Modelo de dominio
## Entradas y salidas
## Casos de uso
## Eventos
## Persistencia
## Seguridad
## Endpoints
## Errores esperados
## Pruebas
## Extension points
```

## Regla de trazabilidad

Toda decision tecnica relevante debe poder rastrearse en alguno de estos lugares:

- README raiz
- documento en `docs/`
- documento del modulo
- estandar en `clean_standar/`

## Documentacion de capacidades transversales

Ademas de modulos, deben existir documentos dedicados para:

- arquitectura
- eventos
- seguridad
- storage
- pruebas
- despliegue
- tiempo real

## Buenas practicas

- escribir para el siguiente desarrollador, no para quien ya conoce el repo
- usar ejemplos cortos y reales
- documentar limites y no solo funciones disponibles
- mantener README y docs alineados con Swagger y pruebas

## Definition of Done documental

Una funcionalidad no deberia considerarse cerrada si:

- aparece en codigo pero no en Swagger cuando es publica
- requiere contexto oral para entender su modulo
- cambia contratos y nadie actualizo la documentacion