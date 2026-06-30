# Modelo 2: Ranker de Componentes

Objetivo:

Convertir condiciones o riesgos probables en componentes recomendables. El
Modelo 2 no recomienda productos comerciales directamente.

Flujo:

```txt
Modelo 1
encuesta + perfil + labs
-> probabilidades por condicion

Modelo 2 v2
condiciones + probabilidades + grafo + evidencia estructurada + safety
-> componentes rankeados + decision comercial

Catalogo comercial
component_id
-> productos reales por farmacia, precio, stock y registro sanitario
```

## Fuentes

El ranker usa:

- `data/knowledge/condition_component_links.csv`
- `data/knowledge/component_evidence_profiles.csv`
- `models/runtime/modelo2_artifacts.pkl`
- `data/catalog/approved_catalog.csv` como referencia de IDs comerciales trazables

La tabla `condition_component_links.csv` define:

```txt
condition_code
component
evidence_strength
evidence_type
recommendation_role
requires_lab
risk_level
source_quality
missing_data_penalty
source_ids
rationale
```

Ejemplo:

```txt
DEFICIT_VIT_D -> Vitamina D -> high -> primary -> lab preferred
DEFICIT_B12 -> Vitamina B12 -> high -> primary -> lab preferred
DEFICIT_HIERRO -> Hierro -> high -> primary_with_lab -> lab required
RIESGO_OMEGA3_BAJO -> Omega 3 -> contextual -> supportive -> lab no
```

## Scoring

Cada componente directo recibe:

```txt
score = probabilidad_condicion * evidence_score
```

`evidence_score` combina:

```txt
evidence_strength
recommendation_role
source_quality
requires_lab
risk_level
missing_data_penalty
```

Esto evita tratar igual una deficiencia directa, un apoyo contextual y un
componente que requiere laboratorio.

Ejemplo:

```txt
DEFICIT_HIERRO -> Hierro
requires_lab: required
risk_level: moderate_high
missing_data_penalty: 0.35
```

Aunque la probabilidad sea alta, el componente queda penalizado si falta dato de
laboratorio suficiente. La capa de safety puede luego bloquear productos
comerciales si el perfil es critico.

Si una condicion no existe en la tabla oficial, el sistema usa las semillas del
artefacto `modelo2_artifacts.pkl` como fallback.

Los candidatos GNN se mantienen solo como soporte complementario y con menor
peso. No deben desplazar un componente directo con evidencia estructurada.

## Salida

Cada recomendacion de componente puede incluir:

```txt
component_id
name
condition
score
condition_probability
evidence_strength
evidence_type
evidence_weight
evidence_score
evidence_factors
recommendation_role
requires_lab
risk_level
source_quality
missing_data_penalty
source_ids
rationale
model2_ranker
model2_stage
graph_similarity
ranking_reason
recommendation_source
commercial_eligible
commercial_recommendation_blocked
commercial_block_reason
adult_upper_limit
upper_limit_unit
upper_limit_note
dose_guidance
age_sex_note
pregnancy_lactation_note
contraindications
interaction_notes
component_safety_level
component_profile_source_ids
```

Luego `ProductCatalogService` busca productos comerciales equivalentes por
`component_id`.

`model2_stage` indica de dónde salió el componente:

- `evidence_validated`: relación oficial condición-componente.
- `artifact_seed_fallback`: semilla del artefacto anterior cuando no hay fila
  oficial suficiente.
- `graph_support`: candidato complementario por similitud/relación del grafo.
- `graph_relationship`: relación de sinergia del grafo.
- `graph_safety_alert`: alerta de combinación riesgosa del grafo.

`commercial_eligible=false` significa que el componente puede mostrarse como
explicación, pero no debe convertirse a tarjeta de producto comercial para ese
perfil.

## Regla de Producto

El Modelo 2 no debe devolver:

```txt
Compra Producto X de Farmacia Y
```

Debe devolver:

```txt
Para DEFICIT_VIT_D, priorizar componente Vitamina D.
```

La seleccion de producto queda en catalogo/reranking:

- registro sanitario
- precio
- stock
- farmacia
- reviews
- restricciones
- safety

## Perfiles por Componente

`component_evidence_profiles.csv` agrega informacion transversal al componente:

- contraindicaciones o contextos sensibles
- limite superior adulto cuando la fuente lo permite
- nota de dosis no prescriptiva
- consideraciones por edad/sexo
- embarazo/lactancia
- interacciones relevantes
- fuentes especificas por afirmacion

