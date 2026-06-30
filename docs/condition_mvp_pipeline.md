# Pipeline MVP de condiciones probables

Este pipeline crea un modelo tabular multilabel para estimar probabilidades de condiciones o prioridades probables. No diagnostica y no reemplaza evaluacion profesional.

## 1. Fuentes oficiales

La base curada vive en:

```txt
data/knowledge/
```

Archivos CSV:

- `source_domains.csv`: dominios oficiales permitidos.
- `sources.csv`: fuentes oficiales y usos.
- `conditions.csv`: condiciones objetivo y thresholds.
- `condition_rules.csv`: reglas de senales por condicion.
- `biomarkers.csv`: biomarcadores, unidades y umbrales usados para etiquetas.
- `condition_component_links.csv`: relacion condicion-componente.
- `condition_data_requirements.csv`: contrato de datos necesarios por condicion.
- `safety_rules.csv`: reglas duras de seguridad.

Fuentes incluidas:

- NIH Office of Dietary Supplements: fichas de vitamina D, B12, hierro, calcio, zinc, magnesio y funcion inmune.
- FDA: informacion de seguridad sobre suplementos.
- MedlinePlus/NIH: seguridad general e interacciones.
- DIGEMID Peru: trazabilidad comercial por registro sanitario.

El primer reporte del pipeline audita dominio, duplicados y cobertura:

```txt
data/reports/condition_model/01_source_audit.csv
```

## 2. Limpieza y validacion de conocimiento

El script valida que:

- Todas las condiciones esten declaradas en `labels`.
- Cada regla tenga `field`, `operator` y `weight`.
- Cada `source_id` exista en `sources.csv`.
- Cada link condicion-componente apunte a una condicion conocida.
- Las reglas safety tengan fuente oficial asociada.

Reporte:

```txt
data/reports/condition_model/02_knowledge_eda.csv
```

## 3. Dataset semisintetico

El dataset se genera desde reglas trazables, no desde texto libre de internet.

Salida:

```txt
data/training/condition_model/condition_training_dataset.csv
```

Features principales:

- Perfil: edad, sexo, peso, talla, IMC interno.
- Habitos: dieta, sol, ejercicio, sueno, estres, alcohol indirecto si se agrega.
- Dieta medible: porciones de pescado/semana, lacteos/dia, legumbres/semana, carnes/semana, frutas/verduras/dia y proteina diaria estimada.
- Sintomas: fatiga, niebla mental, calambres, dolor, cabello, piel, unas.
- Objetivos: energia, inmunidad, rendimiento, salud osea, cognitivo.
- Labs estructurados: estados `normal`, `borderline`, `low`, `critical_low`, `high`, `critical_high`, `missing`.
- Metadatos de labs: si el dato fue observado, edad aproximada del examen, unidad conocida y rango de referencia conocido.
- Senales derivadas para condiciones blandas: `vitamin_c_diet_signal`, `protein_insufficient_signal`, `protein_gap_g_day`, `hair_skin_nails_cluster`.

El dato faltante se modela de forma explicita:

- Labs: categoria `missing` mas `lab_*_observed=0`.
- Cantidades dietarias: valor `-1` mas `*_reported=0`.
- Sintomas: no se usa cero para representar ausencia de respuesta; se generan como escala ordinal.

Contrato de features:

```txt
data/training/condition_model/condition_feature_contract.csv
```

Targets:

```txt
DEFICIT_VIT_D
DEFICIT_B12
DEFICIT_HIERRO
DEFICIT_MAGNESIO
DEFICIT_FOLATO
DEFICIT_ZINC
DEFICIT_CALCIO
BAJA_INMUNIDAD
RIESGO_SALUD_OSEA
ESTRES_SUENO
RENDIMIENTO_DEPORTIVO
RIESGO_VITAMINA_C_BAJA
RIESGO_OMEGA3_BAJO
RIESGO_PROTEINA_INSUFICIENTE
RIESGO_CABELLO_PIEL_UNAS
RIESGO_METABOLICO_GLUCOSA
RIESGO_DISLIPIDEMIA
SAFETY_RENAL
SAFETY_HEPATICA
SAFETY_TIROIDEA
```

