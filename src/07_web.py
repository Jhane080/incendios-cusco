"""Paso 7: arma una página web de un solo archivo (docs/index.html).

Todo va dentro del HTML (también los mapas, como texto base64) para poder
subirlo a claude.ai y publicarlo como artefacto sin depender de otros archivos.
"""

import base64
import io

import pandas as pd
from PIL import Image

import config


def imagen_en_texto(nombre_png):
    # Pasamos a JPEG más chico para que la página no pese varios MB.
    imagen = Image.open(config.SALIDAS / nombre_png).convert("RGB")
    imagen.thumbnail((1100, 1100))
    memoria = io.BytesIO()
    imagen.save(memoria, format="JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(memoria.getvalue()).decode()


ranking = pd.read_csv(config.SALIDAS / "ranking_riesgo.csv")
severidad = pd.read_csv(config.SALIDAS / "severidad_hectareas.csv")
sensibilidad = pd.read_csv(config.SALIDAS / "sensibilidad.csv")
imagenes = pd.read_csv(config.SALIDAS / "imagenes_sentinel2.csv")

columna_principal = f"ha_{config.FECHA_DESPUES}"
columna_alternativa = f"ha_{config.FECHA_DESPUES_ALTERNATIVA}"
fila_estandar = sensibilidad[sensibilidad["umbral"].round(2) == config.UMBRAL_QUEMADO].iloc[0]
fila_baja = sensibilidad.iloc[0]
fila_alta = sensibilidad.iloc[-1]
hectareas = fila_estandar[columna_principal]

primero = ranking.iloc[0]
nombre_primero = primero["distrito"].title()

# --- Barras del ranking (HTML puro, sin librerías externas) ---
filas_ranking = ""
for _, incendio in ranking.iterrows():
    ancho_seco = incendio["dias_aire_seco"] / 21 * 100
    ancho_viento = incendio["dias_ventosos"] / 21 * 100
    ancho_lluvia = incendio["dias_sin_lluvia"] / 21 * 100
    marca_activo = '<span class="activo">● activo</span>' if incendio["activo_48h"] else ""
    filas_ranking += f"""
    <div class="fila">
      <div class="nombre">{incendio["distrito"].title()} #{incendio["incendio_id"]}</div>
      <div class="barra">
        <span class="seco" style="width:{ancho_seco:.1f}%"></span><span class="viento" style="width:{ancho_viento:.1f}%"></span><span class="lluvia" style="width:{ancho_lluvia:.1f}%"></span>
      </div>
      <div class="valor">{incendio["puntaje"]}/21 {marca_activo}</div>
    </div>"""

filas_severidad = ""
for _, clase in severidad.iterrows():
    filas_severidad += f"<tr><td>{clase['clase']}</td><td>{clase['hectareas']:,.0f}</td></tr>"

filas_sensibilidad = ""
for _, fila in sensibilidad.iterrows():
    filas_sensibilidad += (
        f"<tr><td>{fila['umbral']:.2f}</td><td>{fila[columna_principal]:,.0f}</td>"
        f"<td>{fila[columna_alternativa]:,.0f}</td></tr>"
    )

pagina = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>¿Qué incendios de Cusco pueden crecer esta semana?</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; background: #f6f1ea; color: #1d1b19; }}
  header {{ background: #1d1b19; color: #f6f1ea; padding: 48px 8vw 36px; }}
  header p.etiqueta {{ color: #e8833a; font-weight: 700; letter-spacing: .08em; font-size: 13px; }}
  header h1 {{ font-size: 40px; margin: 8px 0 12px; }}
  main {{ padding: 24px 8vw 60px; max-width: 1100px; }}
  .tarjetas {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin: -50px 0 30px; }}
  .tarjeta {{ background: white; border-radius: 10px; padding: 18px; box-shadow: 0 1px 4px #0002; }}
  .tarjeta b {{ display: block; font-size: 34px; color: #b5451b; }}
  h2 {{ margin-top: 40px; }}
  .hallazgo {{ background: white; border-left: 5px solid #b5451b; padding: 14px 18px; margin: 12px 0; border-radius: 6px; }}
  .fila {{ display: grid; grid-template-columns: 170px 1fr 120px; align-items: center; gap: 10px; margin: 4px 0; font-size: 14px; }}
  .barra {{ background: #e9e2d8; height: 18px; border-radius: 3px; display: flex; overflow: hidden; }}
  .seco {{ background: #d73027; }} .viento {{ background: #fc8d59; }} .lluvia {{ background: #fee090; }}
  .activo {{ color: #a50026; font-size: 12px; }}
  .leyenda span {{ display: inline-block; width: 12px; height: 12px; margin: 0 4px 0 14px; vertical-align: middle; }}
  img {{ max-width: 100%; border-radius: 8px; background: white; }}
  table {{ border-collapse: collapse; background: white; margin: 10px 0; }}
  td, th {{ padding: 6px 14px; border-bottom: 1px solid #e9e2d8; text-align: left; }}
  .columnas {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
  footer {{ font-size: 12px; color: #6b655d; padding: 0 8vw 40px; }}
</style>
</head>
<body>
<header>
  <p class="etiqueta">RETO F · CLIMA Y RIESGO · CUSCO · 21 DE OCTUBRE DE 2026</p>
  <h1>¿Qué incendios de Cusco pueden crecer esta semana?</h1>
  <p>Crucé los incendios activos de Cusco con el pronóstico de Open-Meteo y medí con Sentinel-2 cuánto quemó el primero del ranking. · Jhanela Carhuaz</p>
</header>
<main>
  <div class="tarjetas">
    <div class="tarjeta"><b>{len(ranking)}</b>incendios analizados (≥ {config.MIN_FOCOS_INCENDIO} focos VIIRS)</div>
    <div class="tarjeta"><b>{nombre_primero}</b>mayor riesgo: {primero["puntaje"]} de 21 puntos</div>
    <div class="tarjeta"><b>{primero["dias_secos_previos"]} días</b>seguidos sin lluvia en {nombre_primero}</div>
    <div class="tarjeta"><b>{hectareas:,.0f} ha</b>quemadas (dNBR ≥ {config.UMBRAL_QUEMADO}), del {config.FECHA_ANTES[8:]} al {config.FECHA_DESPUES[8:]} oct</div>
  </div>

  <h2>Tres hallazgos</h2>
  <div class="hallazgo"><b>1. {nombre_primero} ({primero["provincia"].title()}) es el incendio que más puede crecer.</b>
    Sigue activo, lleva {primero["dias_secos_previos"]} días sin lluvia y el pronóstico trae humedad de hasta
    {primero["humedad_min_semana"]:.0f} % y ráfagas de hasta {primero["rafaga_max_semana"]:.0f} km/h.
    En Canas y Canchis hay viento parecido, pero llovió hace poco.</div>
  <div class="hallazgo"><b>2. Ya quemó unas {hectareas:,.0f} ha, pero la cifra depende del umbral.</b>
    Con otra fecha posterior da {fila_estandar[columna_alternativa]:,.0f} ha, casi lo mismo. Con umbral
    {fila_baja["umbral"]:.2f} son {fila_baja[columna_principal]:,.0f} ha y con {fila_alta["umbral"]:.2f} solo
    {fila_alta[columna_principal]:,.0f} ha.</div>
  <div class="hallazgo"><b>3. Los focos de calor no ven todo el incendio.</b>
    Los focos VIIRS están en el extremo norte de la cicatriz; la parte más severa está unos 3 a 4 km al sur,
    donde casi no hubo focos. Con el margen típico de 2 km la zona cortaba la cicatriz y daba la mitad del área.</div>

  <h2>Ranking de riesgo: días peligrosos en los próximos 7</h2>
  <p class="leyenda"><span class="seco"></span>humedad &lt; {config.HUMEDAD_CRITICA} %
    <span class="viento"></span>ráfagas &gt; {config.RAFAGA_CRITICA} km/h
    <span class="lluvia"></span>lluvia &lt; {config.LLUVIA_DIA_SECO} mm</p>
  {filas_ranking}

  <h2>El incendio de {nombre_primero}, visto desde el espacio</h2>
  <img src="{imagen_en_texto("mapa_antes_despues_dnbr.png")}" alt="Antes, después y dNBR">
  <div class="columnas">
    <img src="{imagen_en_texto("mapa_severidad.png")}" alt="Mapa de severidad">
    <div>
      <h3>Hectáreas por severidad (Key &amp; Benson)</h3>
      <table><tr><th>Clase</th><th>ha</th></tr>{filas_severidad}</table>
      <h3>Sensibilidad</h3>
      <table><tr><th>Umbral dNBR</th><th>{config.FECHA_DESPUES}</th><th>{config.FECHA_DESPUES_ALTERNATIVA}</th></tr>{filas_sensibilidad}</table>
    </div>
  </div>

  <h2>Método</h2>
  <ol>
    <li>Focos VIIRS de NASA FIRMS (S-NPP y NOAA-20, 14 al 21 oct), sin confianza baja. Focos a ≤ 1 km y ≤ 48 h = un incendio: 412 focos, 98 incendios en Cusco.</li>
    <li>Clima diario de Open-Meteo en cada incendio: 14 días pasados y 7 de pronóstico.</li>
    <li>Puntaje = días con humedad &lt; 30 % + días con ráfagas &gt; 40 km/h + días con lluvia &lt; 1 mm. Es la regla 30-30-30 adaptada a la sierra: sin temperatura, porque a ~3 500 m casi nunca pasa de 30 °C.</li>
    <li>Sentinel-2 L2A (Planetary Computer). Nubes medidas con SCL dentro de la zona: el 18 oct la escena tenía 74 % de nubes y la zona solo 2 %.</li>
    <li>NBR con B8A y B12 a 20 m (offset −1000), dNBR = antes − después, máscara SCL de nubes, sombras, cirros, agua y sin dato.</li>
  </ol>

  <h2>Limitaciones</h2>
  <ul>
    <li>Un foco de calor no es un incendio, y la falta de focos no significa falta de fuego.</li>
    <li>Las nubes y el humo esconden el fuego: el 20 oct la zona estaba 100 % cubierta.</li>
    <li>El pronóstico es de una celda de ~11 km y no ve el viento de valle ni la pendiente.</li>
    <li>El puntaje es una regla razonable, no un modelo validado con incendios que crecieron.</li>
    <li>El incendio sigue activo: el área es hasta el {config.FECHA_DESPUES[8:]} de octubre.</li>
  </ul>
</main>
<footer>Código y datos: github.com/Jhane080/incendios-cusco · Herramienta de práctica; no reemplaza los reportes de COEN, INDECI, SERFOR ni SERNANP.</footer>
</body>
</html>
"""

carpeta = config.RAIZ / "docs"
carpeta.mkdir(exist_ok=True)
(carpeta / "index.html").write_text(pagina, encoding="utf-8")
print(f"docs/index.html: {len(pagina) / 1000:,.0f} KB")
