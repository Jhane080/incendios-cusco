"""Paso 4: busca imágenes Sentinel-2 L2A y mide las nubes DENTRO de la zona.

El % de nubes que trae cada escena es para 100 x 100 km; a nosotros solo nos
importa el rectángulo del incendio, así que lo medimos con la capa SCL.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

import config

focos = gpd.read_file(config.DATOS / "focos_cusco.gpkg")
focos = focos[focos["incendio_id"] == config.INCENDIO_ELEGIDO]

zona = focos.geometry.union_all().envelope.buffer(config.BUFFER_ZONA_M).envelope
zona = gpd.GeoDataFrame(geometry=[zona], crs=config.CRS_METROS)
zona.to_file(config.DATOS / "zona_estudio.gpkg")
print(f"Zona de estudio: {zona.area.iloc[0] / 10_000:,.0f} ha")

zona_grados = zona.to_crs("EPSG:4326").total_bounds

catalogo = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)
busqueda = catalogo.search(
    collections=["sentinel-2-l2a"],
    bbox=zona_grados,
    datetime=config.FECHA_BUSQUEDA,
)
imagenes = list(busqueda.items())
print(f"Imágenes encontradas: {len(imagenes)}")

filas = []
for imagen in imagenes:
    with rasterio.open(imagen.assets["SCL"].href) as fuente:
        limites = transform_bounds("EPSG:4326", fuente.crs, *zona_grados)
        ventana = from_bounds(*limites, transform=fuente.transform)
        scl = fuente.read(1, window=ventana, boundless=True, fill_value=0)

    sin_dato = np.isin(scl, [0]).mean() * 100
    nubes = np.isin(scl, [3, 8, 9, 10]).mean() * 100
    filas.append({
        "id": imagen.id,
        "fecha": imagen.datetime.date(),
        "nubes_escena_pct": imagen.properties["eo:cloud_cover"],
        "nubes_zona_pct": nubes,
        "sin_dato_pct": sin_dato,
        "linea_base": imagen.properties["s2:processing_baseline"],
    })

tabla = pd.DataFrame(filas).sort_values("fecha")
tabla.to_csv(config.SALIDAS / "imagenes_sentinel2.csv", index=False)
print(tabla.round(1).to_string(index=False))
