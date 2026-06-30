# Recommendations

Responsabilidad:

- Convertir encuesta, perfil y examenes en condiciones probables.
- Ejecutar el pipeline hibrido de modelo/reglas.
- Enriquecer componentes con productos comerciales.
- Aplicar safety, presupuesto, stock, reviews, feedback y diversidad.
- Persistir sesiones, items, packs, metricas y advertencias.

Archivos:

- `rutas.py`: endpoint publico de recomendacion.
- `esquemas.py`: respuesta y estructuras de recomendacion.
- `servicio_recomendaciones.py`: orquestacion principal.
- `reglas_presentacion.py`: etiquetas, warnings, aliases y reglas de presentacion.
- `repositorio_recomendaciones.py`: persistencia de sesiones/items/packs.
- `repositorio_metricas_recomendacion.py`: exposicion, repeticion y diversidad.

Regla de mantenimiento:

El modelo puede estimar probabilidades, pero la decision comercial final debe
pasar por reglas de safety y catalogo. No agregar recomendaciones directas desde
el modelo sin pasar por el servicio.
