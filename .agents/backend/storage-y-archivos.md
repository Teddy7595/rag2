# Storage y Archivos

## Objetivo

El sistema de archivos debe ser un modulo propio, no un detalle perdido dentro de otros modulos. Debe soportar storage local y remoto sin cambiar la forma en que el resto del sistema pide guardar, leer o borrar contenido.

## Principios

- separar metadata del contenido binario
- usar un `StorageProviderInterface`
- permitir backend local primero y remoto despues
- proteger rutas y ownership
- publicar eventos de lifecycle relevantes

## Modelo recomendado

La entidad de archivo debe guardar como minimo:

- `id`
- `filename`
- `mime_type`
- `checksum`
- `storage_path`
- `visibility`
- `owner_account_id`
- `owner_module`
- `owner_reference`

## Providers

### Local

Ideal para desarrollo, pruebas y despliegues simples.

### Remoto

Ideal para servidor, CDN y escalado.

Ejemplos:

- S3
- Bunny
- MinIO
- almacenamiento corporativo interno

## Seguridad minima

- impedir path traversal
- validar tamano y mime type
- calcular checksum
- no servir archivos privados por rutas publicas
- registrar accesos sensibles

## Visibilidad

- `private`: acceso controlado por permisos o token
- `public`: acceso directo o via CDN

## Integracion con otros modulos

Otros modulos no deben tocar repositorios internos de archivos. Deben pedir capacidad por evento o servicio de aplicacion.

Flujos tipicos:

- exportar reporte markdown a archivo
- guardar artefactos de modelos
- guardar anexos o evidencias
- servir contenido publico

## Streaming y descargas

El estandar debe poder crecer a:

- streaming de archivos grandes
- rangos parciales
- URLs firmadas temporales
- post-procesamiento asincrono

## Operacion local y servidor

- local: volumen en disco facil de inspeccionar
- servidor: provider remoto, cache y CDN cuando haga sentido