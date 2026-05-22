# Swagger y OpenAPI

## Objetivo

La documentacion no debe ser un efecto secundario del framework. Debe ser un contrato usable por frontend, QA, integraciones y futuros desarrolladores.

## Reglas para routers

Cada endpoint debe definir como minimo:

- `tags`
- `summary`
- `description`
- `status_code`
- `response_model` cuando corresponda

## Reglas para DTOs

Los DTOs deben incluir:

- `Field` con descripciones claras
- ejemplos realistas
- tipos correctos y validaciones utiles
- enums o literales cuando el dominio lo permita

## Headers y contexto

Si un endpoint depende de headers como `Authorization` o `X-Account-Id`, esos contratos deben documentarse expresamente en Swagger y en la documentacion del modulo.

## Errores estandar

Definir respuestas para:

- 400 validacion funcional
- 401 autenticacion
- 403 autorizacion
- 404 recurso no encontrado
- 409 conflicto
- 422 regla de negocio
- 500 error tecnico

## Versionado

- usar prefijo de version en ruta publica cuando aplique
- marcar endpoints obsoletos con `deprecated=True`
- no romper contratos sin version o plan de migracion

## Calidad observable en el repo

El proyecto actual ya muestra una buena direccion en varios routers:

- tags por modulo
- summaries y descriptions descriptivos en training
- DTOs que enriquecen la experiencia Swagger

El estandar debe llevar esa practica a todos los modulos, no solo a algunos.

## Buenas practicas adicionales

- `operationId` estable para clientes generados
- ejemplos de request y response completos
- documentar filtros, paginacion y ordenamiento
- documentar visibilidad publica o privada de archivos

## Salidas de documentacion esperadas

Todo proyecto basado en este estandar debe exponer:

- `/docs`
- `/redoc`
- `/openapi.json`

Y su `README.md` debe enlazar esas rutas.