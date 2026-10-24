# Versionado de insumos no versionados

Fecha: 2026-10-22. Fase 0 del plan de fiabilidad.

## Decisión recomendada: Git LFS

Tamaños actuales: DIGEMID 1.2 MB, componentes/grafo 1.9 MB, raw de scraping 5.4 MB, modelos 7.9 MB, NHANES XPT ~130 MB (dos ciclos).
Total sin NHANES: ~16 MB. Git LFS en GitHub ofrece 1 GB de almacenamiento y 1 GB/mes de transferencia gratis; sobra para
todo salvo los XPT de NHANES, que son descargables públicamente y no hace falta versionar (el script los cachea).

DVC se justificaría con datasets de GB o con varios remotos; aquí añade una herramienta más sin beneficio.

## Qué hacer (una vez, quien tenga permisos sobre el repo)

```bash
# 1) instalar git-lfs (Fedora: sudo dnf install git-lfs; Debian/Ubuntu: sudo apt install git-lfs)
git lfs install
# 2) .gitattributes ya declara los patrones LFS. Quitar del .gitignore estas lineas:
#    data/raw/ (solo digemid y pharmacies), data/training/ (solo supplement_model), models/runtime/*.pkl, models/runtime/*.csv
#    y mantener ignorados data/raw/nhanes, data/processed, data/evaluation, data/reports.
# 3) añadir y commitear
git add .gitattributes data/raw/digemid data/raw/pharmacies data/training/supplement_model models/runtime/*.pkl models/runtime/*.csv
git commit -m "data: versionar insumos del catalogo y modelos con Git LFS"
git lfs ls-files
```

Tras esto `scripts/ops/verificar_insumos.py --strict` debe pasar en un checkout limpio y el manifiesto
`data/insumos_manifest.json` pasa a marcar esos insumos como `versioned: true`.

## Reglas

- `digemid_limpio.csv`: anotar fecha de extracción en el manifiesto (`nota`) cada vez que se reemplace.
- `product_components.csv`: no editar a mano; regenerar con `scripts/catalog/generar_product_components.py`.
- `.pkl`: cada reentrenamiento actualiza el hash en el manifiesto (`verificar_insumos.py --update`) y la model card.
- No versionar nunca `data/reports` (contiene evidencias HTML de DIGEMID y, potencialmente, texto OCR).