Estas notas no son una receta de dosis. Se usan para explicar, penalizar o
pedir revision profesional antes de convertir un componente en producto
comercial.

Tablas adicionales:

- `component_life_stage_guidance.csv`: referencias por edad/sexo/embarazo o
  lactancia cuando existen en fuentes oficiales.
- `component_interaction_rules.csv`: reglas de interacción o contexto sensible.
- `component_claim_evidence.csv`: afirmaciones mostrables y su nivel de
  evidencia/fuente.

Cobertura actual:

- 111 relaciones condicion-componente.
- 46 componentes recomendables resueltos desde evidencia estructurada.
- 45 perfiles de componente.
- 75 reglas o notas por etapa de vida.
- 48 reglas de interacción/contexto sensible.
- 56 claims explicables.
- 42 componentes tienen 4+ productos comerciales aprobados.
- 1 componente queda débil en catálogo aprobado: `Cobre`.
- 3 componentes no tienen producto aprobado actual: `Ashwagandha`,
  `L-teanina` y `Valeriana`.

Ampliación 2026-06-24:

- Se agregaron relaciones contextuales para `Riboflavina`, `Tiamina`,
  `Niacina`, `Ácido pantoténico` y `Manganeso`.
- Se agregaron subobjetivos contextuales no diagnósticos:
  `SALUD_VISUAL`, `SALUD_DIGESTIVA`, `FATIGA_NUTRICIONAL`,
  `HIDRATACION_ELECTROLITOS`, `SALUD_CARDIOVASCULAR_CONTEXTUAL` y
  `SALUD_COGNITIVA`.
- Se agregaron componentes de soporte para esos subobjetivos: `Luteína`,
  `Zeaxantina`, `Colina`, `Sodio`, `Taurina`, `Inositol`,
  `Bacillus coagulans` y `Bifidobacterium longum`.
- Todas entran como soporte secundario, no como reemplazo de componentes
  primarios como hierro, B12, calcio o vitamina D.
- El objetivo es mejorar cobertura explicable y rotación comercial en casos de
  complejo B/metabolismo energético, salud ósea, visión, digestión,
  hidratación/electrolitos, cardiovascular contextual y cognición contextual,
  manteniendo penalización por datos faltantes.

Los nombres de componentes que llegan desde el grafo o el catálogo también se
resuelven por alias. Por ejemplo, `Vitamin C (ascorbic acid)` puede enriquecerse
con el perfil de `Vitamina C` aunque el nodo no venga con el ID preferido.

Correccion de catalogo:

- `Creatina` usa el componente `COMP_7B47CDB437E8`.
- Los productos con `CREATINA MONOHIDRATO`, `CREATINE MONOHYDRATE`,
  `CLORHIDRATO DE CREATINA` y variantes relacionadas ya no apuntan a
  `COMP_67B16EEFC42F` porque ese ID corresponde a vitamina C.
- El parser de composicion soporta cantidades con separadores mixtos, por
  ejemplo `3,250.000000 mg`, para evitar ingredientes deformados como
  `CREATINA MONOHIDRATO 3`.

Estas tablas no implementan dosis personalizadas clínicas. El backend solo
devuelve referencias orientativas y notas de seguridad para que el frontend o
admin expliquen la recomendación sin prescribir.

## Contexto de Seguridad

Las filas con `recommendation_role=safety_context` no son recomendaciones de
compra. Sirven para que el sistema explique una bandera sensible, por ejemplo:

```txt
SAFETY_RENAL -> Potasio
SAFETY_HEPATICA -> Vitamina A / Niacina
SAFETY_TIROIDEA -> Yodo / Selenio
```

El servicio de recomendaciones no adjunta productos comerciales a esos items y
marca:

```txt
commercial_recommendation_blocked=true
commercial_block_reason=Componente mostrado solo como contexto de seguridad...
```

La UI debe mostrarlos como advertencia o contexto, no como tarjeta comprable.

## Prioridades Blandas de Bienestar

Las condiciones blandas no son diagnósticos ni deficiencias. Modelo 2 puede
usarlas para explicar contexto y ordenar componentes, pero no deben activar
productos comerciales por sí solas.

Condiciones tratadas como contexto no comercial:

