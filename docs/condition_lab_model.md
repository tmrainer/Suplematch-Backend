# Modelo real de riesgo de laboratorio (`condition_lab_model`)

Fecha: 2026-10-22. Fase 3 (mediano plazo) del plan de fiabilidad. Script: `scripts/training/entrenar_condiciones_nhanes.py`.
Runtime: `app/ml/runtime/condition_lab_inference.py`, expuesto en `/recommend` como `lab_risk_estimates` con `score_basis="model_real"`.

## Qué predice y con qué

**Tarea:** probabilidad de que un laboratorio esté fuera de rango, usando solo lo que una persona puede responder
(demografía, antropometría, suplementos que toma, dieta, actividad, alcohol, sueño). **Ningún laboratorio entra como feature**
(test `test_features_never_contain_laboratory_columns`). Los cortes de los targets son los de `data/knowledge/biomarkers.csv`
(NIH ODS, OMS 2024, MedlinePlus).

**Datos:** NHANES (CDC). Entrena en el ciclo 2015-2016 (5 992 adultos ≥18) y evalúa en 2017-2018 (5 856 adultos): split
temporal, sin mezcla. Umbrales elegidos en validación interna del train (nunca en test), mínimo 0.30. Calibración sigmoid cv=3.

## Resultados en el ciclo de test (2017-2018)

| Target | Prevalencia | ROC-AUC | AP | Brier (base prevalencia) | ECE | Lectura |
|---|---|---|---|---|---|---|
| Vitamina D < 20 ng/mL | 0.30 | **0.815** | 0.63 | 0.155 (0.208) | 0.029 | Útil: la encuesta predice bien el déficit de vitamina D |
| Glucosa ayunas ≥ 100 | 0.64 | 0.762 | 0.84 | 0.187 (0.231) | 0.046 | Útil; prevalencia alta |
| HDL < 40 | 0.17 | 0.749 | 0.37 | 0.126 (0.141) | 0.022 | Moderado |
| Anemia (OMS por sexo) | 0.11 | 0.737 | 0.25 | 0.088 (0.095) | 0.016 | Moderado; recall bajo al umbral |
| ALT > 40 | 0.09 | 0.695 | 0.19 | 0.077 (0.080) | 0.016 | Débil, apenas mejor que base |
| Colesterol total ≥ 200 | 0.34 | 0.648 | 0.46 | 0.213 (0.226) | 0.032 | Débil |
| Ferritina < 30 (mujeres 18-49) | 0.39 | 0.576 | 0.44 | 0.234 (0.237) | 0.030 | **No útil** con estas features |

Interpretación honesta: es la primera vez que el proyecto tiene un número medido sobre datos reales. Vitamina D y glucosa
justifican sugerir un examen; ferritina, colesterol y ALT no se pueden inferir desde la encuesta y el producto no debería
sugerir que sí.

## Cómo se usa en el producto

- `lab_risk_estimates[]`: `target`, `condition` asociada, `probability` calibrada, `threshold`, `positive`, `score_basis="model_real"`, nota de población.
- No cambia qué componentes se recomiendan (eso sigue en reglas + evidencia). Sirve para priorizar y para decir
  "conviene confirmar con un examen de X".
- El Modelo 1 sintético (`condition_mvp`) sigue operando como índice de riesgo basado en reglas; la salida de ambos
  se distingue por `score_basis`.

## Mapeo encuesta → features (`survey_to_nhanes_features`)

Disponibles: sexo, edad, IMC/peso/talla, suplementos actuales y dosis, proteína estimada, ejercicio (vigorosa/moderada),
alcohol, horas de sueño, calidad de sueño, embarazo, diabetes medicada y, desde el contrato de encuesta
`2026-10-23.1`, **tabaco** (`tabaco`: `nunca|ex|actual`) y **salud autopercibida** (`salud_autopercibida`:
`excelente|muy_buena|buena|regular|mala`), con el mismo vocabulario que el modelo. No disponibles (se imputan con
mediana + indicador): etnia, educación, ingreso, nutrientes de la dieta detallados.

### Ablación: ¿cuánto aportan tabaco y salud autopercibida? (2026-10-23)

Se reentrenó el mismo pipeline forzando `fuma` y `salud_autopercibida` a faltante
(`--drop-features fuma salud_autopercibida --report-suffix ablation_sin_tabaco_salud`). AUC en el ciclo de test:

