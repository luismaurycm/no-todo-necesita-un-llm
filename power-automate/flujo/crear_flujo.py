"""Crea (o actualiza) el flujo «PQRS · Decision-1 de punta a punta» en un entorno de Power Platform.

Qué hace el flujo, cada vez que entra una PQRS a la lista de SharePoint:
  1. Decision-1 clasifica tipo, área, urgencia, riesgo jurídico y completitud en una sola llamada.
  2. Calcula el vencimiento legal (Ley 1755 de 2015: 15 días hábiles, sin fines de semana ni festivos de Colombia).
  3. Si min(confianza tipo, confianza área) >= UMBRAL y no hay riesgo jurídico → sigue solo.
     Si no → tarjeta adaptativa en Teams y espera a que una persona confirme o corrija.
  4. gpt-54-mini redacta el borrador de respuesta.
  5. Decision-1 lo califica con una rúbrica de tres criterios; si no pasa, un reintento con retroalimentación.
  6. Todo queda registrado en la lista (incluida la latencia de Decision-1).

Uso:  python crear_flujo.py config.json          (ver config.ejemplo.json)
Usa la sesión de Azure CLI. Escribe además la definición en flujo_pqrs.json para importarla o revisarla.
"""
import json, subprocess, sys, pathlib, requests

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent.parent))
from comun import PREGUNTAS  # noqa: E402  — las mismas preguntas que se evaluaron con 500 PQRS

CFG = json.loads(pathlib.Path(sys.argv[1]).read_text())
ENV, SITIO, LISTA = CFG["entorno"], CFG["sitio"], CFG["lista_id"]
GRUPO, CANAL = CFG["team_id"], CFG["canal_id"]
CON = CFG["conexiones"]  # {"sharepoint": id, "teams": id, "decision": id}
API_DEC = CFG["api_conector"]
UMBRAL = CFG.get("umbral", 0.95)
PLAZO_DIAS = CFG.get("plazo_dias_habiles", 15)
NOMBRE = CFG.get("nombre", "PQRS · Decision-1 de punta a punta")

# Festivos de Colombia (Ley 51 de 1983 / «ley Emiliani»), noviembre 2026 – junio 2027.
FESTIVOS = ["2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25", "2027-01-01", "2027-01-11", "2027-03-22",
            "2027-03-25", "2027-03-26", "2027-05-01", "2027-05-10", "2027-05-31", "2027-06-07"]

RUBRICA = {
    "responde_puntos": {"type": "noul", "instructions": "¿El borrador responde todos los puntos que plantea la PQRS?",
                        "criteria": {"true": "Responde cada solicitud o hecho planteado", "false": "Deja sin responder algún punto"}},
    "cita_plazo": {"type": "noul", "instructions": "¿El borrador menciona el número de radicado y una fecha o plazo concreto de respuesta o solución?",
                   "criteria": {"true": "Cita radicado y una fecha o plazo concreto", "false": "No cita radicado o no da fecha o plazo"}},
    "tono_adecuado": {"type": "noul", "instructions": "¿El tono es respetuoso, empático y formal, sin prometer lo que la empresa no puede cumplir?",
                      "criteria": {"true": "Respetuoso, empático, formal y sin promesas imposibles", "false": "Tono inadecuado o promete lo que no puede cumplir"}},
}

SP = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline", "connectionName": "shared_sharepointonline"}
TEAMS = {"apiId": "/providers/Microsoft.PowerApps/apis/shared_teams", "connectionName": "shared_teams"}
DEC = {"apiId": f"/providers/Microsoft.PowerApps/apis/{API_DEC}", "connectionName": API_DEC}

T = lambda campo: f"triggerOutputs()?['body/{campo}']"
A = lambda q, k: f"body('Clasificar_con_Decision-1')?['answers']?['{q}']?['{k}']"
ESTADO = (f"@concat('Asunto: ', {T('Title')}, decodeUriComponent('%0A'), 'Canal: ', {T('Canal/Value')}, "
          f"decodeUriComponent('%0A%0A'), {T('Texto')})")


