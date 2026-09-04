#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Motor de pronóstico por ensemble multi-modelo
===============================================================
Calcula la probabilidad de lluvia contando, uno por uno, los miembros de
CUATRO ensembles de centros meteorológicos distintos:

    GFS   · NOAA, Estados Unidos     30 miembros
    ICON  · DWD, Alemania            39 miembros
    IFS   · ECMWF, Europa            50 miembros
    GEM   · ECCC, Canadá             20 miembros
                                    ---
                                    139 escenarios

No hay pesos, ni fórmulas propias, ni ajustes a ojo: la probabilidad es la
fracción de escenarios que superan un umbral de lluvia. Cualquiera con
acceso a la misma API puede repetir la cuenta y obtener el mismo número.
Esa es la única razón por la que una cifra de este tipo merece confianza.

Los modelos deterministas (GFS, ECMWF, ICON, GEM, ARPEGE) se siguen usando
para la temperatura y las rachas, y se publican uno por uno para que se vea
en qué difieren.

USO:
    python3 radar_lagunero.py                 # 7 días, las 3 ciudades
    python3 radar_lagunero.py --dias 5
    python3 radar_lagunero.py --ciudad torreon
    python3 radar_lagunero.py --json          # salida cruda
    python3 radar_lagunero.py --log           # bitácora para verificar después

Solo biblioteca estándar. Datos: Open-Meteo (CC BY 4.0, uso no comercial).
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------------------------------

CIUDADES = {
    "torreon": ("Torreón",       25.5428, -103.4068),
    "gomez":   ("Gómez Palacio", 25.5611, -103.4967),
    "lerdo":   ("Lerdo",         25.5386, -103.5241),
}

# Centro geométrico de la mancha urbana. La rejilla de los ensembles globales
# es más gruesa que la distancia entre las tres ciudades, así que la lluvia se
# calcula una vez para la comarca y se dice abiertamente en el sitio.
COMARCA = (25.548, -103.476)

ENSEMBLES = [
    ("gfs025",       "GFS",   "NOAA · Estados Unidos"),
    ("icon_seamless", "ICON",  "DWD · Alemania"),
    ("ecmwf_ifs025", "IFS",   "ECMWF · Europa"),
    ("gem_global",   "GEM",   "ECCC · Canadá"),
]

MODELOS = [
    ("gfs_seamless",         "GFS (EE.UU.)"),
    ("ecmwf_ifs025",         "ECMWF (Europa)"),
    ("icon_seamless",        "ICON (Alemania)"),
    ("gem_seamless",         "GEM (Canadá)"),
    ("meteofrance_seamless", "ARPEGE (Francia)"),
]

VARIABLES = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum",
             "wind_gusts_10m_max"]

# Umbrales en mm acumulados en 24 h.
#   0.2 — cualquier gota, casi siempre se evapora antes de servir de algo
#   1.0 — lluvia que se nota y moja el pavimento  <- es el titular
#   5.0 — lluvia de verdad, la que llena cauces
#  20.0 — lluvia fuerte, riesgo de encharcamiento
UMBRALES = [0.2, 1.0, 5.0, 20.0]
UMBRAL_TITULAR = 1.0

ZONA = "America/Monterrey"
ZONA_LOCAL = timezone(timedelta(hours=-6))   # Torreón, sin horario de verano

API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
API_AIRE = "https://air-quality-api.open-meteo.com/v1/air-quality"

DIAS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]


# --------------------------------------------------------------------------
# UTILIDADES
# --------------------------------------------------------------------------

def pedir(url, intentos=4):
    """GET con reintentos y espera creciente."""
    ultimo = None
    for n in range(intentos):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "RadarLagunero/2.0 (radarlagunero.com)"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError, OSError) as e:
            ultimo = e
            time.sleep(1.5 * (n + 1))
    raise RuntimeError("No se pudo consultar %s: %s" % (url.split("?")[0], ultimo))


def limpio(valores):
    return [v for v in valores if v is not None]


def mediana(valores):
    v = limpio(valores)
    return statistics.median(v) if v else None


def percentil(valores, q):
    """Percentil por interpolación simple. q entre 0 y 1."""
    v = sorted(limpio(valores))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = q * (len(v) - 1)
    bajo = int(pos)
    resto = pos - bajo
    if bajo + 1 >= len(v):
        return v[-1]
    return v[bajo] + (v[bajo + 1] - v[bajo]) * resto


