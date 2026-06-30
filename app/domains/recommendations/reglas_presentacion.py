from __future__ import annotations

DISCLAIMER = (
    "Estas recomendaciones son orientativas y no reemplazan una evaluación médica. "
    "Consulta con un profesional de salud antes de iniciar suplementos, especialmente "
    "si tomas medicamentos, tienes una condición médica o estás embarazada."
)

CONDITION_LABELS = {
    "SALUDABLE": "Base saludable",
    "DEFICIT_VIT_D": "Déficit de vitamina D",
    "DEFICIT_CALCIO": "Déficit de calcio",
    "DEFICIT_B12": "Déficit de vitamina B12",
    "DEFICIT_HIERRO": "Déficit de hierro",
    "DEFICIT_FOLATO": "Déficit de folato",
    "DEFICIT_MAGNESIO": "Déficit de magnesio",
    "DEFICIT_ZINC": "Déficit de zinc",
    "RIESGO_VITAMINA_C_BAJA": "Riesgo de vitamina C baja",
    "RIESGO_OMEGA3_BAJO": "Riesgo de omega 3 bajo",
    "RIESGO_PROTEINA_INSUFICIENTE": "Riesgo de proteína insuficiente",
    "RIESGO_METABOLICO_GLUCOSA": "Riesgo metabólico por glucosa",
    "RIESGO_DISLIPIDEMIA": "Riesgo de dislipidemia",
    "RIESGO_SALUD_OSEA": "Riesgo de salud ósea",
    "SAFETY_RENAL": "Alerta renal",
    "SAFETY_HEPATICA": "Alerta hepática",
    "SAFETY_TIROIDEA": "Alerta tiroidea",
    "BAJA_INMUNIDAD": "Baja inmunidad",
    "FATIGA": "Fatiga o baja energía",
    "FATIGA_CRONICA": "Fatiga crónica",
    "ESTRES": "Estrés elevado",
    "ESTRES_SUENO": "Estrés y sueño",
    "PROBLEMAS_SUENO": "Problemas de sueño",
    "RENDIMIENTO_DEPORTIVO": "Rendimiento deportivo",
    "SALUD_OSEA": "Salud ósea",
    "SALUD_COGNITIVA": "Salud cognitiva",
    "SALUD_VISUAL": "Salud visual",
    "SALUD_DIGESTIVA": "Salud digestiva",
    "FATIGA_NUTRICIONAL": "Energía y fatiga nutricional",
    "HIDRATACION_ELECTROLITOS": "Hidratación y electrolitos",
    "SALUD_CARDIOVASCULAR_CONTEXTUAL": "Salud cardiovascular contextual",
    "SALUD_CAPILAR": "Salud capilar y piel",
    "RIESGO_CABELLO_PIEL_UNAS": "Cabello, piel y uñas",
}

TYPE_LABELS = {
    "semilla_directa": "Recomendación principal",
    "candidato_gnn": "Soporte complementario",
    "soporte_funcional": "Soporte funcional",
    "INTERACCION_RIESGOSA": "Interacción riesgosa",
}

COMPONENT_NAME_ES: dict[str, str] = {
    "vitamin b12": "Vitamina B12",
    "vitamin b6": "Vitamina B6",
    "vitamin b1": "Vitamina B1",
    "vitamin b2": "Vitamina B2",
    "vitamin c": "Vitamina C",
    "vitamin d": "Vitamina D",
    "vitamin d3": "Vitamina D3",
    "vitamin e": "Vitamina E",
    "vitamin k": "Vitamina K",
    "vitamin k2": "Vitamina K2",
    "vitamin a": "Vitamina A",
    "folic acid": "Ácido fólico",
    "folate": "Folato",
    "niacin": "Niacina",
    "choline": "Colina",
    "lutein": "Luteína",
    "zeaxanthin": "Zeaxantina",
    "pantothenic acid": "Ácido pantoténico",
    "biotin": "Biotina",
    "calcium": "Calcio",
    "magnesium": "Magnesio",
    "magnesium glycinate": "Glicinato de magnesio",
    "magnesium citrate": "Citrato de magnesio",
    "zinc": "Zinc",
    "iron": "Hierro",
    "iodine": "Yodo",
    "selenium": "Selenio",
    "copper": "Cobre",
    "manganese": "Manganeso",
    "chromium": "Cromo",
    "potassium": "Potasio",
    "sodium": "Sodio",
    "sodium chloride": "Sodio",
    "omega-3": "Omega-3",
    "omega 3": "Omega-3",
    "fish oil": "Aceite de pescado",
    "collagen": "Colágeno",
    "coenzyme q10": "Coenzima Q10",
    "coq10": "CoQ10",
    "ashwagandha": "Ashwagandha",
    "melatonin": "Melatonina",
    "probiotics": "Probióticos",
    "l-carnitine": "L-Carnitina",
    "carnitine": "Carnitina",
    "creatine": "Creatina",
    "glutamine": "Glutamina",
    "taurine": "Taurina",
    "l-taurine": "Taurina",
    "inositol": "Inositol",
    "spirulina": "Espirulina",
    "turmeric": "Cúrcuma",
    "curcumin": "Curcumina",
    "ginger": "Jengibre",
    "garlic": "Ajo",
    "green tea extract": "Extracto de té verde",
    "caffeine": "Cafeína",
    "rhodiola": "Rhodiola",
    "ginkgo biloba": "Ginkgo biloba",
    "valerian": "Valeriana",
    "passionflower": "Pasiflora",
    "chamomile": "Manzanilla",
    "evening primrose oil": "Aceite de onagra",
}


