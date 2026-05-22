# Base de Datos

## Principio general

La persistencia debe ser simple para desarrollo local y rigurosa para servidor. La arquitectura debe permitir cambiar de motor o endurecer la operacion sin alterar el dominio.

## Perfil local

- SQLite es valido para desarrollo y pruebas rapidas
- puede usarse creacion automatica de tablas para bootstrap local
- la experiencia debe ser de cero friccion

## Perfil servidor

- PostgreSQL es la opcion recomendada
- las migraciones deben estar gestionadas por una herramienta formal, preferentemente Alembic
- la inicializacion no debe depender de `create_all()` en produccion

## Reglas de modelado

- cada entidad pertenece a un modulo
- las tablas deben reflejar ownership claro
- incluir campos base comunes: `id`, `created_at`, `updated_at`, `is_deleted`
- usar soft delete cuando la trazabilidad sea importante
- indexar por claves de consulta reales, no por intuicion

## Sesiones y transacciones

- una sesion por request o por unidad de trabajo
- el composite controla transacciones de escritura
- las lecturas no deben abrir transacciones largas
- si una operacion toca archivo y DB, el orden debe minimizar inconsistencias y permitir compensacion

## Repositorios

Los repositorios son adapters concretos. Deben:

- cumplir una interfaz o protocolo de aplicacion
- encapsular ORM y consultas
- devolver entidades o resultados de aplicacion limpios
- evitar mezclarse con reglas de negocio

## Multi-tenancy

Si el sistema es account-scoped o tenant-scoped, la base de datos debe tratar eso como una capacidad central, no como un detalle opcional.

Reglas:

- los repositorios deben filtrar por tenant cuando aplique
- los eventos deben propagar `tenant_id`
- los endpoints no deben confiar en IDs sin contexto de tenant

## Migraciones

Estandar recomendado:

- local simple: `create_all()` aceptable
- integracion continua: validar migraciones aplicadas
- produccion: migraciones obligatorias antes del arranque estable

## Outbox y trabajos diferidos

Si el sistema envia notificaciones, integraciones o streams en tiempo real, conviene reservar una tabla outbox para publicar eventos confiables despues del commit.

## Seguridad de datos

- no guardar secretos en texto plano
- hashear credenciales y respuestas sensibles
- cifrar datos especialmente delicados cuando aplique
- separar metadatos de archivos del contenido binario

## Backups y operacion

- definir politica de backup desde el inicio
- documentar restore
- exponer health checks y readiness separados
- monitorear tiempos de consulta y crecimiento de tablas