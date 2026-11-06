# Power Automate: PQRS de punta a punta con Decision-1

## Qué hace el flujo «PQRS · Decision-1 de punta a punta»

| Paso | Acción | Quién |
|---|---|---|
| 1 | Entra una PQRS a la lista **PQRS** de SharePoint (desde un formulario, el correo o a mano) | Disparador de SharePoint |
| 2 | Clasifica tipo, área, urgencia, riesgo jurídico y completitud en **una sola llamada** | Decision-1 |
| 3 | Calcula el vencimiento legal: 15 días hábiles (Ley 1755 de 2015), sin fines de semana ni festivos de Colombia | Power Automate |
| 4 | Registra todo en la lista, incluida la latencia de Decision-1 | SharePoint |
| 5 | Si `min(confianza tipo, confianza área) < 0,95` o hay riesgo jurídico, envía una tarjeta adaptativa a un canal del Team y espera la confirmación | Teams + persona |
| 6 | Redacta el borrador de respuesta | gpt-54-mini |
| 7 | Califica el borrador con una rúbrica (responde todos los puntos, cita radicado y plazo, tono). Si el promedio es < 0,7, reintenta una vez con retroalimentación | Decision-1 |
| 8 | Guarda el borrador y el puntaje; estado «Borrador listo» | SharePoint |

Las preguntas de clasificación son las mismas de `comun.py`, las que se evaluaron con 500 PQRS.

## Cómo montarlo en tu entorno

1. **Conector personalizado.** Cambia `host` en `conector/apiDefinition.swagger.json` por tu recurso de Foundry y ejecuta `python conector/crear_conector.py <ENV_ID> <APP_ID> <TENANT_ID>`.
   - La app de Entra necesita el permiso delegado `user_impersonation` sobre Azure Cognitive Services.
   - El script crea el secreto, lo pasa directo al conector y registra la URL de redirección propia del conector. Sin esa URL, el consentimiento falla con AADSTS50011.
   - Tu usuario necesita el rol *Cognitive Services OpenAI User* (o *Azure AI User*) sobre el recurso de Foundry.
2. **Conexiones.** Crea en el entorno las conexiones de SharePoint, Teams y del conector, y anota sus IDs.
3. **Configuración.** Copia `flujo/config.ejemplo.json` a `flujo/config.json` y completa entorno, sitio, lista, Team, canal, conector y conexiones.
4. **Flujo.** `python flujo/crear_flujo.py flujo/config.json`. Crea el flujo (o lo actualiza si ya existe) y deja la definición en `flujo/flujo_pqrs.json`.

## Lo que hay que saber

- **El umbral (0,95) sale de la evaluación.** Con ese valor se automatiza el 66 % y lo automatizado acierta el 90,7 % en tipo y área. Mira `GUIA_UMBRALES.md` para elegir el tuyo.
- **Festivos.** La lista va de noviembre de 2026 a junio de 2027. Amplíala en `crear_flujo.py` o léela de una lista de SharePoint.
- **Disparador por sondeo.** «Cuando se crea un elemento» revisa la lista cada minuto, así que la PQRS puede tardar hasta un minuto en empezar.
- **La tarjeta de Teams espera.** El flujo queda en pausa hasta que alguien pulse *Confirmar*. La corrección se guarda en la lista y sirve para recalibrar el umbral.
- **Tarjetas adaptativas en Teams.** No pongas la propiedad `label` en los `Input.ChoiceSet`: con ella Teams no envía la respuesta al pulsar *Confirmar*. Usa un `TextBlock` encima como rótulo.
- **Identidad.** Las tres conexiones usan la cuenta de quien las creó. En producción usa una cuenta de servicio o una identidad administrada.
