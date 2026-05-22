# Arquitectura

## Estructura base

```text
project/
├── main.py
├── pyproject.toml
├── README.md
├── docs/
├── scripts/
│   ├── migration.py
│   └── migrations/
├── src/
│   ├── bootstrap.py
│   ├── core/
│   │   ├── database.py
│   │   ├── domain_exception.py
│   │   ├── base_entity.py
│   │   ├── settings.py
│   │   ├── account_context.py
│   │   └── events/
│   └── modules/
│       ├── account/
│       ├── platform/
│       ├── storage/
│       └── training/
└── test/
```

## Estructura por modulo

```text
src/modules/<group>/<module>/
├── adapters/
│   ├── api/
│   ├── composites/
│   ├── dtos/
│   ├── repositories/
│   ├── services/
│   └── events/
├── application/
│   ├── interfaces/
│   └── use_cases/
├── domain/
│   ├── entities/
│   ├── exceptions/
│   └── factories/
└── <module>_module.py
```

## Responsabilidad por capa

### domain

- contiene entidades, invariantes y reglas puras
- no depende de FastAPI ni del driver de base de datos
- concentra excepciones de negocio y factories de creacion o actualizacion

### application

- define contratos y casos de uso
- expresa comandos y queries
- usa interfaces, no implementaciones concretas
- no conoce HTTP, ORM, storage ni framework web

### adapters

- adapta el sistema a HTTP, DB, archivos, eventos o servicios externos
- implementa repositorios concretos
- traduce DTOs de entrada y salida
- mantiene handlers y publishers de eventos fuera del dominio

## Flujo de dependencias

```text
Router -> Composite -> UseCase -> Repository/Factory -> Entity
                    -> EventPublisher -> EventBus -> Handler -> Composite destino
```

Reglas:

- los routers deben ser delgados
- los composites orquestan y delimitan transacciones
- los casos de uso ejecutan una sola intencion de negocio
- los repositorios solo hacen persistencia

## Composition Root

El punto unico de composicion debe vivir en `src/bootstrap.py`.

Ese archivo debe:

- inicializar base de datos
- inicializar EventBus
- registrar grupos de modulos
- dejar al `FastAPI app` listo para servir

## Grupos de modulos

Los grupos son carpetas contenedoras con un archivo `*_group.py` que registra sus modulos hijos. Esto permite ordenar el dominio por capacidades mayores y evita un `bootstrap` inflado.

## Composite como frontera

El `Composite` es el punto donde convergen:

- casos de uso del modulo
- manejo transaccional
- coordinacion con eventos
- validaciones cross-module

Reglas:

- escritura: la transaccion vive en el composite
- lectura: no abrir transacciones innecesarias
- coordinacion con otro modulo: usar eventos o un composite ajeno solo si el acoplamiento esta justificado

## Core compartido

`src/core/` debe contener solo piezas transversales:

- configuracion
- base de datos
- entidades base
- excepciones base
- contexto comun
- sistema de eventos

Regla adicional:

- `BaseEntity` debe vivir en core y toda entidad del dominio debe extenderla
- toda entidad debe nacer con UUID asignado desde su creacion, exista o no en DB

## Scripts de migracion

La evolucion del esquema no debe depender de scripts unicos o manuales.

El proyecto debe tener:

- `scripts/migration.py` como punto de entrada operativo
- `scripts/migrations/` como carpeta de migraciones versionadas
- migraciones repetibles y trazables en una tabla de control

Reglas:

- una migracion no debe asumir ejecucion manual irrepetible
- el estado de migraciones debe quedar persistido
- la evolucion de DB debe poder correrse en local y en servidor con el mismo flujo

No debe convertirse en un basurero de codigo sin hogar.

## Politica de paquetes

- evitar `__init__.py` vacios
- preferir imports directos a modulos concretos
- documentar cualquier excepcion de tooling

## Regla de expansion

Cada nueva capacidad debe caer en una de estas formas:

- un nuevo modulo
- un nuevo adapter
- un nuevo contrato de aplicacion
- un nuevo evento

Si una funcionalidad no entra limpiamente en una de esas formas, la frontera del sistema necesita revision.