Las condiciones `SAFETY_*` y los riesgos metabolicos/lipidicos son senales de bloqueo o contexto clinico. No deben producir recomendacion comercial directa.

Reporte EDA:

```txt
data/reports/condition_model/03_dataset_eda_summary.csv
data/reports/condition_model/03_dataset_label_prevalence.csv
data/reports/condition_model/03_dataset_lab_status_distribution.csv
data/reports/condition_model/03_dataset_numeric_summary.csv
```

Incluye prevalencia por etiqueta, distribucion de labs y resumen numerico.

## 4. Entrenamiento

Script:

```bash
python3 scripts/training/entrenar_modelo_condiciones.py --rows 2500 --seed 42
```

Entrenamiento largo desacoplado, minimo 10000 casos:

```bash
bash scripts/training/entrenar_condiciones_background.sh
```

El script deja PID y log en:

```txt
data/reports/condition_model/condition_mvp_10000_train.pid
data/reports/condition_model/condition_mvp_10000_train.log
```

Si se usa un entorno limpio, instalar solo lo necesario:

```bash
python3 -m pip install -r requirements-training-minimal.txt
```

Modelo:

```txt
OneVsRestClassifier(Calibrated LogisticRegression)
```

Motivo:

- Multilabel.
- Probabilidades calibradas.
- Facil de explicar.
- Adecuado para dataset tabular pequeno/mediano.
- Menor riesgo de sobreajuste que modelos mas complejos para MVP.

Calibracion:

- `label_thresholds`: umbrales de reglas usados para construir la etiqueta semisintetica.
- `thresholds`: umbrales de prediccion optimizados por etiqueta en el split interno para mejorar F1.
- Safety conserva thresholds estrictos si ya logra recall/precision perfectos.

Artefactos:

```txt
models/runtime/condition_mvp_model.pkl
models/runtime/condition_mvp_metadata.csv
```

Metricas:

```txt
data/reports/condition_model/04_training_metrics.csv
data/reports/condition_model/04_training_metrics_by_label.csv
```

Politica de reentrenamiento:

- No reentrenar el modelo por cada cambio de encuesta o catálogo.
- Primero acumular suficientes casos reales anonimizados con:
  - encuesta normalizada
  - laboratorios OCR/manuales observados
  - recomendaciones mostradas
  - productos elegidos
  - feedback/reseñas
  - bloqueos safety
- Usar feedback real primero para calibrar thresholds y reranking.
- Reentrenar solo cuando exista volumen suficiente y un benchmark fijo que
  demuestre mejora sin degradar safety.

Para MVP se recomienda no reentrenar con menos de varios cientos de sesiones
reales útiles por familia de condición. Si aún no hay volumen, mantener el
modelo actual y ajustar reglas/thresholds auditables.

Script operativo:

```bash
python3 scripts/training/evaluar_preparacion_reentrenamiento.py
```

El script consulta PostgreSQL y reporta:

```txt
recommendation_sessions
recommendation_feedback
supplement_reviews
lab_reports
ready
recommendation
```

Puede usarse como gate estricto:

```bash
python3 scripts/training/evaluar_preparacion_reentrenamiento.py --fail-if-not-ready
```

## 5. Evaluacion golden fija

Ademas del split semisintetico, el modelo tiene un set fijo de escenarios extremos y realistas:

```txt
data/evaluation/condition_model/golden_cases.csv
```

Incluye casos de:

- negativos sanos o incompletos
- safety renal, hepatica y tiroidea
- B12 vegano
- vitamina D baja
- hierro/ferritina baja
- magnesio, zinc, calcio y folato bajos
- dieta baja en vitamina C, omega 3 y proteina
- glucosa y lipidos alterados
- estres/sueno, rendimiento, inmunidad y salud osea
- condiciones blandas aisladas y negativos realistas
- dieta cuantificada suficiente para evitar falsos positivos
- escenarios combinados con multiples senales

Ejecutar:

```bash
python3 scripts/training/evaluar_casos_golden_condiciones.py
```

Para usarlo como gate de CI:

