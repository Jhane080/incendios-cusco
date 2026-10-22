"""Paso 5: NBR, dNBR, severidad y prueba de sensibilidad.

NBR = (B8A - B12) / (B8A + B12). La vegetación sana refleja mucho infrarrojo
cercano (B8A) y poco de onda corta (B12); lo quemado, al revés. Si el NBR baja
entre antes y después (dNBR alto), ese píxel se quemó.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.windows import from_bounds

import config

zona = gpd.read_file(config.DATOS / "zona_estudio.gpkg")
catalogo = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

# Cada píxel de 20 m mide 400 m2 = 0,04 ha.
HA_POR_PIXEL = 20 * 20 / 10_000


def buscar_imagen(fecha):
    busqueda = catalogo.search(
        collections=["sentinel-2-l2a"],
        bbox=zona.to_crs("EPSG:4326").total_bounds,
        datetime=fecha,
    )
    for imagen in busqueda.items():
        if config.TESELA in imagen.id:
            return imagen
    raise ValueError(f"No hay imagen de {config.TESELA} el {fecha}")


def leer_banda(imagen, banda):
    with rasterio.open(imagen.assets[banda].href) as fuente:
        limites = zona.to_crs(fuente.crs).total_bounds
        ventana = from_bounds(*limites, transform=fuente.transform).round_offsets().round_lengths()
        valores = fuente.read(1, window=ventana)
        perfil = fuente.profile
        perfil.update(
            transform=fuente.window_transform(ventana),
            width=valores.shape[1],
            height=valores.shape[0],
        )
    return valores, perfil


def calcular_nbr(fecha):
    imagen = buscar_imagen(fecha)
    b8a, perfil = leer_banda(imagen, "B8A")
    b12, _ = leer_banda(imagen, "B12")
    scl, _ = leer_banda(imagen, "SCL")

    nir = (b8a.astype("float32") + config.OFFSET_L2A) / 10_000
    swir = (b12.astype("float32") + config.OFFSET_L2A) / 10_000
    nbr = (nir - swir) / (nir + swir)

    malo = np.isin(scl, config.SCL_ENMASCARAR)
    nbr[malo] = np.nan
    print(f"{fecha}: {imagen.id} · píxeles enmascarados {malo.mean() * 100:.1f} %")
    return nbr, perfil


def hectareas_quemadas(dnbr, umbral):
    return np.nansum(dnbr >= umbral) * HA_POR_PIXEL


nbr_antes, perfil = calcular_nbr(config.FECHA_ANTES)
nbr_despues, _ = calcular_nbr(config.FECHA_DESPUES)
nbr_despues_alt, _ = calcular_nbr(config.FECHA_DESPUES_ALTERNATIVA)

dnbr = nbr_antes - nbr_despues
dnbr_alt = nbr_antes - nbr_despues_alt

perfil.update(dtype="float32", count=1, nodata=np.nan, driver="GTiff")
with rasterio.open(config.DATOS / "dnbr.tif", "w", **perfil) as destino:
    destino.write(dnbr.astype("float32"), 1)

# --- Severidad según Key & Benson (2006) ---
cortes = [-np.inf, -0.25, -0.10, 0.10, 0.27, 0.44, 0.66, np.inf]
clases = [
    "Rebrote alto",
    "Rebrote bajo",
    "No quemado",
    "Severidad baja",
    "Moderada-baja",
    "Moderada-alta",
    "Severidad alta",
]
validos = dnbr[~np.isnan(dnbr)]
conteo = pd.cut(validos, bins=cortes, labels=clases).value_counts().reindex(clases)
severidad = pd.DataFrame({"clase": clases, "hectareas": conteo.values * HA_POR_PIXEL})
severidad.to_csv(config.SALIDAS / "severidad_hectareas.csv", index=False)
print(severidad.round(1).to_string(index=False))

quemado = hectareas_quemadas(dnbr, config.UMBRAL_QUEMADO)
print(f"\nÁrea quemada (dNBR >= {config.UMBRAL_QUEMADO}): {quemado:,.0f} ha")

# --- Sensibilidad: misma zona, otra fecha y otros umbrales ---
filas = []
for umbral in config.UMBRALES_SENSIBILIDAD:
    filas.append({
        "umbral": umbral,
        f"ha_{config.FECHA_DESPUES}": hectareas_quemadas(dnbr, umbral),
        f"ha_{config.FECHA_DESPUES_ALTERNATIVA}": hectareas_quemadas(dnbr_alt, umbral),
    })
sensibilidad = pd.DataFrame(filas)
sensibilidad.to_csv(config.SALIDAS / "sensibilidad.csv", index=False)
print(sensibilidad.to_string(index=False, float_format="{:,.2f}".format))
