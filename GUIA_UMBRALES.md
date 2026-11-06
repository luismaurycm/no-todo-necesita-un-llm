# Guía para elegir umbrales de confianza y revisión humana

Decision-1 devuelve una probabilidad por opción. Esa probabilidad sirve para decidir **qué se automatiza y qué revisa una persona**. Esta guía explica cómo elegir el umbral con datos en lugar de a ojo.

## 1. La regla de enrutamiento

```
automatizar = min(confianza_tipo, confianza_area) >= UMBRAL
              y riesgo_juridico < 0,5
si no → tarjeta adaptativa en Teams para revisión humana
```

- Usa el **mínimo** de las confianzas: basta con que una decisión dude para escalar.
- El **riesgo jurídico** siempre escala, sin importar la confianza. Es una decisión con consecuencias legales.
- La **urgencia** (`score`) se usa para **ordenar la cola**, no para automatizar. En nuestra evaluación fue la decisión más subjetiva para todos los modelos (≈ 45 % de acierto exacto, ≈ 90 % con un nivel de tolerancia).

## 2. La curva de nuestra evaluación (500 PQRS sintéticas)

| Umbral | Se automatiza | Exactitud (tipo y área) de lo automatizado | A revisión humana |
|---|---|---|---|
| 0,50 | 95,2 % | 77,3 % | 4,8 % |
| 0,70 | 88,2 % | 80,5 % | 11,8 % |
| 0,80 | 82,6 % | 82,3 % | 17,4 % |
| 0,90 | 74,4 % | 87,1 % | 25,6 % |
| **0,95** | **66,4 %** | **90,7 %** | **33,6 %** |
| 0,98 | 58,4 % | 94,2 % | 41,6 % |
| 0,99 | 51,8 % | 95,4 % | 48,2 % |

Al subir el umbral, se automatiza menos, pero lo automatizado es más exacto. La probabilidad está bien ordenada: sirve para decidir.

## 3. Cómo elegir el tuyo

1. **Etiqueta entre 200 y 500 PQRS reales y anonimizadas.** Que sean representativas de todos los canales y áreas.
2. **Corre `evaluacion/evaluar.py`** con tus datos y mira `umbral_decision1` en `resultados/resultados.json`.
3. **Pon precio a los errores.** ¿Cuánto cuesta una PQRS mal enrutada (días perdidos del plazo legal, reproceso)? ¿Cuánto cuesta una revisión humana (minutos de un analista)?
4. **Elige el umbral que minimiza el costo total:** `errores_automatizados × costo_error + revisiones × costo_revision`.
5. **Revísalo cada mes** con las correcciones que hacen los analistas en Teams. Si la tasa de corrección sube, el modelo o tus categorías cambiaron.

## 4. Errores frecuentes

- **Confusiones en fronteras naturales.** En nuestra evaluación, la confusión dominante fue *petición leída como reclamo* (26 de 500): mensajes que piden revisar un cobro. Si tu taxonomía tiene fronteras borrosas, describe mejor cada opción en `criteria` o agrega una opción explícita de «no se puede determinar».
- **Redacción de las opciones.** Los puntajes cambian con la redacción y el orden de las opciones. Prueba variaciones antes de fijar el umbral.
- **Datos sintéticos no son tus datos.** Nuestro dataset lo redactó un LLM a partir de etiquetas; en datos reales el riesgo jurídico no será tan explícito (aquí los tres modelos sacaron 100 %).

## 5. Lo que muestra la tarjeta de revisión

- Texto de la PQRS y radicado.
- La sugerencia de tipo, área y urgencia, con la probabilidad de las dos opciones más altas.
- Botones para confirmar o corregir. La corrección se guarda en la lista de SharePoint para recalibrar el umbral.
