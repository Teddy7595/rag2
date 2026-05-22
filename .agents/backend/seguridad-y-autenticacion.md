# Seguridad y Autenticacion

## Base observada en el repo

El proyecto actual ya tiene dos semillas importantes:

- hashing de credenciales y respuestas con PBKDF2
- contexto de cuenta propagado por `X-Account-Id`

Eso alcanza para modelar ownership y recovery basico, pero no constituye una capa completa de seguridad para un sistema expuesto.

## Estandar objetivo

El proyecto estandar debe separar claramente:

- autenticacion: quien eres
- autorizacion: que puedes hacer
- contexto: sobre que tenant, cuenta o recurso operas

## Autenticacion recomendada

### Para usuarios humanos

- access token de corta vida
- refresh token revocable
- opcion de cookie segura o bearer token segun el cliente
- soporte para logout y revocacion

### Para integraciones

- API keys con scopes
- firma HMAC o JWT de servicio a servicio cuando aplique

## Hashing y secretos

- preferir Argon2id o PBKDF2 endurecido
- comparar hashes con funciones seguras
- rotar secretos por entorno
- no registrar secretos ni tokens en logs

## Autorizacion

La autorizacion no debe resolverse solo en routers. Debe existir un modelo de permisos reusable.

Opciones recomendadas:

- RBAC por rol
- permisos por accion
- scopes por token
- ownership por tenant y recurso

## Recuperacion de cuenta

Las preguntas de seguridad pueden existir como mecanismo legado o secundario, pero no deben ser la estrategia principal. Para sistemas serios conviene priorizar:

- email de recuperacion
- OTP temporal
- TOTP
- administracion manual auditada para cuentas corporativas

## Endurecimiento minimo

- rate limiting en login y recovery
- bloqueo temporal por intentos fallidos
- expiracion de tokens
- revocacion por compromiso
- CORS estricto
- HTTPS obligatorio en servidor

## Contexto y tenant

El sistema actual usa `X-Account-Id` como contexto de cuenta. El estandar debe poder evolucionar a:

- extraer tenant desde el token
- mantener headers explicitos para integraciones internas cuando sea util
- validar coherencia entre token, ruta y contexto solicitado

## Auditoria de seguridad

Registrar al menos:

- login exitoso y fallido
- refresh y logout
- cambios de email o password
- accesos a archivos sensibles
- exportaciones y acciones administrativas

## Ideas de evolucion

- modulo `auth` dedicado
- sesiones persistentes para revocacion
- permisos por modulo
- aprobaciones de dos pasos en operaciones delicadas
- webhooks firmados para integraciones salientes