def op(host, operacion, params, after=None):
    return {"type": "OpenApiConnection", "runAfter": after or {},
            "inputs": {"host": {**host, "operationId": operacion}, "parameters": params,
                       "authentication": "@parameters('$authentication')"}}


def var(nombre, tipo, valor, after):
    return {"type": "InitializeVariable", "runAfter": {after: ["Succeeded"]} if after else {},
            "inputs": {"variables": [{"name": nombre, "type": tipo, "value": valor}]}}


def seguir(paso):
    return {paso: ["Succeeded"]}


def patch(campos, after):
    return op(SP, "PatchItem", {"dataset": SITIO, "table": LISTA, "id": f"@{T('ID')}", "item/Title": f"@{T('Title')}", **campos}, after)


# ---------- variables ----------
acciones = {}
previo = "Preparar_variables"  # una sola acción con todas las variables: el historial de ejecución queda limpio
acciones[previo] = {"type": "InitializeVariable", "runAfter": {}, "inputs": {"variables": [
    {"name": n, "type": t, "value": v} for n, t, v in [
        ("fecha", "string", "@convertFromUtc(triggerOutputs()?['body/Created'], 'SA Pacific Standard Time', 'yyyy-MM-dd')"),
        ("habiles", "integer", 0), ("festivos", "array", FESTIVOS), ("tipo", "string", ""), ("area", "string", ""),
        ("intentos", "integer", 0), ("puntaje", "float", 0), ("borrador", "string", ""), ("retro", "string", ""),
    ]]}}

# ---------- 1. clasificar ----------
acciones["Clasificar_con_Decision-1"] = op(DEC, "Decidir", {"body/model": "decision-1", "body/state": ESTADO, "body/questions": PREGUNTAS}, seguir(previo))
acciones["Guardar_tipo"] = {"type": "SetVariable", "runAfter": seguir("Clasificar_con_Decision-1"), "inputs": {"name": "tipo", "value": f"@{A('tipo', 'choice')}"}}
acciones["Guardar_area"] = {"type": "SetVariable", "runAfter": seguir("Guardar_tipo"), "inputs": {"name": "area", "value": f"@{A('area', 'choice')}"}}
acciones["Decision"] = {"type": "Compose", "runAfter": seguir("Guardar_area"), "inputs": {
    "confTipo": f"@{A('tipo', 'confidence')}",
    "confArea": f"@{A('area', 'confidence')}",
    "urgencia": f"@createArray('Baja','Media','Alta','Crítica')?[int(formatNumber(float({A('urgencia', 'score')}), '0', 'en-US'))]",
    "pRiesgo": f"@{A('riesgo_juridico', 'noul')}",
    "pCompleta": f"@{A('completa', 'noul')}",
    "ruta": f"@if(and(greaterOrEquals(min({A('tipo', 'confidence')}, {A('area', 'confidence')}), {UMBRAL}), less({A('riesgo_juridico', 'noul')}, 0.5)), 'Automático', 'Revisión humana')",
    "latenciaMs": "@div(sub(ticks(actions('Clasificar_con_Decision-1')?['endTime']), ticks(actions('Clasificar_con_Decision-1')?['startTime'])), 10000)",
    "radicado": f"@if(empty({T('Radicado')}), concat('PQRS-', formatDateTime({T('Created')}, 'yyyyMMdd'), '-', {T('ID')}), {T('Radicado')})",
}}
D = lambda k: f"outputs('Decision')?['{k}']"

