from __future__ import annotations

from scripts.catalog.construir_catalogo_aprobado import build_catalog_with_rejections


def test_approved_catalog_reports_rejection_reasons(tmp_path) -> None:
    scraped = tmp_path / "scraped.csv"
    digemid = tmp_path / "digemid.csv"
    components = tmp_path / "components.csv"

    scraped.write_text(
        "pharmacy,commercial_name,formal_name,registro_sanitario,price,currency,availability,url,sku,brand,"
        "component_traceable,component_ids_detected,component_names_detected,image_url,image_source,image_local_path,image_downloaded_at,rejection_reason\n"
        "Farmacia,Calcio OK,,DE-1,20.5,PEN,available,https://ok.test,OK,Marca,true_rs_component_map,COMP_CAL,Calcio,https://img.test/calcio.jpg,card,data/raw/pharmacies/product_images/calcio.jpg,2026-06-29T00:00:00Z,\n"
        "Farmacia,Sin componente,,DE-2,18.0,PEN,available,https://component.test,NOCOMP,Marca,false_no_component_match,,,,,,"
        "rs_sin_component_map\n"
        "Farmacia,RS externo,,DE-3,15.0,PEN,available,https://rs.test,BADRS,Marca,false_no_registro_sanitario,,,,,,"
        "rs_no_en_digemid:DE3\n"
        "Farmacia,Precio malo,,DE-1,,PEN,available,https://price.test,NOPRICE,Marca,true_rs_component_map,COMP_CAL,Calcio,,,,,\n"
        "Farmacia,Sin stock,,DE-1,12.0,PEN,out_of_stock,https://stock.test,NOSTOCK,Marca,true_rs_component_map,COMP_CAL,Calcio,,,,,\n",
        encoding="utf-8",
    )
    digemid.write_text(
        "item,Producto,Distribuidor,Fabricante,Forma Farmacéutica,codigo_atc,grupo_atc_3,grupo_atc_4,"
        "descripcion_clasificacion,Composición\n"
        "DE-1,CALCIO,DIST,FAB,TABLETA,,,,,CALCIO\n"
        "DE-2,SIN MAPA,DIST,FAB,TABLETA,,,,,\n",
        encoding="utf-8",
    )
    components.write_text(
        "item,component_id,ingredient,amount,unit,amount_mg,match_score,match_method\n"
        "DE-1,COMP_CAL,Calcio,500,mg,500,95,exact\n",
        encoding="utf-8",
    )

    rows, rejected = build_catalog_with_rejections(scraped, digemid, components)

    assert len(rows) == 1
    assert rows[0]["commercial_name"] == "Calcio OK"
    assert rows[0]["image_url"] == "https://img.test/calcio.jpg"
    assert rows[0]["image_source"] == "card"
    assert rows[0]["image_local_path"] == "data/raw/pharmacies/product_images/calcio.jpg"

    reasons_by_sku = {row["sku"]: row["catalog_rejection_reason"] for row in rejected}

    assert reasons_by_sku["NOCOMP"] == "rs_sin_componentes_trazables"
    assert reasons_by_sku["BADRS"] == "rs_no_en_digemid"
    assert reasons_by_sku["NOPRICE"] == "precio_invalido"
    assert reasons_by_sku["NOSTOCK"] == "no_disponible:out_of_stock"
