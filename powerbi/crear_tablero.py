"""Crea (o actualiza) el modelo semántico y el informe «Tablero PQRS» en un área de trabajo de Power BI vía la API de Fabric.

- Modelo: importa la lista PQRS de SharePoint (conector SharePoint.Tables) y define las medidas del tablero.
- Informe: una página en formato PBIR con indicadores de plazo legal, volumen por área, tasa de automatización y latencia.
Uso: python crear_tablero.py config.json     (copia config.ejemplo.json a config.json y complétalo)
Después hay que poner las credenciales OAuth de SharePoint en el modelo (una vez) y actualizarlo.
"""
import base64, json, pathlib, subprocess, sys, time, requests

CFG = json.loads(pathlib.Path(sys.argv[1]).read_text())
WS, SITIO, LISTA = CFG["workspace_id"], CFG["sitio"], CFG["lista_id"]
MODELO, INFORME = CFG.get("modelo", "Modelo PQRS"), CFG.get("informe", "Tablero PQRS")
AQUI = pathlib.Path(__file__).parent

tok = subprocess.check_output(["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"], text=True).strip()
H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
API = f"https://api.fabric.microsoft.com/v1/workspaces/{WS}"

# ------------------------------------------------------------------ modelo (TMDL)
COLS = [  # (nombre en el modelo, columna de SharePoint, tipo M, tipo TMDL, formato)
    ("Id", "Id", "Int64.Type", "int64", "0"), ("Radicado", "Radicado", "type text", "string", None),
    ("Asunto", "Title", "type text", "string", None), ("Canal", "Canal", "type text", "string", None),
    ("Tipo", "Tipo", "type text", "string", None), ("Área", "Area", "type text", "string", None),
    ("Urgencia", "Urgencia", "type text", "string", None), ("Riesgo jurídico", "RiesgoJuridico", "type logical", "boolean", None),
    ("Completa", "Completa", "type logical", "boolean", None), ("Confianza tipo", "ConfianzaTipo", "type number", "double", "0.0%"),
    ("Confianza área", "ConfianzaArea", "type number", "double", "0.0%"), ("Ruta", "Ruta", "type text", "string", None),
    ("Estado", "Estado", "type text", "string", None), ("Fecha recibido", "FechaRecibido", "type datetime", "dateTime", "dd/mm/yyyy hh:nn"),
    ("Fecha vencimiento", "FechaVencimiento", "type date", "dateTime", "dd/mm/yyyy"), ("Fecha respuesta", "FechaRespuesta", "type datetime", "dateTime", "dd/mm/yyyy"),
    ("Puntaje rúbrica", "PuntajeRubrica", "type number", "double", "0.00"), ("Latencia (ms)", "LatenciaDecisionMs", "type number", "double", "0"),
    ("Origen", "Origen", "type text", "string", None),
]
m = f'''let
    Fuente = SharePoint.Tables("{SITIO}", [ApiVersion = 15]),
    Lista = Fuente{{[Id = "{LISTA}"]}}[Items],
    Columnas = Table.SelectColumns(Lista, {{{", ".join(f'"{c[1]}"' for c in COLS)}}}, MissingField.UseNull),
    Nombres = Table.RenameColumns(Columnas, {{{", ".join(f'{{"{c[1]}", "{c[0]}"}}' for c in COLS if c[0] != c[1])}}}),
    Tipos = Table.TransformColumnTypes(Nombres, {{{", ".join(f'{{"{c[0]}", {c[2]}}}' for c in COLS)}}}),
    // Fechas de SharePoint vienen en UTC: se pasan a hora de Bogotá (UTC-5).
    Bogota = Table.TransformColumns(Tipos, {{{{"Fecha recibido", each if _ = null then null else _ - #duration(0, 5, 0, 0), type datetime}}, {{"Fecha respuesta", each if _ = null then null else _ - #duration(0, 5, 0, 0), type datetime}}}}),
    ConOrigen = Table.ReplaceValue(Bogota, null, "Demo en vivo", Replacer.ReplaceValue, {{"Origen"}}),
    Etiquetas = [peticion = "Petición", queja = "Queja", reclamo = "Reclamo", sugerencia = "Sugerencia", felicitacion = "Felicitación",
        facturacion = "Facturación", soporte_tecnico = "Soporte técnico", atencion_al_cliente = "Atención al cliente", comercial = "Comercial", proteccion_de_datos = "Protección de datos"],
    Legibles = Table.TransformColumns(ConOrigen, {{{{"Tipo", each if _ = null then null else Record.FieldOrDefault(Etiquetas, _, _), type text}}, {{"Área", each if _ = null then null else Record.FieldOrDefault(Etiquetas, _, _), type text}}}})
in
    Legibles'''

