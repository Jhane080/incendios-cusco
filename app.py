"""Dashboard del Reto F: ¿qué incendios de Cusco pueden crecer esta semana según el clima?

Correr desde la raíz del proyecto:
    uv run streamlit run app.py

Todas las cifras se leen de data/ y outputs/. Si se recalcula el dNBR o el
ranking, basta con recargar la página.
"""

import sys

import folium
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import rasterio
import streamlit as st
from plotly.subplots import make_subplots
from rasterio.warp import transform_bounds
from streamlit_folium import st_folium

# Las decisiones de método viven en src/config.py; así el dashboard usa
# exactamente los mismos umbrales y fechas que los scripts.
sys.path.insert(0, "src")
import config  # noqa: E402

st.set_page_config(page_title="Reto F · Incendios en Cusco", layout="wide")


# --- Carga de datos ---
# cache_data evita releer los archivos cada vez que alguien mueve un control.


@st.cache_data
def cargar_datos():
    incendios = gpd.read_file(config.DATOS / "riesgo_incendios.gpkg")
    zona_estudio = gpd.read_file(config.DATOS / "zona_estudio.gpkg")
    # El ubigeo se lee como texto para no perder el cero de la izquierda.
    ranking = pd.read_csv(config.SALIDAS / "ranking_riesgo.csv", dtype={"ubigeo": str})
    clima = pd.read_csv(config.DATOS / "clima_incendios.csv", parse_dates=["fecha"])
    severidad = pd.read_csv(config.SALIDAS / "severidad_hectareas.csv")
    sensibilidad = pd.read_csv(config.SALIDAS / "sensibilidad.csv")
    imagenes = pd.read_csv(config.SALIDAS / "imagenes_sentinel2.csv", dtype={"linea_base": str})
    return incendios, zona_estudio, ranking, clima, severidad, sensibilidad, imagenes


@st.cache_data
def cargar_dnbr_como_imagen():
    with rasterio.open(config.DATOS / "dnbr.tif") as raster:
        dnbr = raster.read(1)
        # Folium dibuja en grados, así que pasamos las esquinas del raster
        # de metros (UTM 18S) a latitud y longitud.
        oeste, sur, este, norte = transform_bounds(raster.crs, "EPSG:4326", *raster.bounds)

    # Un dNBR menor a 0.10 es suelo sin cambio: lo dejamos transparente para
    # que se vea la imagen satelital debajo.
    sin_cambio = np.isnan(dnbr) | (dnbr < 0.10)

    # Escala de 0.10 (quemado leve) a 0.66 (severidad alta, Key & Benson).
    valores_escalados = np.clip((dnbr - 0.10) / (0.66 - 0.10), 0, 1)
    valores_escalados = np.nan_to_num(valores_escalados)
    paleta = matplotlib.colormaps["YlOrRd"]
    imagen_rgba = paleta(valores_escalados)
    imagen_rgba[:, :, 3] = 0.8
    imagen_rgba[sin_cambio, 3] = 0.0

    limites = [[sur, oeste], [norte, este]]
    return imagen_rgba, limites


incendios, zona_estudio, ranking, clima, severidad, sensibilidad, imagenes = cargar_datos()

# El ranking ya viene calculado; lo ordenamos por puntaje para que el
# primero sea siempre el de mayor riesgo.
ranking = ranking.sort_values("puntaje", ascending=False).reset_index(drop=True)
# Hay distritos con más de un incendio (Marangani tiene tres), así que la
# etiqueta lleva también el número del incendio.
ranking["etiqueta"] = ranking["distrito"].str.title() + " (#" + ranking["incendio_id"].astype(str) + ")"

incendio_top = ranking.iloc[0]
puntaje_maximo = 3 * config.DIAS_PRONOSTICO

columna_fecha_despues = "ha_" + config.FECHA_DESPUES
columna_fecha_alternativa = "ha_" + config.FECHA_DESPUES_ALTERNATIVA


# Buscamos las filas por umbral con np.isclose porque 0.27 guardado en un CSV
# puede leerse como 0.27000000000000002.
def hectareas_para_umbral(umbral, columna):
    fila = sensibilidad[np.isclose(sensibilidad["umbral"], umbral)]
    return float(fila[columna].iloc[0])


