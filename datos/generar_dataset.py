"""Genera N PQRS sintéticas de la empresa ficticia Contoso Andina (servicios públicos y telecomunicaciones).

Primero se sortean las etiquetas (la verdad de referencia) y luego un LLM redacta un mensaje que las cumple.
Así el dataset trae etiquetas conocidas sin datos reales. Uso:  python datos/generar_dataset.py 500
"""
import sys, os, json, random, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comun import chat, TIPOS, AREAS, URGENCIA

N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pqrs_sinteticas.jsonl")
GEN = os.environ.get("GEN_DEPLOYMENT", "gpt-54-mini")
rnd = random.Random(2026)

# Distribución parecida a la de una entidad real: muchos reclamos y peticiones, pocas felicitaciones
P_TIPO = {"peticion": .30, "queja": .20, "reclamo": .35, "sugerencia": .08, "felicitacion": .07}
AREA_POR_TIPO = {
    "peticion": {"facturacion": .30, "soporte_tecnico": .20, "atencion_al_cliente": .10, "comercial": .30, "proteccion_de_datos": .10},
    "queja": {"facturacion": .10, "soporte_tecnico": .20, "atencion_al_cliente": .55, "comercial": .10, "proteccion_de_datos": .05},
    "reclamo": {"facturacion": .45, "soporte_tecnico": .30, "atencion_al_cliente": .05, "comercial": .12, "proteccion_de_datos": .08},
    "sugerencia": {"facturacion": .15, "soporte_tecnico": .25, "atencion_al_cliente": .35, "comercial": .20, "proteccion_de_datos": .05},
    "felicitacion": {"facturacion": .10, "soporte_tecnico": .30, "atencion_al_cliente": .50, "comercial": .10, "proteccion_de_datos": 0},
}
CANALES = ["correo al buzón de PQRS", "formulario web", "mensaje de WhatsApp transcrito", "transcripción de llamada"]
ESTILOS = ["formal y ordenado", "molesto, con mayúsculas y signos de exclamación", "breve y directo", "largo y con detalles innecesarios",
           "con faltas de ortografía", "de una persona mayor, muy cortés", "confuso, mezcla dos temas pero uno es claramente el principal"]


def pick(d):
    return rnd.choices(list(d), weights=list(d.values()))[0]


def etiquetas(i):
    tipo = pick(P_TIPO)
    area = pick(AREA_POR_TIPO[tipo])
    if tipo in ("sugerencia", "felicitacion"):
        urg = rnd.choices([0, 1], [.85, .15])[0]
        riesgo = False
    else:
        urg = rnd.choices([0, 1, 2, 3], [.20, .40, .30, .10])[0]
        riesgo = rnd.random() < (.30 if tipo == "reclamo" else .15 if tipo == "queja" else .06)
    completa = rnd.random() < .78
    return {"id": f"PQRS-{i:04d}", "tipo": tipo, "area": area, "urgencia": urg, "riesgo_juridico": riesgo, "completa": completa,
            "canal": rnd.choice(CANALES), "estilo": rnd.choice(ESTILOS)}


def redactar(e):
    pedido = f"""Escribe UNA PQRS realista en español de Colombia dirigida a Contoso Andina (empresa ficticia de energía, agua e internet).
Debe cumplir EXACTAMENTE estas etiquetas, sin nombrarlas:
- Tipo: {e['tipo']} ({TIPOS[e['tipo']]})
- Área que debe responder: {e['area']} ({AREAS[e['area']]})
- Urgencia: {URGENCIA[e['urgencia']]}
- Riesgo jurídico: {'SÍ: menciona tutela, abogado, demanda, Superintendencia o Defensoría' if e['riesgo_juridico'] else 'NO: no menciona acciones legales ni entes de control'}
- Completa: {'SÍ: incluye nombre, cédula o NIT ficticios, un correo o teléfono ficticio y los hechos' if e['completa'] else 'NO: le falta la identificación o el contacto, o los hechos son vagos'}
Canal: {e['canal']}. Estilo: {e['estilo']}. Entre 40 y 180 palabras. Datos personales inventados.
Responde solo JSON: {{"asunto": "...", "texto": "..."}}"""
    j = chat(GEN, [{"role": "user", "content": pedido}], json_mode=True, temperature=1)
    m = json.loads(j["choices"][0]["message"]["content"])
    return {**e, "asunto": m["asunto"], "texto": m["texto"]}


if __name__ == "__main__":
    import threading
    labels = [etiquetas(i + 1) for i in range(N)]
    hechas = {json.loads(l)["id"] for l in open(OUT, encoding="utf-8")} if os.path.exists(OUT) else set()
    lock = threading.Lock()

    def tarea(e):
        r = redactar(e)
        with lock, open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(tarea, [e for e in labels if e["id"] not in hechas]))
    # Ordena por id al terminar
    filas = sorted((json.loads(l) for l in open(OUT, encoding="utf-8")), key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in filas)
    print(f"{len(filas)} PQRS → {OUT}")
