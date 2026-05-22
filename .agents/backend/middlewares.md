# Middlewares

## Principio

Los middlewares resuelven preocupaciones transversales. No deben contener logica de negocio ni reemplazar a los casos de uso.

## Estado observado

En el repo actual no hay una cadena formal de middlewares; el contexto de cuenta entra por dependencia. El estandar debe formalizar la capa transversal sin sobrecargar el dominio.

## Orden recomendado

1. request id y correlation id
2. logging estructurado
3. trusted hosts y proxy headers
4. CORS
5. autenticacion
6. resolucion de tenant o account context
7. rate limiting
8. traduccion de errores no controlados
9. metricas y trazas

## Middleware vs Dependency

Usar middleware para:

- contexto global del request
- seguridad transversal
- observabilidad
- manejo de errores tecnicos

Usar dependency para:

- datos requeridos por endpoints concretos
- validaciones de acceso especificas por recurso
- composicion de adapters y composites

## Middleware minimos del estandar

### Request context

Debe generar o propagar:

- request id
- correlation id
- tenant id si existe

### Logging

Debe registrar:

- metodo
- ruta
- status
- duracion
- request id

### Error handling

Debe traducir excepciones tecnicas a respuestas consistentes sin filtrar detalles internos.

### Seguridad

Debe integrar autenticacion, CORS, headers seguros y, si aplica, CSRF para apps basadas en cookies.

## Reglas practicas

- no acceder a repositorios desde middleware salvo casos excepcionales de auth centralizada
- no duplicar validaciones de permisos en multiples capas sin motivo
- no mutar el request con datos ambiguos o mal nombrados

## Propuesta de madurez

- fase inicial: logging, request id, CORS, error handler
- fase intermedia: auth, tenant resolver, rate limiting
- fase madura: metricas, tracing distribuido, politicas de seguridad mas estrictas