hectareas_quemadas = hectareas_para_umbral(config.UMBRAL_QUEMADO, columna_fecha_despues)
umbral_bajo = min(config.UMBRALES_SENSIBILIDAD)
umbral_alto = max(config.UMBRALES_SENSIBILIDAD)
hectareas_umbral_bajo = hectareas_para_umbral(umbral_bajo, columna_fecha_despues)
hectareas_umbral_alto = hectareas_para_umbral(umbral_alto, columna_fecha_despues)
hectareas_fecha_alternativa = hectareas_para_umbral(config.UMBRAL_QUEMADO, columna_fecha_alternativa)


# --- Encabezado ---

st.title("Reto F · Incendios en Cusco")
st.subheader("¿Qué incendios de Cusco pueden crecer esta semana según el clima?")

columna_1, columna_2, columna_3, columna_4 = st.columns(4)
columna_1.metric(
    "Incendios analizados en Cusco",
    len(ranking),
    help=f"{int(ranking['activo_48h'].sum())} siguen con focos en las últimas 48 h",
)
columna_2.metric(
    "Mayor puntaje de riesgo",
    f"{incendio_top['distrito'].title()}",
    f"{incendio_top['puntaje']}/{puntaje_maximo}",
    delta_color="off",
)
columna_3.metric(
    "Días seguidos sin lluvia",
    int(incendio_top["dias_secos_previos"]),
    help=f"En {incendio_top['distrito'].title()}, contando hacia atrás desde hoy (máximo {config.DIAS_PASADOS})",
)
columna_4.metric(
    "Hectáreas quemadas",
    f"{hectareas_quemadas:,.0f} ha",
    help=f"Píxeles con dNBR >= {config.UMBRAL_QUEMADO}, imagen del {config.FECHA_DESPUES}",
)

pestana_mapa, pestana_ranking, pestana_area, pestana_hallazgos, pestana_metodo = st.tabs(
    ["Mapa", "Ranking de riesgo", "Área quemada", "Hallazgos", "Método y limitaciones"]
)


# --- Pestaña 1: mapa ---

with pestana_mapa:
    st.markdown(
        "Cada círculo es un incendio; el color va de amarillo (puntaje bajo) a rojo "
        "(puntaje alto). El rectángulo es la zona de estudio del incendio elegido y "
        "la mancha de colores encima es su dNBR (cuánto cambió la vegetación)."
    )

    mapa = folium.Map(location=[-13.6, -72.0], zoom_start=8, tiles=None)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Imagen satelital",
    ).add_to(mapa)

    # La zona de estudio está en metros; folium necesita grados.
    zona_en_grados = zona_estudio.to_crs("EPSG:4326")
    folium.GeoJson(
        zona_en_grados,
        name="Zona de estudio",
        style_function=lambda _: {"color": "white", "weight": 2, "fill": False},
    ).add_to(mapa)

    imagen_dnbr, limites_dnbr = cargar_dnbr_como_imagen()
    folium.raster_layers.ImageOverlay(
        image=imagen_dnbr,
        bounds=limites_dnbr,
        name=f"dNBR del incendio #{config.INCENDIO_ELEGIDO}",
    ).add_to(mapa)

    paleta_puntaje = matplotlib.colormaps["YlOrRd"]
    for _, incendio in ranking.iterrows():
        color = matplotlib.colors.to_hex(paleta_puntaje(incendio["puntaje"] / puntaje_maximo))
        activo_texto = "Sí" if incendio["activo_48h"] else "No"
        texto_popup = (
            f"<b>{incendio['distrito'].title()}</b> (#{incendio['incendio_id']})<br>"
            f"Puntaje: {incendio['puntaje']}/{puntaje_maximo}<br>"
            f"Días seguidos sin lluvia: {incendio['dias_secos_previos']}<br>"
            f"Humedad mínima (semana): {incendio['humedad_min_semana']:.0f} %<br>"
            f"Ráfaga máxima (semana): {incendio['rafaga_max_semana']:.0f} km/h<br>"
            f"Activo en las últimas 48 h: {activo_texto}"
        )
        folium.CircleMarker(
            location=[incendio["lat"], incendio["lon"]],
            radius=6 + incendio["puntaje"] / 2,
            color="black",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(texto_popup, max_width=260),
            tooltip=incendio["etiqueta"],
        ).add_to(mapa)

    folium.LayerControl().add_to(mapa)
    # returned_objects=[] evita que cada clic en el mapa recargue la página.
    st_folium(mapa, height=600, use_container_width=True, returned_objects=[])


# --- Pestaña 2: ranking ---

