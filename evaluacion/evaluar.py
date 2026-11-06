"""Evalúa Microsoft-Decision-1 frente a LLM generativos en la clasificación de PQRS.

Mide, por modelo: exactitud por pregunta, precisión/recall/F1 macro de tipo y área, matriz de confusión de tipo,
latencia (p50/p95), tokens y costo por PQRS. Para Decision-1 calcula además la curva de automatización por umbral.
Uso:  python evaluacion/evaluar.py [N]      (N = cuántas PQRS evaluar; por defecto todas)
"""
import sys, os, json, statistics, concurrent.futures as cf
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from comun import decision, chat, TIPOS, AREAS, URGENCIA, PREGUNTAS

DATA = os.path.join(BASE, "datos", "pqrs_sinteticas.jsonl")
OUT = os.path.join(BASE, "resultados")
LLMS = os.environ.get("LLM_DEPLOYMENTS", "gpt-55,gpt-54-mini").split(",")
PRECIOS = json.load(open(os.path.join(BASE, "evaluacion", "precios.json"), encoding="utf-8"))

PROMPT_LLM = f"""Eres el clasificador de PQRS de Contoso Andina. Lee el mensaje y responde SOLO un JSON con estas claves:
"tipo": uno de {json.dumps(TIPOS, ensure_ascii=False)}
"area": uno de {json.dumps(AREAS, ensure_ascii=False)}
"urgencia": entero 0-3 ({PREGUNTAS['urgencia']['instructions']} 0=Baja, 1=Media, 2=Alta, 3=Crítica)
"riesgo_juridico": true/false ({PREGUNTAS['riesgo_juridico']['instructions']})
"completa": true/false ({PREGUNTAS['completa']['instructions']})"""


def estado(r):
    return f"Asunto: {r['asunto']}\nCanal: {r['canal']}\n\n{r['texto']}"


def pred_decision(r):
    j = decision(estado(r))
    a = j["answers"]
    return {"tipo": a["tipo"]["choice"], "conf_tipo": a["tipo"]["confidence"],
            "area": a["area"]["choice"], "conf_area": a["area"]["confidence"],
            "urgencia": int(round(a["urgencia"]["score"])), "urgencia_score": a["urgencia"]["score"],
            "riesgo_juridico": a["riesgo_juridico"]["noul"] >= .5, "p_riesgo": a["riesgo_juridico"]["noul"],
            "completa": a["completa"]["noul"] >= .5, "p_completa": a["completa"]["noul"],
            "in": j["usage"]["input_tokens"], "out": j["usage"]["output_tokens"], "lat": j["_latencia_s"]}


def pred_llm(dep):
    def f(r):
        j = chat(dep, [{"role": "system", "content": PROMPT_LLM}, {"role": "user", "content": estado(r)}], json_mode=True)
        try:
            m = json.loads(j["choices"][0]["message"]["content"])
        except Exception:
            m = {}
        u = j["usage"]
        return {"tipo": m.get("tipo"), "area": m.get("area"), "urgencia": int(m.get("urgencia", -1)),
                "riesgo_juridico": bool(m.get("riesgo_juridico")), "completa": bool(m.get("completa")),
                "in": u["prompt_tokens"], "out": u["completion_tokens"], "lat": j["_latencia_s"]}
    return f


