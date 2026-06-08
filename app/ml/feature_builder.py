from app.schemas.encuesta import EncuestaInput


class FeatureBuilder:
    EDAD_MAP = {
        "menos_18": 17,
        "18_30": 24,
        "31_50": 40,
        "mas_50": 60,
    }

    SUENO_MAP = {
        "menos_5h": 5,
        "5_7h": 4,
        "7_9h": 1,
        "mas_9h": 2,
    }

    EJERCICIO_MAP = {
        "casi_nunca": "sedentario",
        "1_2_semana": "moderado",
        "3_4_semana": "activo",
        "diario": "muy_activo",
    }

    FATIGA_MAP = {
        "siempre": 5,
        "a_menudo": 4,
        "a_veces": 3,
        "casi_nunca": 1,
    }

    SOL_MAP = {
        "menos_15min": "baja",
        "15_30min": "media",
        "30_60min": "media",
        "mas_1h": "alta",
    }

    ENFERMEDAD_MAP = {
        "muy_seguido": 5,
        "3_4_anio": 4,
        "1_2_anio": 2,
        "casi_nunca": 1,
    }

    ESTRES_MAP = {
        "muy_alto": 5,
        "alto": 4,
        "moderado": 3,
        "bajo": 1,
    }

    ALCOHOL_MAP = {
        "frecuente": 2,
        "ocasional": 1,
        "raro": 0,
        "nunca": 0,
    }

    SEVERIDAD_MAP = {
        "nunca": 1,
        "leve": 2,
        "moderado": 3,
        "frecuente": 4,
        "severo": 5,
    }

    PESO_MAP = {
        "menos_50": 47.0,
        "50_65":    57.5,
        "66_80":    73.0,
        "mas_80":   88.0,
    }

    TALLA_MAP = {
        "menos_155": 152.0,
        "155_165":   160.0,
        "166_175":   170.0,
        "mas_175":   180.0,
    }

    SEXO_MAP = {
        "femenino": "F",
        "masculino": "M",
        "prefiero_no_decir": "F",
    }

    TIPO_DIETA_MAP = {
        "omnivoro": "omnivoro",
        "pescetariano": "omnivoro",
        "vegetariano": "vegetariano",
        "vegano": "vegano",
    }

    def build_pipeline_payload(self, encuesta: EncuestaInput) -> dict:
        edad = self.EDAD_MAP[encuesta.edad_rango]
        problemas_sueno = self.SUENO_MAP[encuesta.horas_sueno]
        nivel_actividad = self.EJERCICIO_MAP[encuesta.frecuencia_ejercicio]
        fatiga_general = self.FATIGA_MAP[encuesta.fatiga]
        exposicion_solar = self.SOL_MAP[encuesta.exposicion_solar]
        enfermedad_frecuente = self.ENFERMEDAD_MAP[encuesta.frecuencia_enfermedad]
        irritabilidad = self.ESTRES_MAP[encuesta.estres]
        alcohol_bonus = self.ALCOHOL_MAP.get(encuesta.alcohol, 0)
        tipo_dieta = self.TIPO_DIETA_MAP[getattr(encuesta, "tipo_dieta", "omnivoro")]
        objetivos = set(getattr(encuesta, "objetivos", []) or [])

        # Dieta poco variada incrementa riesgo de déficits
        dieta_deficiente = encuesta.dieta in ("poco_variada", "regular") or tipo_dieta in ("vegano", "vegetariano")
        dolor_muscular = self.SEVERIDAD_MAP[getattr(encuesta, "dolor_muscular", "leve")]
        dolor_articular = self.SEVERIDAD_MAP[getattr(encuesta, "dolor_articular", "leve")]
        niebla_mental = self.SEVERIDAD_MAP[getattr(encuesta, "niebla_mental", "leve")]
        caida_cabello = self.SEVERIDAD_MAP[getattr(encuesta, "caida_cabello", "leve")]
        piel_seca = self.SEVERIDAD_MAP[getattr(encuesta, "piel_seca", "leve")]
        unas_quebradizas = self.SEVERIDAD_MAP[getattr(encuesta, "unas_quebradizas", "leve")]
        calambres = self.SEVERIDAD_MAP[getattr(encuesta, "calambres", "leve")]

        meta_energia = 1 if "energia" in objetivos or fatiga_general >= 3 or problemas_sueno >= 4 or dieta_deficiente else 0
        meta_inmunidad = 1 if "inmunidad" in objetivos or enfermedad_frecuente >= 3 or alcohol_bonus >= 1 else 0
        meta_salud_osea = 1 if "salud_osea" in objetivos or exposicion_solar == "baja" or edad >= 50 or dieta_deficiente else 0
        meta_cognitivo = 1 if "suenio" in objetivos or "estres" in objetivos or irritabilidad >= 4 or problemas_sueno >= 4 else 0
        meta_belleza = 1 if "cabello_piel_unas" in objetivos or max(caida_cabello, piel_seca, unas_quebradizas) >= 3 else 0
        meta_rendimiento = 1 if "rendimiento" in objetivos or nivel_actividad in ["activo", "muy_activo"] else 0

        return {
            "sexo": self.SEXO_MAP[getattr(encuesta, "sexo", "prefiero_no_decir")],
            "tipo_dieta": tipo_dieta,
            "exposicion_solar": exposicion_solar,
            "nivel_actividad": nivel_actividad,

            "edad": edad,
            "peso_kg":   self.PESO_MAP.get(getattr(encuesta, "peso_rango",  "50_65"),    60.0),
            "altura_cm": self.TALLA_MAP.get(getattr(encuesta, "talla_rango", "155_165"), 165.0),

            "fatiga_general": fatiga_general,
            "dolor_muscular": dolor_muscular,
            "dolor_articular": dolor_articular,
            "niebla_mental": max(niebla_mental, 3 if irritabilidad >= 4 else 1),
            "problemas_sueno": problemas_sueno,
            "caida_cabello": caida_cabello,
            "piel_seca": piel_seca,
            "unas_quebradizas": unas_quebradizas,
            "enfermedad_frecuente": min(5, enfermedad_frecuente + alcohol_bonus),
            "calambres": calambres,
            "irritabilidad": irritabilidad,

            "meta_energia": meta_energia,
            "meta_inmunidad": meta_inmunidad,
            "meta_belleza": meta_belleza,
            "meta_rendimiento": meta_rendimiento,
            "meta_salud_osea": meta_salud_osea,
            "meta_cognitivo": meta_cognitivo,
        }
