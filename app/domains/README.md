# Dominios de Backend

Esta carpeta agrupa la logica de negocio por dominio. La capa `app/api/v1` solo
ensambla rutas y dependencias; cada dominio contiene sus propios endpoints,
schemas, servicios y repositorios.

Convenciones:

- `rutas.py`: endpoints FastAPI.
- `esquemas.py`: modelos Pydantic del dominio.
- `servicio_*.py`: reglas de negocio.
- `repositorio_*.py`: acceso a PostgreSQL.
- Archivos auxiliares: catalogos, reglas o parseadores usados solo por el dominio.

Dominios actuales:

- `admin`: moderacion, catalogo, auditoria y observabilidad administrativa.
- `auth`: registro, login, JWT, refresh tokens y logout.
- `catalog`: productos comerciales, precios, stock, restricciones y safety.
- `feedback`: feedback de recomendaciones y resumen legacy de re-ranking.
- `history`: historial de recomendaciones por usuario.
- `labs`: carga, OCR, parseo y analisis de examenes.
- `recommendations`: generacion, explicacion, persistencia y enriquecimiento comercial.
- `reviews`: resenas unitarias y metricas de producto.
- `survey`: contrato, validacion y antropometria de encuesta.
- `users`: usuarios, roles y perfil personal.
