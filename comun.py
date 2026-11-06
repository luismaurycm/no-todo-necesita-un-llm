"""Utilidades compartidas del laboratorio: autenticación, llamadas a Decision-1 y al LLM, y la taxonomía de PQRS."""
import os, time, json, random, requests
from azure.identity import DefaultAzureCredential

ENDPOINT = os.environ.get("AZURE_ENDPOINT", "https://<tu-recurso>.cognitiveservices.azure.com").rstrip("/")
DECISION_DEPLOYMENT = os.environ.get("DECISION_DEPLOYMENT", "decision-1")

_cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
_tok = {"v": None, "exp": 0}


def _headers():
    if os.environ.get("AZURE_API_KEY"):
        return {"api-key": os.environ["AZURE_API_KEY"], "Content-Type": "application/json"}
    if time.time() > _tok["exp"] - 300:
        t = _cred.get_token("https://cognitiveservices.azure.com/.default")
        _tok.update(v=t.token, exp=t.expires_on)
    return {"Authorization": f"Bearer {_tok['v']}", "Content-Type": "application/json"}


def _post(url, body, retries=40):
    for i in range(retries):
        t0 = time.perf_counter()
        r = requests.post(url, headers=_headers(), json=body, timeout=120)
        lat = time.perf_counter() - t0
        if r.status_code in (429, 500, 502, 503, 504):
            h = r.headers
            espera = float(h.get("retry-after") or 0) or float(h.get("retry-after-ms") or 0) / 1000 or float(h.get("x-ratelimit-reset-requests") or 0)
            time.sleep(max(espera, min(2 ** i, 20)) + random.random() * 2)
            continue
        r.raise_for_status()
        j = r.json()
        j["_latencia_s"] = lat  # solo la petición exitosa, sin esperas por reintentos
        j["_reintentos"] = i
        return j
    r.raise_for_status()


# ---------------- Taxonomía ----------------
TIPOS = {
    "peticion": "Solicita información, un documento, un certificado o un servicio",
    "queja": "Expresa inconformidad con la atención, el trato o la conducta de un funcionario",
    "reclamo": "Exige corregir un cobro, un producto o un servicio prestado de forma deficiente",
    "sugerencia": "Propone una mejora al servicio o a un proceso",
    "felicitacion": "Reconoce o agradece un buen servicio",
}
AREAS = {
    "facturacion": "Cobros, facturas, pagos, saldos, devoluciones de dinero",
    "soporte_tecnico": "Fallas del servicio, cortes, daños, instalaciones, la app o el portal",
    "atencion_al_cliente": "Trato del personal, tiempos de espera, oficinas y canales de atención",
    "comercial": "Planes, contratos, traslados, cancelaciones y ofertas",
    "proteccion_de_datos": "Datos personales, habeas data, consentimiento, uso indebido de información",
}
URGENCIA = ["Baja", "Media", "Alta", "Crítica"]

PREGUNTAS = {
    "tipo": {"type": "choice", "instructions": "¿Qué tipo de PQRS es este mensaje?", "criteria": TIPOS},
    "area": {"type": "choice", "instructions": "¿Qué área debe responder este mensaje?", "criteria": AREAS},
    "urgencia": {"type": "score", "instructions": "¿Qué tan urgente es atender este mensaje? Crítica = riesgo para la vida, la salud o un servicio esencial suspendido; Alta = perjuicio económico actual o plazo inminente; Media = afecta al ciudadano pero puede esperar; Baja = informativo.", "criteria": URGENCIA},
    "riesgo_juridico": {"type": "noul", "instructions": "¿El mensaje menciona una acción legal, una tutela, un abogado, la Superintendencia u otro ente de control?",
                        "criteria": {"true": "Menciona o amenaza con una acción legal o un ente de control", "false": "No menciona acciones legales ni entes de control"}},
    "completa": {"type": "noul", "instructions": "¿El mensaje trae lo necesario para tramitarlo: quién lo envía (nombre o documento), cómo contactarlo y los hechos concretos?",
                 "criteria": {"true": "Trae identificación, contacto y hechos", "false": "Le falta identificación, contacto o hechos"}},
}


def decision(state, questions=PREGUNTAS):
    return _post(f"{ENDPOINT}/providers/microsoft/v1/systemone", {"model": DECISION_DEPLOYMENT, "state": state, "questions": questions})


def chat(deployment, messages, json_mode=False, **kw):
    body = {"model": deployment, "messages": messages, **kw}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return _post(f"{ENDPOINT}/openai/v1/chat/completions", body)
