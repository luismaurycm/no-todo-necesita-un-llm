// Carga powerbi/historico.json (497 PQRS con Origen = «Histórico simulado») en la lista «PQRS».
//
// Uso: en el sitio de SharePoint, F12 → Consola, pega este archivo y pulsa Enter. Aparece un botón arriba a la
// izquierda: haz clic y elige historico.json. Tarda uno o dos minutos.
// El flujo NO procesa estas filas: su disparador ignora las que ya traen Tipo.
(() => {
  // URL del sitio: https://<tenant>.sharepoint.com/sites/<sitio> (sirve en cualquier página del sitio)
  const W = location.origin + ((location.pathname.match(/^\/(sites|teams)\/[^/]+/) || [""])[0]);
  const entrada = Object.assign(document.createElement("input"), { type: "file", accept: ".json" });
  Object.assign(entrada.style, { position: "fixed", top: "12px", left: "12px", zIndex: 99999, background: "#fff", padding: "8px" });
  document.body.appendChild(entrada);
  entrada.onchange = async () => {
    const filas = JSON.parse(await entrada.files[0].text());
    entrada.remove();
    const dig = (await (await fetch(W + "/_api/contextinfo", { method: "POST", headers: { Accept: "application/json;odata=nometadata" } })).json()).FormDigestValue;
    const H = { Accept: "application/json;odata=nometadata", "Content-Type": "application/json;odata=nometadata", "X-RequestDigest": dig };
    let ok = 0;
    const errores = [];
    for (const f of filas) {
      const q = await fetch(W + "/_api/web/lists/getbytitle('PQRS')/items", { method: "POST", headers: H, body: JSON.stringify(f) });
      if (q.status === 201) ok++;
      else errores.push(q.status + " " + (await q.text()).slice(0, 200));
      if ((ok + errores.length) % 50 === 0) console.log(ok + errores.length, "/", filas.length);
    }
    console.log(`${ok} filas cargadas`, errores.slice(0, 3));
  };
  console.log("Haz clic en el botón de archivo (arriba a la izquierda) y elige powerbi/historico.json");
})();
