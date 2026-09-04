#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Ensamble multi-modelo
=======================================
Consulta 5 modelos numericos independientes (GFS, ECMWF, ICON, GEM,
Meteo-France) mas el ensemble del GFS (31 miembros) y devuelve una tabla
comparativa con probabilidad ajustada por consenso para Torreon,
Gomez Palacio y Lerdo.

Solo usa la biblioteca estandar de Python. Corre en A-Shell sin instalar nada.

USO:
    python3 radar_lagunero.py                  # 3 dias, las 3 ciudades
    python3 radar_lagunero.py --dias 5
    python3 radar_lagunero.py --ciudad torreon
    python3 radar_lagunero.py --log            # guarda CSV para calibrar
    python3 radar_lagunero.py --json           # salida cruda para otro script

Datos: Open-Meteo (open-meteo.com) — CC BY 4.0, uso no comercial gratuito.
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

# --------------------------------------------------------------------------
# CONFIGURACION
# --------------------------------------------------------------------------

CIUDADES = {
    "torreon":      ("Torreon",       25.5428, -103.4068),
    "gomez":        ("Gomez Palacio", 25.5611, -103.4967),
    "lerdo":        ("Lerdo",         25.5386, -103.5241),
}

# Modelos deterministas de centros meteorologicos distintos.
# La independencia entre ellos es lo que hace util el consenso.
MODELOS = [
    ("gfs_seamless",          "GFS (EE.UU.)"),
    ("ecmwf_ifs025",          "ECMWF (Europa)"),
    ("icon_seamless",         "ICON (Alemania)"),
    ("gem_seamless",          "GEM (Canada)"),
    ("meteofrance_seamless",  "ARPEGE (Francia)"),
]

VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_gusts_10m_max",
]

ZONA = "America/Monterrey"
UMBRAL_LLUVIA = 0.2          # mm — por debajo de esto no es lluvia reportable
API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"

DIAS_ES = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]


# --------------------------------------------------------------------------
# UTILIDADES
# --------------------------------------------------------------------------

def pedir(url, intentos=3):
    """GET con reintentos. Devuelve dict."""
    ultimo = None
    for n in range(intentos):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "RadarLagunero/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as e:
            ultimo = e
    raise RuntimeError("No se pudo consultar la API: %s" % ultimo)


def limpio(valores):
    """Quita None de una lista."""
    return [v for v in valores if v is not None]


def promedio(valores):
    v = limpio(valores)
    return sum(v) / len(v) if v else None