```bash
python3 scripts/training/evaluar_casos_golden_condiciones.py --fail-on-case-failure
```

Reportes:

```txt
data/reports/condition_model/05_golden_summary.csv
data/reports/condition_model/05_golden_case_results.csv
data/reports/condition_model/05_golden_condition_details.csv
data/reports/condition_model/05_golden_condition_summary.csv
```

Esta evaluacion mide regresion funcional del modelo. No reemplaza validacion clinica.

Gate unificado de Modelo 1:

```bash
python3 scripts/validate_condition_model_quality.py
```

Este comando:

- ejecuta golden cases con `--fail-on-case-failure`;
- lee métricas NHANES multi-ciclo por condición;
- lee métricas por fuerza de evidencia (`lab_only`, `diet_only`, `safety_only`);
- falla si safety renal/hepática/tiroidea degrada de forma crítica;
- reporta warnings para condiciones blandas o dietarias que necesitan mejora.

## 6. Evaluacion holdout de 1000+ casos

Para evaluar el modelo entrenado contra casos nuevos no usados en entrenamiento, generar un holdout semisintetico con otra semilla:

```bash
python3 scripts/training/evaluar_holdout_condiciones.py --rows 1000 --seed 20260617
```

Para usarlo como gate:

```bash
python3 scripts/training/evaluar_holdout_condiciones.py \
  --rows 1000 \
  --seed 20260617 \
  --min-f1-macro 0.85 \
  --max-hamming-loss 0.05
```

Salidas:

```txt
data/evaluation/condition_model/holdout_1000_cases.csv
data/reports/condition_model/06_holdout_1000_summary.csv
data/reports/condition_model/06_holdout_1000_condition_metrics.csv
data/reports/condition_model/06_holdout_1000_case_results.csv
data/reports/condition_model/06_holdout_1000_false_negatives.csv
data/reports/condition_model/06_holdout_1000_false_positives.csv
```

Esta evaluacion es mas amplia que los casos golden: mide precision, recall, F1, specificity, falsos positivos y falsos negativos por condicion sobre al menos 1000 casos nuevos.

## Runtime API del Modelo 1

El runtime `app/ml/runtime/condition_mvp_inference.py` devuelve probabilidades
por condición y separa explícitamente la fuerza de señal.

Campos relevantes por condición:

```txt
condition
probability
model_probability
threshold
positive
drivers
driver_details
missing_data
evidence_level
primary_signal_group
signal_strength
signal_groups
rule_score
calibrated_by_rules
safety_flag
```

Grupos de señal:

```txt
observed_lab              laboratorio observado por OCR/manual
medical_safety            señales médicas sensibles o laboratorios críticos
declared_diet             dieta declarada o cantidades dietarias
self_reported_symptoms    síntomas autodeclarados
restrictions              restricciones, condiciones declaradas o suplementos actuales
profile_context           edad, sexo, IMC y antropometría
survey_context            objetivos y contexto de encuesta
derived_soft_signal       señales derivadas como brecha proteica o cluster cabello/piel/uñas
```

Interpretación:

- `probability` es la probabilidad final usada por el motor.
- `model_probability` es la probabilidad cruda del clasificador.
- `rule_score` es la suma auditable de reglas coincidentes.
- `calibrated_by_rules=true` indica que una regla fuerte elevó una condición
  que el clasificador dejaba bajo el threshold.
- `signal_strength` resume la fuerza: `alta`, `media` o `baja`.

El pipeline principal ahora usa `condition_mvp_model.pkl` como Modelo 1
preferido. Si no existe, conserva compatibilidad con `modelo1_pipeline.pkl`.

## 7. Casos reales anonimizados

Para empezar a trabajar con casos reales sin mezclar PII en el repositorio, usar:

```txt
data/evaluation/condition_model/real_cases/real_cases_template.csv
```

Reglas:

- No incluir nombre, apellido, email, telefono, DNI, direccion ni fecha de nacimiento.
- Usar `source_case_id` solo como identificador temporal local.
- El script genera `case_id` anonimo con hash irreversible.
- Solo se aceptan filas con `consent_for_training=true`.
- Si hay revision manual, usar `expected_positive` y `expected_negative` con codigos de condicion.