# ---------- 2. plazo legal en días hábiles ----------
acciones["Calcular_vencimiento"] = {"type": "Until", "runAfter": seguir("Decision"),
    "expression": f"@greaterOrEquals(variables('habiles'), {PLAZO_DIAS})", "limit": {"count": 60, "timeout": "PT10M"},
    "actions": {
        "Dia_siguiente": {"type": "Compose", "runAfter": {}, "inputs": "@addDays(variables('fecha'), 1, 'yyyy-MM-dd')"},
        "Avanzar_fecha": {"type": "SetVariable", "runAfter": seguir("Dia_siguiente"), "inputs": {"name": "fecha", "value": "@outputs('Dia_siguiente')"}},
        "Es_habil": {"type": "If", "runAfter": seguir("Avanzar_fecha"),
            "expression": {"and": [{"not": {"equals": ["@dayOfWeek(variables('fecha'))", 0]}},
                                   {"not": {"equals": ["@dayOfWeek(variables('fecha'))", 6]}},
                                   {"not": {"contains": ["@variables('festivos')", "@variables('fecha')"]}}]},
            "actions": {"Contar_dia": {"type": "IncrementVariable", "runAfter": {}, "inputs": {"name": "habiles", "value": 1}}},
            "else": {"actions": {}}},
    }}

# ---------- 3. registrar ----------
acciones["Registrar_en_SharePoint"] = patch({
    "item/Radicado": f"@{D('radicado')}",
    "item/Tipo/Value": "@variables('tipo')", "item/Area/Value": "@variables('area')", "item/Urgencia/Value": f"@{D('urgencia')}",
    "item/RiesgoJuridico": f"@greaterOrEquals({D('pRiesgo')}, 0.5)", "item/Completa": f"@greaterOrEquals({D('pCompleta')}, 0.5)",
    "item/ConfianzaTipo": f"@{D('confTipo')}", "item/ConfianzaArea": f"@{D('confArea')}",
    "item/Ruta/Value": f"@{D('ruta')}",
    "item/Estado/Value": f"@if(equals({D('ruta')}, 'Automático'), 'Radicada', 'En revisión')",
    "item/FechaRecibido": f"@{T('Created')}", "item/FechaVencimiento": "@variables('fecha')",
    "item/LatenciaDecisionMs": f"@{D('latenciaMs')}",
}, seguir("Calcular_vencimiento"))

