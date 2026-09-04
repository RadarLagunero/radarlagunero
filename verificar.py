#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Verificación contra lo observado
==================================================
Baja las observaciones del aeropuerto de Torreón (MMTC), las guarda, y las
compara contra lo que este sitio pronosticó días antes.

Es la parte incómoda del proyecto y la más importante: cualquiera puede
publicar un pronóstico, pocos publican qué tanto le atinaron. Sin esta
página, "somos honestos con la incertidumbre" es sólo una frase.

Qué se puede verificar de verdad con un METAR:
  · Temperatura máxima y mínima — observación directa, cada hora.
  · Si llovió o no — por los códigos de tiempo presente (RA, TSRA, SHRA...).
  · Si hubo polvo — códigos DU, BLDU, DS, SS, HZ.
El METAR de MMTC no reporta milímetros acumulados, así que NO se afirma
nada sobre cuánta agua cayó. Se verifica lo observable y punto.

USO:
    python3 verificar.py                 # actualiza observaciones y marcador
    python3 verificar.py --solo-marcador
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ESTACION = "MMTC"
ESTACION_NOMBRE = "Aeropuerto Internacional Francisco Sarabia (Torreón)"
API_METAR = "https://aviationweather.gov/api/data/metar"

ZONA_LOCAL = timezone(timedelta(hours=-6))

ARCHIVO_OBS = "observaciones_mmtc.csv"
ARCHIVO_LOG = "pronosticos_log.csv"

CAMPOS_OBS = ["obs_utc", "fecha_local", "hora_local", "temp_c", "dewp_c",
              "viento_kt", "rafaga_kt", "visib", "lluvia", "polvo", "crudo"]

# Códigos de tiempo presente. Se buscan antes de RMK y como token completo.
RE_LLUVIA = re.compile(r"(?:^|\s)(?:[-+]|VC)?(?:MI|BC|PR|DR|BL|SH|TS|FZ)?"
                       r"(?:RA|DZ|GR|GS|SG|PL)(?:RA|DZ)?(?=\s|$)")
RE_POLVO = re.compile(r"(?:^|\s)(?:[-+]|VC)?(?:BL|DR)?(?:DU|SA|DS|SS|PO)(?=\s|$)")
RE_NEBLINA = re.compile(r"(?:^|\s)(?:HZ|FU)(?=\s|$)")


# --------------------------------------------------------------------------
# OBSERVACIONES
# --------------------------------------------------------------------------

