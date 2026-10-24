# Benchmark OCR de examenes de laboratorio

## Objetivo

Validar y calibrar el OCR/parser de examenes medicos usando archivos reales o publicos colocados en la raiz del proyecto. Este flujo no reentrena pesos internos de Tesseract; calibra la extraccion de biomarcadores, unidades, rangos y falsos positivos sobre casos trazables.

## Archivos usados

- PDFs en `/home/leo/DPD/Proyecto/*.pdf`.
- `archive(1).zip`: CSV estructurado de resultados de laboratorio.
- `archive.zip`: imagenes medicas ruidosas usadas como casos negativos.

Los reportes no guardan texto OCR completo para evitar replicar datos sensibles. Solo guardan metricas, biomarcadores detectados, estados y errores.

## Ejecucion

```bash
cd /home/leo/DPD/Proyecto/Suplematch-Backend
/home/leo/DPD/Proyecto/.venv/bin/python scripts/training/entrenar_ocr_labs_desde_archivos.py \
  --project-root /home/leo/DPD/Proyecto \
  --max-csv-cases 500 \
  --max-negative-images 5
```

## Reportes generados

```txt
data/reports/labs/02_uploaded_ocr_summary.json
data/reports/labs/02_uploaded_ocr_file_report.csv
data/reports/labs/02_uploaded_ocr_lab_csv_cases.csv
data/reports/labs/02_uploaded_ocr_negative_cases.csv
```

## Dependencias de OCR escaneado

Para PDFs con texto incrustado basta `pypdf`. Para imagenes y PDFs escaneados se requiere el binario del sistema `tesseract`:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils
```

Si `tesseract` no esta instalado, el benchmark marca esos casos como `skipped`, no como aciertos.

## Estado actual

Con los archivos subidos se validaron correctamente:

- HbA1c sin confundirla con hemoglobina.
- T4 libre separada de T4 total.
- Panel tiroideo con TSH, T3 y T4.
- Formatos PDF donde el resultado aparece antes del nombre del analito.
- Rechazo de frases explicativas que mencionan analitos pero no contienen resultados.

El PDF real de laboratorio con texto extraible detecta TSH, T4 y T3; TSH queda como alerta tiroidea y bloquea compra directa hasta revision profesional.

## Benchmark por carpeta con ground truth (Fase 6 del plan de fiabilidad)

`scripts/validation/benchmark_ocr_carpeta.py` mide precision y recall de valor+unidad sobre una carpeta de PDFs
(o imagenes) anonimizados, usando el mismo camino que `/labs/upload` (`extract_text_from_upload` + `parse_lab_text`).

```bash
# 1) Plantilla. --prefill copia lo que detecta el OCR (verificado=no) para corregir en vez de tipear todo.
python scripts/validation/benchmark_ocr_carpeta.py --input-dir /ruta/pdfs --write-template gt.csv --prefill

# 2) Una persona abre cada PDF y en gt.csv: corrige valores/unidades, borra falsos positivos, AGREGA los
#    biomarcadores que el OCR no vio y marca verificado=si. Archivo sin resultados: una fila sin code, verificado=si.

# 3) Benchmark (reportes en data/reports/labs/ocr_benchmark/)
python scripts/validation/benchmark_ocr_carpeta.py --input-dir /ruta/pdfs --ground-truth gt.csv --hash-file-names
```

- `value`/`unit` del ground truth son los impresos en el informe; se comparan con `original_value`/`original_unit`.
- Tres niveles: `code`, `code_value` (tolerancia 1 % o 0.02) y `code_value_unit` (unidad normalizada); la metrica
  del plan es `code_value_unit`.
- `status`: `passed`, `insufficient_sample` (menos de `--min-files`, default 50) o `failed` (filas invalidas,
  ground truth de archivos que no existen, o umbrales `--min-precision`/`--min-recall` no alcanzados).
- Riesgo de anclaje con `--prefill`: quien anota tiende a aceptar lo que propone el OCR. Revisar cada PDF entero,
  no solo las filas prellenadas; lo ideal es que una segunda persona revise una muestra.
- Los reportes no guardan texto OCR; con `--hash-file-names` tampoco nombres de archivo.
- PDFs escaneados requieren `tesseract` + `poppler`; sin ellos el archivo cuenta como error de extraccion
  (todos sus biomarcadores como no detectados), no se omite.
