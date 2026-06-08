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

    def build_pipeline_payload(self, encuesta: EncuestaInput) -> dict:
        edad = self.EDAD_MAP[encuesta.edad_rango]
        problemas_sueno = self.SUENO_MAP[encuesta.horas_sueno]
        nivel_actividad = self.EJERCICIO_MAP[encuesta.frecuencia_ejercicio]
        fatiga_general = self.FATIGA_MAP[encuesta.fatiga]
        exposicion_solar = self.SOL_MAP[encuesta.exposicion_solar]
        enfermedad_frecuente = self.ENFERMEDAD_MAP[encuesta.frecuencia_enfermedad]
        irritabilidad = self.ESTRES_MAP[encuesta.estres]
        alcohol_bonus = self.ALCOHOL_MAP.get(encuesta.alcohol, 0)

        # Dieta poco variada incrementa riesgo de déficits
        dieta_deficiente = encuesta.dieta in ("poco_variada", "regular")

        meta_energia = 1 if fatiga_general >= 3 or problemas_sueno >= 4 or dieta_deficiente else 0
        meta_inmunidad = 1 if enfermedad_frecuente >= 3 or alcohol_bonus >= 1 else 0
        meta_salud_osea = 1 if exposicion_solar == "baja" or edad >= 50 or dieta_deficiente else 0
        meta_cognitivo = 1 if irritabilidad >= 4 or problemas_sueno >= 4 else 0

        return {
            "sexo": getattr(encuesta, "sexo", "F"),
            "tipo_dieta": "omnivoro",
            "exposicion_solar": exposicion_solar,
            "nivel_actividad": nivel_actividad,

            "edad": edad,
            "peso_kg": 60.0,
            "altura_cm": 165.0,

            "fatiga_general": fatiga_general,
            "dolor_muscular": 2,
            "dolor_articular": 2,
            "niebla_mental": 3 if irritabilidad >= 4 else 2,
            "problemas_sueno": problemas_sueno,
            "caida_cabello": 2,
            "piel_seca": 2,
            "unas_quebradizas": 2,
            "enfermedad_frecuente": min(5, enfermedad_frecuente + alcohol_bonus),
            "calambres": 2,
            "irritabilidad": irritabilidad,

            "meta_energia": meta_energia,
            "meta_inmunidad": meta_inmunidad,
            "meta_belleza": 0,
            "meta_rendimiento": 1 if nivel_actividad in ["activo", "muy_activo"] else 0,
            "meta_salud_osea": meta_salud_osea,
            "meta_cognitivo": meta_cognitivo,
        }
