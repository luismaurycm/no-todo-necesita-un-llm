"""Crea (o actualiza) el conector personalizado «Decision-1 PQRS (Foundry)» en un entorno de Power Platform.

Usa la sesión de Azure CLI. El secreto de la app de Entra se genera aquí y va directo al conector; no se imprime ni se guarda.
Uso: python crear_conector.py <ENV_ID> <APP_ID> <TENANT_ID>
"""
import json, subprocess, sys, pathlib, requests

ENV, APP, TENANT = sys.argv[1:4]
AQUI = pathlib.Path(__file__).parent
NOMBRE = "shared_decision1-pqrs-foundry"


def az(*a):
    return subprocess.check_output(["az", *a], text=True).strip()


tok = az("account", "get-access-token", "--resource", "https://service.powerapps.com/", "--query", "accessToken", "-o", "tsv")
# Secretos huérfanos de intentos anteriores (mismo nombre): se borran solo si el conector se crea bien.
huerfanos = json.loads(az("ad", "app", "credential", "list", "--id", APP, "--query",
                          "[?displayName=='conector-power-platform'].keyId", "-o", "json"))
secreto =json.loads(az("ad", "app", "credential", "reset", "--id", APP, "--append", "--display-name", "conector-power-platform", "--years", "1", "-o", "json"))["password"]
swagger = json.loads((AQUI / "apiDefinition.swagger.json").read_text())

props = {
    "displayName": swagger["info"]["title"],
    "description": swagger["info"]["description"],
    "iconBrandColor": "#E8711A",
    "environment": {"name": ENV},
    "openApiDefinition": swagger,
    "backendService": {"serviceUrl": f"https://{swagger['host']}/"},
    "capabilities": [],
    "connectionParameters": {
        "token": {
            "type": "oauthSetting",
            "oAuthSettings": {
                "identityProvider": "aad",
                "clientId": APP,
                "clientSecret": secreto,
                "scopes": [],
                "redirectMode": "Global",
                "redirectUrl": "https://global.consent.azure-apim.net/redirect",
                "properties": {"IsFirstParty": "False", "AzureActiveDirectoryResourceId": "https://cognitiveservices.azure.com", "IsOnbehalfofLoginSupported": False},
                "customParameters": {
                    "loginUri": {"value": "https://login.windows.net"},
                    "tenantId": {"value": TENANT},
                    "resourceUri": {"value": "https://cognitiveservices.azure.com"},
                    "enableOnbehalfOfLogin": {"value": "false"},
                },
            },
        }
    },
}
url = f"https://api.powerapps.com/providers/Microsoft.PowerApps/apis?api-version=2016-11-01&$filter=environment eq '{ENV}'"
r = requests.post(url, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, json={"properties": props})
print(r.status_code, r.text[:600] if r.status_code >= 300 else r.json().get("name"))
if r.status_code < 300:
    # Cada conector personalizado usa su propia URL de redirección: hay que registrarla en la app o el consentimiento falla (AADSTS50011).
    api = r.json()["name"].removeprefix("shared_")
    az("ad", "app", "update", "--id", APP, "--web-redirect-uris", "https://global.consent.azure-apim.net/redirect",
       f"https://global.consent.azure-apim.net/redirect/{api}")
    for k in huerfanos:
        az("ad", "app", "credential", "delete", "--id", APP, "--key-id", k)
    print("secretos huérfanos borrados:", len(huerfanos))
