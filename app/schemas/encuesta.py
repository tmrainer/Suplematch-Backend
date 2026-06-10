from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.labs import LabBiomarkerInput


Sexo = Literal["femenino", "masculino", "prefiero_no_decir"]
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
    "anticoagulantes",
    "medicacion_cronica",
]
Objetivo = Literal["energia", "inmunidad", "suenio", "rendimiento", "salud_osea", "cabello_piel_unas", "estres"]


class EncuestaInput(BaseModel):
    edad_rango: Literal["menos_18", "18_30", "31_50", "mas_50"]
    horas_sueno: Literal["menos_5h", "5_7h", "7_9h", "mas_9h"]
    frecuencia_ejercicio: Literal["casi_nunca", "1_2_semana", "3_4_semana", "diario"]
    dieta: Literal["poco_variada", "regular", "bastante_variada", "muy_balanceada"]
    fatiga: Literal["siempre", "a_menudo", "a_veces", "casi_nunca"]
    exposicion_solar: Literal["menos_15min", "15_30min", "30_60min", "mas_1h"]
    frecuencia_enfermedad: Literal["muy_seguido", "3_4_anio", "1_2_anio", "casi_nunca"]
    estres: Literal["muy_alto", "alto", "moderado", "bajo"]
    alcohol: Literal["frecuente", "ocasional", "raro", "nunca"]
    sexo: Sexo = "prefiero_no_decir"
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
    objetivos: list[Objetivo] = Field(default_factory=list, max_length=4)
    toma_suplementos: TomaSuplementos = "no"
    suplementos_actuales: list[SuplementoActual] = Field(default_factory=list, max_length=8)
    restricciones: list[Restriccion] = Field(default_factory=list, max_length=6)
    condiciones_seguridad: list[CondicionSeguridad] = Field(default_factory=list, max_length=6)
    presupuesto_min: float | None = Field(default=None, ge=0, le=2000)
    presupuesto_max: float | None = Field(default=None, ge=0, le=2000)
    lab_results: list[LabBiomarkerInput] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_closed_answers(self):
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

        return self
