#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Generador de tarjeta para redes
=================================================
Toma la salida JSON de radar_lagunero.py y genera un PNG de 1080x1350
listo para publicar en Facebook e Instagram.

USO:
    python3 radar_lagunero.py --json > datos.json
    python3 tarjeta_radar.py datos.json

    o en una sola linea:
    python3 radar_lagunero.py --json | python3 tarjeta_radar.py

Requiere Pillow:  pip3 install Pillow
"""

import json
import math
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# MARCA
# --------------------------------------------------------------------------

W, H = 1080, 1350

FONDO_ARRIBA = (9, 24, 41)
FONDO_ABAJO = (16, 46, 74)
CIAN = (56, 189, 248)
CIAN_TENUE = (30, 92, 130)
AMBAR = (245, 158, 11)
BLANCO = (248, 250, 252)
GRIS = (148, 163, 184)
PANEL = (17, 40, 63)

FUENTES = "/usr/share/fonts/truetype/google-fonts/Poppins-%s.ttf"

DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves",
           "Viernes", "Sábado", "Domingo"]

# Los nombres llegan sin acentos desde la API; aqui se muestran bien.
BONITO = {"Torreon": "Torreón", "Gomez Palacio": "Gómez Palacio",
          "Lerdo": "Lerdo"}
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fuente(peso, tam):
    try:
        return ImageFont.truetype(FUENTES % peso, tam)
    except OSError:
        return ImageFont.load_default()


# --------------------------------------------------------------------------
# PIEZAS DE DIBUJO
# --------------------------------------------------------------------------

def degradado(img):
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        c = tuple(int(FONDO_ARRIBA[i] + (FONDO_ABAJO[i] - FONDO_ARRIBA[i]) * t)
                  for i in range(3))
        d.line([(0, y), (W, y)], fill=c)


def anillos_radar(img, cx, cy, radios):
    """Marca de agua: los anillos del radar, sutiles."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for r in radios:
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  outline=CIAN + (26,), width=2)
    for ang in range(0, 360, 45):
        x = cx + math.cos(math.radians(ang)) * radios[-1]
        y = cy + math.sin(math.radians(ang)) * radios[-1]
        d.line([(cx, cy), (x, y)], fill=CIAN + (14,), width=2)
    img.alpha_composite(capa)


def centrar(d, texto, f, y, color, x0=0, x1=W):
    ancho = d.textlength(texto, font=f)
    d.text(((x0 + x1 - ancho) / 2, y), texto, font=f, fill=color)


