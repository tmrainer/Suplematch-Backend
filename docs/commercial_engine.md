# Motor Comercial

El Modelo 2 recomienda componentes. El motor comercial convierte esos
componentes en productos reales solo si el perfil permite compra.

Flujo:

```txt
Modelo 2 -> component_id
ProductCatalogService -> productos candidatos
Safety/restricciones -> bloqueos o penalizaciones
Commercial ranker -> commercial_score + razones
Packs -> diversidad de farmacia y productos seleccionados
```

## Score comercial

Cada producto recibe:

```txt
commercial_score == product_score
commercial_score_version = commercial_ranker_v2
```

El score combina:

- match con el componente recomendado;
- preferencia por producto unitario;
- precio y stock;
- reseñas verificadas/publicadas del producto comercial;
- calidad de catálogo y trazabilidad;
- diversidad de farmacia dentro del pack;
- frescura del scraping/importación;
- exposición histórica de producto/farmacia;
- restricciones del usuario;
- reglas de safety por ingrediente;
- boost de producto preferido por admin.

El backend expone `commercial_score_breakdown` para auditar la decisión.

## Producto unitario vs multicomponente

Si la recomendación pide un componente específico, el motor prioriza productos
unitarios:

```txt
DEFICIT_B12 -> B12 unitaria > multivitamínico con B12
```

Los multicomponentes no se eliminan siempre, pero reciben menor
`unit_preference_score`.

## Safety por producto

El bloqueo ya no depende solo del componente principal. El motor revisa texto,
ingredientes y flags de catálogo:

- alergia pescado/mariscos bloquea omega 3/DHA marino;
- enfermedad renal bloquea creatina comercial;
- anticoagulantes bloquean vitamina K;
- enfermedad hepática bloquea extractos sensibles;
- embarazo/lactancia bloquea vitamina A preformada cuando aplica.

Si un producto queda bloqueado:

```txt
product_safety_blocked = true
commercial_decision = "blocked"
product_score = 0
commercial_score = 0
```

## Flags de calidad

`commercial_quality_flags` resume la trazabilidad:

```txt
has_valid_registration
has_traceable_components
has_verified_label_flags
has_inferred_label_flags
has_declared_amount
has_price
has_stock_or_availability
is_unit_component
is_multicomponent
contains_fish_or_shellfish
may_contain_gelatin
may_contain_dairy
may_contain_soy
has_gluten_free_claim
```

## Razones visibles

`selection_reasons` puede incluir:

- `Buen match con el componente recomendado`
- `Producto unitario priorizado para el componente`
- `Producto multicomponente penalizado frente a opciones unitarias`
- `Elegido por mejor precio`
- `Mejor calificación de usuarios para este producto`

## Reseñas de producto

Las reseñas no califican el componente en abstracto. Califican el producto
comercial específico que se mostró o eligió el usuario.

Endpoint recomendado:

```txt
POST /api/v1/reviews/products
```

Campos usados por el ranker:

- `rating`
- `effectiveness_score`
- `side_effects_score` como tolerancia
- `price_value_score`
- `verified_purchase`

El backend deriva el componente asociado desde `commercial_product_components`.
Esto evita que un usuario suba o baje todo un nutriente por una experiencia con
una marca, farmacia, precio o formulación concreta.
- `Registro sanitario trazable`
- `Farmacia distinta para diversificar`
- `Penalizado por exposición repetida`

Estas razones son aptas para UI de usuario o panel admin.

## Benchmark

Comando:

```bash
python3 scripts/validate_commercial_engine_quality.py
```

Casos evaluados:

- producto unitario sobre multicomponente;
- alergia pescado/mariscos bloqueando omega marino;
- enfermedad renal bloqueando creatina;
- presupuesto bajo priorizando precio;
- diversidad de farmacia en packs;
- score auditable con flags y breakdown.

Resultado de referencia:

```txt
cases: 6
pass_rate: 1.0000
```

El benchmark queda integrado en:

```bash
bash /home/leo/DPD/Proyecto/scripts/validate_full_stack.sh
```
