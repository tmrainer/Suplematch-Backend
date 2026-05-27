from typing import Literal
from pydantic import BaseModel


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