MEDIDAS = {
    "PQRS": ("COUNTROWS ( PQRS )", "#,0"),
    "Automatizadas": ('CALCULATE ( [PQRS], PQRS[Ruta] = "Automático" )', "#,0"),
    "% automatizadas": ("DIVIDE ( [Automatizadas], [PQRS] )", "0.0%"),
    "Abiertas": ('CALCULATE ( [PQRS], PQRS[Estado] <> "Respondida" ) + 0', "#,0"),
    "Vencidas": ('CALCULATE ( [PQRS], PQRS[Estado del plazo] = "Vencida" ) + 0', "#,0"),
    "Por vencer (3 días)": ('CALCULATE ( [PQRS], PQRS[Estado del plazo] = "Por vencer" ) + 0', "#,0"),
    # Texto: si aún no hay PQRS respondidas (por ejemplo, filtrando solo la demo en vivo) muestra «—» en vez de «(Blank)»
    "% a tiempo": ('VAR r = DIVIDE ( CALCULATE ( [PQRS], PQRS[Estado del plazo] = "Respondida a tiempo" ), CALCULATE ( [PQRS], PQRS[Estado] = "Respondida" ) ) '
                   'RETURN IF ( ISBLANK ( r ), "—", FORMAT ( r, "0.0%", "en-US" ) )', None),
    "Con riesgo jurídico": ("CALCULATE ( [PQRS], PQRS[Riesgo jurídico] = TRUE () )", "#,0"),
    "Latencia Decision-1 (ms)": ("MEDIAN ( PQRS[Latencia (ms)] )", "#,0"),
    "Confianza mínima media": ("AVERAGEX ( PQRS, MIN ( PQRS[Confianza tipo], PQRS[Confianza área] ) )", "0.0%"),
    "Puntaje medio rúbrica": ("AVERAGE ( PQRS[Puntaje rúbrica] )", "0.00"),
}
CALCULADAS = {
    "Estado del plazo": '''VAR hoy = TODAY ()
            VAR vence = PQRS[Fecha vencimiento]
            RETURN SWITCH ( TRUE (),
                PQRS[Estado] = "Respondida" && DATEVALUE ( PQRS[Fecha respuesta] ) <= vence, "Respondida a tiempo",
                PQRS[Estado] = "Respondida", "Respondida tarde",
                vence < hoy, "Vencida",
                vence <= hoy + 3, "Por vencer",
                "En plazo" )''',
    "Semana": "PQRS[Fecha recibido] - WEEKDAY ( PQRS[Fecha recibido], 3 ) - MOD ( PQRS[Fecha recibido], 1 )",
}

t = ["table PQRS", ""]
for nombre, (expr, fmt) in MEDIDAS.items():
    t += [f"\tmeasure '{nombre}' = {expr}"] + ([f"\t\tformatString: {fmt}"] if fmt else []) + [""]
for nombre, _, _, tipo, fmt in COLS:
    t += [f"\tcolumn '{nombre}'", f"\t\tdataType: {tipo}"] + ([f"\t\tformatString: {fmt}"] if fmt else []) + [f"\t\tsourceColumn: {nombre}", "\t\tsummarizeBy: none", ""]
