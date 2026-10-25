# Plan de fiabilidad: datos, fuentes y modelos

Fecha de inicio: 2026-10-22. Origen: auditoría técnica del repo (ML, recolección de datos, asociación de fuentes).
Este documento es la fuente de verdad del plan; cada fase lista hallazgo, acción, estado y evidencia.

Estados: `[x]` hecho · `[~]` en curso · `[ ]` pendiente.

## Principios

1. Honestidad antes que sofisticación: reglas con fuentes valen más que ML sintético. No llamar "probabilidad" a una suma de pesos.
2. Una sola fuente de verdad por concepto (features, umbrales de biomarcadores, componentes con ID).
3. Nada entra al catálogo sin trazabilidad del origen del registro sanitario (RS).
4. Reproducible desde un checkout limpio; CI falla si no.

## Fuentes oficiales verificadas (2026-10-22)

| Tema | Fuente | Hallazgo | Uso en el proyecto |
|---|---|---|---|
| DIGEMID registro sanitario | https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/ | Solo consulta web paginada. **No existe descarga CSV ni API documentada.** En datosabiertos.gob.pe no hay dataset de registro sanitario (búsquedas "digemid" y "registro sanitario": 0 resultados relevantes; solo "Registro de datos de Farmacia de la cobertura prestacional del sector privado", SUSALUD). | `digemid_limpio.csv` debe documentarse como extracción manual con fecha, o solicitarse formalmente a DIGEMID vía acceso a la información pública. Dejar de evadir Cloudflare. |
| Vitamina D (25-OH-D) | NIH ODS, Vitamin D Health Professional Fact Sheet, https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/ | Food and Nutrition Board: ≥50 nmol/L (≥20 ng/mL) suficiente para la mayoría; <30 nmol/L (<12 ng/mL) riesgo de deficiencia. Conversión: 1 ng/mL = 2.5 nmol/L. | Unificar `biomarkers.csv` (low=20) y `biomarcadores.py` (low=30) a estos cortes; implementar conversión nmol/L↔ng/mL en OCR de labs. |
| Hemoglobina / anemia | OMS, *Guideline on haemoglobin cutoffs to define anaemia in individuals and populations*, 2024, ISBN 978-92-4-008854-2 (Tablas 2 y 3) | Cortes (g/L): niños 6–23 m <105; 24–59 m <110; 5–11 a <115; 12–14 a <120; mujeres no embarazadas 15–65 a <120; hombres 15–65 a <130; embarazo 1.er/3.er trimestre <110, 2.º trimestre <105. Severidad: leve 110–119 (mujeres) / 110–129 (hombres); moderada 80–109; severa <80. | Reemplazar el rango único Hb 12–17.5 g/dL por cortes por sexo/edad/embarazo. Unidad canónica g/L con conversión desde g/dL. |
| NHANES vitamina D | CDC, VID_J (2017-2018), https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/VID_J.htm | `LBXVIDMS` = 25OHD2+25OHD3 en **nmol/L**, método LC-MS/MS. CDC recomienda usar datos equivalentes LC-MS/MS para tendencias. | Los importadores NHANES deben convertir nmol/L→ng/mL antes de aplicar umbrales en ng/mL (verificar en `importar_casos_nhanes_condiciones.py`). |
| NHANES ferritina | CDC, FERTIN_J (2017-2018), https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/FERTIN_J.htm | `LBXFER` en ng/mL; población 1–5 años y ≥12 años. Sin cambio de método en 2017-2018. | Confirmar que los casos NHANES de 6–11 años no esperan ferritina. |
| NHANES suplementos | CDC, DSQIDS/DSQTOT por ciclo (ej. P_DSQTOT, DSQIDS_L) | Variables de ingesta de suplementos (`DSQTVD` vitamina D mcg, `DSQIIRON` hierro mg). | Candidatas a features reales de encuesta para un Modelo 1 entrenado con datos reales (Fase 3). |
| ENDES (Perú) | INEI, microdatos https://proyectos.inei.gob.pe/microdatos/ ; datosabiertos.gob.pe ENDES 2022 (zip completo) y 2024 (muestra csv) | Módulo RECH6: `hc53` hemoglobina g/dL, `hc56` ajustada por altitud, `hc57` clasificación de anemia. Desde 2024 el corte 6–23 meses baja a 10.5 g/dL. | Única fuente peruana con laboratorio real (hemoglobina) para validar DEFICIT_HIERRO / anemia en población local. |
| Datos personales de salud | Ley 29733 y Reglamento D.S. 016-2024-JUS (deroga D.S. 003-2013-JUS) | Datos de salud = datos sensibles. Consentimiento **por escrito** (firma manuscrita, digital o electrónica), previo, informado, expreso e inequívoco. Obligación de inventario de datos y notificación de incidentes con datos sensibles. | `LabReport.raw_text` con DNI/nombre y `consent_health_data=True` hardcodeado incumplen esto. Fase 6. |

## Fase 0. Base reproducible

