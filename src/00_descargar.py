"""Paso 0: descarga los focos de calor de los últimos 7 días y los límites distritales."""

import requests

import config

config.DATOS.mkdir(exist_ok=True)

for satelite, url in config.URL_FIRMS.items():
    destino = config.DATOS / f"firms_{satelite}.csv"
    respuesta = requests.get(url, timeout=120)
    respuesta.raise_for_status()
    destino.write_bytes(respuesta.content)
    print(f"{satelite}: {len(respuesta.content) / 1e6:.1f} MB -> {destino.name}")

respuesta = requests.get(config.URL_DISTRITOS, timeout=120)
respuesta.raise_for_status()
(config.DATOS / "distritos.geojson").write_bytes(respuesta.content)
print("Distritos descargados")