t += ["\tcolumn 'Estado del plazo' = ```", *[f"\t\t\t{l.strip()}" for l in CALCULADAS["Estado del plazo"].splitlines()], "\t\t\t```", "\t\tdataType: string", "\t\tsummarizeBy: none", ""]
t += [f"\tcolumn Semana = {CALCULADAS['Semana']}", "\t\tdataType: dateTime", "\t\tformatString: dd/mm", "\t\tsummarizeBy: none", ""]
t += ["\tpartition PQRS = m", "\t\tmode: import", "\t\tsource = ```", *[f"\t\t\t\t{l}" for l in m.splitlines()], "\t\t\t\t```", ""]
tmdl_tabla = "\n".join(t)

modelo_partes = {
    "definition.pbism": json.dumps({"version": "4.0", "settings": {}}),
    "definition/database.tmdl": "database\n\tcompatibilityLevel: 1567\n",
    "definition/model.tmdl": "model Model\n\tculture: es-CO\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\nref table PQRS\n",
    "definition/tables/PQRS.tmdl": tmdl_tabla,
}

# ------------------------------------------------------------------ informe (PBIR)
S = "https://developer.microsoft.com/json-schemas/fabric/item/report"
med = lambda n: {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "PQRS"}}, "Property": n}}, "queryRef": f"PQRS.{n}", "nativeQueryRef": n}
col = lambda n: {"field": {"Column": {"Expression": {"SourceRef": {"Entity": "PQRS"}}, "Property": n}}, "queryRef": f"PQRS.{n}", "nativeQueryRef": n}
lit = lambda v: {"expr": {"Literal": {"Value": v}}}
titulo = lambda txt: {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{txt}'")}}]}

visuales = []
def visual(nombre, tipo, x, y, w, h, roles, titulo_txt=None, objetos=None):
    v = {"$schema": f"{S}/definition/visualContainer/1.0.0/schema.json", "name": nombre,
         "position": {"x": x, "y": y, "z": len(visuales), "width": w, "height": h},
         "visual": {"visualType": tipo, "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
                    "drillFilterOtherVisuals": True}}
    if objetos:
        v["visual"]["objects"] = objetos
    if titulo_txt:
        v["visual"]["visualContainerObjects"] = titulo(titulo_txt)
    visuales.append(v)

tarjetas = ["PQRS", "% automatizadas", "Abiertas", "Vencidas", "Por vencer (3 días)", "% a tiempo", "Latencia Decision-1 (ms)"]
ancho = (1280 - 40 - 10 * (len(tarjetas) - 1)) / len(tarjetas)
for i, n in enumerate(tarjetas):
    visual(f"tarjeta{i}", "card", 20 + i * (ancho + 10), 70, ancho, 110, {"Values": [med(n)]})

COLORES = {"Vencida": "#C4314B", "Respondida tarde": "#E8711A", "Por vencer": "#F2C80F", "En plazo": "#118DFF", "Respondida a tiempo": "#12239E"}
visual("plazos", "donutChart", 20, 195, 400, 250, {"Category": [col("Estado del plazo")], "Y": [med("PQRS")]}, "Estado del plazo legal (Ley 1755)",
       {"dataPoint": [{"properties": {"fill": {"solid": {"color": lit(f"'{c}'")}}},
                       "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": col("Estado del plazo")["field"], "Right": {"Literal": {"Value": f"'{k}'"}}}}}]}}
                      for k, c in COLORES.items()]})
visual("areas", "clusteredBarChart", 440, 195, 400, 250, {"Category": [col("Área")], "Y": [med("PQRS")]}, "Volumen por área")
visual("ruta", "clusteredColumnChart", 860, 195, 400, 250, {"Category": [col("Tipo")], "Y": [med("% automatizadas")]}, "% automatizado por tipo (umbral 0,95)")
visual("semana", "lineChart", 20, 460, 610, 240, {"Category": [col("Semana")], "Y": [med("PQRS"), med("Automatizadas")]}, "PQRS por semana: total y automatizadas")
visual("cola", "tableEx", 650, 460, 610, 240,
       {"Values": [col("Radicado"), col("Tipo"), col("Área"), col("Urgencia"), col("Fecha vencimiento"), col("Estado del plazo"), col("Origen")]},
       "Cola abierta: lo que vence primero")