```txt
BAJA_INMUNIDAD
ESTRES_SUENO
RENDIMIENTO_DEPORTIVO
RIESGO_CABELLO_PIEL_UNAS
SALUD_VISUAL
SALUD_DIGESTIVA
FATIGA_NUTRICIONAL
HIDRATACION_ELECTROLITOS
SALUD_CARDIOVASCULAR_CONTEXTUAL
SALUD_COGNITIVA
```

Regla aplicada:

- Si un componente nace solo de una prioridad blanda, queda con
  `commercial_eligible=false`.
- Si el mismo componente también está respaldado por una condición nutricional
  fuerte, el dedupe prefiere la relación nutricional y puede adjuntar producto.
- Los candidatos del grafo quedan no comerciales cuando el perfil solo tiene
  prioridades blandas o safety, sin condición nutricional de respaldo.

Ejemplo:

```txt
ESTRES_SUENO -> Magnesio
Resultado: contexto no comercial.

DEFICIT_MAGNESIO + ESTRES_SUENO -> Magnesio
Resultado: recomendación comercializable por DEFICIT_MAGNESIO, no por estrés/sueño.
```

El copy esperado para usuario debe decir "prioridad de bienestar", "señal
blanda" o "contexto"; no "déficit" ni "condición detectada".

La misma regla aplica si una recomendación trae una interacción de severidad
`high` con acción `block`, `block_commercial`, `block_or_warn` o
`warn_or_block`. En ese caso se mantiene la explicación del componente, pero
`products` queda vacío.

Los packs se construyen solo con componentes comercialmente elegibles. Quedan
fuera:

- `recommendation_role=safety_context`
- `tipo=contexto_seguridad`
- `commercial_eligible=false`
- componentes con interacción `high` bloqueante

## Evaluación del Modelo 2

El backend incluye un benchmark operativo de Modelo 2:

```bash
python3 scripts/validate_model2_quality.py
```

El script evalúa casos fijos de producto:

- vitamina D baja
- B12 en dieta vegana
- hierro con necesidad de laboratorio
- folato con contexto B12
- vitamina C baja
- proteína insuficiente
- omega 3 bajo
- alergia a pescado/mariscos bloqueando DHA comercial
- perfil renal deportivo bloqueando creatina
- salud ósea con anticoagulantes bloqueando vitamina K
- riesgo metabólico/glucosa como contexto no comercial
- dislipidemia como contexto no comercial
- sueño/estrés
- sueño/estrés con déficit real de magnesio
- cabello/piel/uñas
- cabello/piel/uñas con déficit real de zinc
- baja inmunidad como bienestar no comercial
- rendimiento deportivo como bienestar no comercial
- safety renal bloqueando electrolitos/creatina
- safety hepática bloqueando componentes sensibles
- contexto tiroideo no comercial
- salud visual como contexto no comercial
- salud digestiva como contexto no comercial
- fatiga nutricional como contexto no comercial
- hidratación/electrolitos como contexto no comercial
- salud cardiovascular contextual como contexto no comercial
- salud cognitiva como contexto no comercial

Métricas reportadas:

- `top3_accuracy`: si aparece al menos un componente esperado en top 3.
- `block_accuracy`: si los componentes que deben bloquearse quedan sin producto
  comercial.
- `risk_avoidance_accuracy`: si componentes riesgosos quedan ausentes,
  bloqueados o sin producto comercial.
- `commercial_coverage`: proporción de componentes elegibles que logran producto
  comercial del catálogo. Solo se calcula sobre casos donde sí corresponde
  comercializar.
- `pharmacy_diversity`: diversidad de farmacias en productos seleccionados para
  packs.

Resultado de referencia actual:

```txt
cases: 27
top3_accuracy: 1.0000
block_accuracy: 1.0000
risk_avoidance_accuracy: 1.0000
commercial_coverage_cases: 11
commercial_coverage: 0.9575
pharmacy_diversity: 0.3951
```

Salida:

```txt
data/reports/supplement_model/01_model2_case_details.csv
data/reports/supplement_model/01_model2_summary.json
```

Ejemplo de uso:

```txt
Usuario mujer, 34 años, riesgo DEFICIT_HIERRO:
Hierro -> referencia oficial adulta femenina -> RDA 18 mg/day
Hierro -> requiere laboratorio -> no empujar compra directa sin ferritina/hemoglobina
```

```txt
Usuario con anticoagulantes y RIESGO_SALUD_OSEA:
Vitamina K -> interacción high -> mostrar alerta y evitar CTA comercial directo
```
