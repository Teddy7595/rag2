# Imagen oficial de pgvector sobre PostgreSQL 16
FROM pgvector/pgvector:pg16

# Credenciales via docker-compose.yml (environment:), no se hornean en la imagen
# para evitar tener dos fuentes de verdad desincronizadas.

EXPOSE 5432