Preparacion:

```bash
REAL_CASES_HASH_SALT="cambiar-por-secreto-local" \
python3 scripts/training/preparar_casos_reales_condiciones.py \
  --input data/evaluation/condition_model/real_cases/mis_casos_reales.csv
```

Salidas:

```txt
data/evaluation/condition_model/real_cases/real_cases_anonymized.csv
data/reports/condition_model/07_real_cases_predictions.csv
data/reports/condition_model/07_real_cases_rejected.csv
data/reports/condition_model/07_real_cases_summary.csv
```

El archivo `demo_real_cases_input.csv` es artificial y solo valida el formato.

## 8. Casos publicos reales: NHANES

Para tener pruebas reales reproducibles sin recolectar PII propia, se agrego un importador de NHANES 2017-2018. NHANES es publicado por CDC/NCHS como datos de uso publico por componentes. Los archivos se unen por `SEQN`, pero `SEQN` nunca sale en los CSV finales; se transforma a un `case_id` hash irreversible.

Fuente base:

```txt
https://wwwn.cdc.gov/nchs/nhanes/
https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/
```

Comando:

```bash
NHANES_CASE_HASH_SALT="cambiar-por-secreto-local" \
python3 scripts/training/importar_casos_nhanes_condiciones.py --limit 1000
```

Archivos CDC descargados/cacheados:

```txt
DEMO_J.XPT     Demographics
BMX_J.XPT      Body Measures
BIOPRO_J.XPT   Standard Biochemistry Profile
CBC_J.XPT      Complete Blood Count
TCHOL_J.XPT    Total Cholesterol
HDL_J.XPT      HDL Cholesterol
TRIGLY_J.XPT   Triglycerides and LDL
GLU_J.XPT      Fasting Glucose
VID_J.XPT      Vitamin D
VIC_J.XPT      Vitamin C
FOLATE_J.XPT   RBC Folate
FERTIN_J.XPT   Ferritin
```

Salidas actuales:

```txt
data/evaluation/condition_model/real_cases/nhanes_2017_2018_condition_cases.csv
data/reports/condition_model/08_nhanes_2017_2018_predictions.csv
data/reports/condition_model/08_nhanes_2017_2018_summary.csv
data/reports/condition_model/08_nhanes_2017_2018_condition_summary.csv
data/reports/condition_model/08_nhanes_2017_2018_source_manifest.csv
```

Resultado materializado:

```txt
accepted_cases=1000
prediction_rows=20000
condition_labels=20
clinical_validation=not_clinically_validated
```

Uso correcto:

- Sirve para probar el comportamiento del modelo sobre personas/laboratorios reales.
- No sirve como truth set clinico porque no tiene etiquetas curadas para cada condicion SupleMatch.
- Las condiciones derivadas siguen siendo probabilidades y deben revisarse contra reglas y safety gate.
- `VITB12_J.XPT`/`B12_J.XPT` no esta disponible en este ciclo; B12 queda como `unknown` en esta fuente.

MIMIC-IV tambien es una fuente real de-identificada, pero requiere usuario PhysioNet credentialed, DUA y entrenamiento CITI. Por eso queda como fuente futura, no como dataset inmediato del MVP.

## 9. Benchmark NHANES semi-curado

Para subir el set NHANES de "datos reales no etiquetados" a "benchmark real parcial", se agrego una capa de etiquetas derivadas por reglas auditables. Estas etiquetas no salen del modelo; salen de laboratorios reales normalizados:

- vitamina D: `lab_vitamin_d_status`
- ferritina/hierro: `lab_ferritin_status` y hemoglobina como contexto
- folato: `lab_folate_status`
- calcio/salud osea: `lab_calcium_status` y `lab_vitamin_d_status`
- vitamina C: `benchmark_lab_vitamin_c_status`
- glucosa: `lab_glucose_status`
- dislipidemia: colesterol total, LDL, HDL y trigliceridos
- safety renal: creatinina y eGFR estimado
- safety hepatica: ALT y AST

Comando:

```bash
python3 scripts/training/construir_benchmark_nhanes_condiciones.py
```

Salidas:

