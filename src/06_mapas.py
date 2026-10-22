"""Paso 6: mapas en PNG para el README y el dashboard."""

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from rasterio.windows import from_bounds

import config

zona = gpd.read_file(config.DATOS / "zona_estudio.gpkg")
focos = gpd.read_file(config.DATOS / "focos_cusco.gpkg")
focos = focos[focos["incendio_id"] == config.INCENDIO_ELEGIDO].to_crs(zona.crs)
riesgo = gpd.read_file(config.DATOS / "riesgo_incendios.gpkg")

with rasterio.open(config.DATOS / "dnbr.tif") as fuente:
    dnbr = fuente.read(1)
    limites = fuente.bounds
extension = [limites.left, limites.right, limites.bottom, limites.top]

catalogo = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)


def leer_color_real(fecha):
    busqueda = catalogo.search(
        collections=["sentinel-2-l2a"],
        bbox=zona.to_crs("EPSG:4326").total_bounds,
        datetime=fecha,
    )
    imagen = [item for item in busqueda.items() if config.TESELA in item.id][0]
    with rasterio.open(imagen.assets["visual"].href) as fuente:
        ventana = from_bounds(*zona.to_crs(fuente.crs).total_bounds, transform=fuente.transform)
        rgb = fuente.read([1, 2, 3], window=ventana)
    return np.moveaxis(rgb, 0, -1)


# --- Mapa 1: antes, después y dNBR ---
figura, ejes = plt.subplots(1, 3, figsize=(16, 6))
ejes[0].imshow(leer_color_real(config.FECHA_ANTES), extent=extension)
ejes[0].set_title(f"Antes · {config.FECHA_ANTES}")
ejes[1].imshow(leer_color_real(config.FECHA_DESPUES), extent=extension)
ejes[1].set_title(f"Después · {config.FECHA_DESPUES}")
imagen_dnbr = ejes[2].imshow(dnbr, extent=extension, cmap="RdYlGn_r", vmin=-0.3, vmax=0.7)
ejes[2].set_title("dNBR (más rojo = más quemado)")
figura.colorbar(imagen_dnbr, ax=ejes[2], shrink=0.7)
for eje in ejes:
    eje.set_xticks([])
    eje.set_yticks([])
figura.suptitle("Incendio de Limatambo (Anta, Cusco) · Sentinel-2 L2A", fontsize=14)
figura.tight_layout()
figura.savefig(config.SALIDAS / "mapa_antes_despues_dnbr.png", dpi=130)
plt.close(figura)

# --- Mapa 2: severidad con los focos encima ---
cortes = [-1, 0.10, 0.27, 0.44, 0.66, 2]
colores = ["#f0f0f0", "#fee08b", "#fdae61", "#f46d43", "#a50026"]
nombres = ["No quemado", "Baja", "Moderada-baja", "Moderada-alta", "Alta"]
paleta = ListedColormap(colores)

figura, eje = plt.subplots(figsize=(9, 8))
eje.imshow(dnbr, extent=extension, cmap=paleta, norm=BoundaryNorm(cortes, paleta.N))
focos.plot(ax=eje, color="black", markersize=12, marker="^", label="Focos VIIRS")
leyenda = [Patch(color=color, label=nombre) for color, nombre in zip(colores, nombres)]
leyenda.append(plt.Line2D([], [], color="black", marker="^", linestyle="", label="Focos VIIRS"))
eje.legend(handles=leyenda, loc="lower right", title="Severidad (Key & Benson)")
eje.set_xticks([])
eje.set_yticks([])
eje.set_xlabel("")
eje.set_ylabel("")
eje.set_title(f"Severidad del incendio de Limatambo · {config.FECHA_ANTES} vs {config.FECHA_DESPUES}")
figura.tight_layout()
figura.savefig(config.SALIDAS / "mapa_severidad.png", dpi=130)
plt.close(figura)

# --- Gráfico 3: el cruce con el clima ---
riesgo["etiqueta"] = riesgo["distrito"].str.title() + " #" + riesgo["incendio_id"].astype(str)
riesgo = riesgo.sort_values("puntaje")
figura, eje = plt.subplots(figsize=(10, 8))
eje.barh(riesgo["etiqueta"], riesgo["dias_aire_seco"], color="#d73027", label="Días con humedad < 30 %")
eje.barh(riesgo["etiqueta"], riesgo["dias_ventosos"], left=riesgo["dias_aire_seco"],
         color="#fc8d59", label="Días con ráfagas > 40 km/h")
eje.barh(riesgo["etiqueta"], riesgo["dias_sin_lluvia"],
         left=riesgo["dias_aire_seco"] + riesgo["dias_ventosos"], color="#fee090", label="Días sin lluvia")
for posicion, (puntaje, activo) in enumerate(zip(riesgo["puntaje"], riesgo["activo_48h"])):
    if activo:
        eje.text(puntaje + 0.2, posicion, "● activo", va="center", fontsize=9, color="#a50026")
eje.set_xlabel("Puntaje de riesgo: días peligrosos en el pronóstico de 7 días (máx. 21)")
eje.set_title("¿Qué incendios de Cusco pueden crecer esta semana?")
eje.legend(loc="lower right")
eje.set_xlim(0, 21)
figura.tight_layout()
figura.savefig(config.SALIDAS / "grafico_riesgo_clima.png", dpi=130)
plt.close(figura)

print("Mapas guardados en outputs/")