def a_multiplo(pct, paso=5):
    """Redondea al múltiplo más cercano. Publicar '57%' finge una precisión
    que el método no tiene; '55%' es honesto."""
    if pct is None:
        return None
    return int(round(pct / paso) * paso)


def fecha_es(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %02d %s" % (DIAS_ES[d.weekday()], d.day, MESES_ES[d.month - 1])


# --------------------------------------------------------------------------
# CONSULTAS
# --------------------------------------------------------------------------

def traer_ensembles(lat, lon, dias):
    """Los cuatro ensembles. Devuelve {fecha: {clave_centro: {'pcp':[], 'tmax':[]}}}."""
    salida = {}
    fallaron = []
    for clave, nombre, centro in ENSEMBLES:
        url = ("%s?latitude=%s&longitude=%s"
               "&daily=precipitation_sum,temperature_2m_max"
               "&models=%s&timezone=%s&forecast_days=%d"
               % (API_ENSEMBLE, lat, lon, clave, urllib.parse.quote(ZONA), dias))
        try:
            d = pedir(url)["daily"]
        except RuntimeError as e:
            # Un centro caído no debe tumbar el pronóstico: se sigue con los
            # demás y el sitio publica con cuántos miembros se calculó.
            fallaron.append(nombre)
            print("  [!] ensemble %s no disponible: %s" % (nombre, e), file=sys.stderr)
            continue
        kp = [k for k in d if k.startswith("precipitation_sum_member")]
        kt = [k for k in d if k.startswith("temperature_2m_max_member")]
        for i, fecha in enumerate(d["time"]):
            pcp = [d[k][i] for k in kp if d[k][i] is not None]
            tmx = [d[k][i] for k in kt if d[k][i] is not None]
            if pcp:
                salida.setdefault(fecha, {})[clave] = {"pcp": pcp, "tmax": tmx}
        time.sleep(0.4)
    if not salida:
        raise RuntimeError("Ningún ensemble respondió")
    return salida, fallaron


def traer_deterministas(lat, lon, dias):
    url = ("%s?latitude=%s&longitude=%s&daily=%s&models=%s"
           "&timezone=%s&forecast_days=%d"
           % (API_FORECAST, lat, lon, ",".join(VARIABLES),
              ",".join(m[0] for m in MODELOS),
              urllib.parse.quote(ZONA), dias))
    return pedir(url)["daily"]


def traer_horario(lat, lon):
    """48 h hora por hora, más salida y puesta de sol e índice UV."""
    url = ("%s?latitude=%s&longitude=%s"
           "&hourly=temperature_2m,apparent_temperature,precipitation_probability,"
           "precipitation,wind_gusts_10m,visibility"
           "&daily=sunrise,sunset,uv_index_max"
           "&timezone=%s&forecast_days=2"
           % (API_FORECAST, lat, lon, urllib.parse.quote(ZONA)))
    return pedir(url)


def traer_aire(lat, lon):
    """Polvo en suspensión y partículas: la firma del clima lagunero."""
    url = ("%s?latitude=%s&longitude=%s&hourly=pm10,pm2_5,dust&timezone=%s"
           "&forecast_days=2" % (API_AIRE, lat, lon, urllib.parse.quote(ZONA)))
    return pedir(url)


# --------------------------------------------------------------------------
# ANÁLISIS DE LA LLUVIA — conteo puro sobre los miembros
# --------------------------------------------------------------------------

def analizar_lluvia(por_centro, horizonte):
    """Recibe {clave_centro: {'pcp': [...], 'tmax': [...]}} de un día."""
    todos = [v for c in por_centro.values() for v in c["pcp"]]
    n = len(todos)

    prob = {}
    for u in UMBRALES:
        prob[u] = 100.0 * sum(1 for v in todos if v >= u) / n

    # Cuánta agua, no sólo si llueve. Resuelve la contradicción de anunciar
    # una probabilidad alta junto a "0.0 mm".
    acumulado = {
        "p50": percentil(todos, 0.50),
        "p90": percentil(todos, 0.90),
        "max": max(todos),
    }

    # Desacuerdo entre centros sobre el umbral que titula: es la medida de
    # incertidumbre más honesta que se puede publicar, porque son cuatro
    # equipos independientes mirando la misma atmósfera.
    centros = {}
    for clave, datos in por_centro.items():
        m = datos["pcp"]
        centros[clave] = 100.0 * sum(1 for v in m if v >= UMBRAL_TITULAR) / len(m)
    desacuerdo = max(centros.values()) - min(centros.values()) if len(centros) > 1 else None

    # Dispersión de la temperatura máxima entre los 139 miembros.
    tmx = [v for c in por_centro.values() for v in c["tmax"]]
    sd_tmax = statistics.pstdev(tmx) if len(tmx) > 1 else None

    return {
        "n_miembros": n,
        "n_centros": len(por_centro),
        "prob": prob,
        "prob_titular": prob[UMBRAL_TITULAR],
        "acumulado": acumulado,
        "por_centro": centros,
        "desacuerdo": desacuerdo,
        "sd_tmax": sd_tmax,
        "confianza_lluvia": confianza_lluvia(desacuerdo, horizonte),
        "confianza_temp": confianza_temp(sd_tmax),
    }


def confianza_lluvia(desacuerdo, horizonte):
    """Cortes calibrados contra la dispersión que realmente se observa entre
    los cuatro centros. No es una opinión: es cuánto difieren entre sí."""
    if desacuerdo is None:
        return "BAJA"
    if desacuerdo <= 25 and horizonte <= 3:
        return "ALTA"
    if desacuerdo <= 40 and horizonte <= 6:
        return "MEDIA"
    return "BAJA"


def confianza_temp(sd):
    if sd is None:
        return "BAJA"
    if sd <= 1.2:
        return "ALTA"
    if sd <= 2.0:
        return "MEDIA"
    return "BAJA"


def analizar_temperatura(diario, i):
    """Consenso (mediana) de los modelos deterministas, y la fila de cada uno."""
    filas = []
    for clave, nombre in MODELOS:
        filas.append({
            "modelo": nombre,
            "tmax":   diario.get("temperature_2m_max_%s" % clave, [None])[i],
            "tmin":   diario.get("temperature_2m_min_%s" % clave, [None])[i],
            "lluvia": diario.get("precipitation_sum_%s" % clave, [None])[i],
            "rafaga": diario.get("wind_gusts_10m_max_%s" % clave, [None])[i],
        })
    disponibles = [f for f in filas if f["tmax"] is not None]
    return {
        "filas": filas,
        "modelos_con_datos": len(disponibles),
        "tmax": mediana([f["tmax"] for f in filas]),
        "tmin": mediana([f["tmin"] for f in filas]),
        "rafaga": mediana([f["rafaga"] for f in filas]),
    }


# --------------------------------------------------------------------------
# TOLVANERAS
# --------------------------------------------------------------------------

def riesgo_tolvanera(aire, horario):
    """Combina polvo en suspensión, PM10, rachas y visibilidad.

    La tolvanera es el fenómeno que define a la comarca y ningún medio local
    lo pronostica. Los umbrales siguen la guía de calidad del aire de la OMS
    para PM10 (50 µg/m³ en 24 h) y el criterio aeronáutico de visibilidad.
    """
    h = aire["hourly"]
    polvo = max(limpio(h["dust"][:24]) or [0])
    pm10 = max(limpio(h["pm10"][:24]) or [0])
    pm25 = max(limpio(h["pm2_5"][:24]) or [0])

    hh = horario["hourly"]
    rafaga = max(limpio(hh["wind_gusts_10m"][:24]) or [0])
    vis_m = min(limpio(hh["visibility"][:24]) or [99999])
    vis = vis_m / 1000.0

    if pm10 >= 150 or polvo >= 150 or (rafaga >= 60 and vis < 5):
        nivel, texto = "ALTO", ("Tolvanera probable. Evita salir si tienes asma "
                                "o problemas respiratorios y no dejes ropa tendida.")
    elif pm10 >= 80 or polvo >= 60 or (rafaga >= 45 and vis < 10):
        nivel, texto = "MODERADO", ("Puede levantarse polvo por la tarde. "
                                    "Molesto para alérgicos.")
    elif pm10 >= 50 or polvo >= 25 or rafaga >= 40:
        nivel, texto = "BAJO", "Algo de polvo en el aire, sin mayor problema."
    else:
        nivel, texto = "NULO", "Aire limpio, sin polvo en suspensión."

    return {"nivel": nivel, "texto": texto, "polvo": polvo, "pm10": pm10,
            "pm25": pm25, "rafaga": rafaga, "visibilidad_km": round(vis, 1)}


# --------------------------------------------------------------------------
# LENGUAJE
# --------------------------------------------------------------------------

def lectura(lluvia, temp, tolvanera=None):
    """La frase de la portada, en lenguaje de calle y sin adornos."""
    p = lluvia["prob_titular"]
    p5 = lluvia["prob"][5.0]
    p90 = lluvia["acumulado"]["p90"]
    t = temp["tmax"]
    r = temp["rafaga"]
    partes = []

    if p >= 70:
        partes.append("Va a llover")
    elif p >= 50:
        partes.append("Es más probable que llueva a que no")
    elif p >= 30:
        partes.append("Puede llover")
    elif p >= 12:
        partes.append("Poca probabilidad de lluvia")
    else:
        partes.append("No se espera lluvia")

    if p >= 30 and p5 >= 25:
        partes.append("y si cae, puede dejar más de 5 mm")
    elif p >= 30 and p90 is not None and p90 < 2:
        partes.append("pero sería poca cosa")

    if t is not None:
        if t >= 40:
            partes.append("calor extremo, máxima cerca de %.0f °C" % t)
        elif t >= 36:
            partes.append("mucho calor, máxima cerca de %.0f °C" % t)
        else:
            partes.append("máxima cerca de %.0f °C" % t)

    if r is not None and r >= 55:
        partes.append("ojo con rachas de %.0f km/h" % r)
    elif r is not None and r >= 40:
        partes.append("viento con rachas de %.0f km/h" % r)

    frase = ", ".join(partes) + "."

    if tolvanera and tolvanera["nivel"] in ("ALTO", "MODERADO"):
        frase += " " + tolvanera["texto"]

    if lluvia["confianza_lluvia"] == "BAJA" and lluvia["desacuerdo"] is not None:
        frase += (" Los centros no se ponen de acuerdo: entre el más seco y el "
                  "más lluvioso hay %.0f puntos de diferencia, así que este "
                  "número puede moverse." % lluvia["desacuerdo"])
    return frase


def cuando_llueve(horario):
    """Las horas con mayor probabilidad, para responder '¿a qué hora?'."""
    h = horario["hourly"]
    hoy = datetime.now(ZONA_LOCAL).strftime("%Y-%m-%d")
    idx = [i for i, t in enumerate(h["time"]) if t.startswith(hoy)]
    if not idx:
        return None
    probs = [(i, h["precipitation_probability"][i]) for i in idx
             if h["precipitation_probability"][i] is not None]
    ahora = datetime.now(ZONA_LOCAL).hour
    futuras = [(i, p) for i, p in probs if int(h["time"][i][11:13]) >= ahora]
    if not futuras:
        return None
    pico = max(futuras, key=lambda x: x[1])
    if pico[1] < 25:
        return None
    return {"hora": h["time"][pico[0]][11:16], "prob": pico[1]}


# --------------------------------------------------------------------------
# SALIDA EN TERMINAL
# --------------------------------------------------------------------------

def barra(pct, ancho=20):
    if pct is None:
        return "-" * ancho
    n = int(round(pct / 100 * ancho))
    return "#" * n + "." * (ancho - n)


def imprimir_comarca(fechas, lluvias):
    print()
    print("=" * 66)
    print(" LLUVIA EN LA COMARCA LAGUNERA")
    print(" %d escenarios de %d centros meteorológicos independientes"
          % (lluvias[0]["n_miembros"], lluvias[0]["n_centros"]))
    print("=" * 66)
    print()
    print("  %-10s %7s %7s %7s %7s %8s %s"
          % ("día", ">0.2mm", ">1mm", ">5mm", ">20mm", "p90", "confianza"))
    print("  " + "-" * 62)
    for iso, a in zip(fechas, lluvias):
        print("  %-10s %6.0f%% %6.0f%% %6.0f%% %6.0f%% %6.1fmm  %s"
              % (fecha_es(iso), a["prob"][0.2], a["prob"][1.0],
                 a["prob"][5.0], a["prob"][20.0],
                 a["acumulado"]["p90"], a["confianza_lluvia"]))
    print()
    a = lluvias[0]
    print("  Hoy, centro por centro (probabilidad de pasar de 1 mm):")
    for clave, nombre, centro in ENSEMBLES:
        if clave in a["por_centro"]:
            print("    %-6s %-24s %3.0f%%  %s"
                  % (nombre, centro, a["por_centro"][clave],
                     barra(a["por_centro"][clave])))
    if a["desacuerdo"] is not None:
        print()
        print("  Desacuerdo entre centros: %.0f puntos" % a["desacuerdo"])


def imprimir_ciudad(nombre, fechas, temps, tolvanera, hora_pico):
    print()
    print("-" * 66)
    print(" %s" % nombre.upper())
    print("-" * 66)
    print("  %-10s %8s %8s %10s" % ("día", "máx", "mín", "rachas"))
    for iso, t in zip(fechas, temps):
        print("  %-10s %7.1f° %7.1f° %8s"
              % (fecha_es(iso), t["tmax"], t["tmin"],
                 "%.0f km/h" % t["rafaga"] if t["rafaga"] is not None else "-"))
    if hora_pico:
        print()
        print("  Hora de mayor probabilidad hoy: %s (%d%%)"
              % (hora_pico["hora"], hora_pico["prob"]))
    if tolvanera:
        print()
        print("  Polvo: %s — PM10 %.0f µg/m³, visibilidad mín %.1f km"
              % (tolvanera["nivel"], tolvanera["pm10"], tolvanera["visibilidad_km"]))


# --------------------------------------------------------------------------
# BITÁCORA — la materia prima de la verificación
# --------------------------------------------------------------------------

CAMPOS_LOG = ["emitido", "ciudad", "fecha_pronosticada", "horizonte_dias",
              "prob_lluvia_1mm", "prob_lluvia_02mm", "acum_p50", "acum_p90",
              "tmax_prev", "tmin_prev", "confianza_lluvia", "confianza_temp",
              "tmax_obs", "tmin_obs", "llovio_obs", "fuente_obs"]


def guardar_log(archivo, ciudad, fechas, lluvias, temps):
    nuevo = not os.path.exists(archivo)
    with open(archivo, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_LOG)
        if nuevo:
            w.writeheader()
        emitido = datetime.now(ZONA_LOCAL).strftime("%Y-%m-%d %H:%M")
        for n, (iso, a, t) in enumerate(zip(fechas, lluvias, temps)):
            w.writerow({
                "emitido": emitido, "ciudad": ciudad, "fecha_pronosticada": iso,
                "horizonte_dias": n,
                "prob_lluvia_1mm": "%.0f" % a["prob"][1.0],
                "prob_lluvia_02mm": "%.0f" % a["prob"][0.2],
                "acum_p50": "%.1f" % a["acumulado"]["p50"],
                "acum_p90": "%.1f" % a["acumulado"]["p90"],
                "tmax_prev": "%.1f" % t["tmax"] if t["tmax"] is not None else "",
                "tmin_prev": "%.1f" % t["tmin"] if t["tmin"] is not None else "",
                "confianza_lluvia": a["confianza_lluvia"],
                "confianza_temp": a["confianza_temp"],
                "tmax_obs": "", "tmin_obs": "", "llovio_obs": "", "fuente_obs": "",
            })


# --------------------------------------------------------------------------
# RECOLECCIÓN COMPLETA
# --------------------------------------------------------------------------

def recolectar(dias, ciudades=None):
    """Todo lo que el sitio necesita, en una estructura."""
    claves = ciudades or list(CIUDADES)
    generado = datetime.now(ZONA_LOCAL)

    # La lluvia se calcula UNA vez para la comarca: a la resolución de los
    # ensembles globales, Torreón, Gómez y Lerdo caen en la misma celda.
    ens, centros_caidos = traer_ensembles(COMARCA[0], COMARCA[1], dias)
    fechas = sorted(ens)[:dias]
    lluvias = [analizar_lluvia(ens[f], i) for i, f in enumerate(fechas)]

    salida = {
        "generado": generado.isoformat(),
        "fechas": fechas,
        "lluvia": lluvias,
        "centros_caidos": centros_caidos,
        "ciudades": {},
    }

    for clave in claves:
        nombre, lat, lon = CIUDADES[clave]
        diario = traer_deterministas(lat, lon, dias)
        temps = [analizar_temperatura(diario, i)
                 for i in range(min(len(diario["time"]), len(fechas)))]
        horario = traer_horario(lat, lon)
        aire = traer_aire(lat, lon)
        salida["ciudades"][clave] = {
            "nombre": nombre, "lat": lat, "lon": lon,
            "temps": temps,
            "horario": horario,
            "aire": aire,
            "tolvanera": riesgo_tolvanera(aire, horario),
            "hora_pico": cuando_llueve(horario),
        }
        time.sleep(0.3)

    return salida


def a_json_publico(datos):
    """El JSON abierto que publica el sitio. Que se pueda auditar es el punto."""
    out = {
        "generado": datos["generado"],
        "metodo": ("Fracción de miembros de un ensemble multi-modelo que supera "
                   "cada umbral de lluvia acumulada en 24 h. Sin pesos ni ajustes."),
        "centros": [{"clave": c, "nombre": n, "institucion": i}
                    for c, n, i in ENSEMBLES],
        "miembros": datos["lluvia"][0]["n_miembros"] if datos["lluvia"] else 0,
        "umbrales_mm": UMBRALES,
        "umbral_titular_mm": UMBRAL_TITULAR,
        "licencia": "Datos de Open-Meteo, CC BY 4.0",
        "comarca": [],
        "ciudades": {},
    }
    for f, a in zip(datos["fechas"], datos["lluvia"]):
        out["comarca"].append({
            "fecha": f,
            "prob_pct": {str(u): round(a["prob"][u], 1) for u in UMBRALES},
            "acumulado_mm": {k: round(v, 2) for k, v in a["acumulado"].items()},
            "por_centro_pct": {k: round(v, 1) for k, v in a["por_centro"].items()},
            "desacuerdo_pts": round(a["desacuerdo"], 1) if a["desacuerdo"] else None,
            "miembros": a["n_miembros"],
            "confianza_lluvia": a["confianza_lluvia"],
            "confianza_temperatura": a["confianza_temp"],
        })
    for clave, c in datos["ciudades"].items():
        out["ciudades"][clave] = {
            "nombre": c["nombre"],
            "dias": [{"fecha": f, "tmax": t["tmax"], "tmin": t["tmin"],
                      "rafaga_kmh": t["rafaga"],
                      "modelos_con_datos": t["modelos_con_datos"]}
                     for f, t in zip(datos["fechas"], c["temps"])],
            "tolvanera": c["tolvanera"],
        }
    return out


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Radar Lagunero — ensemble multi-modelo de 4 centros")
    ap.add_argument("--dias", type=int, default=7, help="días a pronosticar (1-14)")
    ap.add_argument("--ciudad", choices=list(CIUDADES) + ["todas"], default="todas")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    ap.add_argument("--log", action="store_true",
                    help="guarda el pronóstico en pronosticos_log.csv")
    args = ap.parse_args()

    dias = max(1, min(args.dias, 14))
    claves = list(CIUDADES) if args.ciudad == "todas" else [args.ciudad]

    try:
        datos = recolectar(dias, claves)
    except RuntimeError as e:
        print("  [!] %s" % e, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(a_json_publico(datos), ensure_ascii=False, indent=2))
    else:
        imprimir_comarca(datos["fechas"], datos["lluvia"])
        for clave in claves:
            c = datos["ciudades"][clave]
            imprimir_ciudad(c["nombre"], datos["fechas"], c["temps"],
                            c["tolvanera"], c["hora_pico"])
        print()
        print("=" * 66)
        print(" > %s" % lectura(datos["lluvia"][0],
                                datos["ciudades"][claves[0]]["temps"][0],
                                datos["ciudades"][claves[0]]["tolvanera"]))
        print("=" * 66)
        print(" Datos: Open-Meteo (CC BY 4.0). Para fenómenos peligrosos, el")
        print(" aviso que cuenta es el del SMN / CONAGUA y Protección Civil.")

    if args.log:
        for clave in claves:
            guardar_log("pronosticos_log.csv", CIUDADES[clave][0],
                        datos["fechas"], datos["lluvia"],
                        datos["ciudades"][clave]["temps"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
