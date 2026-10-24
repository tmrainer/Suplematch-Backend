# Paquete de revisión clínica

Cierra dos casillas del plan de fiabilidad cuando un profesional lo completa: "≥100 casos de validación revisados
por nutricionista" (Fase 4) y "revisión de reglas y safety rules, firmada y versionada" (Fase 7).

## Generar

```bash
# Necesita los artefactos en models/runtime (condition_mvp + modelo2) y torch. ~5 min para 120 casos.
python scripts/clinical/generar_paquete_revision.py --cases 120
# -> data/reports/clinical_review/clinical_review_v1_<fecha>_<huella>.xlsx (+ .manifest.json)
```

El `.xlsx` contiene:

| Hoja | Contenido | Qué marca quien revisa |
|---|---|---|
| Instrucciones | Qué revisar, cómo leer `risk_index` (no es probabilidad), qué es error grave | — |
| Casos | 120 perfiles sintéticos corridos end-to-end por `RecommendationService` (sin BD): perfil legible, condiciones detectadas con índice, estimaciones NHANES, nivel de seguridad, alertas, 10 primeras recomendaciones | acuerdo con condiciones y recomendaciones, faltantes/sobrantes, seguridad correcta/insuficiente/excesiva, error grave |
| Recomendaciones | Lista completa por caso (componente, rol, evidencia, compra permitida, motivo) | — |
| Reglas condición, Reglas seguridad, Interacciones, Vínculos condición-comp, Etapa de vida, Reglas ingrediente | Una fila por regla de `data/knowledge/*.csv` y `DEFAULT_INGREDIENT_SAFETY_RULES` | aprobar / modificar / rechazar / no_se, cambio propuesto, fuente sugerida |
| Firma | Nombre, profesión, colegiatura, fecha, firma; hash de cada archivo revisado | datos del profesional |

Casos estratificados con semilla fija (`--seed`, default 2026): cada condición de seguridad ×4 (embarazo siempre
mujer), 4 menores, 8 mayores de 60, 15 vegetarianos/veganos, 25 con labs (valores bajo/normal/alto según
`biomarkers.csv`); el resto al azar. Son sintéticos: no contienen datos de personas.

Cada regla lleva `rule_key` (hash de sus columnas identificadoras), así la revisión se cruza con el CSV aunque
cambie el orden de filas.

## Importar la revisión

```bash
python scripts/clinical/importar_revision.py --xlsx <paquete_revisado>.xlsx
# -> <package_id>_resultado.json y <package_id>_acciones.csv en data/reports/clinical_review/
```

- `status`: `completa` cuando los ≥100 casos tienen las 4 columnas obligatorias, todas las reglas tienen decisión
  y la firma está completa.
- `plan_checkbox_ready`: `completa`, sin errores graves y sin archivos cambiados desde que se generó el paquete.
- `changed_files`: archivos revisados cuyo hash cambió. Las reglas con `rule_key` que ya no existe salen como
  `regla_cambiada_o_eliminada` y las nuevas como `new_rules_not_reviewed`: hay que revisarlas de nuevo.
- `acciones.csv`: reglas a modificar/rechazar y casos con error grave, para convertirlos en cambios en
  `data/knowledge` (cada cambio sube la columna `version` del CSV).

## Cambiar reglas: informe de impacto y candado

Cualquier cambio en las tablas clínicas de `data/knowledge` cambia el comportamiento clínico:

1. `python scripts/clinical/informe_impacto_reglas.py --base-ref HEAD` (o `--base-file`, o
   `--base-aggregation sum --aggregation family`) muestra las reglas agregadas, quitadas o con peso cambiado, y los
   positivos por condición antes y después sobre los casos del paquete, **solo con reglas, sin reentrenar**.
2. `python scripts/clinical/manifiesto_reglas.py --approve --by ... --note ...` registra el hash aprobado de cada
   tabla en `data/knowledge/clinical_rules_manifest.json`. `tests/unit/test_clinical_rules_manifest.py` falla si una
   tabla cambia sin aprobar. La línea base actual (2026-10-24) es técnica, NO una revisión clínica.
3. Recién entonces se reentrena `condition_mvp`.

Otras herramientas: `scripts/clinical/valor_preguntas.py` (cuánto cambia la detección sin cada pregunta) y
`scripts/training/estabilidad_semillas_condiciones.py` (qué detecciones dependen de la semilla del modelo).

## Lo que mostró el primer paquete (2026-10-23, antes de cualquier revisión)