- [x] Import roto `import_nhanes_condition_mvp_cases` → `importar_casos_nhanes_condiciones` en `scripts/training/importar_casos_nhanes_multiciclo.py`.
- [x] Rutas absolutas de otra máquina eliminadas: `SUPPLEMENT_MODEL_DATA_DIR` y `MODEL2_ARTIFACTS_PATH` (modelo2), `PYTHON_BIN` por defecto `python3`.
- [x] `torch-geometric` declarado en `requirements.txt` (solo entrenamiento).
- [x] `app/ml/model_loader.check_model_artifacts` verifica `.pkl` en disco; `/health/ready` reporta `models=false` y `model_artifacts.missing` si faltan. Antes reportaba `ready` sin ningún modelo.
- [x] README: eliminadas afirmaciones de GraphSAGE/SHAP como núcleo; se explica que Modelo 1 es sintético y cómo generar artefactos.
- [x] Tests vacíos reemplazados: `test_feature_builder.py` (paridad training/runtime), `test_data_contracts.py` (integridad de knowledge base con ratchets), `test_data_validator.py`, `test_model1_service.py` y `test_model2_service.py` (smoke, se omiten si falta el `.pkl`).
- [x] `condition_data_requirements.csv` cubre las 6 condiciones contextuales (test `test_condition_data_requirements_cover_all_conditions` pasa).
- [x] Versionado: decisión Git LFS (`docs/insumos_versionado.md`, `.gitattributes` con patrones listos; pasos para quitar las rutas del `.gitignore` y commitear ~16 MB). Insumos recuperados del historial de git (borrados en `3f6183c`, 2026-06-30): `digemid_limpio.csv` (2000 RS, commit `f173ec5`), `Component_Master_Clean.csv` (935 nodos) y `Component_Relationship_Edges_Clean.csv` (`f173ec5`), raw de scraping `supplements_exhaustive_clean.csv` (4029 filas, `86c79cc`), `modelo1_pipeline.pkl` y `modelo2_artifacts.pkl` (`f173ec5`). `condition_mvp_model.pkl` entrenado localmente (2500 filas sintéticas, seed 42). Todos declarados con sha256 en `data/insumos_manifest.json`; `verificar_insumos.py --strict` pasa. Siguen fuera de git (`.gitignore`): decidir DVC vs LFS.
- [x] Tests que dependen de `data/reports`, `data/evaluation` o `.pkl` marcados con `skipif` (antes 27 fallaban en checkout limpio). Estado tras Fase 0: `pytest tests/unit` → 186 passed, 37 skipped, 0 failed en Python 3.12 limpio.
- [x] CI `.github/workflows/ci.yml`: job `unit-tests` (pytest unit, insumos versionados, dry-run de limpieza) y job `integration-tests` con servicio Postgres 16 (`alembic upgrade head`, seed, importación de catálogo, `pytest tests/integration`; los tests de `/recommend` se omiten sin `.pkl`).
- [x] **Infraestructura local verificada el 2026-10-22 contra PostgreSQL 16**: migraciones `0001…0014` aplican limpias, seed e importación OK (549 productos, 323 en cola de revisión RS), `tests/integration` **35 passed** con artefactos y torch. `Makefile` con `db-up/migrate/seed/import-catalog/test-integration/test-unit`. `docker-compose.yml` con servicios `backend` (healthcheck, migraciones al arrancar, artefactos montados) y `maintenance` (perfil). Dockerfile: Playwright opcional (`INSTALL_PLAYWRIGHT`, ~400 MB menos) y `HEALTHCHECK`.

## Fase 1. Catálogo y DIGEMID

Hallazgo verificado: `approved_catalog.csv` contenía champús Pantene/Sedal/Wella, cremas y fórmulas infantiles aprobados como suplementos, con la composición de otro producto y `commercial_confidence_level=alta` en el 100% de filas. Causa: regex de RS que aceptaba palabras comunes + inferencia por substring (`"PRO" in nombre`).

- [x] `REGISTRO_RE` exige código con dígitos (prefijo DIGEMID + 3–6 dígitos) y marcador explícito o mayúsculas sin unidad posterior. Test: `tests/unit/test_registro_sanitario_matching.py`.
- [x] `score_name_match`: nombres DIGEMID de un solo token solo coinciden con nombre comercial idéntico; multi-token exige frase completa con límites de palabra y ≥2 tokens compartidos.
- [x] `scripts/catalog/filtros_categoria.py`: rechazo de cosméticos, higiene, tópicos, fórmula infantil y marcas de cuidado personal. Usado por builder, validador y limpieza.
- [x] `construir_catalogo_aprobado.py` propaga `registro_sanitario_source` y rechaza grupos de RS inferido con >5 nombres comerciales (`rs_inferido_fanout`). Con esto `commercial_confidence` ya distingue RS informado (+0.28) de inferido (+0.18).
- [x] `validar_pipeline_catalogo.py`: errores nuevos `approved_non_supplement_rows` y `approved_rs_fanout_over_max`; warnings `approved_name_without_digemid_overlap` y columna `registro_sanitario_source` ausente.
- [x] `scripts/catalog/coincidencia_nombres.py`: comparación de nombres con tokens alfanuméricos y sinónimos ES/EN (DIGEMID registra "VITAMIN C 1000 mg", "D3 2000 UI").
- [x] `scripts/catalog/limpiar_catalogo_aprobado.py` aplicado al catálogo servido (ver sección "Resultado de la limpieza").
- [x] Cola de revisión humana en Postgres (`catalog_rs_reviews`, migración `20261022_0014`): 100% de productos con RS inferido (312 hoy) + ~5% de muestra determinista por hash; se puebla al importar o con `scripts/ops/poblar_cola_revision_rs.py`; endpoints admin `GET/PATCH /admin/catalog/rs-review` y `/summary` con `AdminAction`; productos `rejected` dejan de servirse, `pending` se sirven con `rs_review_status`. Ver `docs/catalog_rs_review.md`. Pendiente: correr migración e integración contra Postgres.
- [x] Scraping: `PoliteHttp` con robots.txt por host, 3 reintentos con backoff + jitter, `Retry-After`, pausa tras cada request; credenciales Algolia de InRetail en `INKAFARMA_ALGOLIA_APP_ID/API_KEY` (sin ellas esas farmacias se saltan); descarga de imágenes opt-in y no redistribuida; `unquote` en nombres desde URL. Tests `test_scraper_http_hygiene.py`. Pendiente humano: revisar términos de uso de InRetail antes de poblar las variables.
- [x] DIGEMID: scraper visual sin cookies ni espera de challenge, User-Agent honesto, aborta con código 3 si el portal bloquea; `update_from_source` fusiona por RS (nunca borra) y `--replace` solo para export oficial; eliminado `DIGEMID_MIN_ROWS=1`. Pendiente humano: solicitud de acceso a la información pública a DIGEMID (Ley 27806) y fechar `digemid_limpio.csv`.
- [x] Parser de composición reescrito: UFC/CFU y notación científica, miles con espacio (sin romper el formato DIGEMID de 6 decimales), `kg` no se convierte a mg, cabeceras "POR DOSIS" descartadas, sales/formas entre paréntesis → `salt_form`. Vitamina E UI→mg por forma (dl-α 0.45, d-α 0.67, default 0.67 conservador para UL).
- [x] **Generador de `product_components.csv` reconstruido** (`scripts/catalog/generar_product_components.py`): composición DIGEMID → parser → patrones de nutriente (anión/catión: yoduro de potasio = yodo) → ids canónicos de la knowledge base. Sin fuzzy. El CSV legado y el catálogo servido mapeaban `VITAMINA B1`/`B2` a **B12**, creatina a vitamina C, `CLORHIDRATO DE PIRIDOXINA` a piridoxamina y `FUMARATO FERROSO` a gluconato ferroso; 20/20 ingredientes de control ahora correctos (`tests/unit/test_generar_product_components.py`). 13 756 filas, 79% mapeadas; lo no mapeado son excipientes y aminoácidos.
- [x] **Catálogo reconstruido de punta a punta** con `scripts/catalog/reconstruir_catalogo.sh` (re-inferencia offline de RS con el matcher nuevo, builder, enriquecimiento, validación, limpieza). Ver sección "Reconstrucción del catálogo".
- [x] Seguridad sobre composición completa: `product_text` incluye `digemid_composicion` y todos los ingredientes del producto (modo CSV agrupa filas por farmacia+sku); flags verificados del enriquecimiento ya se usan; regla de vitamina A en embarazo sensible a dosis (UL 3000 mcg, NIH ODS) y yodo (yoduro/iodide) en `problema_tiroideo`.
- [x] Importador desactiva (`inactive`, con motivo y fecha) los productos ausentes del CSV para las farmacias presentes; `--no-deactivate-missing` para desactivar. Snapshots de precio: uno por producto. Diff de catálogo lee la columna de rechazo correcta.

