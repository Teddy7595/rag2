# Documentacion y Composicion Frontend

## Objetivo

La documentacion del frontend debe explicar como esta compuesto, como funciona y como puede extenderse sin depender de conocimiento oral.

## Capas de documentacion

### README del frontend

Debe explicar:

- que resuelve el frontend actual
- cuales son sus pantallas principales
- como se conecta con el backend
- cual es su stack real hoy
- como se extiende con nuevas pantallas o componentes

### Documentos `front_*.md`

Deben fijar contratos sobre:

- filosofia general
- arquitectura
- componentes
- estado y flujos
- composicion y documentacion

### Documentacion por pantalla

Cada pantalla importante debe documentar:

- proposito
- ruta
- punto de entrada
- componentes usados
- servicios o APIs que consume
- estados principales
- salidas esperadas
- errores esperados

## Plantilla sugerida por pantalla

```text
# Pantalla X

## Proposito
## Ruta
## Entrada
## Componentes
## Estado
## Servicios
## Proceso
## Salida
## Errores esperados
## Extension points
```

## Plantilla sugerida por frontend de modulo

```text
# Frontend del modulo X

## Proposito
## Pantallas
## Componentes
## Estado compartido
## Integraciones con backend
## Eventos y flujos
## Riesgos y limites
## Pruebas
```

## Regla de trazabilidad

Toda decision importante del frontend debe poder rastrearse en alguno de estos lugares:

- `README.md` del frontend
- documento `front_*.md`
- documentacion especifica de pantalla
- roadmap o documento arquitectonico del proyecto

## Definicion de terminado documental

Una capacidad de frontend no deberia considerarse cerrada si:

- existe en codigo pero no en la documentacion del frontend
- no puede explicarse por su flujo entrada -> proceso -> salida
- depende de nombres ambiguos para entender su contexto
- cambia una pantalla o contrato de API y nadie actualiza el README o la documentacion asociada

## Resultado esperado

El frontend debe poder entenderse aunque cambie el stack. La composicion y funcionamiento deben seguir claros para quien lea el proyecto despues.