def bajar_metar(horas=72):
    url = "%s?ids=%s&format=json&hours=%d" % (API_METAR, ESTACION, horas)
    req = urllib.request.Request(url, headers={"User-Agent": "RadarLagunero/2.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def cuerpo(crudo):
    """El METAR sin la sección de comentarios (RMK), que puede traer códigos
    de otras horas y confundir la lectura."""
    return crudo.split(" RMK")[0]


def interpretar(obs):
    utc = datetime.fromtimestamp(obs["obsTime"], tz=timezone.utc)
    local = utc.astimezone(ZONA_LOCAL)
    c = cuerpo(obs.get("rawOb", ""))
    return {
        "obs_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fecha_local": local.strftime("%Y-%m-%d"),
        "hora_local": local.strftime("%H:%M"),
        "temp_c": obs.get("temp"),
        "dewp_c": obs.get("dewp"),
        "viento_kt": obs.get("wspd"),
        "rafaga_kt": obs.get("wgst"),
        "visib": obs.get("visib"),
        "lluvia": 1 if RE_LLUVIA.search(c) else 0,
        "polvo": 1 if (RE_POLVO.search(c) or RE_NEBLINA.search(c)) else 0,
        "crudo": obs.get("rawOb", ""),
    }


def actualizar_observaciones(archivo=ARCHIVO_OBS):
    """Añade lo nuevo sin duplicar. Se guarda todo para que el archivo sea
    auditable: es la prueba, no un resumen."""
    previas = {}
    if os.path.exists(archivo):
        with open(archivo, newline="", encoding="utf-8") as fh:
            for fila in csv.DictReader(fh):
                previas[fila["obs_utc"]] = fila

    try:
        crudas = bajar_metar(72)
    except Exception as e:                              # noqa: BLE001
        print("  [!] No se pudo bajar el METAR: %s" % e, file=sys.stderr)
        return previas, 0

    nuevas = 0
    for o in crudas:
        if not o.get("obsTime"):
            continue
        r = interpretar(o)
        if r["obs_utc"] not in previas:
            previas[r["obs_utc"]] = r
            nuevas += 1

    with open(archivo, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_OBS)
        w.writeheader()
        for k in sorted(previas):
            w.writerow({c: previas[k].get(c, "") for c in CAMPOS_OBS})
    return previas, nuevas


def resumen_diario(observaciones):
    """Agrega por día local.

    MMTC no reporta las 24 horas: emite de madrugada a las 22 h aprox., unas
    17 observaciones al día. La máxima (media tarde) y la mínima (amanecer)
    caen dentro de esa ventana, así que se pueden verificar. La lluvia de
    madrugada, no: por eso 'llovió' es un piso, nunca un dato cerrado, y el
    sitio lo dice con todas sus letras.
    """
    por_dia = {}
    for r in observaciones.values():
        d = por_dia.setdefault(r["fecha_local"], {"temps": [], "lluvia": 0,
                                                  "polvo": 0, "n": 0, "horas": []})
        t = r.get("temp_c")
        if t not in (None, ""):
            d["temps"].append(float(t))
        d["lluvia"] = max(d["lluvia"], int(r.get("lluvia") or 0))
        d["polvo"] = max(d["polvo"], int(r.get("polvo") or 0))
        d["horas"].append(r["hora_local"])
        d["n"] += 1

    salida = {}
    for fecha, d in por_dia.items():
        if d["n"] < 12 or not d["temps"]:
            continue
        horas = sorted(d["horas"])
        # Sin observaciones de tarde no se puede hablar de la máxima.
        if not any("13:00" <= h <= "19:00" for h in horas):
            continue
        salida[fecha] = {
            "tmax_obs": max(d["temps"]), "tmin_obs": min(d["temps"]),
            "llovio_obs": d["lluvia"], "polvo_obs": d["polvo"],
            "n_obs": d["n"], "desde": horas[0], "hasta": horas[-1],
        }
    return salida


# --------------------------------------------------------------------------
# RELLENAR LA BITÁCORA
# --------------------------------------------------------------------------

def completar_log(diario, archivo=ARCHIVO_LOG):
    if not os.path.exists(archivo):
        return 0
    with open(archivo, newline="", encoding="utf-8") as fh:
        lector = csv.DictReader(fh)
        campos = lector.fieldnames
        filas = list(lector)

    tocadas = 0
    for f in filas:
        if f.get("tmax_obs"):
            continue
        obs = diario.get(f["fecha_pronosticada"])
        if not obs:
            continue
        f["tmax_obs"] = "%.1f" % obs["tmax_obs"]
        f["tmin_obs"] = "%.1f" % obs["tmin_obs"]
        f["llovio_obs"] = str(obs["llovio_obs"])
        f["fuente_obs"] = "METAR %s" % ESTACION
        tocadas += 1

    if tocadas:
        with open(archivo, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)
    return tocadas


# --------------------------------------------------------------------------
# MARCADOR
# --------------------------------------------------------------------------

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def marcador(archivo=ARCHIVO_LOG):
    """Calcula qué tanto le atinamos. Un solo pronóstico por día y horizonte:
    el más reciente antes de que empezara el día pronosticado."""
    if not os.path.exists(archivo):
        return None
    with open(archivo, newline="", encoding="utf-8") as fh:
        filas = [f for f in csv.DictReader(fh) if f.get("tmax_obs")]
    if not filas:
        return None

    # Un pronóstico por (ciudad, fecha, horizonte): el último emitido.
    unicos = {}
    for f in filas:
        k = (f["ciudad"], f["fecha_pronosticada"], f["horizonte_dias"])
        if k not in unicos or f["emitido"] > unicos[k]["emitido"]:
            unicos[k] = f
    filas = list(unicos.values())

    por_h = {}
    for f in filas:
        h = int(f["horizonte_dias"])
        d = por_h.setdefault(h, {"err_tmax": [], "brier": [], "acertados": 0,
                                 "n_lluvia": 0})
        tp, to = _f(f["tmax_prev"]), _f(f["tmax_obs"])
        if tp is not None and to is not None:
            d["err_tmax"].append(tp - to)
        p = _f(f["prob_lluvia_02mm"])
        obs = f.get("llovio_obs")
        if p is not None and obs in ("0", "1"):
            o = int(obs)
            d["brier"].append((p / 100.0 - o) ** 2)
            # "Acertó" = la probabilidad quedó del lado correcto del 50 %.
            if (p >= 50) == (o == 1):
                d["acertados"] += 1
            d["n_lluvia"] += 1

    horizontes = []
    for h in sorted(por_h):
        d = por_h[h]
        e = d["err_tmax"]
        horizontes.append({
            "horizonte_dias": h,
            "n_dias": len(e),
            "error_medio_tmax": round(sum(abs(x) for x in e) / len(e), 2) if e else None,
            "sesgo_tmax": round(sum(e) / len(e), 2) if e else None,
            "brier": round(sum(d["brier"]) / len(d["brier"]), 3) if d["brier"] else None,
            "acierto_lluvia_pct": (round(100 * d["acertados"] / d["n_lluvia"])
                                   if d["n_lluvia"] else None),
            "n_lluvia": d["n_lluvia"],
        })

    # Fiabilidad: de todas las veces que dijimos "60 %", ¿llovió el 60 % de
    # las veces? Es la prueba de fuego de una probabilidad.
    cajas = {}
    for f in filas:
        p = _f(f["prob_lluvia_02mm"])
        obs = f.get("llovio_obs")
        if p is None or obs not in ("0", "1"):
            continue
        caja = min(int(p // 20) * 20, 80)
        c = cajas.setdefault(caja, {"n": 0, "llovio": 0, "suma_p": 0.0})
        c["n"] += 1
        c["llovio"] += int(obs)
        c["suma_p"] += p

    fiabilidad = [{
        "rango": "%d-%d%%" % (k, k + 19),
        "n": v["n"],
        "prob_media": round(v["suma_p"] / v["n"]),
        "observado_pct": round(100 * v["llovio"] / v["n"]),
    } for k, v in sorted(cajas.items())]

    todas = [x for h in por_h.values() for x in h["err_tmax"]]
    return {
        "generado": datetime.now(ZONA_LOCAL).isoformat(),
        "estacion": {"icao": ESTACION, "nombre": ESTACION_NOMBRE},
        "dias_verificados": len({f["fecha_pronosticada"] for f in filas}),
        "pronosticos_evaluados": len(filas),
        "desde": min(f["fecha_pronosticada"] for f in filas),
        "hasta": max(f["fecha_pronosticada"] for f in filas),
        "error_medio_tmax_global": round(sum(abs(x) for x in todas) / len(todas), 2)
                                   if todas else None,
        "sesgo_tmax_global": round(sum(todas) / len(todas), 2) if todas else None,
        "por_horizonte": horizontes,
        "fiabilidad": fiabilidad,
        "notas": [
            "El METAR de %s no reporta milímetros acumulados: se verifica si "
            "llovió o no, nunca cuánto." % ESTACION,
            "La estación reporta de madrugada a las 22 h aproximadamente. La "
            "máxima y la mínima caen dentro de esa ventana, pero una lluvia de "
            "madrugada puede no quedar registrada: por eso 'llovió' es un piso.",
            "Se evalúa un solo pronóstico por día y horizonte: el último "
            "emitido antes de que empezara el día.",
        ],
    }


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Verificación contra el METAR de MMTC")
    ap.add_argument("--solo-marcador", action="store_true")
    ap.add_argument("--salida", default="public/aciertos.json")
    args = ap.parse_args()

    if args.solo_marcador:
        obs = {}
        if os.path.exists(ARCHIVO_OBS):
            with open(ARCHIVO_OBS, newline="", encoding="utf-8") as fh:
                obs = {f["obs_utc"]: f for f in csv.DictReader(fh)}
        nuevas = 0
    else:
        obs, nuevas = actualizar_observaciones()

    diario = resumen_diario(obs)
    tocadas = completar_log(diario)
    m = marcador()

    os.makedirs(os.path.dirname(args.salida) or ".", exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(m or {"generado": datetime.now(ZONA_LOCAL).isoformat(),
                        "dias_verificados": 0,
                        "estacion": {"icao": ESTACION, "nombre": ESTACION_NOMBRE},
                        "nota": "Aún no hay días completos que verificar."},
                  fh, ensure_ascii=False, indent=2)

    print("Observaciones nuevas: %d | días completos: %d | filas completadas: %d"
          % (nuevas, len(diario), tocadas))
    if m:
        print("Días verificados: %d | error medio en la máxima: %.2f °C"
              % (m["dias_verificados"], m["error_medio_tmax_global"] or 0))
    else:
        print("Todavía no hay nada que calificar: hacen falta días completos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