def macro(gold, pred, labels):
    p, r = [], []
    for l in labels:
        tp = sum(g == l and q == l for g, q in zip(gold, pred))
        fp = sum(g != l and q == l for g, q in zip(gold, pred))
        fn = sum(g == l and q != l for g, q in zip(gold, pred))
        p.append(tp / (tp + fp) if tp + fp else 0)
        r.append(tp / (tp + fn) if tp + fn else 0)
    P, R = sum(p) / len(p), sum(r) / len(r)
    return {"precision": P, "recall": R, "f1": 2 * P * R / (P + R) if P + R else 0}


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def resumen(nombre, filas, preds):
    acc = lambda k: sum(r[k] == p[k] for r, p in zip(filas, preds)) / len(filas)
    lat = [p["lat"] for p in preds]
    tin, tout = sum(p["in"] for p in preds), sum(p["out"] for p in preds)
    pr = PRECIOS.get(nombre, {})
    costo = (tin * pr.get("entrada_usd_por_millon", 0) + tout * pr.get("salida_usd_por_millon", 0)) / 1e6
    tipos = list(TIPOS)
    return {
        "modelo": nombre, "n": len(filas),
        "exactitud": {k: acc(k) for k in ["tipo", "area", "urgencia", "riesgo_juridico", "completa"]},
        "urgencia_a_un_nivel": sum(abs(r["urgencia"] - p["urgencia"]) <= 1 for r, p in zip(filas, preds)) / len(filas),
        "todas_correctas": sum(all(r[k] == p[k] for k in ["tipo", "area", "riesgo_juridico"]) for r, p in zip(filas, preds)) / len(filas),
        "tipo_macro": macro([r["tipo"] for r in filas], [p["tipo"] for p in preds], tipos),
        "area_macro": macro([r["area"] for r in filas], [p["area"] for p in preds], list(AREAS)),
        "matriz_tipo": {g: {q: sum(r["tipo"] == g and p["tipo"] == q for r, p in zip(filas, preds)) for q in tipos} for g in tipos},
        "latencia_s": {"p50": statistics.median(lat), "p95": pct(lat, .95), "media": statistics.mean(lat)},
        "tokens_por_pqrs": {"entrada": tin / len(filas), "salida": tout / len(filas)},
        "costo_usd_por_1000_pqrs": costo / len(filas) * 1000 if pr else None,
    }


def curva_umbral(filas, preds):
    """Si se automatiza solo cuando tipo y área superan el umbral, ¿qué % se automatiza y con qué exactitud?"""
    out = []
    for u in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99]:
        auto = [(r, p) for r, p in zip(filas, preds) if min(p["conf_tipo"], p["conf_area"]) >= u]
        ok = sum(r["tipo"] == p["tipo"] and r["area"] == p["area"] for r, p in auto)
        out.append({"umbral": u, "automatizado": len(auto) / len(filas), "exactitud_automatizadas": ok / len(auto) if auto else None,
                    "a_revision_humana": 1 - len(auto) / len(filas)})
    return out


if __name__ == "__main__":
    filas = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    if len(sys.argv) > 1:
        filas = filas[: int(sys.argv[1])]
    modelos = {"decision-1": pred_decision, **{d: pred_llm(d) for d in LLMS}}
    res, todas = {"modelos": []}, {}
    import threading
    lock = threading.Lock()
    for nombre, fn in modelos.items():
        cache_f = os.path.join(OUT, f"cache_{nombre}.jsonl")
        cache = {}
        if os.path.exists(cache_f):
            for l in open(cache_f, encoding="utf-8"):
                c = json.loads(l); cache[c["id"]] = c["pred"]

        def una(r, fn=fn, cache_f=cache_f):
            if r["id"] in cache:
                return cache[r["id"]]
            p = fn(r)
            with lock, open(cache_f, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": r["id"], "pred": p}, ensure_ascii=False) + "\n")
            return p

        with cf.ThreadPoolExecutor(int(os.environ.get("HILOS", "4"))) as ex:
            preds = list(ex.map(una, filas))
        todas[nombre] = preds
        res["modelos"].append(resumen(nombre, filas, preds))
        print(nombre, json.dumps(res["modelos"][-1]["exactitud"]), f"p50={res['modelos'][-1]['latencia_s']['p50']:.2f}s", flush=True)
    res["umbral_decision1"] = curva_umbral(filas, todas["decision-1"])
    json.dump(res, open(os.path.join(OUT, "resultados.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "predicciones.jsonl"), "w", encoding="utf-8") as f:
        for i, r in enumerate(filas):
            f.write(json.dumps({"id": r["id"], "real": {k: r[k] for k in ["tipo", "area", "urgencia", "riesgo_juridico", "completa"]},
                                **{m: todas[m][i] for m in todas}}, ensure_ascii=False) + "\n")
    print("→ resultados/resultados.json")
