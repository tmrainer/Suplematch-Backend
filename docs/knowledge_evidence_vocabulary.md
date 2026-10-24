# Vocabulario de evidencia de la base de conocimiento

Fecha: 2026-10-22. Fase 2 del plan de fiabilidad.

## Problema

`condition_component_links.evidence_strength` y `component_claim_evidence.evidence_level` mezclaban
nivel de evidencia con tipo de fuente (`official_nutrient_role`, `high_with_lab`, `limited_contextual`…),
diez valores sin definición. El ranker asigna pesos arbitrarios a esos strings.

## Vocabulario canónico (`evidence_grade`)

Un solo eje, inspirado en GRADE. Se añadió como columna nueva en ambas tablas; las columnas antiguas se
conservan para no romper el runtime hasta que el ranker migre.

| evidence_grade | Significado | Mapeo desde valores antiguos |
|---|---|---|
| `high` | Reemplazo de deficiencia documentada o efecto con ensayos consistentes citados por la fuente oficial | `high`, `high_with_lab` |
| `moderate` | Evidencia consistente pero indirecta o con heterogeneidad | `moderate` |
| `low` | Evidencia limitada o solo observacional | `low_moderate`, `low` |
| `very_low` | Asociación plausible/contextual sin evidencia de efecto clínico | `contextual`, `limited_contextual` |
| `expert_opinion` | Declaración de rol fisiológico o seguridad de una ficha oficial, no evidencia de intervención | `official_nutrient_role`, `official_nutrient_context`, `official_contextual`, `safety_context` |

## Reglas

- Toda fila nueva debe traer `evidence_grade` del vocabulario; `tests/unit/test_data_contracts.py` lo exige.
- `condition_rules.csv` ahora tiene `source_ids` (heredados de la condición) y `weight_basis=expert_heuristic`:
  los pesos no provienen de la literatura, son heurísticas del equipo. Hasta que se calibren con datos reales,
  la API los expone como índice basado en reglas (`score_basis`), no como probabilidad clínica.
- Duplicados (condición, componente) fusionados: se conservó la fila de versión más reciente, con la mayor
  `evidence_strength` del grupo y la unión de `source_ids`. El rationale indica la fusión.
- Pendiente: que `modelo2_inference.EVIDENCE_WEIGHTS` lea `evidence_grade` y no `evidence_strength`, y que
  los pesos se documenten aquí con su justificación.

## Identidad de componentes (`component_id`)

Fecha: 2026-10-22. Fase 2, ítem "`component_id` canónico en todas las tablas de `data/knowledge`".

- `data/knowledge/component_aliases.csv` es la **única fuente de identidad** de componentes. Una fila por
  componente: `component_id` (`COMP_` + 12 hex, el mismo id que usa `data/catalog/approved_catalog.csv` y el
  grafo del Modelo 2), `canonical_name_es` (forma ortográfica única: "Ácido fólico", nunca "Acido folico"),
  `canonical_name_en` y `aliases` separados por `|` (nombres EN del master, variantes ortográficas, marcas de
  familia como "Fish Oil" o "whey protein").
- Las cinco tablas de componentes (`condition_component_links`, `component_evidence_profiles`,
  `component_claim_evidence`, `component_interaction_rules`, `component_life_stage_guidance`) llevan la columna
  `component_id` y su `component` debe ser exactamente el `canonical_name_es` de ese id.
  `tests/unit/test_data_contracts.py` lo exige (id existente, nombre igual al canónico, ids únicos, todo
  componente de links con perfil de evidencia).
- `app/ml/runtime/modelo2_inference.py` une las tablas por `component_id`. Si una fila llega sin id, resuelve por
  nombre normalizado contra `component_aliases.csv` y emite un `logging.warning`; una fila sin id y sin alias se
  ignora en los joins. `COMPONENT_ALIASES`, `COMPONENT_ID_OVERRIDES` y `COMPONENT_DISPLAY_BY_ID` siguen
  exportándose (los usan `scripts/catalog/generar_product_components.py` y
  `scripts/catalog/auditar_cobertura_componentes.py`) pero se construyen desde el CSV al importar: no editarlos a
  mano, editar el CSV.
- Procedencia de los 46 ids: todos existían ya en `COMPONENT_ID_OVERRIDES` (y en
  `data/training/supplement_model/Component_Master_Clean.csv`); ninguno se generó. Regla para altas futuras:
  reutilizar el `component_id` del master por `canonical_name` (EN); si el componente no existe en el master,
  generar `COMP_` + 12 hex (mayúsculas) de `sha1(canonical_name_es normalizado)` y anotar "sin fuente en master"
  en `aliases`/doc hasta que se incorpore al master.
- Cambios de datos en esta migración: ortografía unificada en 16 filas ("Acido folico" → "Ácido fólico",
  "Acido pantotenico" → "Ácido pantoténico", "Proteina" → "Proteína", "Luteina" → "Luteína") y nuevo perfil de
  evidencia para Manganeso (`nih_ods_manganese_hp`), con lo que `KNOWN_LINK_COMPONENTS_WITHOUT_PROFILE` baja a 0.