# ---------- 4. revisión humana en Teams ----------
pct = lambda x: f"@{{formatNumber(mul(float({x}), 100), '0')}} %"
opciones = lambda q: [{"title": k, "value": k} for k in PREGUNTAS[q]["criteria"]]
tarjeta = {
    "type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.4",
    "body": [
        {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": f"PQRS para revisar · @{{{D('radicado')}}}"},
        {"type": "TextBlock", "wrap": True, "isSubtle": True,
         "text": f"@{{if(greaterOrEquals({D('pRiesgo')}, 0.5), '⚠️ Riesgo jurídico detectado', 'Confianza por debajo del umbral de {UMBRAL}')}}"},
        {"type": "TextBlock", "weight": "Bolder", "wrap": True, "text": f"@{{{T('Title')}}}"},
        {"type": "TextBlock", "wrap": True, "text": f"@{{{T('Texto')}}}"},
        {"type": "FactSet", "facts": [
            {"title": "Tipo sugerido", "value": f"@{{variables('tipo')}} ({pct(D('confTipo'))})"},
            {"title": "Área sugerida", "value": f"@{{variables('area')}} ({pct(D('confArea'))})"},
            {"title": "Urgencia", "value": f"@{{{D('urgencia')}}}"},
            {"title": "Riesgo jurídico", "value": pct(D('pRiesgo'))},
            {"title": "Vence", "value": "@{variables('fecha')}"},
        ]},
        # Ojo: Teams no envía la respuesta si los Input llevan "label"; el rótulo va en un TextBlock aparte.
        {"type": "TextBlock", "text": "Tipo", "weight": "Bolder", "spacing": "Medium"},
        {"type": "Input.ChoiceSet", "id": "tipo", "value": "@{variables('tipo')}", "choices": opciones("tipo")},
        {"type": "TextBlock", "text": "Área", "weight": "Bolder"},
        {"type": "Input.ChoiceSet", "id": "area", "value": "@{variables('area')}", "choices": opciones("area")},
    ],
    "actions": [{"type": "Action.Submit", "title": "Confirmar"}],
}
acciones["Necesita_revision"] = {"type": "If", "runAfter": seguir("Registrar_en_SharePoint"),
    "expression": {"equals": [f"@{D('ruta')}", "Revisión humana"]},
    "actions": {
        "Tarjeta": {"type": "Compose", "runAfter": {}, "inputs": tarjeta},
        "Revisar_en_Teams": op(TEAMS, "PostCardAndWaitForResponse", {
            "poster": "Flow bot", "location": "Channel",
            "body/body/recipient/groupId": GRUPO, "body/body/recipient/channelId": CANAL,
            "body/body/messageBody": "@{string(outputs('Tarjeta'))}",
            "body/body/updateMessage": "Gracias. La PQRS sigue su curso con tu revisión.",
        }, seguir("Tarjeta")) | {"type": "OpenApiConnectionWebhook"},
        "Tipo_revisado": {"type": "SetVariable", "runAfter": seguir("Revisar_en_Teams"), "inputs": {"name": "tipo", "value": "@body('Revisar_en_Teams')?['data']?['tipo']"}},
        "Area_revisada": {"type": "SetVariable", "runAfter": seguir("Tipo_revisado"), "inputs": {"name": "area", "value": "@body('Revisar_en_Teams')?['data']?['area']"}},
        "Guardar_revision": patch({"item/Tipo/Value": "@variables('tipo')", "item/Area/Value": "@variables('area')", "item/Estado/Value": "Radicada"}, seguir("Area_revisada")),
    }, "else": {"actions": {}}}

# ---------- 5. borrador + rúbrica (un reintento con retroalimentación) ----------
SISTEMA = ("Eres analista de PQRS de Contoso Andina, empresa colombiana de servicios. Redacta en español la respuesta formal al ciudadano. "
           "Responde cada punto que plantea, menciona el número de radicado y la fecha máxima de respuesta o solución, usa un tono respetuoso y empático "
           "y no prometas lo que no puedas cumplir. Escribe texto plano, sin Markdown ni asteriscos. Máximo 180 palabras. Firma: Equipo de Atención al Ciudadano, Contoso Andina.")
P = lambda q: f"body('Calificar_con_rubrica')?['answers']?['{q}']?['noul']"
acciones["Redactar_y_calificar"] = {"type": "Until", "runAfter": seguir("Necesita_revision"),
    "expression": "@or(greaterOrEquals(variables('puntaje'), 0.7), greaterOrEquals(variables('intentos'), 2))",
    "limit": {"count": 2, "timeout": "PT15M"},
    "actions": {
        "Contar_intento": {"type": "IncrementVariable", "runAfter": {}, "inputs": {"name": "intentos", "value": 1}},
        "Redactar_con_gpt-54-mini": op(DEC, "Generar", {"body/model": "gpt-54-mini", "body/messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": f"@{{concat('Radicado: ', {D('radicado')}, ' · Tipo: ', variables('tipo'), ' · Área: ', variables('area'), ' · Fecha máxima de respuesta: ', variables('fecha'), decodeUriComponent('%0A%0A'), {ESTADO[1:]},decodeUriComponent('%0A%0A'), variables('retro'))}}"},
        ]}, seguir("Contar_intento")),
        "Guardar_borrador": {"type": "SetVariable", "runAfter": seguir("Redactar_con_gpt-54-mini"),
                             "inputs": {"name": "borrador", "value": "@body('Redactar_con_gpt-54-mini')?['choices']?[0]?['message']?['content']"}},
        "Calificar_con_rubrica": op(DEC, "Decidir", {"body/model": "decision-1", "body/questions": RUBRICA,
            "body/state": f"@concat('PQRS (radicado ', {D('radicado')}, ', fecha máxima ', variables('fecha'), '):', decodeUriComponent('%0A'), {T('Texto')}, decodeUriComponent('%0A%0A'), 'Borrador de respuesta:', decodeUriComponent('%0A'), variables('borrador'))",
        }, seguir("Guardar_borrador")),
        "Guardar_puntaje": {"type": "SetVariable", "runAfter": seguir("Calificar_con_rubrica"),
                            "inputs": {"name": "puntaje", "value": f"@div(add(add(float({P('responde_puntos')}), float({P('cita_plazo')})), float({P('tono_adecuado')})), 3)"}},
        "Retroalimentacion": {"type": "SetVariable", "runAfter": seguir("Guardar_puntaje"), "inputs": {"name": "retro", "value":
            f"@concat('Corrige tu borrador anterior. ', if(less({P('responde_puntos')}, 0.5), 'Responde todos los puntos. ', ''), "
            f"if(less({P('cita_plazo')}, 0.5), 'Cita el radicado y la fecha máxima. ', ''), if(less({P('tono_adecuado')}, 0.5), 'Ajusta el tono. ', ''), "
            "'Borrador anterior: ', variables('borrador'))"}},
    }}

