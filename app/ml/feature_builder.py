from app.domains.survey.esquemas_encuesta import EncuestaInput


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
    }

    TIPO_DIETA_MAP = {
        "omnivoro": "omnivoro",
        "pescetariano": "pescetariano",
        "vegetariano": "vegetariano",
        "vegano": "vegano",
    }

    SLEEP_QUALITY_MAP = {
        "buena": 1,
        "regular": 3,
        "mala": 5,
    }

    NIGHT_WAKEUPS_MAP = {
        "nunca": 1,
        "1_2": 3,
        "3_o_mas": 5,
    }

    CAFFEINE_SLEEP_MAP = {
        "no": 0,
        "a_veces": 1,
        "si": 2,
    }

    RECOVERY_MAP = {
        "no": 1,
        "leve": 2,
        "moderada": 4,
        "alta": 5,
    }

    @staticmethod
    def _quantity(encuesta: EncuestaInput, field: str) -> float | None:
        value = getattr(encuesta, field, None)
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _feature_value(value: float | None) -> float:
        return -1.0 if value is None else float(value)

    @staticmethod
    def _status_from_value(value: float | None, low: float, critical: float | None = None, high_is_better: bool = True) -> str:
        if value is None:
            return "unknown"

        critical = low if critical is None else critical
        if high_is_better:
            if value <= critical:
                return "critical_low"
            if value <= low:
                return "low"
            return "normal"

        if value >= critical:
            return "critical_high"
        if value >= low:
            return "high"
        return "normal"

    @staticmethod
    def _diet_b12_status(tipo_dieta: str, meat_servings_week: float | None) -> str:
        if tipo_dieta == "vegano":
            return "critical_low"
        if tipo_dieta == "vegetariano":
            return "low"
        if meat_servings_week is None:
            return "unknown"
        if meat_servings_week <= 0.5:
            return "critical_low"
        if meat_servings_week <= 2:
            return "low"
        return "normal"

    @staticmethod
    def _diet_protein_status(protein_g_day: float | None, weight_kg: float) -> str:
        if protein_g_day is None:
            return "unknown"

        grams_per_kg = protein_g_day / max(weight_kg, 1.0)
        if grams_per_kg < 0.55:
            return "critical_low"
        if grams_per_kg < 0.8:
            return "low"
        return "normal"

    @staticmethod
    def _diet_folate_status(legumes_week: float | None, fruit_veg_day: float | None) -> str:
        if legumes_week is None and fruit_veg_day is None:
            return "unknown"

        legumes = legumes_week or 0.0
        fruit_veg = fruit_veg_day or 0.0
        if legumes <= 1 and fruit_veg <= 1:
            return "critical_low"
        if legumes <= 2 and fruit_veg <= 2:
            return "low"
        return "normal"

    @staticmethod
    def _diet_zinc_status(tipo_dieta: str, meat_servings_week: float | None, legume_servings_week: float | None) -> str:
        if meat_servings_week is None and legume_servings_week is None and tipo_dieta not in {"vegano", "vegetariano"}:
            return "unknown"

        meat = meat_servings_week or 0.0
        legumes = legume_servings_week or 0.0
        if tipo_dieta in {"vegano", "vegetariano"} and legumes < 3:
            return "low"
        if meat <= 0.5 and legumes <= 1:
            return "critical_low"
        if meat <= 2 and legumes <= 2:
            return "low"
        return "normal"

    @staticmethod
    def _estimated_protein_g_day(
        red_meat_week: float | None,
        poultry_week: float | None,
        fish_week: float | None,
        eggs_week: float | None,
        legumes_week: float | None,
        dairy_week: float | None,
    ) -> float | None:
        if all(value is None for value in (red_meat_week, poultry_week, fish_week, eggs_week, legumes_week, dairy_week)):
            return None

        weekly_grams = (
            (red_meat_week or 0.0) * 25.0
            + (poultry_week or 0.0) * 25.0
            + (fish_week or 0.0) * 22.0
            + (eggs_week or 0.0) * 6.0
            + (legumes_week or 0.0) * 12.0
            + (dairy_week or 0.0) * 8.0
        )
        return round(weekly_grams / 7.0, 2)

    def build_pipeline_payload(self, encuesta: EncuestaInput) -> dict:
        edad = int(encuesta.age_years) if getattr(encuesta, "age_years", None) is not None else self.EDAD_MAP[encuesta.edad_rango]
        problemas_sueno = self.SUENO_MAP[encuesta.horas_sueno]
        nivel_actividad = self.EJERCICIO_MAP[encuesta.frecuencia_ejercicio]
        fatiga_general = self.FATIGA_MAP[encuesta.fatiga]
        exposicion_solar = self.SOL_MAP[encuesta.exposicion_solar]
        enfermedad_frecuente = self.ENFERMEDAD_MAP[encuesta.frecuencia_enfermedad]
        irritabilidad = self.ESTRES_MAP[encuesta.estres]
        alcohol_bonus = self.ALCOHOL_MAP.get(encuesta.alcohol, 0)
        alcohol_drinks_week = getattr(encuesta, "alcohol_drinks_week", None)
        if alcohol_drinks_week is not None:
            if alcohol_drinks_week >= 14:
                alcohol_bonus = max(alcohol_bonus, 2)
            elif alcohol_drinks_week >= 4:
                alcohol_bonus = max(alcohol_bonus, 1)
        tipo_dieta = self.TIPO_DIETA_MAP[getattr(encuesta, "tipo_dieta", "omnivoro")]
        objetivos = set(getattr(encuesta, "objetivos", []) or [])
        objetivo_principal = getattr(encuesta, "objetivo_principal", None)

        # Dieta poco variada incrementa riesgo de déficits
        dieta_deficiente = encuesta.dieta in ("poco_variada", "regular") or tipo_dieta in ("vegano", "vegetariano")
        dolor_muscular = self.SEVERIDAD_MAP[getattr(encuesta, "dolor_muscular", "leve")]
        dolor_articular = self.SEVERIDAD_MAP[getattr(encuesta, "dolor_articular", "leve")]
        niebla_mental = self.SEVERIDAD_MAP[getattr(encuesta, "niebla_mental", "leve")]
        caida_cabello = self.SEVERIDAD_MAP[getattr(encuesta, "caida_cabello", "leve")]
        piel_seca = self.SEVERIDAD_MAP[getattr(encuesta, "piel_seca", "leve")]
        unas_quebradizas = self.SEVERIDAD_MAP[getattr(encuesta, "unas_quebradizas", "leve")]
        calambres = self.SEVERIDAD_MAP[getattr(encuesta, "calambres", "leve")]
        digestive_discomfort = self.SEVERIDAD_MAP[getattr(encuesta, "digestive_discomfort", "nunca")]
        weight_kg = float(encuesta.weight_kg) if getattr(encuesta, "weight_kg", None) is not None else self.PESO_MAP.get(getattr(encuesta, "peso_rango", "50_65"), 60.0)
        height_cm = float(encuesta.height_cm) if getattr(encuesta, "height_cm", None) is not None else self.TALLA_MAP.get(getattr(encuesta, "talla_rango", "155_165"), 165.0)

        exercise_days_week = getattr(encuesta, "exercise_days_week", None)
        if exercise_days_week is not None:
            if exercise_days_week == 0:
                nivel_actividad = "sedentario"
            elif exercise_days_week <= 2:
                nivel_actividad = "moderado"
            elif exercise_days_week <= 4:
                nivel_actividad = "activo"
            else:
                nivel_actividad = "muy_activo"

        sleep_quality = getattr(encuesta, "sleep_quality", None)
        if sleep_quality:
            problemas_sueno = max(problemas_sueno, self.SLEEP_QUALITY_MAP[sleep_quality])

        night_wakeups = getattr(encuesta, "night_wakeups", None)
        if night_wakeups:
            problemas_sueno = max(problemas_sueno, self.NIGHT_WAKEUPS_MAP[night_wakeups])

        caffeine_after_3pm = getattr(encuesta, "caffeine_after_3pm", None)
        if caffeine_after_3pm:
            caffeine_bonus = self.CAFFEINE_SLEEP_MAP[caffeine_after_3pm]
            problemas_sueno = min(5, problemas_sueno + caffeine_bonus)
            irritabilidad = min(5, irritabilidad + caffeine_bonus)

        recovery_difficulty = getattr(encuesta, "recovery_difficulty", None)
        if recovery_difficulty:
            recovery_score = self.RECOVERY_MAP[recovery_difficulty]
            dolor_muscular = max(dolor_muscular, recovery_score)

        fish_servings_week = self._quantity(encuesta, "fish_servings_week")
        dairy_servings_day = self._quantity(encuesta, "dairy_servings_day")
        legume_servings_week = self._quantity(encuesta, "legume_servings_week")
        red_meat_servings_week = self._quantity(encuesta, "red_meat_servings_week")
        poultry_servings_week = self._quantity(encuesta, "poultry_servings_week")
        eggs_servings_week = self._quantity(encuesta, "eggs_servings_week")
        meat_servings_week = self._quantity(encuesta, "meat_servings_week")
        if meat_servings_week is None and (red_meat_servings_week is not None or poultry_servings_week is not None):
            meat_servings_week = (red_meat_servings_week or 0.0) + (poultry_servings_week or 0.0)
        fruit_veg_servings_day = self._quantity(encuesta, "fruit_veg_servings_day")
        protein_g_day_estimate = self._quantity(encuesta, "protein_g_day_estimate")
        dairy_servings_week = self._quantity(encuesta, "dairy_servings_week")
        if dairy_servings_week is None and dairy_servings_day is not None:
            dairy_servings_week = dairy_servings_day * 7
        if protein_g_day_estimate is None:
            protein_g_day_estimate = self._estimated_protein_g_day(
                red_meat_servings_week,
                poultry_servings_week,
                fish_servings_week,
                eggs_servings_week,
                legume_servings_week,
                dairy_servings_week,
            )
        fermented_foods_week = self._quantity(encuesta, "fermented_foods_week")
        water_intake_l_day = self._quantity(encuesta, "water_intake_l_day")
        screen_hours_day = self._quantity(encuesta, "screen_hours_day")
        heavy_sweat_days_week = getattr(encuesta, "heavy_sweat_days_week", None)
        headache_days_week = getattr(encuesta, "headache_days_week", None)
        fatigue_days_week = getattr(encuesta, "fatigue_days_week", None)
        caffeine_servings_day = self._quantity(encuesta, "caffeine_servings_day")

        if fatigue_days_week is not None:
            if fatigue_days_week >= 5:
                fatiga_general = max(fatiga_general, 5)
            elif fatigue_days_week >= 3:
                fatiga_general = max(fatiga_general, 4)
            elif fatigue_days_week >= 1:
                fatiga_general = max(fatiga_general, 3)

        if caffeine_servings_day is not None and caffeine_servings_day >= 3:
            irritabilidad = min(5, max(irritabilidad, 4))
            problemas_sueno = min(5, max(problemas_sueno, 3))
        if headache_days_week is not None and headache_days_week >= 3:
            meta_hidratacion_headache = True
        else:
            meta_hidratacion_headache = False

        diet_omega3_status = self._status_from_value(fish_servings_week, low=1.0, critical=0.25)
        diet_calcium_status = self._status_from_value(dairy_servings_day, low=1.0, critical=0.25)
        diet_vitamin_c_status = self._status_from_value(fruit_veg_servings_day, low=2.0, critical=1.0)
        diet_magnesium_status = self._status_from_value(legume_servings_week, low=2.0, critical=0.5)
        diet_folate_status = self._diet_folate_status(legume_servings_week, fruit_veg_servings_day)
        diet_zinc_status = self._diet_zinc_status(tipo_dieta, meat_servings_week, legume_servings_week)
        diet_b12_status = self._diet_b12_status(tipo_dieta, meat_servings_week)
        diet_protein_status = self._diet_protein_status(protein_g_day_estimate, weight_kg)
        if getattr(encuesta, "iron_anemia_history", None) == "si":
            diet_folate_status = "low" if diet_folate_status == "normal" else diet_folate_status
            dieta_deficiente = True

        if any(
            status in {"low", "critical_low"}
            for status in (
                diet_omega3_status,
                diet_calcium_status,
                diet_vitamin_c_status,
                diet_magnesium_status,
                diet_folate_status,
                diet_zinc_status,
                diet_b12_status,
                diet_protein_status,
            )
        ):
            dieta_deficiente = True

        meta_energia = 1 if objetivo_principal == "energia" or "energia" in objetivos or fatiga_general >= 3 or problemas_sueno >= 4 or dieta_deficiente else 0
        meta_inmunidad = 1 if objetivo_principal == "inmunidad" or "inmunidad" in objetivos or enfermedad_frecuente >= 3 or alcohol_bonus >= 1 else 0
        meta_salud_osea = 1 if objetivo_principal == "salud_osea" or "salud_osea" in objetivos or exposicion_solar == "baja" or edad >= 50 or dieta_deficiente else 0
        meta_cognitivo = 1 if objetivo_principal == "suenio_estres" or "suenio" in objetivos or "estres" in objetivos or irritabilidad >= 4 or problemas_sueno >= 4 else 0
        meta_belleza = 1 if objetivo_principal == "cabello_piel_unas" or "cabello_piel_unas" in objetivos or max(caida_cabello, piel_seca, unas_quebradizas) >= 3 else 0
        meta_rendimiento = 1 if objetivo_principal == "rendimiento" or "rendimiento" in objetivos or nivel_actividad in ["activo", "muy_activo"] else 0
        meta_visual = 1 if objetivo_principal == "salud_visual" or "salud_visual" in objetivos or (screen_hours_day is not None and screen_hours_day >= 6) else 0
        meta_digestiva = 1 if objetivo_principal == "digestion" or "digestion" in objetivos or digestive_discomfort >= 3 else 0
        meta_hidratacion = 1 if objetivo_principal == "hidratacion" or "hidratacion" in objetivos or calambres >= 3 or meta_hidratacion_headache or (heavy_sweat_days_week is not None and heavy_sweat_days_week >= 3) else 0
        meta_cardiovascular = 1 if objetivo_principal == "salud_cardiovascular" or "salud_cardiovascular" in objetivos or edad >= 50 else 0
        meta_cognitivo = max(meta_cognitivo, 1 if objetivo_principal == "salud_cognitiva" or "salud_cognitiva" in objetivos else 0)

        return {
            "sexo": self.SEXO_MAP.get(getattr(encuesta, "sexo", "femenino"), "F"),
            "tipo_dieta": tipo_dieta,
            "exposicion_solar": exposicion_solar,
            "nivel_actividad": nivel_actividad,

            "edad": edad,
            "peso_kg": weight_kg,
            "altura_cm": height_cm,
            "bmi": float(encuesta.bmi) if getattr(encuesta, "bmi", None) is not None else round(weight_kg / ((height_cm / 100) ** 2), 1),
            "fish_servings_week": self._feature_value(fish_servings_week),
            "dairy_servings_day": self._feature_value(dairy_servings_day),
            "legume_servings_week": self._feature_value(legume_servings_week),
            "meat_servings_week": self._feature_value(meat_servings_week),
            "red_meat_servings_week": self._feature_value(red_meat_servings_week),
            "poultry_servings_week": self._feature_value(poultry_servings_week),
            "eggs_servings_week": self._feature_value(eggs_servings_week),
            "fruit_veg_servings_day": self._feature_value(fruit_veg_servings_day),
            "protein_g_day_estimate": self._feature_value(protein_g_day_estimate),
            "fermented_foods_week": self._feature_value(fermented_foods_week),
            "water_intake_l_day": self._feature_value(water_intake_l_day),
            "screen_hours_day": self._feature_value(screen_hours_day),
            "heavy_sweat_days_week": -1 if heavy_sweat_days_week is None else int(heavy_sweat_days_week),
            "headache_days_week": -1 if headache_days_week is None else int(headache_days_week),
            "fatigue_days_week": -1 if fatigue_days_week is None else int(fatigue_days_week),
            "alcohol_drinks_week": -1 if alcohol_drinks_week is None else int(alcohol_drinks_week),
            "caffeine_servings_day": self._feature_value(caffeine_servings_day),
            "exercise_days_week": -1 if exercise_days_week is None else int(exercise_days_week),

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
            "digestive_discomfort": digestive_discomfort,

            "dieta_deficiente": int(dieta_deficiente),
            "estres_alto": int(irritabilidad >= 4),

            "meta_energia": meta_energia,
            "meta_inmunidad": meta_inmunidad,
            "meta_belleza": meta_belleza,
            "meta_rendimiento": meta_rendimiento,
            "meta_salud_osea": meta_salud_osea,
            "meta_cognitivo": meta_cognitivo,
            "meta_visual": meta_visual,
            "meta_digestiva": meta_digestiva,
            "meta_hidratacion": meta_hidratacion,
            "meta_cardiovascular": meta_cardiovascular,

            "benchmark_diet_b12_status": diet_b12_status,
            "benchmark_diet_vitamin_c_status": diet_vitamin_c_status,
            "benchmark_diet_zinc_status": diet_zinc_status,
            "benchmark_diet_magnesium_status": diet_magnesium_status,
            "benchmark_diet_calcium_status": diet_calcium_status,
            "benchmark_diet_folate_status": diet_folate_status,
            "benchmark_diet_protein_status": diet_protein_status,
            "benchmark_diet_omega3_status": diet_omega3_status,
        }
