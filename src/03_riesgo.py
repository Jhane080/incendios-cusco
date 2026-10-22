"""Paso 3: ranking de qué incendios pueden crecer esta semana.

Puntaje de 0 a 21: por cada uno de los 7 días de pronóstico suma 1 si el aire
está seco, 1 si hay ráfagas fuertes y 1 si no llueve.
"""

import geopandas as gpd
import pandas as pd

import config

clima = pd.read_csv(config.DATOS / "clima_incendios.csv", parse_dates=["fecha"])
incendios = gpd.read_file(config.DATOS / "incendios_cusco.gpkg")

hoy = pd.Timestamp.now(tz="America/Lima").normalize().tz_localize(None)
pasado = clima[clima["fecha"] < hoy].copy()
pronostico = clima[clima["fecha"] >= hoy].copy()

pronostico["dia_seco_aire"] = pronostico["humedad_min"] < config.HUMEDAD_CRITICA
pronostico["dia_ventoso"] = pronostico["rafaga_max"] > config.RAFAGA_CRITICA
pronostico["dia_sin_lluvia"] = pronostico["lluvia_mm"] < config.LLUVIA_DIA_SECO

riesgo = pronostico.groupby("incendio_id").agg(
    dias_aire_seco=("dia_seco_aire", "sum"),
    dias_ventosos=("dia_ventoso", "sum"),
    dias_sin_lluvia=("dia_sin_lluvia", "sum"),
    humedad_min_semana=("humedad_min", "min"),
    rafaga_max_semana=("rafaga_max", "max"),
    lluvia_semana_mm=("lluvia_mm", "sum"),
)
riesgo["puntaje"] = riesgo["dias_aire_seco"] + riesgo["dias_ventosos"] + riesgo["dias_sin_lluvia"]

# Cuántos días seguidos lleva sin llover hasta ayer: más días, combustible más seco.
dias_secos_seguidos = {}
for incendio_id, tabla in pasado.sort_values("fecha").groupby("incendio_id"):
    contador = 0
    for lluvia in tabla["lluvia_mm"]:
        if lluvia < config.LLUVIA_DIA_SECO:
            contador = contador + 1
        else:
            contador = 0
    dias_secos_seguidos[incendio_id] = contador
riesgo["dias_secos_previos"] = pd.Series(dias_secos_seguidos)
riesgo["lluvia_14d_mm"] = pasado.groupby("incendio_id")["lluvia_mm"].sum()
riesgo["altitud_m"] = pasado.groupby("incendio_id")["altitud_m"].first()

riesgo = incendios.merge(riesgo.reset_index(), on="incendio_id")

# Un incendio sin focos en las últimas 48 h probablemente ya se apagó.
ultimo_foco = pd.to_datetime(riesgo["ultimo_foco"], utc=True)
corte = ultimo_foco.max() - pd.Timedelta(hours=48)
riesgo["activo_48h"] = ultimo_foco >= corte

riesgo = riesgo.sort_values(["puntaje", "dias_secos_previos"], ascending=False)
riesgo.to_file(config.DATOS / "riesgo_incendios.gpkg")
riesgo.drop(columns="geometry").to_csv(config.SALIDAS / "ranking_riesgo.csv", index=False)

columnas = [
    "incendio_id", "distrito", "provincia", "n_focos", "activo_48h", "altitud_m",
    "dias_aire_seco", "dias_ventosos", "dias_sin_lluvia", "puntaje",
    "dias_secos_previos", "humedad_min_semana", "rafaga_max_semana", "lluvia_semana_mm",
]
pd.set_option("display.width", 250)
print(f"Pronóstico desde {hoy.date()}; último foco: {ultimo_foco.max()}")
print(riesgo[columnas].round(1).to_string(index=False))