| Target | Con tabaco + salud | Sin | Δ |
|---|---|---|---|
| vitamina D baja | 0.815 | 0.814 | +0.001 |
| ferritina baja | 0.576 | 0.576 | 0.000 |
| anemia | 0.737 | 0.731 | +0.006 |
| glucosa alta | 0.762 | 0.765 | −0.003 |
| colesterol alto | 0.648 | 0.648 | 0.000 |
| HDL bajo | 0.749 | 0.745 | +0.004 |
| ALT alta | 0.695 | 0.697 | −0.001 |

Conclusión: **el aporte es nulo en la práctica** (|Δ| ≤ 0.006, dentro del ruido). La hipótesis "añadirlos mejora el
modelo real" no se sostiene; se mantienen en la encuesta por ser opcionales y baratos, pero no justifican pantalla
propia. Las variables que sí pesan (dieta detallada, ingreso, etnia) no son preguntables en una encuesta corta.
Reporte: `data/reports/condition_model/nhanes_real_metrics_ablation_sin_tabaco_salud.{json,csv}`.

## Limitaciones

1. Población de EE. UU.; **no validado en Perú**. Validar anemia con ENDES (hemoglobina real, módulo RECH6) antes de usar
   `target_anemia` para DEFICIT_HIERRO en producción.
2. Sin pesos muestrales: las métricas no son estimaciones poblacionales.
3. Ferritina: NHANES 2015-16 solo la midió en mujeres 12-49; el target se restringe a mujeres 18-49 en ambos ciclos.
4. No es diagnóstico.

## Reproducir

```bash
python scripts/training/entrenar_condiciones_nhanes.py          # descarga XPT a data/raw/nhanes/ y entrena
python scripts/training/entrenar_condiciones_nhanes.py --quick  # humo con 1 500 filas por ciclo
```
Salidas: `models/runtime/condition_lab_model.pkl`, `models/runtime/condition_lab_model_card.json`,
`data/reports/condition_model/nhanes_real_metrics.{json,csv}`.


## Validación peruana con ENDES (2026-10-22)

Script: `scripts/training/validar_anemia_endes.py`. Datos: ENDES 2022 y 2024 (INEI, datos abiertos), mujeres 18–49 con hemoglobina medida.
Target oficial `V457` (anemia INEI sobre Hb ajustada por altitud); coincide al 100 % con el corte OMS (<12 g/dL, <11 embarazo) sobre `V456`.

| Evaluación | n | Prevalencia | ROC-AUC | AP | Brier (base) | ECE |
|---|---|---|---|---|---|---|
| (a) Modelo NHANES tal cual, ENDES 2022 | 28947 | 0.217 | **0.501** | 0.220 | 0.175 (0.170) | 0.061 |
| (a) Modelo NHANES tal cual, ENDES 2024 | 27464 | 0.242 | **0.497** | 0.243 | 0.190 (0.183) | 0.066 |
| (b) NHANES recalibrado (isotónica 2022) → 2024 | 27464 | | 0.498 | | 0.184 | 0.025 |
| (c) Modelo nativo ENDES (2022 → 2024), con altitud, región, riqueza, IMC, embarazo, tabaco, diabetes | 27464 | | 0.573 | 0.303 | 0.181 | 0.024 |

**Conclusión:** el modelo entrenado en EE. UU. (AUC 0.737 allí) rinde como el azar en mujeres peruanas. No es un problema de calibración:
recalibrar deja la discriminación en 0.50. Ni siquiera un modelo nativo con variables peruanas supera 0.57, y además el ajuste de
hemoglobina por altitud elimina la señal de altitud por construcción. La anemia en Perú depende de factores que la encuesta no captura
(ingesta de hierro hemo, parasitosis, menstruación, embarazos previos, suplementación reciente).

**Decisión aplicada:** `target_anemia` excluido de `lab_risk_estimates` (`EXCLUDED_TARGETS` en `condition_lab_inference.py`). El producto debe
**sugerir un hemograma**, no estimar anemia. Los demás targets (vitamina D, glucosa, lípidos, ALT) siguen sin validación peruana porque ENDES no
los mide; se mantienen con la nota de población de EE. UU.

Artefactos: `data/reports/condition_model/endes_anemia_validation.{json,csv}`, `models/runtime/anemia_endes_model.pkl` (solo evidencia),
sección `peru_validation` en `condition_lab_model_card.json`.