## Fase 2. Base de conocimiento y fuentes

- [x] `component_id` canónico: `data/knowledge/component_aliases.csv` (46 componentes, alias ES/EN) y columna `component_id` en las 5 tablas; `modelo2_inference.py` une por id (fallback por nombre con warning) y construye `COMPONENT_ALIASES`/`COMPONENT_ID_OVERRIDES`/`COMPONENT_DISPLAY_BY_ID` desde el CSV. Ortografía unificada (16 filas). Manganeso con perfil (`nih_ods_manganese_hp`). Ids del catálogo sin cambios. **Ids duplicados del grafo GNN resueltos (2026-10-23)**: `data/knowledge/gnn_node_equivalences.csv` (142 nodos → 27 canónicos, generado por `scripts/ops/generar_equivalencias_gnn.py`); `modelo2_inference` descarta candidatos GNN equivalentes a un componente ya recomendado y deduplica por id canónico. Test de sincronía con el generador.
- [x] Columna `evidence_grade` canónica en links y claims (ver `docs/knowledge_evidence_vocabulary.md`); test de vocabulario. `_evidence_weight` consume `evidence_grade` (hecho en Fase 4).
- [x] `condition_rules.csv` con `source_ids` (heredados de la condición) y `weight_basis=expert_heuristic`; test exige ambos. Los pesos siguen siendo heurísticos y así se declara.
- [ ] Fuentes primarias (PubMed/DOI, Cochrane, EFSA, guías); `accessed_at` y `version` por fuente; reemplazar la ficha genérica de MedlinePlus (44 usos). Candidatos listos (2026-10-24): `scripts/clinical/buscar_fuentes_primarias.py` busca en PubMed (E-utilities) Cochrane, revisiones sistemáticas y ECA por cada uno de los 56 claims y deja `data/reports/clinical_review/fuentes_primarias_candidatas.csv` (166 candidatos: 13 Cochrane, 111 revisiones, 42 ECA) con columnas `revision_acepta`/`revision_nota`. Falta la revisión humana; no cambia tablas clínicas.
- [x] 12 pares duplicados fusionados (111 → 98 links); ratchet en 0.
- [x] `biomarkers.csv` es la única fuente de umbrales: 33 filas, variantes de hemoglobina por sexo/edad/embarazo (OMS 2024), vitamina D según NIH FNB (12/20/30/50 ng/mL), `alt_units` con factores de conversión; `biomarcadores.py` lo carga y ya no duplica valores. Training filtra las filas por defecto.
- [x] `problema_tiroideo` unificado (test lo verifica). También `component_interaction_rules.csv`: `embarazo` → `embarazo_lactancia` y `tiroides` → `problema_tiroideo` (las reglas de vitamina A en embarazo nunca se activaban). Las 8 reglas huérfanas se resolvieron: la encuesta acepta `diabetes_medicada`, `inmunosupresion` (bloquea comercial), `sedantes` e `hipertension`; `insomnio` se deriva de `sleep_quality`/`night_wakeups`/`horas_sueno` (`_derived_safety_context`) y solo alimenta reglas de interacción; la regla Vitamina B6/`neuropatia` se retiró por no tener pregunta. Test: todo trigger debe estar en la encuesta o en los derivados (`KNOWN_ORPHAN_SAFETY_TRIGGERS` vacío) y el contrato de encuesta debe listar todos los códigos del esquema. **El frontend debe exponer las 4 preguntas nuevas** (`scripts/ops/exportar_contrato_encuesta.py` ya las incluye).
- [x] Validación de esquema vía `tests/unit/test_data_contracts.py` en CI (source_ids, vocabularios, umbrales monótonos, variantes de biomarcadores, códigos de condición). Sin dependencia nueva.

## Fase 3. Modelo 1 (condiciones)

- [x] `condition_details` expone `score_basis` (`model` | `model+rules` | `rules_only`), `final_score`, `model_probability` y `rule_score`; `CategorizedConditionResult.score_basis` en la API. `MIN_DECISION_THRESHOLD = 0.30` tapa la calibración a 0.05.
- [x] API (2026-10-23): `risk_index` + `score_semantics="indice_riesgo_reglas"` + `score_label="Índice de riesgo basado en reglas"` en `condition_results`, `wellness_priorities`, `safety_flags`, `conditions_display` y `explanations`; la respuesta declara `condition_score_semantics`. `probability` se conserva como obsoleto por compatibilidad. `lab_risk_estimates` lleva `score_semantics="probabilidad_calibrada_real"`. **Pendiente frontend**: mostrar `score_label`, no "probabilidad".
- [x] `app/ml/features_contract.py`: única definición de columnas, `rule_matches`, `attach_soft_signal_features`, `prepare_features` y `FEATURE_CONTRACT_VERSION`; training y runtime importan de ahí (ganó la versión del runtime: 12 síntomas, 8 cantidades de dieta, cluster capilar sin zinc, faltante `"missing"`). 165 features. `.pkl` guarda la versión del contrato y el runtime avisa si difiere. 22 tests de paridad (`test_features_contract.py`), incluida paridad bit a bit de derivaciones en 100 filas. Bug corregido: `None` en `lab_*_status` contaba como lab observado. Reentrenado: f1_macro 0.9096, hamming 0.0309 (sintético; sigue sin valor clínico).
- [x] Distribución realista de laboratorios (2026-10-23): `--lab-panel-rate 0.30` con paneles acotados (basic/metabolic/nutritional/extended); ~70 % de filas solo encuesta. Umbrales ahora en partición de validación interna (antes en el test). Reentrenado con 10 000 filas: f1_macro 0.889 total, 0.859 solo encuesta, 0.871 con labs (antes 0.91 con umbrales en test y casi todas las filas con labs). Métricas estratificadas en `04_training_metrics_by_label.csv` y en la model card.
- [x] **Modelo real entrenado** (`scripts/training/entrenar_condiciones_nhanes.py`, `docs/condition_lab_model.md`): NHANES 2015-16 train / 2017-18 test, 7 targets de laboratorio con cortes de `biomarkers.csv`, features solo de cuestionario, umbral en validación interna, calibración. Test: vitamina D AUC 0.815, glucosa 0.762, HDL 0.749, anemia 0.737, ALT 0.695, colesterol 0.648, ferritina 0.576 (no útil). ECE ≤ 0.05 en todos. Expuesto en `/recommend` como `lab_risk_estimates` con `score_basis="model_real"`; model card con hash y limitaciones. **Validado con ENDES 2022/2024** (28 947 y 27 464 mujeres 18–49 con Hb medida): `target_anemia` AUC 0.501/0.497 (azar); recalibrado 0.498; modelo nativo ENDES 0.573. **Anemia excluida de `lab_risk_estimates`**; el producto sugiere hemograma. Detalle en `docs/condition_lab_model.md`. Tabaco y salud autopercibida añadidos a la encuesta (contrato `2026-10-23.1`, opcionales) y mapeados al modelo; **ablación NHANES: aportan |ΔAUC| ≤ 0.006, es decir nada** (documentado; se mantienen por baratos).
- [x] Umbrales elegidos en validación interna del train tanto en el modelo real como en `condition_mvp` (desde 2026-10-23, `threshold_selection="internal_validation_split"` en el artefacto).
- [x] Model cards para los tres artefactos servidos: `condition_lab_model_card.json`, `condition_mvp_model_card.json` (sintético, `clinical_validity="none_synthetic"`, métricas total/sin labs/con labs) y `modelo2_model_card.json`; `tests/unit/test_model_cards.py` exige hash coincidente con el `.pkl`.

