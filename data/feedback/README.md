# Feedback Data

Exportaciones anonimizadas de feedback, reviews, exposicion y elecciones de
producto usadas para analisis offline.

La fuente relacional principal es PostgreSQL. Esta carpeta solo debe contener
exports controlados, por ejemplo:

- snapshots anonimizados para re-ranking.
- datasets offline para evaluacion.
- archivos agregados sin datos personales identificables.

No guardar aqui dumps completos de usuarios ni datos sensibles crudos.
