from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.survey.antropometria import (
    age_to_range,
    bmi,
    height_to_cm,
    height_to_range,
    normalize_height_unit,
    normalize_weight_unit,
    weight_to_kg,
    weight_to_range,
)
from app.domains.labs.esquemas import LabBiomarkerInput


Sexo = Literal["femenino", "masculino"]
PesoRango = Literal["menos_50", "50_65", "66_80", "mas_80"]
TallaRango = Literal["menos_155", "155_165", "166_175", "mas_175"]
TipoDieta = Literal["omnivoro", "pescetariano", "vegetariano", "vegano"]
Severidad = Literal["nunca", "leve", "moderado", "frecuente", "severo"]
TomaSuplementos = Literal["no", "si"]
SuplementoActual = Literal[
    "vitamina_d",
    "calcio",
    "magnesio",
    "zinc",
    "vitamina_c",
    "hierro",
    "omega_3",
    "multivitaminico",
    "proteina",
    "otro",
]
Restriccion = Literal[
    "sin_restricciones",
    "alergia_lacteos",
    "alergia_soya",
    "alergia_pescado_mariscos",
    "evita_gelatina",
    "sin_gluten",
]
CondicionSeguridad = Literal[
    "ninguna",
    "embarazo_lactancia",
    "enfermedad_renal",
    "enfermedad_hepatica",
    "problema_tiroideo",
    "anticoagulantes",
    "medicacion_cronica",
]
Objetivo = Literal[
    "energia",
    "inmunidad",
    "suenio",
    "rendimiento",
    "salud_osea",
    "cabello_piel_unas",
    "estres",
    "salud_visual",
    "digestion",
    "hidratacion",
    "salud_cardiovascular",
    "salud_cognitiva",
    "nutricion_general",
]
ObjetivoPrincipal = Literal[
    "energia",
    "inmunidad",
    "suenio_estres",
    "rendimiento",
    "salud_osea",
    "cabello_piel_unas",
    "salud_visual",
    "digestion",
    "hidratacion",
    "salud_cardiovascular",
    "salud_cognitiva",
    "nutricion_general",
]
Presupuesto = Literal["bajo", "medio", "alto", "sin_preferencia"]
SleepQuality = Literal["buena", "regular", "mala"]
NightWakeups = Literal["nunca", "1_2", "3_o_mas"]
CaffeineAfter3pm = Literal["no", "a_veces", "si"]
TrainingType = Literal["no_aplica", "fuerza", "cardio", "mixto", "movilidad"]
RecoveryDifficulty = Literal["no", "leve", "moderada", "alta"]
SupplementFrequency = Literal["diario", "varias_semana", "ocasional", "no_se"]
BinaryUnknown = Literal["no", "si", "no_se"]
CaffeineSource = Literal["cafe", "te", "energizante", "preworkout", "gaseosa_cola", "chocolate", "otro"]


class SuplementoDosisActual(BaseModel):
    amount: float = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=32)