def barra_prob(d, x, y, ancho, alto, pct, color):
    d.rounded_rectangle([x, y, x + ancho, y + alto], radius=alto // 2,
                        fill=(255, 255, 255, 20), outline=CIAN_TENUE, width=1)
    lleno = int(ancho * min(max(pct, 0), 100) / 100)
    if lleno > alto:
        d.rounded_rectangle([x, y, x + lleno, y + alto],
                            radius=alto // 2, fill=color)


def puntos_acuerdo(d, x, y, activos, total, r=9, sep=26):
    """Cinco puntos = cinco modelos. Llenos = coinciden en lluvia."""
    for i in range(total):
        cx = x + i * sep
        relleno = CIAN if i < activos else (0, 0, 0, 0)
        d.ellipse([cx - r, y - r, cx + r, y + r],
                  fill=relleno, outline=CIAN, width=2)


# --------------------------------------------------------------------------
# TARJETA
# --------------------------------------------------------------------------

def titular(dia):
    p = dia["prob_ajustada"]
    if p >= 70:
        return "LLUVIA MUY PROBABLE", CIAN
    if p >= 45:
        return "PUEDE LLOVER HOY", CIAN
    if p >= 20:
        return "LLUVIA AISLADA", CIAN
    if dia["tmax"] and dia["tmax"] >= 38:
        return "CALOR EXTREMO", AMBAR
    return "DÍA SECO", AMBAR


def construir(datos, indice_dia=0, salida="tarjeta.png"):
    ciudades = list(datos.keys())
    principal = datos[ciudades[0]][indice_dia]

    img = Image.new("RGBA", (W, H), FONDO_ARRIBA)
    degradado(img)
    anillos_radar(img, W // 2, 300, [180, 300, 430, 570, 720])
    d = ImageDraw.Draw(img, "RGBA")

    # --- Encabezado ---------------------------------------------------
    d.text((70, 62), "RADAR", font=fuente("Bold", 40), fill=BLANCO)
    d.text((70, 104), "LAGUNERO", font=fuente("Light", 40), fill=CIAN)

    f = datetime.strptime(principal["fecha"], "%Y-%m-%d")
    fecha_txt = "%s %d de %s" % (DIAS_ES[f.weekday()], f.day,
                                 MESES_ES[f.month - 1])
    ancho = d.textlength(fecha_txt.upper(), font=fuente("Medium", 24))
    d.text((W - 70 - ancho, 80), fecha_txt.upper(),
           font=fuente("Medium", 24), fill=GRIS)
    d.line([(70, 178), (W - 70, 178)], fill=CIAN_TENUE, width=2)

    # --- Titular ------------------------------------------------------
    txt, color = titular(principal)
    centrar(d, txt, fuente("Bold", 78), 232, color)

    pct = principal["prob_ajustada"]
    centrar(d, "%.0f%% de probabilidad ajustada" % pct,
            fuente("Light", 34), 336, GRIS)

    # --- Ciudades -----------------------------------------------------
    y = 408
    for nombre in ciudades:
        dia = datos[nombre][indice_dia]
        d.rounded_rectangle([70, y, W - 70, y + 172], radius=26,
                            fill=PANEL, outline=CIAN_TENUE, width=1)

        d.text((110, y + 24), BONITO.get(nombre, nombre).upper(),
               font=fuente("Bold", 34), fill=BLANCO)

        temps = "%.0f° / %.0f°" % (dia["tmax"], dia["tmin"])
        aw = d.textlength(temps, font=fuente("Medium", 34))
        d.text((W - 110 - aw, y + 24), temps,
               font=fuente("Medium", 34), fill=AMBAR)

        p = dia["prob_ajustada"]
        barra_prob(d, 110, y + 86, W - 340, 24, p, CIAN)
        d.text((W - 200, y + 78), "%.0f%%" % p,
               font=fuente("Bold", 36), fill=CIAN)

        rafaga = dia.get("rafaga")
        detalle = "lluvia estimada %.1f mm" % dia["lluvia_mm"]
        if rafaga and rafaga >= 35:
            detalle += "   ·   rachas %.0f km/h" % rafaga
        d.text((110, y + 124), detalle, font=fuente("Light", 24), fill=GRIS)

        y += 190

    # --- Bloque de valor agregado -------------------------------------
    yb = y + 16
    d.rounded_rectangle([70, yb, W - 70, yb + 196], radius=26,
                        fill=(10, 30, 50, 220), outline=CIAN, width=2)
    d.text((110, yb + 22), "CÓMO LO CALCULAMOS",
           font=fuente("Bold", 26), fill=CIAN)

    ac = principal["acuerdo_modelos"].split("/")
    d.text((110, yb + 72), "Modelos que coinciden",
           font=fuente("Light", 24), fill=GRIS)
    puntos_acuerdo(d, 620, yb + 84, int(ac[0]), int(ac[1]))
    d.text((790, yb + 70), principal["acuerdo_modelos"],
           font=fuente("Medium", 26), fill=BLANCO)

    ens = principal["ensemble"].split("/")
    d.text((110, yb + 120), "Miembros del ensemble con lluvia",
           font=fuente("Light", 24), fill=GRIS)
    d.text((790, yb + 118), principal["ensemble"],
           font=fuente("Medium", 26), fill=BLANCO)

    d.text((110, yb + 158), "Confianza del pronóstico: %s"
           % principal["confianza"], font=fuente("Medium", 24), fill=AMBAR)

    # --- Pie ----------------------------------------------------------
    centrar(d, "Consenso de 5 modelos numéricos + ensemble de 31 miembros",
            fuente("Light", 22), H - 96, GRIS)
    centrar(d, "radarlagunero.com   ·   Avisos oficiales: SMN / CONAGUA",
            fuente("Medium", 22), H - 62, CIAN_TENUE)

    img.convert("RGB").save(salida, "PNG", quality=95)
    return salida


def main():
    if len(sys.argv) > 1:
        datos = json.load(open(sys.argv[1], encoding="utf-8"))
    else:
        datos = json.load(sys.stdin)
    salida = construir(datos, indice_dia=0)
    print("Tarjeta guardada en: %s" % salida)


if __name__ == "__main__":
    main()