acciones["Guardar_borrador_en_SharePoint"] = patch({
    "item/Borrador": "@variables('borrador')", "item/PuntajeRubrica": "@variables('puntaje')", "item/Estado/Value": "Borrador listo",
}, seguir("Redactar_y_calificar"))

definicion = {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {"$connections": {"defaultValue": {}, "type": "Object"}, "$authentication": {"defaultValue": {}, "type": "SecureObject"}},
    "triggers": {"Cuando_llega_una_PQRS": {
        "type": "OpenApiConnection", "recurrence": {"interval": 1, "frequency": "Minute"},
        "splitOn": "@triggerOutputs()?['body/value']",
        # Solo PQRS nuevas sin clasificar: el histórico que se carga ya clasificado no dispara el flujo.
        "conditions": [{"expression": "@empty(triggerOutputs()?['body/Tipo'])"}],
        "inputs": {"host": {**SP, "operationId": "GetOnNewItems"}, "parameters": {"dataset": SITIO, "table": LISTA},
                   "authentication": "@parameters('$authentication')"}}},
    "actions": acciones,
}
(AQUI / "flujo_pqrs.json").write_text(json.dumps(definicion, ensure_ascii=False, indent=2))

refs = {
    "shared_sharepointonline": {"connectionName": CON["sharepoint"], "source": "Embedded", "id": SP["apiId"], "tier": "NotSpecified"},
    "shared_teams": {"connectionName": CON["teams"], "source": "Embedded", "id": TEAMS["apiId"], "tier": "NotSpecified"},
    API_DEC: {"connectionName": CON["decision"], "source": "Embedded", "id": DEC["apiId"], "tier": "NotSpecified"},
}
tok = subprocess.check_output(["az", "account", "get-access-token", "--resource", "https://service.flow.microsoft.com/", "--query", "accessToken", "-o", "tsv"], text=True).strip()
H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
BASE = f"https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV}/flows"
cuerpo = {"properties": {"displayName": NOMBRE, "definition": definicion, "connectionReferences": refs, "state": "Started"}}
existente = next((f["name"] for f in requests.get(f"{BASE}?api-version=2016-11-01", headers=H).json().get("value", [])
                  if f["properties"]["displayName"] == NOMBRE), None)
if existente:
    r = requests.patch(f"{BASE}/{existente}?api-version=2016-11-01", headers=H, json=cuerpo)
else:
    r = requests.post(f"{BASE}?api-version=2016-11-01", headers=H, json=cuerpo)
print(r.status_code, r.text[:1500] if r.status_code >= 300 else r.json()["name"])
