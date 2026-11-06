// Crea la lista «PQRS» con todas sus columnas en el sitio de SharePoint donde lo ejecutes.
//
// Uso: abre el sitio (por ejemplo https://<tenant>.sharepoint.com/sites/<tu-sitio>) con una cuenta que pueda
// crear listas, abre las herramientas de desarrollador (F12) → Consola, pega este archivo completo y pulsa Enter.
// Es idempotente: si la lista o una columna ya existe, la deja como está.
(async () => {
  // URL del sitio: https://<tenant>.sharepoint.com/sites/<sitio> (sirve en cualquier página del sitio)
  const W = location.origin + ((location.pathname.match(/^\/(sites|teams)\/[^/]+/) || [""])[0]);
  const dig = (await (await fetch(W + "/_api/contextinfo", { method: "POST", headers: { Accept: "application/json;odata=nometadata" } })).json()).FormDigestValue;
  const H = { Accept: "application/json;odata=nometadata", "Content-Type": "application/json;odata=verbose", "X-RequestDigest": dig };
  const L = W + "/_api/web/lists/getbytitle('PQRS')";
  const out = [];

  let r = await fetch(L, { headers: H });
  if (r.status === 404) {
    r = await fetch(W + "/_api/web/lists", { method: "POST", headers: H,
      body: JSON.stringify({ __metadata: { type: "SP.List" }, Title: "PQRS", BaseTemplate: 100, Description: "PQRS sintéticas de Contoso Andina" }) });
    out.push("lista " + r.status);
  } else out.push("la lista ya existe");

  const opc = (n, xs) => `<Field Type="Choice" DisplayName="${n}" Name="${n}" Format="Dropdown"><CHOICES>${xs.map((o) => `<CHOICE>${o}</CHOICE>`).join("")}</CHOICES></Field>`;
  // Nombres internos sin tildes ni espacios: el flujo y el modelo de Power BI los usan tal cual.
  const campos = [
    `<Field Type="Text" DisplayName="Radicado" Name="Radicado" />`,
    `<Field Type="Text" DisplayName="Remitente" Name="Remitente" />`,
    `<Field Type="Note" DisplayName="Texto" Name="Texto" NumLines="6" RichText="FALSE" />`,
    opc("Canal", ["Correo", "Formulario web", "WhatsApp", "Llamada"]),
    opc("Tipo", ["peticion", "queja", "reclamo", "sugerencia", "felicitacion"]),
    opc("Area", ["facturacion", "soporte_tecnico", "atencion_al_cliente", "comercial", "proteccion_de_datos"]),
    opc("Urgencia", ["Baja", "Media", "Alta", "Crítica"]),
    `<Field Type="Boolean" DisplayName="RiesgoJuridico" Name="RiesgoJuridico"><Default>0</Default></Field>`,
    `<Field Type="Boolean" DisplayName="Completa" Name="Completa"><Default>0</Default></Field>`,
    `<Field Type="Number" DisplayName="ConfianzaTipo" Name="ConfianzaTipo" Decimals="2" />`,
    `<Field Type="Number" DisplayName="ConfianzaArea" Name="ConfianzaArea" Decimals="2" />`,
    opc("Ruta", ["Automático", "Revisión humana"]),
    opc("Estado", ["Radicada", "En revisión", "Borrador listo", "Respondida"]),
    `<Field Type="DateTime" DisplayName="FechaRecibido" Name="FechaRecibido" Format="DateTime" />`,
    `<Field Type="DateTime" DisplayName="FechaVencimiento" Name="FechaVencimiento" Format="DateOnly" />`,
    `<Field Type="DateTime" DisplayName="FechaRespuesta" Name="FechaRespuesta" Format="DateTime" />`,
    `<Field Type="Note" DisplayName="Borrador" Name="Borrador" NumLines="8" RichText="FALSE" />`,
    `<Field Type="Number" DisplayName="PuntajeRubrica" Name="PuntajeRubrica" Decimals="2" />`,
    `<Field Type="Number" DisplayName="LatenciaDecisionMs" Name="LatenciaDecisionMs" Decimals="0" />`,
    `<Field Type="Text" DisplayName="Origen" Name="Origen" />`,
  ];
  const hay = (await (await fetch(L + "/fields?$select=InternalName", { headers: H })).json()).value.map((f) => f.InternalName);
  for (const x of campos) {
    const nombre = x.match(/ Name="([^"]+)"/)[1];
    if (hay.includes(nombre)) continue;
    const q = await fetch(L + "/fields/createfieldasxml", { method: "POST", headers: H,
      body: JSON.stringify({ parameters: { __metadata: { type: "SP.XmlSchemaFieldCreationInformation" }, SchemaXml: x, Options: 8 } }) });
    out.push(nombre + " " + q.status);
  }

  // Nombres visibles en español (los internos no cambian) y columnas del flujo fuera del formulario de alta.
  const M = { ...H, "X-HTTP-Method": "MERGE", "IF-MATCH": "*" };
  const visibles = { Title: "Asunto", Area: "Área", RiesgoJuridico: "Riesgo jurídico", ConfianzaTipo: "Confianza tipo",
    ConfianzaArea: "Confianza área", FechaRecibido: "Recibido", FechaVencimiento: "Vence", FechaRespuesta: "Respondida el",
    PuntajeRubrica: "Puntaje rúbrica", LatenciaDecisionMs: "Latencia Decision-1 (ms)" };
  for (const [n, t] of Object.entries(visibles))
    await fetch(`${L}/fields/getbyinternalnameortitle('${n}')`, { method: "POST", headers: M, body: JSON.stringify({ __metadata: { type: "SP.Field" }, Title: t }) });
  for (const n of ["Radicado", "Tipo", "Area", "Urgencia", "RiesgoJuridico", "Completa", "ConfianzaTipo", "ConfianzaArea", "Ruta", "Estado",
                   "FechaVencimiento", "FechaRespuesta", "Borrador", "PuntajeRubrica", "LatenciaDecisionMs", "Origen"])
    await fetch(`${L}/fields/getbyinternalnameortitle('${n}')/setshowinnewform(false)`, { method: "POST", headers: H });

  const id = (await (await fetch(L + "?$select=Id", { headers: H })).json()).Id;
  console.log(out.join(", "));
  console.log("Id de la lista (lista_id en los config.json):", id);
})();