def _translate_component_name(name: str) -> str:
    return COMPONENT_NAME_ES.get(name.lower(), name)


COMPONENT_ICONS = {
    "vitamin d": "sun",
    "vitamina d": "sun",
    "calcium": "bone",
    "calcio": "bone",
    "zinc": "zap",
    "vitamin c": "citrus",
    "vitamina c": "citrus",
    "magnesium": "moon",
    "magnesio": "moon",
    "iron": "activity",
    "hierro": "activity",
    "omega": "waves",
}

COMPONENT_DOSAGE_HINTS = {
    "vitamin d": "Consultar dosis según niveles y exposición solar",
    "vitamina d": "Consultar dosis según niveles y exposición solar",
    "calcium": "Tomar según dieta y recomendación profesional",
    "calcio": "Tomar según dieta y recomendación profesional",
    "zinc": "Evitar exceder uso prolongado sin supervisión",
    "vitamin c": "Puede tomarse junto con alimentos",
    "vitamina c": "Puede tomarse junto con alimentos",
    "magnesium": "Suele tolerarse mejor por la noche",
    "magnesio": "Suele tolerarse mejor por la noche",
    "iron": "Evitar combinarlo con calcio en la misma toma",
    "hierro": "Evitar combinarlo con calcio en la misma toma",
}

CURRENT_SUPPLEMENT_KEYWORDS = {
    "vitamina_d": ("vitamin d", "vitamina d", "d3"),
    "calcio": ("calcium", "calcio"),
    "magnesio": ("magnesium", "magnesio"),
    "zinc": ("zinc",),
    "vitamina_c": ("vitamin c", "vitamina c", "ascorb"),
    "hierro": ("iron", "hierro"),
    "omega_3": ("omega", "epa", "dha"),
    "multivitaminico": ("multi",),
    "proteina": ("protein", "proteina"),
}

SECURITY_WARNING_LABELS = {
    "embarazo_lactancia": "Embarazo o lactancia: validar cualquier suplemento con un profesional de salud.",
    "enfermedad_renal": "Enfermedad renal: evitar suplementación sin evaluación médica.",
    "enfermedad_hepatica": "Enfermedad hepática: revisar seguridad y dosis con un profesional.",
    "problema_tiroideo": "Problema tiroideo: revisa yodo, algas y fórmulas tiroideas antes de consumir.",
    "anticoagulantes": "Uso de anticoagulantes: revisa interacciones, especialmente con omega 3, vitamina K y fórmulas herbales.",
    "medicacion_cronica": "Medicación crónica: confirmar posibles interacciones antes de iniciar suplementos.",
}

RESTRICTION_WARNING_LABELS = {
    "alergia_lacteos": "Alergia a lácteos: revisar excipientes y origen del producto.",
    "alergia_soya": "Alergia a soya: revisar excipientes del producto.",
    "alergia_pescado_mariscos": "Alergia a pescado o mariscos: cuidado con omega 3 de origen marino.",
    "evita_gelatina": "Evita gelatina: revisar cápsulas blandas o de origen animal.",
    "sin_gluten": "Sin gluten: verificar declaración del fabricante.",
}

HARD_SAFETY_CONDITIONS = {
    "embarazo_lactancia",
    "enfermedad_renal",
    "enfermedad_hepatica",
}

TARGETED_SAFETY_CONDITIONS = {
    "problema_tiroideo",
    "anticoagulantes",
    "medicacion_cronica",
}

CONDITION_ALIASES = {
    "ESTRES": "ESTRES_SUENO",
    "PROBLEMAS_SUENO": "ESTRES_SUENO",
    "SALUD_CAPILAR": "RIESGO_CABELLO_PIEL_UNAS",
}

NUTRITION_RISK_CONDITIONS = {
    "DEFICIT_VIT_D",
    "DEFICIT_CALCIO",
    "DEFICIT_B12",
    "DEFICIT_HIERRO",
    "DEFICIT_FOLATO",
    "DEFICIT_MAGNESIO",
    "DEFICIT_ZINC",
    "RIESGO_VITAMINA_C_BAJA",
    "RIESGO_OMEGA3_BAJO",
    "RIESGO_PROTEINA_INSUFICIENTE",
}

BIOMEDICAL_RISK_CONDITIONS = {
    "RIESGO_METABOLICO_GLUCOSA",
    "RIESGO_DISLIPIDEMIA",
    "RIESGO_SALUD_OSEA",
    "SALUD_OSEA",
}

WELLNESS_PRIORITY_CONDITIONS = {
    "BAJA_INMUNIDAD",
    "FATIGA",
    "FATIGA_CRONICA",
    "ESTRES_SUENO",
    "RENDIMIENTO_DEPORTIVO",
    "SALUD_COGNITIVA",
    "SALUD_VISUAL",
    "SALUD_DIGESTIVA",
    "FATIGA_NUTRICIONAL",
    "HIDRATACION_ELECTROLITOS",
    "SALUD_CARDIOVASCULAR_CONTEXTUAL",
    "RIESGO_CABELLO_PIEL_UNAS",
}

SAFETY_FLAG_CONDITIONS = {
    "SAFETY_RENAL",
    "SAFETY_HEPATICA",
    "SAFETY_TIROIDEA",
}
