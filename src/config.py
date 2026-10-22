"""Todas las decisiones de método del proyecto, en un solo lugar.

Si cambias algo aquí, vuelve a correr los scripts desde el número que lo usa.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
SALIDAS = RAIZ / "outputs"

# --- Zona ---
DEPARTAMENTO = "CUSCO"

# --- Focos de calor (NASA FIRMS, VIIRS, últimos 7 días) ---
URL_FIRMS = {
    "S-NPP": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_7d.csv",
    "NOAA-20": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_7d.csv",
}
URL_DISTRITOS = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_distrital_simple.geojson"

# Los focos de confianza baja suelen ser reflejos o suelo caliente, no fuego.
CONFIANZA_EXCLUIDA = "low"

# Dos focos son el mismo incendio si están a 1 km o menos y a 48 h o menos.
DISTANCIA_MAX_M = 1000
HORAS_MAX = 48

# EPSG:32718 (UTM 18S) mide en metros; en grados (EPSG:4326) no se pueden medir distancias.
CRS_METROS = "EPSG:32718"

# --- Clima (Open-Meteo, sin clave) ---
# Adaptamos la "regla 30-30-30" de los bomberos forestales a la sierra:
# a 3 500 m la temperatura casi nunca pasa de 30 °C, así que la quitamos y
# usamos ráfagas (no viento sostenido) porque son las que saltan el fuego.
HUMEDAD_CRITICA = 30  # % de humedad mínima del día
RAFAGA_CRITICA = 40  # km/h
LLUVIA_DIA_SECO = 1  # mm; menos que esto no moja el combustible
DIAS_PRONOSTICO = 7
DIAS_PASADOS = 14  # para contar cuántos días seguidos lleva sin llover

# Solo pedimos clima para los incendios con al menos este número de focos.
MIN_FOCOS_INCENDIO = 5

# --- Sentinel-2 y dNBR (se completa en el paso 3) ---
# Con 2 km la cicatriz se salía por el borde sur; con 5 km cabe entera y
# el incendio vecino más cercano sigue fuera (está a 19 km).
BUFFER_ZONA_M = 5000
# Limatambo (Anta): primero del ranking de riesgo, sigue activo y no es
# Curahuasi ni Huanoquite (los que usó el profesor).
INCENDIO_ELEGIDO = 1
FECHA_BUSQUEDA = "2026-09-20/2026-10-21"
# Clases SCL que tapan el suelo: 0 sin dato, 3 sombra de nube, 6 agua,
# 8 y 9 nube, 10 cirro.
SCL_ENMASCARAR = [0, 3, 6, 8, 9, 10]
# Elegidas con outputs/imagenes_sentinel2.csv (nubes medidas dentro de la zona).
# El incendio empezó el 14 oct; el 20 oct la zona estaba 100 % cubierta.
TESELA = "T18LYK"
FECHA_ANTES = "2026-10-13"  # 0 % nubes en la zona
FECHA_DESPUES = "2026-10-18"  # 0,1 % nubes en la zona
FECHA_DESPUES_ALTERNATIVA = "2026-10-17"  # 0 % nubes, para la sensibilidad
# Desde la línea base 04.00 los valores traen +1000; reflectancia = (valor - 1000) / 10000.
OFFSET_L2A = -1000
UMBRAL_QUEMADO = 0.27
UMBRALES_SENSIBILIDAD = [0.10, 0.27, 0.44]