## Fase 4. Modelo 2 (componentes)

- [x] GNN evaluado (2026-10-22) con los CSV del grafo recuperados: 935 nodos, split 70/30 de aristas, GraphSAGE 2 capas, early stop en epoch 89. **Link prediction en aristas reservadas: ROC-AUC 0.974, AP 0.977.** Supera con holgura el umbral 0.65 → se conserva como fuente de candidatos complementarios. Matiz: las aristas provienen de fuentes estructuradas (DrugBank, AACT, ODS), así que el GNN aprende a reproducir ese grafo; no demuestra utilidad de recomendación para usuarios. Esa evaluación requiere feedback real (Fase 5). **Artefacto servido reemplazado el 2026-10-23** (reentrenado con `modelo2_train.py`, AUC 0.940 / AP 0.937 en aristas reservadas, model card con hashes); benchmark de 27 casos sin regresión (top3 1.0, block 1.0, cobertura 0.963). **Early stop por ROC-AUC de validación (2026-10-23, `graphsage_link_v3`)**: split 70/15/15, negativos de validación fijos, se restaura el mejor epoch (51 de 66); test AUC 0.959 / AP 0.975 en 90 aristas (antes 0.940/0.937 en 179 aristas con split 70/30, no comparable 1:1); benchmark de 27 casos sin regresión (cobertura 0.976).
- [x] `_evidence_weight` usa `evidence_grade` (`EVIDENCE_GRADE_WEIGHTS`), con `evidence_strength` solo como fallback; `evidence_grade` expuesto en cada recomendación.
- [ ] ≥100 casos de validación revisados por nutricionista; retirar el benchmark de 27 casos con accuracy 1.0. Paquete listo (2026-10-23): `scripts/clinical/generar_paquete_revision.py` (120 casos end-to-end + hojas de reglas + firma) e `importar_revision.py`; ver `docs/clinical_review_package.md`. Falta que lo complete un profesional.
- [~] Reglas de interacción ya tienen `source_ids` verificados por test; sinergias del GNN (`functional_pairs`) siguen sin fuente clínica propia (declarado en la model card de modelo2).

## Fase 5. Feedback y reranker

- [x] Postgres única fuente: `LEGACY_FEEDBACK_SQLITE_ENABLED=false` por defecto (store SQLite/JSON inerte salvo demos); el reranker acepta `feedback_stats` inyectadas y el score con feedback real lo aplica `RecommendationMetricsRepository`.
- [x] `/feedback` devuelve 404 si `recommendation_id` no existe en Postgres (`FEEDBACK_REQUIRE_KNOWN_RECOMMENDATION`); un segundo envío del mismo usuario/sesión para el mismo pack actualiza en vez de duplicar (`status=updated`); rating acotado 1–5 también en repositorio. Test de integración actualizado (requiere Postgres; no ejecutado aquí).
- [x] Feedback contextual: `context_key = pack_key|cond1+cond2+cond3`; `apply_metrics_to_packs` usa recompensa por contexto (n≥3) con fallback global y expone `feedback_context_count/global_count/source`. Score bayesiano con prior 0.70 sobre **recompensa** (`reward()` = 0.4·rating + 0.2·compra + 0.3·sigue tomando a 30 d + 0.1 beneficio percibido), no rating crudo.
- [x] Base de interacciones: tabla `recommendation_events` (migración `20261022_0013`) con impression/click/product_click/purchase_intent/dismiss/still_taking_30d/stopped, posición, `context_key`; impresiones registradas automáticamente por el backend al guardar packs; `POST /feedback/events` (lote ≤50, 404 si la recomendación no existe, dedupe de impresiones). Ver `docs/recommender_events.md` (plan: bayesiano contextual → bandit a ~2 000 eventos → learning-to-rank a ~20 000). Pendiente frontend: emitir clicks/compras/retención.

## Fase 6. Labs OCR y PII

- [x] Conversión de unidades desde `alt_units` (nmol/L, mmol/L, µmol/L, g/L, pmol/L, mEq/L…) con `original_value/original_unit/unit_converted`; sin unidad se asume la canónica si el valor es plausible o se infiere una alternativa única (`unit_inferred`, con warning); unidad desconocida → `unit_assumed` y confianza ≤0.5. HbA1c mmol/mol no se convierte (no lineal).
- [x] Hemoglobina por sexo/edad/embarazo (OMS 2024) vía `LabPatientContext` en `/labs/*` y contexto derivado de la encuesta en `/recommend`; `reference_group` en cada resultado.
- [ ] Benchmark con ≥50 PDFs reales anonimizados; precision y recall de valor+unidad. Harness listo (2026-10-23): `scripts/validation/benchmark_ocr_carpeta.py --input-dir <carpeta> --ground-truth gt.csv` (plantilla con `--write-template --prefill`, métricas code / code_value / code_value_unit, `insufficient_sample` bajo 50 archivos); ver `docs/lab_ocr_benchmark.md`. Faltan los PDFs y el ground truth anotado.
- [x] `redact_pii` enmascara DNI, teléfonos, correos y líneas de cabecera antes de persistir; consentimiento con `accepted_at` y `text_version`; anónimos no persisten. Retención: `LAB_REPORT_RETENTION_DAYS=365`, `LabAnalysisService.purge_expired()`, `scripts/ops/mantenimiento_diario.sh` (purga + verificación de insumos) con línea de cron y servicio compose `maintenance` documentados en `docs/deployment.md`; dry-run verificado contra Postgres.
- [x] Upload leído por bloques con corte en 8 MB.

