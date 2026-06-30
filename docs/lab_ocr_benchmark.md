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
