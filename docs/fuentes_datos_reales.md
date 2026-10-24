# Fuentes oficiales con laboratorio y cuestionario para ampliar el modelo de condiciones

Fecha: 2026-10-24. Objetivo: encontrar datos reales individuales (laboratorio + cuestionario) para ampliar
`condition_lab_model` más allá de NHANES 2015-2018. **V** = comprobado en la fuente oficial (página del archivo o
diccionario, respuesta HTTP 200); **NV** = no comprobado.

## NHANES (CDC): descarga abierta, dominio público

Hoy usamos los ciclos I (2015-16, train) y J (2017-18, test). El ciclo L (agosto 2021-agosto 2023) ya se usa para
validación externa (`scripts/training/validar_condiciones_nhanes_externo.py`).

| Biomarcador | Archivos y ciclos (V) | Población, n (V) |
|---|---|---|
| Vitamina D | `VID_G`, `VID_H`, `VID_I`, `VID_J`, `VID_L` (no hay `P_VID`) | `VID_L`: ≥1 año, LC-MS/MS, 7 307 resultados |
| B12 | Solo `VITB12_G` y `VITB12_H` (`LBDB12`, pg/mL) | ≥19 años, unos 5 450 por ciclo |
| Ácido metilmalónico | `MMA_G`, `MMA_H` (`LBXMMASI`) | ≥19 años, unos 5 440 |
| Folato en glóbulo rojo | `FOLATE_G`, `_H`, `_I`, `_J`, `P_FOLATE`, `_L` (`LBDRFO`) | `_L`: todos ≥1 año, 7 506 |
| Vitamina C | `VIC_D` (2005-06) y `VIC_J` (`LBXVIC`); no hay `VIC_L` | ≥6 años, 6 740 en `_J` |
| Zinc, cobre, selenio | `CUSEZN_G`, `_H`, `_I` (`LBXSZN`) | Un tercio de la muestra, unos 2 400 por ciclo |
| Omega-3 en suero | `FAS_G`, `FAS_H` (`LBXEPA`, `LBXDHA`, `LBXDP3`, `LBXALN`) | Submuestra en ayunas, unos 4 400 |
| Ferritina | `FERTIN_I`, `_J`, `P_FERTIN`, `_L` | `_L`: solo niños 1-5 y mujeres 12-49 |
| Densidad ósea (DXA) | Fémur `DXXFEM_H`, `_J`, `P_DXXFEM`; cuerpo entero `DXX_G` a `DXX_J` | Fémur: ≥50 años, unos 2 290 en `_J` |
| HbA1c, insulina, PCR | `GHB_*` en todos los ciclos; `INS_H` a `INS_L`; `HSCRP_I`, `_J`, `P_`, `_L` | Existencia V; contenido NV |
| Magnesio sérico | No está en 2021-23; en otros ciclos no se encontró (búsqueda no exhaustiva) | — |

Cuidado: los archivos `P_` (2017-marzo 2020) incluyen a los participantes de 2017-18; no sirven como test si J es test.
En el ciclo L cambiaron `PAQ`, `SLQ050` y `HSD010`: el modelo actual los recibe como faltantes (ver abajo).

## Otras fuentes

| Fuente | Biomarcadores | Acceso y términos | Utilidad para Perú |
|---|---|---|---|
| ENSANUT 2018 México (INSP), ensanut.insp.mx/encuestas/ensanut2018/descargas.php | V en diccionarios: vitamina D, ferritina, PCR, homocisteína (mujeres 20-49); lo mismo más B12 (adultos mayores); glucosa, HbA1c, lípidos, insulina (crónicos adultos). Hay frecuencia de alimentos | Descarga abierta sin registro visible; términos y n: NV | La mejor proxy latinoamericana encontrada |
| VIANEV Perú (INS/MINSA), microdata.fao.org catálogo 2921 | "Indicadores bioquímicos" sin detalle (NV) | V: solo investigación, **excluye uso comercial** | Sí, pero no utilizable por una empresa |
| ENS Chile 2016-17 (MINSAL) | Vitamina D (V en literatura); B12 NV | Portal respondió 403 a consultas automáticas (NV) | Buena |
| PNS Brasil 2013 (IBGE/Fiocruz) | HbA1c, lípidos, creatinina, hemograma; 8 952 adultos | ZIP "Exames" publicado (V); licencia "todos os direitos reservados" | Media |
| ENSIN 2015 Colombia (ICBF) | Bioquímica sin detalle (NV) | Sin procedimiento de microdatos encontrado | Buena, sin acceso confirmado |
| KNHANES (Corea), CHMS (Canadá), NDNS (Reino Unido) | Varios | Registro o solo en centros de datos | Baja o inviable |