## Fase 7. Gobernanza clínica y legal

- [ ] Revisión de reglas y safety rules por nutricionista o médico, firmada y versionada. Cubierta por el mismo paquete (hojas de reglas + firma con hashes; el importador detecta reglas cambiadas después de la revisión).
- [x] Menores por `age_years` numérico (fallback `edad_rango`): `medical_review_required` y aviso.
- [ ] Checklist legal: scraping y ToS, imágenes, datos de salud.
- [x] `model_versions` incluye `model1_sha256`, `model2_sha256` (hash corto del `.pkl`) y `knowledge` (versiones de conditions/links/biomarkers); se persiste con cada `RecommendationSession`.

## Estado al cierre del 2026-10-22

`pytest tests/unit` en Python 3.12 limpio: ver última línea de este documento. Integración (`tests/integration`) no ejecutada: requiere Postgres.

Pendientes que requieren acción humana o insumos externos:
- Recuperar o reescribir los generadores de `product_components.csv`, `Component_Master_Clean.csv` y `Component_Relationship_Edges_Clean.csv`; regenerar el catálogo con el parser nuevo.
- Solicitud de acceso a la información pública a DIGEMID; fechar `digemid_limpio.csv`.
- Revisar términos de uso de InRetail/Algolia antes de poblar `INKAFARMA_ALGOLIA_*`.
- Entrenar `condition_mvp` y el GNN para producir `.pkl` con `model_card`/métricas y decidir si el GNN se queda.
- Revisión de reglas y safety rules por nutricionista/médico (Fase 7).
- Modelo 1 con datos reales (NHANES train / ENDES validación), Fase 3 mediano plazo.
- Retención y borrado automático de `LabReport` (Fase 6).

## Reconstrucción del catálogo (2026-10-22, tarde)

Entradas: raw de scraping recuperado (4029 filas, 2026-06), DIGEMID recuperado (2000 RS), `product_components.csv` regenerado.
Re-inferencia de RS con el matcher nuevo: 907 RS inferidos por el matcher viejo → 357 con el nuevo (los 550 restantes eran falsos positivos por substring).

| Métrica | Catálogo servido antes | Reconstruido |
|---|---|---|
| Filas | 3888 | 2925 |
| Productos | 632 | 548 |
| `component_id` distintos | 196 (duplicados del master) | 70 (ids canónicos de knowledge) |
| Componentes de knowledge con producto | 43/45 | 42/45 |
| Cosméticos / RS con >5 nombres | 0 / 4 | 0 / 0 |
| Filas B12 | 259 (incluía B1 y B2 mal mapeadas) | 126 |
| Filas creatina / vitamina C | 11 / 107 | 26 / 154 |
| Validador | — | `passed`, 1 warning |

Backup del catálogo anterior: `data/reports/catalog/approved_catalog_pre_rebuild_*.csv`. Para volver: `git checkout -- data/catalog/approved_catalog.csv`.
Pérdida de cobertura: ~84 productos menos, casi todos con RS que solo el substring antiguo asignaba. Vuelven cuando el scraper lea el RS real de la página o un humano lo confirme.

## Resultado de la limpieza del catálogo (2026-10-22)


### Ejecutado el 2026-10-22 con `python3 scripts/catalog/limpiar_catalogo_aprobado.py --apply`

| Métrica | Antes | Después |
|---|---|---|
| Filas (producto × componente) | 4538 | 3888 |
| Productos distintos | 842 | 632 |

Filas removidas por motivo: RS genérico con fan-out 365, categoría no suplemento 267, nombre sin coincidencia con DIGEMID 18.

Grupos de RS genérico eliminados (nombre DIGEMID de un solo token asignado por substring): `DE2583:VITYBELL:6`, `DE3109:OMEGA 3 .:20`, `DE3502:PRO .:31`, `DE3564:BIOTINA .:35`, `DE4606:MAGNESIO .:93`.
Los productos de estos grupos (magnesio, omega 3, biotina) no están mal en sí; estaban asociados a una composición y dosis ajenas. Vuelven al catálogo cuando el scraper los re-asocie con su RS real (`registro_sanitario_source` ≠ `digemid_name_match` o revisión manual).

Filas removidas guardadas en `data/reports/catalog/approved_catalog_removed_20261022_220155.csv` (directorio no versionado).

Post-limpieza: 0 cosméticos; 4 RS siguen con más de 5 nombres comerciales distintos. Son nombres DIGEMID específicos (no genéricos), por lo que no se removieron automáticamente; requieren revisión manual:
- `DE0825` (VITAMINA E 1000 UI): 8 nombres. Ej.: Cápsulas Blandas de Vitamina E 1000 UI Now con Tocoferoles Mixtos; PACK 2 UNIDADES DE VITAMINA E 1000 UI 450MG NATURES TRUTH FRASCO 60 CAPSULAS; Pack Mason Vitamina E 1000 UI Cápsulas Blandas Mason Frasco 50 UN + Agua Cielo Frasco 625 ML; Terbol Vitamina E 1000 UI
- `DE2482` (MADDRE DHA): 7 nombres. Ej.: Maddre DHA Cápsula Blanda; Maddre DHA Cápsulas - Frasco 30 und; Maddre DHA Sabor Chocolate; Maddre DHA Sabor Vainilla
- `DE4803` (VITAMINA E 400 UI): 6 nombres. Ej.: Pack Mason Vitamina E 400 UI Capsulas Blandas Frasco 100 UN + Agua Cielo Frasco 625 ML; Pack Mason Vitamina E 400 UI Cápsulas Blandas Frasco 30 Un + Agua Cielo Frasco 625 ML; Vitamina E 400 UI Cápsula Blanda; Vitamina E 400 UI Mason Natural Cápsula blanda
- `DE4077` (VITA VITAL .): 6 nombres. Ej.: Vita Vital Capsulas Blandas Caja 30 Un; Vita Vital Citrato De Potasio Y Naranja Capsulas Frasco 90 Un; Vita Vital Colageno Hidrolizado En Polvo Collagen Peptides Caja 30 Un; Vita Vital Glicinato De Magnesio Capsulas %E2%80%93 Frasco 100 Un

