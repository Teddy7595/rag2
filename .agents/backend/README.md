# Clean Standar

Este directorio reconstituye la filosofia observable en `backend_python` y la convierte en un estandar reusable para futuros proyectos. El objetivo no es clonar este repositorio tal cual, sino fijar una base que permita construir sistemas limpios, modulares, desacoplados y listos para crecer sin reescribir el nucleo cada vez.

## Objetivos del estandar

- usar Clean Architecture por modulo
- mantener un monolito modular como base de crecimiento
- separar dominio, aplicacion e infraestructura de forma explicita
- comunicar modulos por contratos y eventos, no por imports directos arbitrarios
- funcionar bien en local y en servidor
- soportar archivos, sockets, notificaciones y procesos en tiempo real sin romper la arquitectura

## Documentos incluidos

- [filosofia-general.md](./filosofia-general.md)
- [arquitectura.md](./arquitectura.md)
- [eventos.md](./eventos.md)
- [base-datos.md](./base-datos.md)
- [seguridad-y-autenticacion.md](./seguridad-y-autenticacion.md)
- [middlewares.md](./middlewares.md)
- [swagger-y-openapi.md](./swagger-y-openapi.md)
- [pruebas.md](./pruebas.md)
- [storage-y-archivos.md](./storage-y-archivos.md)
- [tiempo-real-y-sockets.md](./tiempo-real-y-sockets.md)
- [docker-y-despliegue.md](./docker-y-despliegue.md)
- [documentacion-modular.md](./documentacion-modular.md)

## Arranque esperado para cualquier proyecto basado en este estandar

Todo proyecto que adopte este estandar debe poder iniciarse con una experiencia minima y predecible.

### Modo local

```bash
cp .env.example .env
uv sync
python main.py
```

Alternativa directa:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Pruebas

```bash
pytest
```

### Docker

```bash
docker compose up --build
```

## Contrato minimo del proyecto estandar

- `main.py` debe exponer `app`
- `src/bootstrap.py` debe ser la composicion central
- `.env.example` debe existir
- `README.md` raiz debe explicar instalacion, arranque, pruebas y despliegue
- `docs/` debe contener la narrativa tecnica funcional
- cada modulo debe poder entenderse sin leer medio repositorio

## Que toma este estandar del repo actual

- grupos de modulos registrados desde `bootstrap`
- wiring explicito por `*_module.py`
- `Composite` como frontera de orquestacion
- `EventBus` como via interna de desacoplamiento
- persistencia simple para local y pruebas aisladas
- documentacion Swagger enriquecida en varios routers del dominio de entrenamiento

## Uso recomendado

Lee primero `filosofia-general.md` y `arquitectura.md`. Luego usa los demas documentos como contratos operativos por capacidad.