## Modelo actual (contrato `nhanes_questionnaire_v2_2026-10-24`) y validación externa

Reentrenado el 2026-10-24 con dos features nuevas que la encuesta v2 ya pregunta: `metformina` y `antiacidos`
(IBP o anti-H2, desde `RXQ_RX`), más la dosis de B12 en suplementos. Targets nuevos: HbA1c ≥ 5.7 % (`GHB`) y B12
< 300 pg/mL (`VITB12`, solo en 2011-2014: train G, test H). La validación externa es NHANES 2021-2023 sin
reentrenar (`python scripts/training/validar_condiciones_nhanes_externo.py`, 8 153 adultos; reporte en
`data/reports/condition_model/nhanes_external_2021_2023.json`).

| Target | AUC test | AUC externo 2021-23 | ECE externo | En producción |
|---|---|---|---|---|
| Vitamina D < 20 ng/mL | 0.815 | **0.810** | 0.022 | Sí, y segunda opinión de `DEFICIT_VIT_D` |
| HbA1c ≥ 5.7 % | **0.844** | **0.834** | 0.029 | Sí (reemplaza a glucosa) |
| HDL < 40 | 0.749 | 0.753 | 0.053 | Sí |
| ALT > 40 | 0.696 | 0.699 | 0.041 | Sí (casi nunca positivo) |
| Glucosa ayunas ≥ 100 | 0.762 | 0.748 | 0.079 | No: reemplazada por HbA1c |
| Anemia | 0.740 | 0.719 | 0.006 | No: en Perú AUC 0.50 (ENDES) |
| Colesterol ≥ 200 | 0.651 | 0.632 | 0.143 | No: Brier peor que la base fuera de muestra |
| B12 < 300 pg/mL (test 2013-14) | 0.687 | sin dato | — | No: F1 0.01 al umbral, casi no marca positivos |
| Ferritina < 30 (mujeres) | 0.575 | 0.581 | 0.030 | No útil |

Notas:
- En el ciclo L faltan del todo actividad física, problemas de sueño y salud autopercibida (cambios del
  cuestionario) y un 39 % no tiene recordatorio de 24 h; se imputan con la mediana del train.
- `RXQ_RX_L` ya no publica los nombres de los medicamentos: la validación externa evalúa metformina y
  antiácidos como "no", igual que el runtime cuando la persona no los marca. Dejarlos como faltantes descalibra
  HDL (ECE 0.159) y HbA1c (0.098) por un artefacto del ciclo, no del producto.
- El umbral de vitamina D (elegido en validación interna) pasó de 0.34 a 0.38 con el reentreno: en el paquete
  clínico la vitamina D baja de 27 a 21 de 120 casos; los escenarios de calidad no cambian.

## Próximas acciones recomendadas

1. **Validación latinoamericana con ENSANUT 2018** de vitamina D, HbA1c y lípidos, después de confirmar términos
   de uso con el INSP (ensanut@insp.mx).
2. **Reentrenar vitamina D con más ciclos** (G+H+I) y reservar J y L como test.
3. **B12**: con la encuesta actual no alcanza. Faltaría dieta vegetal en NHANES (no hay variable directa) o un
   recordatorio de 24 h en la app; mientras tanto `DEFICIT_B12` sigue saliendo de las reglas (dieta vegana, metformina, edad).
4. No vale la pena con la encuesta actual: zinc, folato (fortificación), ferritina y magnesio.

Riesgos: validez en Perú (ENDES mostró que un modelo de EE. UU. puede caer al azar en anemia); términos de uso por
confirmar en todas las fuentes salvo NHANES; el modelo usa el recordatorio de 24 h de NHANES, que la encuesta
de la app solo aproxima.