with pestana_ranking:
    st.markdown(
        f"El puntaje suma, para los próximos {config.DIAS_PRONOSTICO} días: días con humedad "
        f"menor a {config.HUMEDAD_CRITICA} %, días con ráfagas mayores a {config.RAFAGA_CRITICA} km/h "
        f"y días con lluvia menor a {config.LLUVIA_DIA_SECO} mm. Máximo: {puntaje_maximo}."
    )

    columnas_tabla = {
        "etiqueta": "Incendio",
        "provincia": "Provincia",
        "ubigeo": "Ubigeo",
        "puntaje": "Puntaje",
        "dias_aire_seco": "Días aire seco",
        "dias_ventosos": "Días con ráfagas",
        "dias_sin_lluvia": "Días sin lluvia",
        "dias_secos_previos": "Días seguidos sin lluvia (pasado)",
        "humedad_min_semana": "Humedad mín. (%)",
        "rafaga_max_semana": "Ráfaga máx. (km/h)",
        "n_focos": "Focos",
        "activo_48h": "Activo 48 h",
    }
    tabla_ranking = ranking[list(columnas_tabla.keys())].rename(columns=columnas_tabla)
    st.dataframe(tabla_ranking, hide_index=True, width="stretch")

    # Para apilar barras, plotly necesita una fila por incendio y condición.
    condiciones = {
        "dias_aire_seco": f"Aire seco (humedad < {config.HUMEDAD_CRITICA} %)",
        "dias_ventosos": f"Ráfagas > {config.RAFAGA_CRITICA} km/h",
        "dias_sin_lluvia": f"Sin lluvia (< {config.LLUVIA_DIA_SECO} mm)",
    }
    ranking_largo = ranking.melt(
        id_vars="etiqueta",
        value_vars=list(condiciones.keys()),
        var_name="condicion",
        value_name="dias",
    )
    ranking_largo["condicion"] = ranking_largo["condicion"].map(condiciones)

    grafico_barras = px.bar(
        ranking_largo,
        x="etiqueta",
        y="dias",
        color="condicion",
        labels={"etiqueta": "", "dias": "Días de la semana", "condicion": "Condición"},
        title="Días de peligro en el pronóstico, por incendio",
        color_discrete_sequence=["#e6a141", "#5b8fc7", "#b5523b"],
    )
    grafico_barras.update_layout(xaxis_tickangle=-45, legend_orientation="h", legend_y=1.1)
    st.plotly_chart(grafico_barras, width="stretch")

    st.markdown("#### Pronóstico diario de un incendio")
    incendio_elegido_texto = st.selectbox("Elige un incendio", ranking["etiqueta"])
    id_seleccionado = ranking.loc[ranking["etiqueta"] == incendio_elegido_texto, "incendio_id"].iloc[0]

    # El CSV trae 14 días pasados y luego el pronóstico; nos quedamos con los
    # últimos días, que son los que entran al puntaje.
    clima_incendio = clima[clima["incendio_id"] == id_seleccionado].sort_values("fecha")
    pronostico = clima_incendio.tail(config.DIAS_PRONOSTICO)

    grafico_pronostico = make_subplots(specs=[[{"secondary_y": True}]])
    grafico_pronostico.add_trace(
        go.Bar(x=pronostico["fecha"], y=pronostico["lluvia_mm"], name="Lluvia (mm)", marker_color="#5b8fc7", opacity=0.5),
        secondary_y=True,
    )
    grafico_pronostico.add_trace(
        go.Scatter(x=pronostico["fecha"], y=pronostico["humedad_min"], name="Humedad mínima (%)", mode="lines+markers", line_color="#e6a141"),
        secondary_y=False,
    )
    grafico_pronostico.add_trace(
        go.Scatter(x=pronostico["fecha"], y=pronostico["rafaga_max"], name="Ráfaga máxima (km/h)", mode="lines+markers", line_color="#b5523b"),
        secondary_y=False,
    )
    grafico_pronostico.add_hline(
        y=config.HUMEDAD_CRITICA, line_dash="dash", line_color="#e6a141",
        annotation_text=f"Humedad crítica {config.HUMEDAD_CRITICA} %",
    )
    grafico_pronostico.add_hline(
        y=config.RAFAGA_CRITICA, line_dash="dash", line_color="#b5523b",
        annotation_text=f"Ráfaga crítica {config.RAFAGA_CRITICA} km/h",
    )
    grafico_pronostico.update_yaxes(title_text="Humedad (%) y ráfaga (km/h)", secondary_y=False)
    grafico_pronostico.update_yaxes(title_text="Lluvia (mm)", secondary_y=True, rangemode="tozero")
    grafico_pronostico.update_layout(
        title=f"Pronóstico de {config.DIAS_PRONOSTICO} días: {incendio_elegido_texto}",
        legend_orientation="h",
        legend_y=-0.2,
    )
    st.plotly_chart(grafico_pronostico, width="stretch")