```txt
data/evaluation/condition_model/nhanes_2017_2018_benchmark_labels.csv
data/reports/condition_model/09_nhanes_2017_2018_benchmark_details.csv
data/reports/condition_model/09_nhanes_2017_2018_benchmark_case_results.csv
data/reports/condition_model/09_nhanes_2017_2018_benchmark_condition_metrics.csv
data/reports/condition_model/09_nhanes_2017_2018_benchmark_summary.csv
```

Resultado actual:

```txt
cases=1000
labels=20000
evaluated_labels=8218
benchmark_coverage=0.4109
macro_f1_evaluated_conditions=0.7783
clinical_validation=rule_derived_benchmark_not_diagnosis
```

Interpretacion:

- `positive` y `negative` solo se asignan cuando existe evidencia de laboratorio suficiente.
- `unknown` es una clase explicita, no se trata como negativo.
- Las metricas solo evaluan labels con `confidence >= 0.75`.
- Condiciones sin biomarcador en NHANES 2017-2018, como B12, zinc, TSH, omega 3 o proteina, quedan fuera de evaluacion.
- El benchmark ya detecta brechas reales: vitamina C aparece con cobertura alta, pero el modelo actual no consume ese laboratorio; dislipidemia tiene recall bajo frente a panel lipidico real.

Para ampliar B12 se debe agregar otro ciclo NHANES con archivo `VITB12_*`/`B12_*`, por ejemplo 2011-2012 o 2013-2014, manteniendo la misma logica de hash y labels `unknown` cuando falte evidencia.

## 10. Benchmark NHANES multi-ciclo y calibracion

Para subir cobertura real se agrego un importador multi-ciclo:

```bash
python3 scripts/training/importar_casos_nhanes_multiciclo.py --limit-per-cycle 500
```

Ciclos incluidos:

```txt
2011_2012: B12 serico, TSH, dieta 24h
2013_2014: B12 serico, dieta 24h
2015_2016: ferritina, dieta 24h
2017_2018: ferritina, vitamina C, dieta 24h
```

Salidas:

```txt
data/evaluation/condition_model/real_cases/nhanes_multi_cycle_condition_cases.csv
data/reports/condition_model/08_nhanes_multi_cycle_predictions.csv
data/reports/condition_model/08_nhanes_multi_cycle_summary.csv
data/reports/condition_model/08_nhanes_multi_cycle_condition_summary.csv
data/reports/condition_model/08_nhanes_multi_cycle_source_manifest.csv
```

Luego se construye el benchmark:

```bash
python3 scripts/training/construir_benchmark_nhanes_condiciones.py \
  --cases data/evaluation/condition_model/real_cases/nhanes_multi_cycle_condition_cases.csv \
  --predictions data/reports/condition_model/08_nhanes_multi_cycle_predictions.csv \
  --labels data/evaluation/condition_model/nhanes_multi_cycle_benchmark_labels.csv \
  --details data/reports/condition_model/09_nhanes_multi_cycle_benchmark_details.csv \
  --case-results data/reports/condition_model/09_nhanes_multi_cycle_benchmark_case_results.csv \
  --condition-metrics data/reports/condition_model/09_nhanes_multi_cycle_benchmark_condition_metrics.csv \
  --summary data/reports/condition_model/09_nhanes_multi_cycle_benchmark_summary.csv
```

Resultado actual:

```txt
cases=2000
labels=40000
evaluated_labels=23516
benchmark_coverage=0.5879
macro_f1_evaluated_conditions=0.6001
```

La cobertura subio porque ahora hay:

- B12 serico en 2011-2012 y 2013-2014.
- TSH en 2011-2012.
- Dieta de 24 horas para B12, vitamina C, zinc, magnesio, calcio, folato y proteina.

Calibracion conservadora de thresholds:

```bash
python3 scripts/training/calibrar_thresholds_condiciones.py
python3 scripts/training/calibrar_thresholds_condiciones.py --apply
```

La calibracion usa split estable por `case_id`:

- 50% calibracion.
- 50% evaluacion.
- No acepta cambios que bajen demasiado especificidad.
- No aplica thresholds menores a `0.05`.
- Safety usa especificidad minima mas alta.

