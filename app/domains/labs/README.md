# Labs

Responsabilidad:

- Recibir texto, imagen o PDF de examenes.
- Extraer texto por OCR cuando aplica.
- Buscar biomarcadores conocidos usando alias y palabras guia.
- Normalizar unidades, valores y rangos de referencia.
- Generar senales de deficiencia, safety y condicion probable.
- Persistir reportes y resultados por usuario con consentimiento.

Archivos:

- `rutas.py`: endpoints de examenes.
- `esquemas.py`: requests/responses de laboratorio.
- `biomarcadores.py`: definiciones de biomarcadores, alias, rangos y criticidad.
- `servicio_analisis_examenes.py`: OCR, parseo, analisis y persistencia.

Regla de mantenimiento:

Los rangos incluidos son heuristicas de prototipo. Cuando el laboratorio entrega
su propio rango de referencia, el sistema debe priorizar ese rango sobre el
rango default.
