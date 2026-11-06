# No todo necesita un LLM: laboratorio de PQRS con Microsoft-Decision-1

Material de la sesión de **CM Consulting** en **Microsoft 365 Live 2026**. Clasifica PQRS con `Microsoft-Decision-1` (Microsoft Foundry), redacta la respuesta con un LLM y evalúa la respuesta otra vez con Decision-1. Incluye un dataset sintético, un script que compara Decision-1 con dos GPT en precisión, latencia y costo, y la solución de punta a punta de la demo: lista de SharePoint, flujo de Power Automate, revisión humana en Teams y tablero de Power BI.

> Todos los datos son **sintéticos**. Contoso Andina es una empresa ficticia.

## Qué hay aquí

| Ruta | Qué es |
|---|---|
| `comun.py` | Autenticación con Entra ID, llamada a Decision-1 (`/providers/microsoft/v1/systemone`), llamada al LLM y la taxonomía de PQRS |
| `datos/generar_dataset.py` | Genera PQRS sintéticas: primero sortea las etiquetas (la verdad) y luego un LLM redacta un mensaje que las cumple |
| `datos/pqrs_sinteticas.jsonl` | Las 500 PQRS usadas en la sesión |
| `evaluacion/evaluar.py` | Compara Decision-1 con los LLM: exactitud, precisión/recall macro, matriz de confusión, latencia, costo y curva de umbral |
| `evaluacion/precios.json` | Precios de lista (Azure Retail Prices API, East US 2, GlobalStandard, 5-nov-2026) |
| `resultados/` | `resultados.json` y `predicciones.jsonl` de la corrida de la sesión |
| `GUIA_UMBRALES.md` | Cómo elegir el umbral de confianza y qué mandar a revisión humana |
| `sharepoint/` | `crear_lista.js` crea la lista **PQRS** con sus columnas; `cargar_historico.js` carga el histórico simulado. Se ejecutan en la consola del navegador, sobre el sitio |
| `power-automate/` | Conector personalizado de Decision-1 y el flujo de punta a punta: clasificar, calcular el plazo legal, revisión en Teams, borrador con LLM y rúbrica. Ver su `README.md` |
| `powerbi/` | Histórico simulado y el tablero (modelo TMDL + informe PBIR) creado por la API de Fabric. Ver su `README.md` |

## Cómo reproducirlo

1. Despliega `Microsoft-Decision-1` y un modelo GPT en tu recurso de Foundry:

   ```bash
   az cognitiveservices account deployment create -g <RG> -n <CUENTA> \
     --deployment-name decision-1 --model-name Microsoft-Decision-1 \
     --model-format Microsoft --model-version 1 --sku-name GlobalStandard --sku-capacity 10
   ```

2. Asígnate el rol **Cognitive Services User** en el recurso e inicia sesión con `az login`.
3. Instala las dependencias y define el endpoint:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   export AZURE_ENDPOINT="https://<tu-recurso>.cognitiveservices.azure.com"
   export LLM_DEPLOYMENTS="gpt-55,gpt-54-mini"   # tus nombres de despliegue
   ```

4. Ejecuta:

   ```bash
   python datos/generar_dataset.py 500     # opcional: ya viene el dataset
   python evaluacion/evaluar.py            # o evaluar.py 50 para una prueba rápida
   ```

Para usar tus propias PQRS, crea un `.jsonl` con los campos `asunto`, `texto`, `canal`, `tipo`, `area`, `urgencia` (0-3), `riesgo_juridico` y `completa`, **anonimizado**.

## La solución de punta a punta (demo)

```
Formulario / correo / WhatsApp ─► Lista PQRS (SharePoint) ─► Power Automate
                                                              ├─ Decision-1: tipo, área, urgencia, riesgo jurídico, completitud (1 llamada)
                                                              ├─ Plazo legal: 15 días hábiles con festivos de Colombia (Ley 1755)
                                                              ├─ ¿min(confianza) < 0,95 o riesgo jurídico? ─► tarjeta en Teams ─► una persona confirma
                                                              ├─ gpt-54-mini redacta el borrador
                                                              └─ Decision-1 lo califica con una rúbrica (reintento si < 0,7)
Lista PQRS ─► Power BI: plazos, volumen y automatización
```

Orden de montaje:

1. `sharepoint/crear_lista.js` en el sitio que quieras usar (anota el Id de la lista).
2. `power-automate/`: conector, conexiones y flujo (pasos en `power-automate/README.md`).
3. `powerbi/`: histórico opcional y tablero (pasos en `powerbi/README.md`).

Los `config.ejemplo.json` traen los campos que debes completar con los identificadores de tu tenant; tus `config.json` quedan fuera de Git.

## Una llamada a Decision-1

```json
POST {endpoint}/providers/microsoft/v1/systemone
{
  "model": "decision-1",
  "state": "Asunto: Cobro no autorizado ...",
  "questions": {
    "tipo":            { "type": "choice", "instructions": "¿Qué tipo de PQRS es?", "criteria": { "peticion": "...", "queja": "...", "reclamo": "...", "sugerencia": "...", "felicitacion": "..." } },
    "urgencia":        { "type": "score",  "instructions": "¿Qué tan urgente es?", "criteria": ["Baja", "Media", "Alta", "Crítica"] },
    "riesgo_juridico": { "type": "noul",   "instructions": "¿Menciona una acción legal o un ente de control?" }
  }
}
```

## Advertencias

- El dataset es sintético y lo redactó un modelo de la familia GPT. Con datos reales los números cambian: **mide con los tuyos**.
- Para decisiones con consecuencias sobre personas, Decision-1 es apoyo a la decisión, con revisión humana (ver la documentación de Microsoft).
- Referencia: [Deploy and use Microsoft-Decision-1 in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision).

---
CM Consulting · cmconsulting.com.co