class EncuestaInput(BaseModel):
    edad_rango: Literal["menos_18", "18_30", "31_50", "mas_50"] = "18_30"
    horas_sueno: Literal["menos_5h", "5_7h", "7_9h", "mas_9h"]
    frecuencia_ejercicio: Literal["casi_nunca", "1_2_semana", "3_4_semana", "diario"]
    dieta: Literal["poco_variada", "regular", "bastante_variada", "muy_balanceada"]
    fatiga: Literal["siempre", "a_menudo", "a_veces", "casi_nunca"]
    exposicion_solar: Literal["menos_15min", "15_30min", "30_60min", "mas_1h"]
    frecuencia_enfermedad: Literal["muy_seguido", "3_4_anio", "1_2_anio", "casi_nunca"]
    estres: Literal["muy_alto", "alto", "moderado", "bajo"]
    alcohol: Literal["frecuente", "ocasional", "raro", "nunca"]
    sexo: Sexo = "femenino"
    age_years: int | None = Field(default=None, ge=1, le=120)
    weight_value: float | None = Field(default=None, gt=0, le=500000)
    weight_unit: str | None = Field(default=None, max_length=24)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_value: float | None = Field(default=None, gt=0, le=10000)
    height_unit: str | None = Field(default=None, max_length=24)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    bmi: float | None = Field(default=None, gt=0, le=100)
    peso_rango: PesoRango = "50_65"
    talla_rango: TallaRango = "155_165"
    tipo_dieta: TipoDieta = "omnivoro"
    dolor_muscular: Severidad = "nunca"
    dolor_articular: Severidad = "nunca"
    niebla_mental: Severidad = "nunca"
    caida_cabello: Severidad = "nunca"
    piel_seca: Severidad = "nunca"
    unas_quebradizas: Severidad = "nunca"
    calambres: Severidad = "nunca"
    objetivo_principal: ObjetivoPrincipal | None = None
    objetivos: list[Objetivo] = Field(default_factory=list, max_length=4)
    fish_servings_week: float | None = Field(default=None, ge=0, le=21)
    dairy_servings_day: float | None = Field(default=None, ge=0, le=10)
    dairy_servings_week: float | None = Field(default=None, ge=0, le=21)
    legume_servings_week: float | None = Field(default=None, ge=0, le=21)
    meat_servings_week: float | None = Field(default=None, ge=0, le=21)
    red_meat_servings_week: float | None = Field(default=None, ge=0, le=21)
    poultry_servings_week: float | None = Field(default=None, ge=0, le=21)
    eggs_servings_week: float | None = Field(default=None, ge=0, le=21)
    no_meat: bool | None = None
    fruit_veg_servings_day: float | None = Field(default=None, ge=0, le=20)
    protein_g_day_estimate: float | None = Field(default=None, ge=0, le=300)
    iron_anemia_history: BinaryUnknown | None = None
    caffeine_sources: list[CaffeineSource] = Field(default_factory=list, max_length=7)
    caffeine_servings_day: float | None = Field(default=None, ge=0, le=20)
    fermented_foods_week: float | None = Field(default=None, ge=0, le=21)
    water_intake_l_day: float | None = Field(default=None, ge=0, le=10)
    screen_hours_day: float | None = Field(default=None, ge=0, le=24)
    heavy_sweat_days_week: int | None = Field(default=None, ge=0, le=7)
    headache_days_week: int | None = Field(default=None, ge=0, le=7)
    fatigue_days_week: int | None = Field(default=None, ge=0, le=7)
    alcohol_drinks_week: int | None = Field(default=None, ge=0, le=80)
    digestive_discomfort: Severidad = "nunca"
    sleep_quality: SleepQuality | None = None
    night_wakeups: NightWakeups | None = None
    caffeine_after_3pm: CaffeineAfter3pm | None = None
    exercise_days_week: int | None = Field(default=None, ge=0, le=7)
    training_type: TrainingType | None = None
    recovery_difficulty: RecoveryDifficulty | None = None
    toma_suplementos: TomaSuplementos = "no"
    suplementos_actuales: list[SuplementoActual] = Field(default_factory=list, max_length=8)
    suplementos_frecuencia: SupplementFrequency | None = None
    suplementos_dosis_conocida: bool | None = None
    suplementos_dosis_actual: dict[SuplementoActual, SuplementoDosisActual] = Field(default_factory=dict, max_length=8)
    restricciones: list[Restriccion] = Field(default_factory=list, max_length=6)
    condiciones_seguridad: list[CondicionSeguridad] = Field(default_factory=list, max_length=6)
    presupuesto: Presupuesto | None = None
    presupuesto_min: float | None = Field(default=None, ge=0, le=2000)
    presupuesto_max: float | None = Field(default=None, ge=0, le=2000)
    preferred_pack_size: Literal[3, 5] | None = 3
    lab_results: list[LabBiomarkerInput] = Field(default_factory=list, max_length=40)

    @field_validator("weight_unit")
    @classmethod
    def validate_weight_unit(cls, value: str | None) -> str | None:
        return normalize_weight_unit(value) if value else None

    @field_validator("height_unit")
    @classmethod
    def validate_height_unit(cls, value: str | None) -> str | None:
        return normalize_height_unit(value) if value else None

    @model_validator(mode="after")
    def validate_closed_answers(self):
        if self.age_years is not None:
            self.edad_rango = age_to_range(self.age_years)

        if self.weight_value is not None and self.weight_unit is not None:
            self.weight_kg = weight_to_kg(self.weight_value, self.weight_unit)
        if self.weight_kg is not None:
            if not 2 <= self.weight_kg <= 500:
                raise ValueError("Peso fuera de rango razonable.")
            self.peso_rango = weight_to_range(self.weight_kg)

        if self.height_value is not None and self.height_unit is not None:
            self.height_cm = height_to_cm(self.height_value, self.height_unit)
        if self.height_cm is not None:
            if not 40 <= self.height_cm <= 260:
                raise ValueError("Talla fuera de rango razonable.")
            self.talla_rango = height_to_range(self.height_cm)

        if self.weight_kg is not None and self.height_cm is not None:
            self.bmi = bmi(self.weight_kg, self.height_cm)

        if self.toma_suplementos == "si" and not self.suplementos_actuales:
            raise ValueError("Debe indicar qué suplementos consume actualmente.")

        if self.toma_suplementos == "no" and self.suplementos_actuales:
            raise ValueError("No puede listar suplementos si indicó que no consume suplementos.")

        if "sin_restricciones" in self.restricciones and len(self.restricciones) > 1:
            raise ValueError("Sin restricciones no puede combinarse con alergias o restricciones.")

        if "ninguna" in self.condiciones_seguridad and len(self.condiciones_seguridad) > 1:
            raise ValueError("Ninguna condición de seguridad no puede combinarse con otras condiciones.")

        if self.sexo == "masculino" and "embarazo_lactancia" in self.condiciones_seguridad:
            raise ValueError("Embarazo o lactancia no es compatible con sexo masculino.")

        if self.objetivo_principal:
            principal_to_goals = {
                "energia": ["energia"],
                "inmunidad": ["inmunidad"],
                "suenio_estres": ["suenio", "estres"],
                "rendimiento": ["rendimiento"],
                "salud_osea": ["salud_osea"],
                "cabello_piel_unas": ["cabello_piel_unas"],
                "salud_visual": ["salud_visual"],
                "digestion": ["digestion"],
                "hidratacion": ["hidratacion"],
                "salud_cardiovascular": ["salud_cardiovascular"],
                "salud_cognitiva": ["salud_cognitiva"],
                "nutricion_general": [],
            }
            objetivos = list(self.objetivos)
            for objetivo in principal_to_goals[self.objetivo_principal]:
                if objetivo not in objetivos and len(objetivos) < 4:
                    objetivos.append(objetivo)
            self.objetivos = objetivos

        if self.exercise_days_week == 0 and self.training_type not in (None, "no_aplica"):
            raise ValueError("Si no entrena en la semana, el tipo de entrenamiento debe ser no_aplica.")

        if self.exercise_days_week is not None and self.exercise_days_week > 0 and self.training_type == "no_aplica":
            raise ValueError("Si entrena al menos un dia, seleccione un tipo de entrenamiento valido.")

        if self.no_meat:
            self.red_meat_servings_week = 0
            self.poultry_servings_week = 0

        if self.meat_servings_week is None and (
            self.red_meat_servings_week is not None or self.poultry_servings_week is not None
        ):
            self.meat_servings_week = (self.red_meat_servings_week or 0) + (self.poultry_servings_week or 0)

        if self.dairy_servings_day is None and self.dairy_servings_week is not None:
            self.dairy_servings_day = round(self.dairy_servings_week / 7, 4)

        if self.toma_suplementos == "no":
            self.suplementos_frecuencia = None
            self.suplementos_dosis_conocida = None
            self.suplementos_dosis_actual = {}

        if self.toma_suplementos == "si":
            selected = set(self.suplementos_actuales)
            self.suplementos_dosis_actual = {
                key: value
                for key, value in self.suplementos_dosis_actual.items()
                if key in selected
            }
            if self.suplementos_dosis_conocida and set(self.suplementos_dosis_actual) != selected:
                raise ValueError("Si conoce la dosis, debe indicar la dosis aproximada de cada suplemento actual.")
            if not self.suplementos_dosis_conocida:
                self.suplementos_dosis_actual = {}

        if self.presupuesto == "sin_preferencia":
            self.presupuesto_min = None
            self.presupuesto_max = None

        if self.presupuesto and self.presupuesto_min is None and self.presupuesto_max is None:
            budget_ranges = {
                "bajo": (0.0, 80.0),
                "medio": (80.0, 200.0),
                "alto": (200.0, 500.0),
                "sin_preferencia": (None, None),
            }
            self.presupuesto_min, self.presupuesto_max = budget_ranges[self.presupuesto]

        return self