Sobre 120 casos: 19 `normal`, 61 `caution`, 40 `medical_review_required`. Media de 11 condiciones detectadas y
33 componentes por caso; "Riesgo de proteína insuficiente" y "Energía y fatiga nutricional" salen en los 120 casos,
y algunas condiciones se marcan detectadas con índice 0.00. Es probable sobre-detección del `condition_mvp`
sintético; es lo primero que conviene pedir que juzgue el profesional.

## Tras los cambios de encuesta (2026-10-24, contrato `2026-10-24.1`)

Paquete vigente: ver la sección siguiente (el `..._837ac44b6304.xlsx` de esta etapa ya fue reemplazado) (el del 2026-10-23 queda como referencia; no
enviar). El generador ahora llena el bloque de alimentos completo y coherente con el tipo de dieta (o lo deja
vacío en 20 % de los casos) con la escala nueva, y responde las preguntas nuevas en ~70 % de los casos. Los casos
aleatorios no son idénticos a los del paquete anterior; las cuotas sí.

| | 2026-10-23 | 2026-10-24 |
|---|---|---|
| Condiciones por caso (media) | 11.2 | 10.0 |
| Condiciones "detectadas" con índice 0.00 | 81 | 0 |
| Proteína insuficiente / Fatiga | 120 / 120 | 70 / 77 |
| Componentes por caso | 32.8 | 27.8 |

Lo que sigue alto no depende ya de la encuesta y conviene que lo juzgue el profesional:

- Reglas de contexto de bienestar (`RUNTIME_CONTEXT_CONDITIONS` en `condition_mvp_inference.py`) cuentan dos veces
  la misma señal: p. ej. Salud cognitiva suma `meta_cognitivo`, `problemas_sueno` y `cognitive_context_signal`,
  que se activan con lo mismo; dormir menos de 7 h basta (92/120).
- Reglas dietarias correlacionadas: proteína suma `protein_g_day_estimate < 55` (absoluto, sin peso corporal),
  `protein_insufficient_signal` y el estado por kg; vitamina C suma `dieta_deficiente`, `fruit_veg <= 2`,
  `vitamin_c_diet_signal` y el estado dietario.
- Casos que el modelo anterior marcaba y el actual no, porque la propia regla no llega al umbral (0.55): poco sol
  sin otro factor (vitamina D, 0.42) y entrenar a diario sin otro factor (rendimiento, 0.50). Si deben marcarse,
  es un cambio de peso en `condition_rules.csv`.

## Agregación por familia, umbrales y segunda opinión (2026-10-24, tarde)

Paquete vigente: `clinical_review_v1_20261024_647af323ccc1.xlsx`.

| | 2026-10-23 | encuesta v2 | + familias / segunda opinión |
|---|---|---|---|
| Condiciones por caso | 11.2 | 10.0 | 5.0 |
| Componentes por caso | 32.8 | 27.8 | 17.0 |
| Índice 0.00 | 81 | 0 | 0 |

Qué cambió (detalle en `app/ml/features_contract.py`):

- Cada familia de evidencia cuenta una vez (máximo); las señales derivadas tipo "O" (`meta_*`, `*_signal`) son
  proxies y solo cuentan si ninguno de sus datos de origen ya contó.
- Sin laboratorio, un positivo necesita dos familias independientes.
- 4 condiciones que solo llegaban a su umbral contando doble usan como umbral sus dos señales más fuertes:
  Salud ósea 0.42, Cabello/piel 0.40, Cardiovascular 0.40, Cognitiva 0.42. Las demás conservan su umbral.
- Las reglas de contexto de bienestar que estaban en el código pasaron al CSV (+20 reglas, mismos pesos).
- Vitamina D limítrofe (confirmada por la encuesta y a menos de 0.15 del umbral) se marca si el modelo real
  NHANES también la estima positiva; el índice mostrado es esa probabilidad calibrada.
- Para revertir: `entrenar_modelo_condiciones.py --rule-aggregation sum` (el runtime usa el modo guardado en el
  artefacto).

Puntos para el profesional:

- Rendimiento deportivo es casi inalcanzable: exige actividad, dolor muscular, calambres y fatiga a la vez.
- Vitamina D solo por poco sol ya no se marca (una sola familia y NHANES no ve exposición solar).
- Los 4 umbrales derivados de arriba.
- Estabilidad (5 semillas): 20 % de las detecciones depende de la semilla; las más inestables son Cognitiva,
  Estrés y sueño y Vitamina D.

