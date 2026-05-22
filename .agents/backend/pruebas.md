# Pruebas

## Filosofia de calidad

Las pruebas deben validar el sistema desde tres angulos:

- reglas del dominio
- integracion entre capas
- comportamiento HTTP y operativo

## Niveles minimos

### Unitarias

Cubren:

- factories
- entidades con reglas no triviales
- validadores puros
- utilidades del core

### Integracion

Cubren:

- repositorios
- casos de uso con DB real de prueba
- contratos de eventos
- adapters de storage

### E2E

Cubren:

- request HTTP completo
- dependencia de DB aislada
- headers de contexto
- casos felices y casos de error

## Estado observado

El repo actual ya tiene una base correcta:

- pruebas unitarias de factories
- pruebas E2E por modulo
- SQLite en memoria por prueba mediante fixture aislada

Ese patron debe convertirse en regla del estandar.

## Casos extra obligatorios para el estandar

- pruebas de eventos request y publish
- pruebas de exportacion de archivos
- pruebas de permisos y autenticacion
- pruebas de visibilidad publica o privada en storage
- pruebas de sockets o SSE cuando exista tiempo real

## Fixtures recomendadas

- `client` HTTP
- DB en memoria o base efimera por test
- fake storage provider
- fake event bus cuando la prueba no requiera el real
- helpers para crear tenants, usuarios y recursos base

## Definition of Done por modulo

- al menos un camino feliz E2E
- al menos un error de negocio controlado
- factories cubiertas por unit tests
- contratos de evento cubiertos si el modulo expone eventos
- README del modulo actualizado

## CI esperado

Todo proyecto estandar debe poder ejecutar:

```bash
pytest
```

Y, si el stack crece, separar suites por velocidad:

```bash
pytest test/unit
pytest test/e2e
```