# --- Pestaña 3: área quemada ---

with pestana_area:
    st.markdown(
        f"Incendio elegido: #{config.INCENDIO_ELEGIDO}. Imagen antes: {config.FECHA_ANTES}; "
        f"imagen después: {config.FECHA_DESPUES}. Se cuenta como quemado todo píxel con "
        f"dNBR >= {config.UMBRAL_QUEMADO}."
    )

    mapas_png = {
        "mapa_antes_despues_dnbr.png": "Antes, después y dNBR",
        "mapa_severidad.png": "Severidad (clases de Key & Benson)",
    }
    columnas_png = st.columns(len(mapas_png))
    posicion = 0
    for nombre_archivo, titulo in mapas_png.items():
        ruta = config.SALIDAS / nombre_archivo
        # Si alguien está recalculando, el PNG puede no existir todavía.
        if ruta.exists():
            columnas_png[posicion].image(str(ruta), caption=titulo, width="stretch")
        else:
            columnas_png[posicion].warning(f"Falta {nombre_archivo}")
        posicion = posicion + 1

    columna_severidad, columna_sensibilidad = st.columns(2)
    with columna_severidad:
        st.markdown("#### Hectáreas por clase de severidad")
        st.dataframe(
            severidad.rename(columns={"clase": "Clase", "hectareas": "Hectáreas"}),
            hide_index=True,
            width="stretch",
            column_config={"Hectáreas": st.column_config.NumberColumn(format="%.1f")},
        )
    with columna_sensibilidad:
        st.markdown("#### ¿Cuánto cambia el área con el umbral?")
        st.dataframe(
            sensibilidad.rename(
                columns={
                    "umbral": "Umbral dNBR",
                    columna_fecha_despues: f"Ha ({config.FECHA_DESPUES})",
                    columna_fecha_alternativa: f"Ha ({config.FECHA_DESPUES_ALTERNATIVA})",
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={
                f"Ha ({config.FECHA_DESPUES})": st.column_config.NumberColumn(format="%.1f"),
                f"Ha ({config.FECHA_DESPUES_ALTERNATIVA})": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    st.markdown("#### Imágenes Sentinel-2 revisadas: nubes en la escena vs. en la zona")
    tabla_imagenes = imagenes[["fecha", "id", "nubes_escena_pct", "nubes_zona_pct", "sin_dato_pct", "linea_base"]]
    st.dataframe(
        tabla_imagenes.rename(
            columns={
                "fecha": "Fecha",
                "id": "Imagen",
                "nubes_escena_pct": "Nubes escena (%)",
                "nubes_zona_pct": "Nubes zona (%)",
                "sin_dato_pct": "Sin dato (%)",
                "linea_base": "Línea base",
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Nubes escena (%)": st.column_config.NumberColumn(format="%.1f"),
            "Nubes zona (%)": st.column_config.NumberColumn(format="%.1f"),
            "Sin dato (%)": st.column_config.NumberColumn(format="%.1f"),
        },
    )


# --- Pestaña 4: hallazgos ---

with pestana_hallazgos:
    # Hallazgo 1: el incendio con más riesgo y qué lo empuja arriba.
    activo_top = "sigue activo" if incendio_top["activo_48h"] else "no tuvo focos en las últimas 48 h"
    st.markdown("#### 1. El incendio con más riesgo")
    st.markdown(
        f"**{incendio_top['distrito'].title()}** ({incendio_top['provincia'].title()}, incendio "
        f"#{incendio_top['incendio_id']}) tiene el puntaje más alto: "
        f"**{incendio_top['puntaje']} de {puntaje_maximo}**. En los próximos {config.DIAS_PRONOSTICO} días "
        f"se esperan {incendio_top['dias_aire_seco']} días con aire seco (humedad mínima de hasta "
        f"{incendio_top['humedad_min_semana']:.0f} %), {incendio_top['dias_ventosos']} días con ráfagas "
        f"fuertes (hasta {incendio_top['rafaga_max_semana']:.0f} km/h) y {incendio_top['dias_sin_lluvia']} "
        f"días sin lluvia. Además lleva {incendio_top['dias_secos_previos']} días seguidos sin llover, "
        f"así que el combustible ya está seco, y {activo_top}."
    )

    # Hallazgo 2: el área quemada depende mucho del umbral elegido.
    st.markdown("#### 2. Cuánto se quemó, y cuánto depende del umbral")
    st.markdown(
        f"Con dNBR >= {config.UMBRAL_QUEMADO}, el incendio #{config.INCENDIO_ELEGIDO} dejó "
        f"**{hectareas_quemadas:,.0f} ha quemadas** según la imagen del {config.FECHA_DESPUES} "
        f"({hectareas_fecha_alternativa:,.0f} ha con la del {config.FECHA_DESPUES_ALTERNATIVA}). "
        f"Pero si el umbral baja a {umbral_bajo} el área sube a {hectareas_umbral_bajo:,.0f} ha, y si "
        f"sube a {umbral_alto} cae a {hectareas_umbral_alto:,.0f} ha. La cifra es una estimación "
        f"que depende de una decisión, no una medición exacta."
    )

    # Hallazgo 3: el porcentaje de nubes de la escena no dice nada de la zona.
    # Elegimos como ejemplo la imagen donde más se separan las dos cifras.
    diferencia_nubes = (imagenes["nubes_escena_pct"] - imagenes["nubes_zona_pct"]).abs()
    ejemplo = imagenes.loc[diferencia_nubes.idxmax()]
    # El id es S2C_MSIL2A_<fecha>_<órbita>_<tesela>_<procesamiento>: la tesela es el 5.º trozo.
    tesela_ejemplo = ejemplo["id"].split("_")[4]
    st.markdown("#### 3. El % de nubes de la escena engaña")
    st.markdown(
        f"Cada imagen Sentinel-2 cubre unos 110 × 110 km, y el catálogo informa las nubes de toda la "
        f"escena. La imagen del **{ejemplo['fecha']}** (tesela {tesela_ejemplo}) figura con "
        f"**{ejemplo['nubes_escena_pct']:.1f} % de nubes**, pero dentro de nuestra zona de estudio solo "
        f"había **{ejemplo['nubes_zona_pct']:.1f} %**. Si hubiéramos filtrado por el dato del catálogo, "
        f"habríamos descartado una imagen útil (o aceptado una inútil). Por eso medimos las nubes "
        f"con la máscara SCL dentro de la zona."
    )


# --- Pestaña 5: método y limitaciones ---

with pestana_metodo:
    st.markdown("#### Método")
    st.markdown(
        f"""
1. **Focos de calor.** NASA FIRMS, sensor VIIRS (S-NPP y NOAA-20), últimos 7 días, sin los focos
   de confianza baja (suelen ser reflejos o suelo caliente).
2. **De focos a incendios.** Dos focos son el mismo incendio si están a {config.DISTANCIA_MAX_M / 1000:.0f} km
   o menos y a {config.HORAS_MAX} h o menos uno del otro.
3. **Clima.** Open-Meteo: {config.DIAS_PASADOS} días pasados y {config.DIAS_PRONOSTICO} días de pronóstico
   para cada incendio.
4. **Puntaje de riesgo** (0 a {puntaje_maximo}) = días con humedad < {config.HUMEDAD_CRITICA} % + días con
   ráfagas > {config.RAFAGA_CRITICA} km/h + días con lluvia < {config.LLUVIA_DIA_SECO} mm. Es la "regla
   30-30-30" de los bomberos forestales adaptada a la sierra: quitamos la temperatura porque a
   unos 3 500 m casi nunca pasa de 30 °C, y usamos ráfagas porque son las que hacen saltar el fuego.
5. **Área quemada.** Sentinel-2 L2A de Microsoft Planetary Computer, bandas B8A y B12 a 20 m,
   con offset {config.OFFSET_L2A} (línea base 04.00 en adelante) y máscara de nubes SCL.
   dNBR = NBR antes ({config.FECHA_ANTES}) − NBR después ({config.FECHA_DESPUES}); quemado si
   dNBR >= {config.UMBRAL_QUEMADO}.
"""
    )

    st.markdown("#### Limitaciones")
    st.markdown(
        """
- **Un foco de calor no es un incendio.** Puede ser una quema agrícola controlada o una superficie caliente.
- **Las nubes y el humo esconden el fuego.** Un incendio bajo nubes no aparece en FIRMS ni en Sentinel-2.
- **El pronóstico es de una celda de unos 11 km.** No ve el viento de valle ni las diferencias de altura
  dentro de la celda, que en la sierra pueden ser enormes.
- **El puntaje no está validado.** No lo hemos comparado contra el crecimiento real de los incendios;
  ordena por condiciones de clima, no predice.
- **El umbral cambia mucho el área.** Ver la tabla de sensibilidad en la pestaña "Área quemada".
"""
    )
