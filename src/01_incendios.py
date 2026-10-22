"""Paso 1: limpia los focos de Cusco y los agrupa en incendios.

Un foco de calor no es un incendio: un mismo incendio aparece como decenas de
focos en varias pasadas del satélite. Unimos los focos que están a <= 1 km y
<= 48 h entre sí; si A toca a B y B toca a C, los tres son un solo incendio.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

import config

# --- Leer y limpiar ---
tablas = []
for satelite in config.URL_FIRMS:
    tabla = pd.read_csv(config.DATOS / f"firms_{satelite}.csv")
    tabla["fuente"] = satelite
    tablas.append(tabla)
focos = pd.concat(tablas, ignore_index=True)
print(f"Focos en Sudamérica: {len(focos):,}")

focos = focos[focos["confidence"] != config.CONFIANZA_EXCLUIDA]
print(f"Sin confianza baja: {len(focos):,}")

# La hora viene como 328 en vez de "03:28"; la completamos a 4 dígitos.
hora = focos["acq_time"].astype(str).str.zfill(4)
focos["fecha_hora"] = pd.to_datetime(focos["acq_date"] + " " + hora, format="%Y-%m-%d %H%M", utc=True)

focos = gpd.GeoDataFrame(
    focos,
    geometry=gpd.points_from_xy(focos["longitude"], focos["latitude"]),
    crs="EPSG:4326",
)

# --- Quedarnos con Cusco ---
distritos = gpd.read_file(config.DATOS / "distritos.geojson")
distritos = distritos[distritos["NOMBDEP"] == config.DEPARTAMENTO]
distritos = distritos[["IDDIST", "NOMBDIST", "NOMBPROV", "geometry"]]
distritos = distritos.rename(columns={"IDDIST": "ubigeo"})

focos = gpd.sjoin(focos, distritos, predicate="within").drop(columns="index_right")
focos = focos.to_crs(config.CRS_METROS).reset_index(drop=True)
print(f"Focos en {config.DEPARTAMENTO}: {len(focos):,}")

# --- Agrupar en incendios ---
# 1) Parejas de focos a <= 1 km.
coordenadas = np.column_stack([focos.geometry.x, focos.geometry.y])
arbol = cKDTree(coordenadas)
parejas = arbol.query_pairs(r=config.DISTANCIA_MAX_M, output_type="ndarray")

# 2) De esas parejas, solo las que además están a <= 48 h.
horas = focos["fecha_hora"].astype("int64") / 3.6e12
diferencia_horas = np.abs(horas.values[parejas[:, 0]] - horas.values[parejas[:, 1]])
parejas = parejas[diferencia_horas <= config.HORAS_MAX]

# 3) Cada grupo conectado de parejas es un incendio.
n = len(focos)
conexiones = coo_matrix((np.ones(len(parejas)), (parejas[:, 0], parejas[:, 1])), shape=(n, n))
n_incendios, etiquetas = connected_components(conexiones, directed=False)
focos["incendio_id"] = etiquetas
print(f"Incendios: {n_incendios:,}")

# --- Resumen por incendio ---
incendios = focos.dissolve(
    by="incendio_id",
    aggfunc={
        "fecha_hora": ["min", "max", "count"],
        "frp": "sum",
        "NOMBDIST": lambda nombres: nombres.mode().iloc[0],
        "NOMBPROV": lambda nombres: nombres.mode().iloc[0],
        "ubigeo": lambda codigos: codigos.mode().iloc[0],
    },
)
incendios.columns = ["geometry", "inicio", "ultimo_foco", "n_focos", "frp_total", "distrito", "provincia", "ubigeo"]
incendios = incendios.reset_index()

# La envolvente de los focos da una idea del tamaño (no es el área quemada).
incendios["envolvente_ha"] = incendios.geometry.convex_hull.area / 10_000
centros = incendios.geometry.centroid.to_crs("EPSG:4326")
incendios["lat"] = centros.y
incendios["lon"] = centros.x
incendios["dias_activo"] = (incendios["ultimo_foco"] - incendios["inicio"]).dt.total_seconds() / 86400

incendios = incendios.sort_values("n_focos", ascending=False)

focos.to_file(config.DATOS / "focos_cusco.gpkg")
incendios.to_file(config.DATOS / "incendios_cusco.gpkg")

columnas = ["incendio_id", "distrito", "provincia", "n_focos", "frp_total", "envolvente_ha", "inicio", "ultimo_foco"]
pd.set_option("display.width", 200)
print(incendios[columnas].head(15).round({"frp_total": 1, "envolvente_ha": 1}).to_string(index=False))