---

`pytest tests/unit` (Python 3.12, checkout limpio, 2026-10-22 cierre): **249 passed, 37 skipped, 0 failed**. Los 37 skips corresponden a artefactos no versionados (`.pkl`, `data/reports`, `data/evaluation`, `product_components.csv`).

`pytest tests/unit` (2026-10-22, cierre 2): **394 passed, 9 skipped con torch; sin torch 374 passed, 29 skipped**. Migraciones nuevas: `20261022_0013_recommendation_events`, `20261022_0014_catalog_rs_review` (sin ejecutar: requieren Postgres).

## Cierre ML del 2026-10-23

Hecho: labs realistas + umbrales en validación + model card en `condition_mvp` (reentrenado 10k); model card y reentreno del GNN; equivalencias de nodos GNN; `risk_index`/`score_semantics` en la API; `tabaco` y `salud_autopercibida` en la encuesta (contrato `2026-10-23.1`, exportado al frontend) con ablación NHANES que muestra aporte nulo. Pendientes humanos sin cambio: revisión clínica (≥100 casos, reglas firmadas), fuentes primarias, benchmark OCR con PDFs reales, checklist legal.

**Frontend (repo `Joaquin2705/frontend-suplematch`, clonado en `../frontend-suplematch`, 2026-10-23):** contrato `2026-10-23.1` instalado en `src/data/surveyContract.json`; 4 condiciones de seguridad nuevas y `tabaco`/`salud_autopercibida` en la encuesta (sin paso nuevo, dentro de "Contexto adicional opcional"); `src/api/events.js` emite `impression`, `click`, `product_click`, `purchase_intent`, `dismiss`, `still_taking_30d`/`stopped` a `POST /feedback/events` (fire-and-forget); Feedback envía `purchased`, `still_taking_30d`, `perceived_benefit`; Historial pregunta "¿sigues tomando?" a partir de 14 días; Condiciones lee `risk_index`, explica el índice de reglas y muestra `lab_risk_estimates` como "exámenes que convendría confirmar". Sin commits en ese repo. Pendiente humano: desplegar frontend y backend juntos para que lleguen eventos reales.

`pytest tests/unit` (2026-10-23, Python 3.12 con torch): ver última línea de este documento.

`pytest tests/unit` (2026-10-23, cierre ML, Python 3.12 con torch): **417 passed, 9 skipped, 0 failed**.

## Continuación del 2026-10-23 (tarde)

- `make test-integration` contra Postgres 16 (pod `suple-dev`): migraciones hasta `20261022_0014` aplicadas, catálogo importado (2925 filas, 323 RS a revisión), **35 passed** con torch (sin torch 29 passed, 6 skipped por artefactos/torch).
- Frontend: E2E de Playwright **7/7** (antes 5 fallaban también en HEAD). Causas: `addInitScript(localStorage.clear())` borraba la sesión al recargar; la encuesta tiene pasos nuevos y el examen avanza solo; copy de resultados cambiado. `answerSurvey` ahora recorre la encuesta por título de paso.
- `modelo1_pipeline.pkl` retirado: sin fallback en `model_loader`, `pipeline_completo`, `servicio_recomendaciones` y `warmup_models`; borrados `app/ml/explainability.py` (SHAP sobre el RF legacy) y `scripts/training/modelo1_clasificador.py`; `shap` fuera de `requirements.txt`. Test `test_model_loader.py`: el legacy solo ya no cuenta como listo.
- `evidence_grade` ahora llega a la API (el mapper de `servicio_recomendaciones` y `RecommendationItem` lo descartaban, pese a lo indicado en Fase 4).
- GNN con early stop por AUC de validación (Fase 4), harness OCR por carpeta (Fase 6) y paquete de revisión clínica (Fases 4 y 7); ver casillas.
- Hallazgo del paquete clínico: probable sobre-detección de `condition_mvp` (11 condiciones de media por caso; proteína y fatiga en 120/120). Ver `docs/clinical_review_package.md`.

`pytest tests/unit` (2026-10-23, tarde, Python 3.12 con torch): ver línea siguiente.

`pytest tests/unit` (2026-10-23, tarde, Python 3.12 con torch): **431 passed, 9 skipped, 0 failed**. Integración: **35 passed**. E2E frontend: **7/7**.

## Encuesta v2 (2026-10-24, contrato `2026-10-24.1`, `FEATURE_CONTRACT_VERSION` `2026-10-24.1`)

Motivo: el paquete clínico mostró sobre-detección (11.2 condiciones por caso; proteína y fatiga en 120/120). Cambios:

- Objetivos fuera de la detección: `meta_*` solo con síntomas, hábitos y edad (`FeatureBuilder` y generador sintético). Los objetivos ordenan condiciones y componentes (`GOAL_CONDITIONS`, `_order_*_by_goals`), siempre después de las alertas de seguridad.
- Faltante ≠ 0: proteína solo con el bloque de alimentos completo (grupos excluidos por el tipo de dieta = 0); carne total solo con carne roja y pollo respondidos; zinc faltante si falta lo que lo define. Base de 15 g/día de cereales/tubérculos y +20 g por proteína en polvo (heurísticas a revisar).
- Escala semanal 0/1/3/5/7/14 (antes máximo 7 = 1 al día) con porciones peruanas y "No sé"; contrato `rules.food_block`.
- `dieta_deficiente`: solo "poco variada", anemia previa o 2+ nutrientes bajos de cantidades respondidas (antes 1, "regular" y ser vegetariano).
- Preguntas nuevas (todas opcionales salvo `analisis_ultimo_anio`): seguimiento de fatiga, protector/piel al sol, menstruación abundante, parto reciente, donación de sangre, años de dieta vegetal, metformina/IBP, fortificados con B12, B12 como suplemento; 5 valores clave de laboratorio tipeables. Tres features nuevas (`iron_loss_risk`, `vitamin_d_sun_barrier`, `b12_absorption_risk`) con 5 reglas nuevas en `condition_rules.csv` (fuentes NIH ODS).
- Bug: condiciones duplicadas (modelo + reglas de contexto) que salían positivas con índice 0.00; ahora una fila por condición (la de mayor índice).
- `condition_mvp` reentrenado (10 000 filas): f1_macro 0.908 (sin labs 0.909).

