"""Arma un histórico SIMULADO de PQRS (agosto–noviembre 2026) para que el tablero de Power BI tenga volumen.

- Texto, asunto, canal y etiquetas: las 500 PQRS sintéticas del dataset.
- Clasificación, confianzas y latencia: las respuestas REALES de Decision-1 en la evaluación (resultados/predicciones.jsonl).
- Ruta: la misma regla del flujo (umbral 0,95 y sin riesgo jurídico). En «Revisión humana» se asume que la persona corrigió
  a la etiqueta real; en «Automático» queda lo que dijo Decision-1, con sus errores.
- Fechas de llegada y de respuesta: SIMULADAS (semilla fija). Todas las filas llevan Origen = «Histórico simulado».
Salida: historico.json (lista de elementos listos para la lista de SharePoint).
"""
import json, random, datetime as dt, pathlib

LAB = pathlib.Path(__file__).resolve().parent.parent
rnd = random.Random(2026)
UMBRAL, PLAZO = 0.95, 15
EXCLUIR = {"PQRS-0002", "PQRS-0003", "PQRS-0018"}  # se usan en la demo en vivo
FESTIVOS = {dt.date.fromisoformat(d) for d in ["2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"]}
HOY = dt.date(2026, 11, 5)
CANAL = lambda c: "Llamada" if "llamada" in c else "Formulario web" if "formulario" in c else "WhatsApp" if "whatsapp" in c.lower() else "Correo"
URG = ["Baja", "Media", "Alta", "Crítica"]


def habil(d):
    return d.weekday() < 5 and d not in FESTIVOS


def sumar_habiles(d, n):
    while n:
        d += dt.timedelta(days=1)
        n -= habil(d)
    return d


filas = [json.loads(l) for l in open(LAB / "datos" / "pqrs_sinteticas.jsonl", encoding="utf-8")]
pred = {(c := json.loads(l))["id"]: c["decision-1"] for l in open(LAB / "resultados" / "predicciones.jsonl", encoding="utf-8")}
filas = [r for r in filas if r["id"] not in EXCLUIR]

# Llegadas: días hábiles entre el 3 de agosto y el 4 de noviembre, con algo más de volumen al final.
dias = [d for i in range(95) if habil(d := dt.date(2026, 8, 3) + dt.timedelta(days=i)) and d < HOY]
pesos = [1 + 0.6 * i / len(dias) for i in range(len(dias))]
llegadas = sorted(rnd.choices(dias, pesos, k=len(filas)))

items = []
for r, dia in zip(filas, llegadas):
    p = pred[r["id"]]
    revision = min(p["conf_tipo"], p["conf_area"]) < UMBRAL or p["riesgo_juridico"]
    tipo, area = (r["tipo"], r["area"]) if revision else (p["tipo"], p["area"])
    recibido = dt.datetime.combine(dia, dt.time(rnd.randint(7, 17), rnd.randint(0, 59))) + dt.timedelta(hours=5)  # hora Bogotá → UTC
    vence = sumar_habiles(dia, PLAZO)
    # Días hábiles hasta responder: más rápido si fue automático; algunas de revisión humana se pasan del plazo.
    habiles = rnd.randint(2, 9) if not revision else (rnd.randint(4, 14) if rnd.random() > 0.12 else rnd.randint(16, 22))
    respuesta = sumar_habiles(dia, habiles)
    item = {"Title": r["asunto"], "Texto": r["texto"], "Canal": CANAL(r["canal"]), "Origen": "Histórico simulado",
            "Radicado": f"PQRS-{dia:%Y%m%d}-H{r['id'][-4:]}", "Tipo": tipo, "Area": area, "Urgencia": URG[max(0, min(3, p["urgencia"]))],
            "RiesgoJuridico": bool(p["riesgo_juridico"]), "Completa": bool(p["completa"]),
            "ConfianzaTipo": round(p["conf_tipo"], 4), "ConfianzaArea": round(p["conf_area"], 4),
            "Ruta": "Revisión humana" if revision else "Automático", "LatenciaDecisionMs": round(p["lat"] * 1000),
            "FechaRecibido": recibido.isoformat() + "Z", "FechaVencimiento": vence.isoformat() + "T05:00:00Z"}
    if respuesta <= HOY:
        item |= {"Estado": "Respondida", "FechaRespuesta": f"{respuesta.isoformat()}T{rnd.randint(13, 22):02d}:00:00Z",
                 "PuntajeRubrica": round(rnd.uniform(0.72, 0.99), 3)}
    else:
        item |= {"Estado": "En revisión" if revision and rnd.random() < 0.5 else "Borrador listo"}
        if item["Estado"] == "Borrador listo":
            item["PuntajeRubrica"] = round(rnd.uniform(0.72, 0.99), 3)
    items.append(item)

(pathlib.Path(__file__).parent / "historico.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
auto = sum(i["Ruta"] == "Automático" for i in items)
tarde = sum(i.get("FechaRespuesta", "9")[:10] > i["FechaVencimiento"][:10] for i in items if "FechaRespuesta" in i)
print(f"{len(items)} PQRS · automáticas {auto / len(items):.1%} · respondidas {sum('FechaRespuesta' in i for i in items)} · fuera de plazo {tarde}")