Cambio aplicado al artefacto:

```txt
RIESGO_SALUD_OSEA: 0.35 -> 0.05
```

Backup creado:

```txt
models/backups/condition_mvp_model.2026-06-17T054329_0000.bak.pkl
```

Brechas detectadas por el benchmark multi-ciclo:

- `DEFICIT_B12` ya es evaluable y el modelo reentrenado usa B12 de laboratorio/dieta.
- `RIESGO_VITAMINA_C_BAJA`, `RIESGO_OMEGA3_BAJO` y `RIESGO_DISLIPIDEMIA` mejoraron al incorporar dieta/lab y reglas mas fuertes.
- `DEFICIT_ZINC`, `DEFICIT_MAGNESIO`, `DEFICIT_CALCIO` y `RIESGO_SALUD_OSEA` siguen como brechas de mejora.
- `RIESGO_PROTEINA_INSUFICIENTE` funciona bien con dieta porque el feature `protein_g_day_estimate` ya esta en el contrato.

El reentrenamiento actual agrego al contrato de features:

```txt
benchmark_diet_b12_status
benchmark_diet_vitamin_c_status
benchmark_diet_zinc_status
benchmark_diet_magnesium_status
benchmark_diet_calcium_status
benchmark_diet_folate_status
benchmark_diet_protein_status
benchmark_diet_omega3_status
benchmark_lab_vitamin_c_status
```

Resultado posterior a reentrenamiento:

```txt
benchmark_coverage=0.6332
macro_f1_evaluated_conditions=0.7255
```

Reportes adicionales:

```txt
data/reports/condition_model/09_nhanes_multi_cycle_benchmark_evidence_group_metrics.csv
data/reports/condition_model/09_nhanes_multi_cycle_benchmark_executive_report.csv
```

El reporte por fuerza de evidencia separa:

```txt
lab_only
diet_only
safety_only
surrogate
unknown
```

El reporte ejecutivo incluye:

```txt
cobertura
precision
recall
riesgo de falso negativo
estado: listo | necesita_mejora | no_evaluable
```

Calibracion final aplicada:

```txt
DEFICIT_FOLATO: 0.54 -> 0.27
```

Comando unico:

```bash
python3 scripts/training/ejecutar_suite_benchmark_condiciones.py --rows 10000 --limit-per-cycle 500
```

Para aplicar thresholds aceptados en la misma corrida:

```bash
python3 scripts/training/ejecutar_suite_benchmark_condiciones.py \
  --rows 10000 \
  --limit-per-cycle 500 \
  --apply-calibration
```

## 11. Como interpretar metricas

Las metricas altas indican que el modelo aprendio bien las reglas semisinteticas. No equivalen a validacion clinica.

Para convertirlo en modelo real se necesita:

- Dataset anonimo con casos reales.
- Labs reales antes/despues si existen.
- Etiquetas curadas por criterio profesional o reglas mas auditadas.
- Evaluacion externa y calibracion por condicion.

## 12. Integracion recomendada

No reemplazar automaticamente `modelo1_pipeline.pkl`.

Siguiente paso recomendado:

```txt
ConditionEvidenceService
```

Que consuma:

- probabilidades de `condition_mvp_model.pkl`
- reglas CSV de `data/knowledge`
- labs/OCR
- safety gate

Y devuelva:

```json
{
  "condition": "DEFICIT_VIT_D",
  "probability": 0.74,
  "threshold": 0.55,
  "positive": true,
  "evidence_level": "self_reported",
  "drivers": ["exposicion_solar", "fatiga_general"],
  "missing_data": ["vitamin_d"],
  "safety_flag": false
}
```

La salida sigue siendo probabilistica. `positive=true` significa que supera el umbral interno de riesgo/prioridad, no que exista diagnostico.

## 13. Limitaciones

- La base curada es una abstraccion para MVP, no una guia medica completa.
- El dataset es semisintetico.
- El feedback de usuarios debe alimentar primero el re-ranker, no este modelo principal.
- Las reglas safety deben poder bloquear recomendaciones comerciales aunque el modelo estime alta probabilidad.
