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

## Validación externa hecha (2026-10-24): NHANES 2021-2023 sin reentrenar

`python scripts/training/validar_condiciones_nhanes_externo.py`, 8 153 adultos. Reporte en
`data/reports/condition_model/nhanes_external_2021_2023.json`.

| Target | AUC test 2017-18 | AUC externo 2021-23 | Calibración externa (ECE) | Lectura |
|---|---|---|---|---|
| Vitamina D < 20 ng/mL | 0.815 | **0.811** | 0.021 | Se sostiene; prevalencia bajó de 0.30 a 0.20 y la media predicha (0.22) la sigue |
| Glucosa ayunas ≥ 100 | 0.762 | 0.752 | 0.089 | Se sostiene; calibración peor |
| HDL < 40 | 0.749 | 0.752 | 0.061 | Se sostiene |
| Anemia | 0.737 | 0.719 | 0.009 | Se sostiene en EE. UU. (en Perú no: ENDES 0.50-0.57) |
| ALT > 40 | 0.695 | 0.702 | 0.047 | Débil |
| Colesterol ≥ 200 | 0.648 | 0.637 | 0.136 | Débil y descalibrado (Brier peor que la base) |
| Ferritina < 30 (mujeres) | 0.576 | 0.579 | 0.028 | No útil |

Esto pasa aunque en el ciclo L faltan del todo actividad física, problemas de sueño y salud autopercibida (cambios
del cuestionario) y un 39 % no tiene recordatorio de 24 h (se imputan con la mediana del train).

## Próximas acciones recomendadas

1. **B12 (DEFICIT_B12)**: modelo nuevo con `VITB12_G` (train) y `VITB12_H` (test). Target B12 < 200 pg/mL, o
   < 300 con MMA > 0.27 µmol/L. Features de la encuesta v2 que ya existen: edad, metformina, IBP, B12 en
   suplementos, dieta vegetal. AUC esperado moderado (estimación, no medido).
2. **Glucosa → HbA1c ≥ 5.7** (`GHB_*`): está en todos los adultos examinados, no solo en la submuestra en ayunas,
   y es el examen que se pide en Perú.
3. **Validación latinoamericana con ENSANUT 2018** de vitamina D, HbA1c y lípidos, después de confirmar términos
   de uso con el INSP (ensanut@insp.mx).
4. **Reentrenar con más ciclos** (G+H+I para vitamina D) y reservar J y L como test.
5. No vale la pena con la encuesta actual: zinc, folato (fortificación), ferritina y magnesio.

Riesgos: validez en Perú (ENDES mostró que un modelo de EE. UU. puede caer al azar en anemia); términos de uso por
confirmar en todas las fuentes salvo NHANES; el modelo usa el recordatorio de 24 h de NHANES, que la encuesta
de la app solo aproxima.