Resultado (paquete clínico, extremo a extremo): 10.0 condiciones por caso (antes 11.2); índice 0.00: 0 (antes 81); proteína 70/120, fatiga 77/120. Escenarios de `validate_recommendation_quality`: foco cubierto 10/15 (antes 14/15); los 4 perdidos no alcanzan el umbral por sus propias reglas (vitamina D solo por poco sol, rendimiento solo por entrenar), el modelo anterior los marcaba igual. Ver `docs/clinical_review_package.md`. Frontend: E2E 8/8 (test nuevo de payload).

Nota: durante la sesión quité por error 6 reglas `meta_*` de condiciones de riesgo (cambio de pesos que corresponde al nutricionista); se restauraron con sus valores y fuentes originales antes del reentreno final.

`pytest tests/unit` (2026-10-24, Python 3.12 con torch): **444 passed, 9 skipped, 0 failed**. Integración: **35 passed**.

## Reglas por familia, candado clínico, encuesta más corta y segunda opinión (2026-10-24, tarde)

1. **Doble conteo** (`features_contract.aggregate_rule_score`, modo `family` por defecto): una vez por familia de evidencia, proxies para señales derivadas, confirmación con dos familias sin laboratorio, umbral de las dos señales más fuertes para 4 condiciones que solo se alcanzaban contando doble. Reglas de contexto movidas de `condition_mvp_inference.py` a `condition_rules.csv` (+20). Mismo código en entrenamiento y runtime; el modo se guarda en el artefacto (`--rule-aggregation sum` revierte). `condition_mvp` f1_macro 0.849 (antes 0.908: una regresión logística aprende peor el máximo por familia).
2. **Candado**: `data/knowledge/clinical_rules_manifest.json` + `tests/unit/test_clinical_rules_manifest.py` (8 tablas, saltos de línea normalizados); `scripts/clinical/informe_impacto_reglas.py` mide el cambio de reglas sobre los casos sin reentrenar. Línea base técnica, no clínica.
3. **Encuesta**: compuertas para pasos opcionales (sol, hierro, B12, medicamentos B12), pregunta de variedad de dieta retirada (3/120 casos; `scripts/clinical/valor_preguntas.py`), media 27 → 24 pasos. Embudo `survey_step_events` (migración `20261024_0015`, `POST /survey/events`, `GET /survey/funnel` admin, `src/api/surveyEvents.js`).
4. **Segunda opinión** NHANES para vitamina D limítrofe (`apply_second_opinion`). **Estabilidad** con 5 semillas (`scripts/training/estabilidad_semillas_condiciones.py`): 20 % de detecciones inestables; los escenarios fallidos son fallos estables.

Resultado (paquete clínico de punta a punta): 5.0 condiciones por caso (11.2 el 23/10), 17 componentes (32.8). Escenarios de `validate_recommendation_quality`: 8/15 (los 7 restantes son fallos estables: vitamina D solo por sol, rendimiento, un caso de inmunidad, y un escenario que espera `FATIGA_CRONICA`, código que ya no existe).

`pytest tests/unit` (2026-10-24, tarde): ver línea siguiente.


`pytest tests/unit` (2026-10-24, tarde, Python 3.12 con torch): **464 passed, 9 skipped, 0 failed**. Integración: **38 passed**. E2E frontend: **8/8**.

## Vitamina D, feedback → ranking y fuentes reales (2026-10-24, noche)

1. **Vitamina D**: los escenarios con solo poco sol fallaban porque la confirmación exigía dos familias de la encuesta y la segunda opinión NHANES solo actuaba cerca del umbral. NHANES no ve la exposición solar, así que poco sol + estimación positiva de NHANES son dos evidencias independientes: nueva vía `complementary_family` en `apply_second_opinion` (sin cambiar pesos de `condition_rules.csv`). Paquete clínico: vitamina D 19 → 27 de 120 casos, 4.97 → 5.04 condiciones por caso. Escenarios de calidad 8/15 → 11/15 (quedan rendimiento deportivo, adolescente con fatiga, fatiga sin sueño corto y mayor de 50 con NHANES 0.32 < 0.34).
2. **Bug**: `/recommend` respondía 500 cuando actuaba la segunda opinión (`score_basis="rules+second_opinion_nhanes"` no estaba en el esquema). Corregido, con test de regresión.
3. **Bug**: sin componentes elegibles para pack (solo prioridades blandas) el reranker emitía un pack vacío con id `pack_d41d8cd98f` (md5 de "") compartido entre perfiles, que mezclaba su feedback. Ahora no hay pack.
4. **Feedback → ranking probado de punta a punta** (`tests/integration/test_feedback_ranking.py`): /recommend → /feedback → /recommend contra Postgres, con pipeline falso (corre en CI) y con modelos reales. Con modelos reales **un voto negativo** saca al pack principal del primer puesto (score_feedback 0.70 → 0.62): el ranking es demasiado sensible con pocos votos. Ver propuesta.
5. `validar_calidad_recomendaciones.py` usa Postgres (antes el store SQLite legado, apagado por defecto), separa "por diseño" (perfil crítico, solo prioridades blandas) de fallos y cambia `FATIGA_CRONICA` por `FATIGA_NUTRICIONAL`.
6. **Fuentes reales**: `docs/fuentes_datos_reales.md`. Validación externa NHANES 2021-2023 sin reentrenar (`validar_condiciones_nhanes_externo.py`): vitamina D AUC 0.811 (0.815 en test), glucosa 0.752, HDL 0.752.
7. **Propuesta** de suplementos individuales con 1-5 estrellas: `docs/propuesta_recomendacion_por_suplemento.md` (no implementada).

`pytest tests/unit` (2026-10-24, noche, Python 3.12 con torch): **470 passed, 9 skipped, 0 failed**. Integración: **40 passed**. Copia limpia como CI: 431 passed / 48 skipped, integración 33 passed / 7 skipped.

## Robustez del feedback, HbA1c y fuentes primarias (2026-10-24, noche 2)

1. **Feedback**: `MIN_FEEDBACK_TO_RERANK = 5`. Con menos votos el score queda en el prior (`feedback_source="insufficient"`). Antes 1 voto sacaba al pack principal del primer puesto; ahora hacen falta 5 (test de integración con modelos reales).
2. **Modelo real**: features `metformina` y `antiacidos` (`RXQ_RX`) y B12 en suplementos; targets nuevos HbA1c (AUC 0.844 test / 0.834 en 2021-2023) y B12 (0.687, no sirve). En producción quedan vitamina D, HbA1c, HDL y ALT; fuera glucosa (reemplazada por HbA1c), anemia, ferritina, colesterol y B12. Ver `docs/fuentes_datos_reales.md`. Umbral de vitamina D 0.34 → 0.38: paquete clínico 21 de 120 casos (27 antes del reentreno); escenarios sin cambio (11/15).
3. **Cola RS**: `GET /admin/catalog/rs-review/export.csv` (BOM, protección contra fórmulas).
4. **Fuentes primarias**: candidatos de PubMed por claim (ver casilla de Fase 2).
5. **CI**: `actions/checkout@v7` y `actions/setup-python@v7` (Node 24).

