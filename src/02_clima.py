"""Paso 2: baja el clima diario de Open-Meteo para cada incendio.

Pedimos 14 días hacia atrás (para saber cuánto lleva sin llover) y 7 de
pronóstico (para saber qué puede pasar esta semana). Open-Meteo no pide clave.
"""

import geopandas as gpd
import pandas as pd
import requests

import config

incendios = gpd.read_file(config.DATOS / "incendios_cusco.gpkg")
incendios = incendios[incendios["n_focos"] >= config.MIN_FOCOS_INCENDIO]
print(f"Incendios con >= {config.MIN_FOCOS_INCENDIO} focos: {len(incendios)}")

# Open-Meteo acepta varias coordenadas separadas por comas en una sola consulta.
parametros = {
    "latitude": ",".join(incendios["lat"].round(4).astype(str)),
    "longitude": ",".join(incendios["lon"].round(4).astype(str)),
    "daily": ",".join([
        "temperature_2m_max",
        "relative_humidity_2m_min",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "precipitation_sum",
    ]),
    "past_days": config.DIAS_PASADOS,
    "forecast_days": config.DIAS_PRONOSTICO,
    "timezone": "America/Lima",
}
respuesta = requests.get("https://api.open-meteo.com/v1/forecast", params=parametros, timeout=120)
respuesta.raise_for_status()
resultados = respuesta.json()

tablas = []
for incendio_id, resultado in zip(incendios["incendio_id"], resultados):
    tabla = pd.DataFrame(resultado["daily"])
    tabla["incendio_id"] = incendio_id
    tabla["altitud_m"] = resultado["elevation"]
    tablas.append(tabla)

clima = pd.concat(tablas, ignore_index=True)
clima = clima.rename(columns={
    "time": "fecha",
    "temperature_2m_max": "temp_max",
    "relative_humidity_2m_min": "humedad_min",
    "wind_speed_10m_max": "viento_max",
    "wind_gusts_10m_max": "rafaga_max",
    "precipitation_sum": "lluvia_mm",
})
clima.to_csv(config.DATOS / "clima_incendios.csv", index=False)
print(clima.describe().round(1).to_string())
