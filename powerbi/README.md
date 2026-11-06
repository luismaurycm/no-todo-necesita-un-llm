# Tablero de Power BI: plazos, volumen y automatización

Una página con:

- **Indicadores:** total de PQRS, % automatizadas, abiertas, vencidas, por vencer (3 días), % respondidas a tiempo y latencia mediana de Decision-1.
- **Estado del plazo legal:** a tiempo, tarde, en plazo, por vencer y vencida. Las vencidas salen en rojo.
- **Volumen por área.**
- **% automatizado por tipo**, con el umbral de 0,95.
- **Serie semanal:** total y automatizadas.
- **Cola abierta**, ordenada por vencimiento.
- **Filtro de origen:** «Histórico simulado» o «Demo en vivo».

## Archivos

| Archivo | Qué hace |
|---|---|
| `generar_historico.py` | Arma 497 PQRS de agosto a noviembre de 2026 a partir del dataset y de las respuestas reales de Decision-1 en la evaluación. Las fechas son simuladas y cada fila lleva `Origen = Histórico simulado`. |
| `crear_tablero.py` | Crea o actualiza el modelo semántico (TMDL, importa la lista de SharePoint) y el informe (PBIR) mediante la API de Fabric. |
| `config.ejemplo.json` | Plantilla de la configuración: cópiala a `config.json` con tu área de trabajo, sitio y lista. |
| `definicion/PQRS.tmdl` | Lo genera `crear_tablero.py`: la tabla, sus medidas y su consulta M, para revisarlas. |

## Pasos

1. **Generar el histórico:** `python powerbi/generar_historico.py`.
2. **Cargarlo en la lista PQRS** con `sharepoint/cargar_historico.js`. El flujo **no** lo procesa, porque su disparador ignora las filas que ya traen `Tipo`.
3. **Crear el tablero:** copia `powerbi/config.ejemplo.json` a `powerbi/config.json`, complétalo y ejecuta `python powerbi/crear_tablero.py powerbi/config.json`.
4. **Conectar el modelo a SharePoint, una sola vez.** En Power BI ve al modelo semántico → Configuración → Credenciales del origen de datos → OAuth2 y nivel de privacidad «Organizacional».
5. **Actualizar el modelo** desde Power BI o con `POST .../datasets/{id}/refreshes`. Es un modelo de importación, así que una PQRS nueva aparece en el tablero después de la siguiente actualización.

## Notas

- **«Estado del plazo» depende de `TODAY()`.** Se recalcula en cada actualización del modelo.
- **Vencimientos y festivos.** El vencimiento lo calcula el flujo, con días hábiles y festivos de Colombia. El histórico usa la misma regla.
- **Histórico simulado.** El histórico **no** es evidencia de desempeño: sirve para que el tablero tenga volumen. La evidencia está en `resultados/resultados.json`.