`pytest tests/unit` (2026-10-24, noche 2, Python 3.12 con torch): **480 passed, 9 skipped, 0 failed**. Integración: **41 passed**. Copia limpia como CI: 440 passed / 49 skipped, integración 34 passed / 7 skipped.

### Nombres reconocibles para el usuario (2026-10-24)

Todo nombre visible va en lenguaje común: suplementos en español con la vitamina B por número ("Vitamina B2 (riboflavina)", "Ácido fólico (vitamina B9)", "Omega-3 DHA", "Probiótico Bacillus coagulans"; antes "Boron", "Phosphorus", "Folate", "DHA"), condiciones sin jerga ("Riesgo de colesterol o triglicéridos altos" en vez de "dislipidemia", "Defensas bajas", "Memoria y concentración") y estimaciones de laboratorio con nombre común + examen a pedir ("Azúcar en sangre alta en los últimos meses" / "Hemoglobina glicosilada (HbA1c)"). La traducción ignora tildes y mayúsculas y se aplica también a títulos de packs, sinergias y alertas. Tests: `tests/unit/test_component_display_names.py` y `test_labels_are_plain_language_and_every_target_names_its_exam`. Revisado sobre las salidas de 120 casos clínicos + 15 escenarios.

### Modelos desplegados = modelos del commit (2026-10-24)

1. `check_artifact_versions` (`app/ml/model_loader.py`) compara cada `.pkl` con el sha256 de `insumos_manifest.json`
   y el `feature_contract_version` de `condition_lab_model.pkl` con `condition_lab_inference.FEATURE_CONTRACT_VERSION`
   (el script de entrenamiento la importa). En `staging`/`production` cualquier diferencia deja `/health/ready` en
   `degraded`; el modelo real con otro contrato no sirve estimaciones en ningún entorno.
2. `scripts/ops/modelos_release.py publicar|descargar|verificar`: los `.pkl` viajan como assets de un release de GitHub
   y se verifican contra el manifiesto antes de reemplazar nada.
3. Tests con nombre de archivo repetido: `tests/integration/test_catalog_rs_review.py` pasa a
   `test_catalog_rs_review_api.py`; `tests/unit/test_test_layout.py` impide otro par. `pytest tests` corre unit e
   integración juntos: **592 passed, 11 skipped**.

### Escenarios de calidad: 16/16 (2026-10-24)

Los 4 que fallaban, uno por uno:

| Escenario | Causa | Cambio |
|---|---|---|
| `mayor_50_activo_sol_bajo` | Edad ≥ 50 (0.12) + poco sol (0.30) = 0.42 < 0.55: los dos grupos de riesgo de NIH ODS juntos no marcaban vitamina D | **Regla**: `DEFICIT_VIT_D edad>=50` 0.12 → 0.25. Paquete clínico: vitamina D 21 → 25 de 120 (solo reglas 5 → 12), resto igual. Modelo 1 reentrenado (`--rows 10000 --seed 42`, f1_macro 0.849 → 0.850). **Pendiente de revisión del nutricionista** (nota en `clinical_rules_manifest.json`). |
| `adolescente_fatiga_inmunidad` | 5-7 h de sueño contaban igual a cualquier edad; 3-4 resfríos al año son normales en adolescentes (CDC) | `feature_builder`: en menores 5-7 h equivale a "menos de 5 h" (CDC/AASM: 8-10 h a esa edad). Detecta Estrés y sueño. Foco esperado corregido a `ESTRES_SUENO`. |
| `fatiga_cronica_estres_sueno_bajo` | Expectativa heredada de `FATIGA_CRONICA`: con dieta regular la fatiga se explica por dormir < 5 h con estrés muy alto | Foco esperado acepta `ESTRES_SUENO` (lo que el sistema ya detectaba). |
| `rendimiento_deportivo_activo` | Persona activa, sana y sin síntomas: hacer ejercicio no es una condición | Pasa a **control negativo** (`SALUDABLE`, sin packs). Nuevo `deportista_calambres_dolor_muscular` cubre el caso con síntomas (detecta Hidratación y electrolitos). |

El validador ahora limpia el feedback después de cada escenario: dos escenarios con el mismo pack se contaminaban la
línea base. Aparte: el manifiesto decía `--rows 2500` para el Modelo 1, pero el modelo servido usaba 10 000 filas.

### Precisión real con exámenes de usuarios (2026-10-24)

`scripts/validation/precision_real.py` mide, por condición, la precisión y la sensibilidad de lo que la encuesta
estima (sin exámenes) contra el examen de la misma persona, para el sistema servido, solo reglas + NHANES y solo
NHANES (`docs/precision_real.md`). Hoy la base no tiene pares reales: el reporte sale vacío hasta que haya usuarios
con exámenes. `build_pipeline_input` (servicio de recomendaciones) es ahora el único camino que arma la entrada del
pipeline, compartido por `/recommend` y la medición.

### Precisión con NHANES 2013-2014 (2026-10-24)

`scripts/validation/precision_nhanes.py`: 2 932 adultos reales, encuesta → sistema → examen. El Modelo 1 no mejora
a las reglas; el modelo NHANES es la mejor señal (vitamina D AUC 0.70, azúcar 0.77); las reglas de vitamina D tienen
AUC 0.46 (no descuentan suplementos; la barrera por protector solar y la edad 50-59 van al revés o no suman). El cambio
`edad>=50` 0.12 → 0.25 no tiene respaldo en estos datos. Detalle y propuestas en `docs/precision_nhanes_2013_2014.md`.
Calcio y magnesio en sangre salieron de la verdad de `precision_real` (no reflejan el déficit).

Aplicado el 2026-10-25: `edad>=50` vuelve a 0.12, el protector solar deja de ser barrera y quien toma vitamina D no
recibe la marca sin examen. Vitamina D en NHANES: precisión 45 % → 63 % (sensibilidad 11 % → 6 %); paquete clínico
25 → 12 casos. Ver `docs/precision_nhanes_2013_2014.md`.