visual("encabezado", "textbox", 20, 10, 900, 50, {}, None, {"general": [{"properties": {"paragraphs": [{"textRuns": [
    {"value": "PQRS Contoso Andina · Decision-1 + Power Automate", "textStyle": {"fontSize": "20pt", "fontWeight": "bold"}}]}]}}]})
visual("filtro_origen", "slicer", 940, 5, 320, 60, {"Values": [col("Origen")]}, None, {"data": [{"properties": {"mode": lit("'Dropdown'")}}]})
# La cola muestra solo lo abierto.
visuales[-3]["filterConfig"] = {"filters": [{"name": "soloAbiertas", "field": col("Estado")["field"], "type": "Categorical",
    "filter": {"Version": 2, "From": [{"Name": "p", "Entity": "PQRS", "Type": 0}],
               "Where": [{"Condition": {"Not": {"Expression": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": "Estado"}}],
                                                                       "Values": [[{"Literal": {"Value": "'Respondida'"}}]]}}}}}]}}]}
# Los textbox no llevan query.
for v in visuales:
    if v["visual"]["visualType"] == "textbox":
        v["visual"].pop("query")

informe_partes = {
    "definition.pbir": json.dumps({"$schema": f"{S}/definitionProperties/2.0.0/schema.json", "version": "4.0",
                                   "datasetReference": {"byConnection": {"connectionString": "semanticmodelid={MODELO_ID}"}}}),
    "definition/version.json": json.dumps({"$schema": f"{S}/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}),
    "definition/report.json": json.dumps({"$schema": f"{S}/definition/report/1.0.0/schema.json", "layoutOptimization": "None",
                                          "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"}}}),
    "definition/pages/pages.json": json.dumps({"$schema": f"{S}/definition/pagesMetadata/1.0.0/schema.json", "pageOrder": ["tablero"], "activePageName": "tablero"}),
    "definition/pages/tablero/page.json": json.dumps({"$schema": f"{S}/definition/page/1.0.0/schema.json", "name": "tablero",
                                                       "displayName": "Tablero PQRS", "displayOption": "FitToPage", "height": 720, "width": 1280}),
    **{f"definition/pages/tablero/visuals/{v['name']}/visual.json": json.dumps(v, ensure_ascii=False) for v in visuales},
}


# ------------------------------------------------------------------ despliegue
def partes(d):
    return {"parts": [{"path": p, "payload": base64.b64encode(c.encode()).decode(), "payloadType": "InlineBase64"} for p, c in d.items()]}


def esperar(r):
    if r.status_code == 202:
        op = r.headers["Location"]
        while True:
            time.sleep(int(r.headers.get("Retry-After", 3)))
            r = requests.get(op, headers=H)
            estado = r.json().get("status")
            if estado in ("Succeeded", "Failed"):
                if estado == "Failed":
                    sys.exit(json.dumps(r.json(), ensure_ascii=False)[:2000])
                res = requests.get(op + "/result", headers=H)
                return res.json() if res.status_code == 200 else {}
    if r.status_code >= 300:
        sys.exit(f"{r.status_code} {r.text[:2000]}")
    return r.json() if r.text else {}


def crear_o_actualizar(tipo, nombre, defin):
    items = requests.get(f"{API}/{tipo}", headers=H).json().get("value", [])
    actual = next((i for i in items if i["displayName"] == nombre), None)
    if actual:
        esperar(requests.post(f"{API}/{tipo}/{actual['id']}/updateDefinition", headers=H, json={"definition": partes(defin)}))
        return actual["id"]
    return esperar(requests.post(f"{API}/{tipo}", headers=H, json={"displayName": nombre, "definition": partes(defin)}))["id"]


(AQUI / "definicion").mkdir(exist_ok=True)
(AQUI / "definicion" / "PQRS.tmdl").write_text(tmdl_tabla, encoding="utf-8")
modelo_id = crear_o_actualizar("semanticModels", MODELO, modelo_partes)
print("modelo", modelo_id)
informe_partes["definition.pbir"] = informe_partes["definition.pbir"].replace("{MODELO_ID}", modelo_id)
informe_id = crear_o_actualizar("reports", INFORME, informe_partes)
print("informe", informe_id)