def mediana(valores):
    v = sorted(limpio(valores))
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def fecha_es(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %02d %s" % (DIAS_ES[d.weekday()], d.day, MESES_ES[d.month - 1])


# --------------------------------------------------------------------------
# CONSULTAS
# --------------------------------------------------------------------------

def traer_modelos(lat, lon, dias):
    url = ("%s?latitude=%s&longitude=%s&daily=%s&models=%s"
           "&timezone=%s&forecast_days=%d"
           % (API_FORECAST, lat, lon, ",".join(VARIABLES),
              ",".join(m[0] for m in MODELOS),
              urllib.parse.quote(ZONA), dias))
    return pedir(url)["daily"]


def traer_ensemble(lat, lon, dias):
    """31 miembros del GFS. La dispersion entre ellos es la incertidumbre real."""
    url = ("%s?latitude=%s&longitude=%s&daily=precipitation_sum"
           "&models=gfs025&timezone=%s&forecast_days=%d"
           % (API_ENSEMBLE, lat, lon, urllib.parse.quote(ZONA), dias))
    d = pedir(url)["daily"]
    miembros = [k for k in d if k.startswith("precipitation_sum_member")]
    fracciones = []
    for i in range(len(d["time"])):
        vals = limpio([d[m][i] for m in miembros])
        if vals:
            mojados = sum(1 for v in vals if v >= UMBRAL_LLUVIA)
            fracciones.append((mojados, len(vals), mojados / len(vals)))
        else:
            fracciones.append((0, 0, None))
    return fracciones


# --------------------------------------------------------------------------
# ANALISIS
# --------------------------------------------------------------------------

def analizar_dia(diario, i, ens):
    """Extrae los valores de cada modelo para el dia i y calcula el consenso."""
    filas = []
    for clave, nombre in MODELOS:
        filas.append({
            "modelo": nombre,
            "tmax":   diario.get("temperature_2m_max_%s" % clave, [None])[i],
            "tmin":   diario.get("temperature_2m_min_%s" % clave, [None])[i],
            "lluvia": diario.get("precipitation_sum_%s" % clave, [None])[i],
            "prob":   diario.get("precipitation_probability_max_%s" % clave,
                                 [None])[i],
            "rafaga": diario.get("wind_gusts_10m_max_%s" % clave, [None])[i],
        })

    tmax = [f["tmax"] for f in filas]
    lluvias = limpio([f["lluvia"] for f in filas])
    probs = limpio([f["prob"] for f in filas])

    # 1. Acuerdo entre modelos deterministas
    mojados = sum(1 for v in lluvias if v >= UMBRAL_LLUVIA)
    frac_det = mojados / len(lluvias) if lluvias else None

    # 2. Probabilidad promedio que reportan los propios modelos
    prob_media = promedio(probs)

    # 3. Fraccion de miembros del ensemble con lluvia
    m_moj, m_tot, frac_ens = ens

    # Probabilidad ajustada: el ensemble pesa mas porque es la unica
    # fuente que mide incertidumbre de verdad.
    partes, pesos = [], []
    if frac_ens is not None:
        partes.append(frac_ens * 100); pesos.append(0.50)
    if prob_media is not None:
        partes.append(prob_media);     pesos.append(0.30)
    if frac_det is not None:
        partes.append(frac_det * 100); pesos.append(0.20)
    ajustada = (sum(p * w for p, w in zip(partes, pesos)) / sum(pesos)
                if partes else None)

    # Confianza: que tan de acuerdo estan
    disp_t = (max(limpio(tmax)) - min(limpio(tmax))) if limpio(tmax) else None
    acuerdo = abs((frac_det or 0.5) - 0.5) * 2      # 1 = unanimidad
    if disp_t is not None and acuerdo >= 0.8 and disp_t <= 2.5:
        confianza = "ALTA"
    elif disp_t is not None and acuerdo >= 0.5 and disp_t <= 4.0:
        confianza = "MEDIA"
    else:
        confianza = "BAJA"

    return {
        "filas": filas,
        "tmax": mediana(tmax),
        "tmin": mediana([f["tmin"] for f in filas]),
        "lluvia": mediana(lluvias),
        "rafaga": mediana([f["rafaga"] for f in filas]),
        "det": (mojados, len(lluvias)),
        "ens": (m_moj, m_tot),
        "ajustada": ajustada,
        "confianza": confianza,
        "dispersion_t": disp_t,
    }


def lectura(a):
    """Frase en lenguaje de calle, lista para editar y publicar."""
    p = a["ajustada"] or 0
    t = a["tmax"]
    r = a["rafaga"]
    partes = []

    if p >= 70:
        partes.append("Lluvia muy probable")
    elif p >= 45:
        partes.append("Buenas posibilidades de lluvia")
    elif p >= 20:
        partes.append("Lluvia aislada posible")
    else:
        partes.append("Dia seco")

    if t is not None:
        if t >= 40:
            partes.append("calor extremo, maxima cerca de %.0f C" % t)
        elif t >= 35:
            partes.append("mucho calor, maxima cerca de %.0f C" % t)
        else:
            partes.append("maxima cerca de %.0f C" % t)

    if r is not None and r >= 50:
        partes.append("ojo con rachas de viento de %.0f km/h" % r)
    elif r is not None and r >= 35:
        partes.append("viento con rachas de %.0f km/h, posible tolvanera" % r)

    frase = ", ".join(partes) + "."

    # La razon de la baja confianza importa: no es lo mismo que los modelos
    # discrepen en si llueve, a que discrepen en cuanto va a calentar.
    if a["confianza"] == "BAJA":
        mojados, total = a["det"]
        frac = mojados / total if total else 0.5
        if 0.2 < frac < 0.8:
            frase += " Los modelos no coinciden en la lluvia: seguimos pendientes."
        elif a["dispersion_t"] is not None and a["dispersion_t"] > 4.0:
            frase += (" Hay hasta %.0f grados de diferencia entre modelos en la "
                      "temperatura." % a["dispersion_t"])
        else:
            frase += " Pronostico con incertidumbre: seguimos pendientes."
    return frase


# --------------------------------------------------------------------------
# SALIDA
# --------------------------------------------------------------------------

def barra(pct, ancho=20):
    if pct is None:
        return "-" * ancho
    n = int(round(pct / 100 * ancho))
    return "#" * n + "." * (ancho - n)


def imprimir(nombre, dias_iso, analisis):
    print()
    print("=" * 62)
    print(" %s" % nombre.upper())
    print("=" * 62)
    for iso, a in zip(dias_iso, analisis):
        print()
        print(" %s" % fecha_es(iso))
        print(" " + "-" * 60)
        print("  %-18s %6s %6s %8s %6s %7s"
              % ("Modelo", "Tmax", "Tmin", "Lluvia", "Prob", "Rafaga"))
        for f in a["filas"]:
            print("  %-18s %6s %6s %8s %6s %7s" % (
                f["modelo"],
                "%.1f" % f["tmax"]   if f["tmax"]   is not None else "  -",
                "%.1f" % f["tmin"]   if f["tmin"]   is not None else "  -",
                "%.1f" % f["lluvia"] if f["lluvia"] is not None else "  -",
                "%d%%"  % f["prob"]  if f["prob"]   is not None else "  -",
                "%.0f" % f["rafaga"] if f["rafaga"] is not None else "  -",
            ))
        print("  " + "-" * 58)
        print("  %-18s %6s %6s %8s %6s %7s" % (
            "CONSENSO",
            "%.1f" % a["tmax"]   if a["tmax"]   is not None else "  -",
            "%.1f" % a["tmin"]   if a["tmin"]   is not None else "  -",
            "%.1f" % a["lluvia"] if a["lluvia"] is not None else "  -",
            "", 
            "%.0f" % a["rafaga"] if a["rafaga"] is not None else "  -",
        ))
        print()
        print("   Acuerdo entre modelos : %d de %d dan lluvia" % a["det"])
        print("   Ensemble GFS          : %d de %d miembros con lluvia" % a["ens"])
        disp = ("%.1f C" % a["dispersion_t"]
                if a["dispersion_t"] is not None else "-")
        print("   Dispersion de Tmax    : %s" % disp)
        print()
        pct = a["ajustada"]
        print("   PROBABILIDAD AJUSTADA : %s  %s"
              % ("%3.0f%%" % pct if pct is not None else "  -", barra(pct)))
        print("   CONFIANZA             : %s" % a["confianza"])
        print()
        print("   > %s" % lectura(a))


def guardar_log(archivo, ciudad, dias_iso, analisis):
    """Guarda el pronostico para compararlo despues con lo observado.
    Esta bitacora es la que te permite calcular tu factor de correccion local."""
    nuevo = not os.path.exists(archivo)
    with open(archivo, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["emitido", "ciudad", "fecha_pronosticada", "horizonte_dias",
                        "tmax_prev", "tmin_prev", "lluvia_prev_mm",
                        "prob_ajustada", "confianza",
                        "tmax_obs", "tmin_obs", "lluvia_obs_mm"])
        hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
        for n, (iso, a) in enumerate(zip(dias_iso, analisis)):
            w.writerow([hoy, ciudad, iso, n,
                        "%.1f" % a["tmax"] if a["tmax"] is not None else "",
                        "%.1f" % a["tmin"] if a["tmin"] is not None else "",
                        "%.1f" % a["lluvia"] if a["lluvia"] is not None else "",
                        "%.0f" % a["ajustada"] if a["ajustada"] is not None else "",
                        a["confianza"], "", "", ""])


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Ensamble multi-modelo lagunero")
    ap.add_argument("--dias", type=int, default=3, help="dias a pronosticar (1-14)")
    ap.add_argument("--ciudad", choices=list(CIUDADES) + ["todas"],
                    default="todas")
    ap.add_argument("--log", action="store_true",
                    help="guarda el pronostico en pronosticos_log.csv")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    args = ap.parse_args()

    dias = max(1, min(args.dias, 14))
    objetivo = (list(CIUDADES) if args.ciudad == "todas" else [args.ciudad])

    salida = {}
    for clave in objetivo:
        nombre, lat, lon = CIUDADES[clave]
        try:
            diario = traer_modelos(lat, lon, dias)
            ens = traer_ensemble(lat, lon, dias)
        except RuntimeError as e:
            print("  [!] %s: %s" % (nombre, e), file=sys.stderr)
            continue

        fechas = diario["time"]
        analisis = [analizar_dia(diario, i, ens[i]) for i in range(len(fechas))]

        if args.json:
            salida[nombre] = [
                {"fecha": f, "tmax": a["tmax"], "tmin": a["tmin"],
                 "lluvia_mm": a["lluvia"], "rafaga": a["rafaga"],
                 "prob_ajustada": a["ajustada"], "confianza": a["confianza"],
                 "acuerdo_modelos": "%d/%d" % a["det"],
                 "ensemble": "%d/%d" % a["ens"],
                 "lectura": lectura(a)}
                for f, a in zip(fechas, analisis)]
        else:
            imprimir(nombre, fechas, analisis)

        if args.log:
            guardar_log("pronosticos_log.csv", nombre, fechas, analisis)

    if args.json:
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        print()
        print("-" * 62)
        print(" Fuente: Open-Meteo. Ensemble GFS de 31 miembros.")
        print(" Para fenomenos peligrosos, cita el aviso oficial del SMN/CONAGUA.")
        print("-" * 62)


if __name__ == "__main__":
    main()
