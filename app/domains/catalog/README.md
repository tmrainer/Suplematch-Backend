# Catalog

Responsabilidad:

- Cargar productos comerciales aprobados.
- Consultar productos por componente desde PostgreSQL o CSV fallback.
- Aplicar restricciones, safety, presupuesto, stock, trazabilidad y reviews.
- Penalizar repeticion de farmacia/producto y diversificar opciones.
- Administrar reglas de seguridad de catalogo.

Archivos:

- `rutas_componentes.py`: consulta de componentes/productos.
- `rutas_precios.py`: comparacion comercial.
- `catalogo_csv.py`: parseo del catalogo aprobado en CSV.
- `servicio_catalogo_productos.py`: scoring, filtros y diversidad.
- `seguridad_productos.py`: deteccion de restricciones por texto/producto.
- `repositorio_catalogo.py`: acceso a productos comerciales en DB.
- `repositorio_reglas_seguridad.py`: reglas administrables de safety.

Regla de mantenimiento:

PostgreSQL es la fuente principal para endpoints comerciales. El CSV existe como
fallback y como artefacto de importacion, no como persistencia relacional final.
