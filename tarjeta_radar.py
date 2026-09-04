#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Tarjeta para redes
====================================
Genera public/tarjeta.png (1080x1350) para publicar en Facebook e Instagram.
Ese mismo archivo es el og:image del sitio, así que cada liga compartida sale
con imagen en vez del recuadro gris.

USO:
    python3 tarjeta_radar.py                    # usa public/datos.json
    python3 tarjeta_radar.py --datos otro.json --salida public/tarjeta.png

Requiere Pillow. Busca Poppins en varias rutas y, si no la encuentra, cae a
DejaVu sin romperse.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

FONDO_A = (9, 24, 41)
FONDO_B = (16, 46, 74)
CIAN = (56, 189, 248)
CIAN_T = (30, 92, 130)
AMBAR = (245, 158, 11)
BLANCO = (248, 250, 252)
GRIS = (148, 163, 184)
PANEL = (17, 40, 63)
VERDE = (74, 222, 128)
ROJO = (251, 113, 133)

RUTAS_FUENTE = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Poppins-%s.ttf"),
    "/usr/share/fonts/truetype/poppins/Poppins-%s.ttf",
    "/usr/share/fonts/truetype/google-fonts/Poppins-%s.ttf",
    os.path.expanduser("~/Library/Fonts/Poppins-%s.ttf"),
]
RESPALDO = {"Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "SemiBold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "Medium": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "Regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "Light": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fuente(peso, tam):
    for patron in RUTAS_FUENTE:
        ruta = patron % peso
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tam)
    alt = RESPALDO.get(peso)
    if alt and os.path.exists(alt):
        return ImageFont.truetype(alt, tam)
    return ImageFont.load_default()


# --------------------------------------------------------------------------
# DIBUJO
# --------------------------------------------------------------------------

def degradado(img):
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(FONDO_A[i] + (FONDO_B[i] - FONDO_A[i]) * t)
                          for i in range(3)))


def anillos(img, cx, cy, radios):
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for r in radios:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CIAN + (26,), width=2)
    for ang in range(0, 360, 45):
        d.line([(cx, cy),
                (cx + math.cos(math.radians(ang)) * radios[-1],
                 cy + math.sin(math.radians(ang)) * radios[-1])],
               fill=CIAN + (14,), width=2)
    img.alpha_composite(capa)


def centrar(d, texto, f, y, color, x0=0, x1=W):
    ancho = d.textlength(texto, font=f)
    d.text(((x0 + x1 - ancho) / 2, y), texto, font=f, fill=color)


def barra(d, x, y, ancho, alto, pct, color=CIAN):
    d.rounded_rectangle([x, y, x + ancho, y + alto], radius=alto // 2,
                        fill=(255, 255, 255, 22), outline=CIAN_T, width=1)
    lleno = int(ancho * min(max(pct, 0), 100) / 100)
    if lleno > alto:
        d.rounded_rectangle([x, y, x + lleno, y + alto], radius=alto // 2, fill=color)


# --------------------------------------------------------------------------
# CONTENIDO
# --------------------------------------------------------------------------

def veredicto(p, tmax):
    if p >= 70:
        return "VA A LLOVER", CIAN
    if p >= 50:
        return "MÁS PROBABLE QUE LLUEVA", CIAN
    if p >= 30:
        return "PUEDE LLOVER", CIAN
    if p >= 12:
        return "POCA LLUVIA", BLANCO
    if tmax and tmax >= 40:
        return "CALOR EXTREMO", AMBAR
    if tmax and tmax >= 36:
        return "DÍA SECO Y MUY CALIENTE", AMBAR
    return "DÍA SECO", BLANCO


def redondear(p, paso=5):
    return int(round(p / paso) * paso)


def texto_pct(p):
    if 0 < p < 2.5:
        return "<5%"
    if 97.5 < p < 100:
        return ">95%"
    return "%d%%" % redondear(p)


def construir(datos, salida="public/tarjeta.png"):
    hoy = datos["comarca"][0]
    p = hoy["prob_pct"]["1.0"]
    centros = hoy["por_centro_pct"]
    nombres = {c["clave"]: c["nombre"] for c in datos["centros"]}

    ciudades = [(c["nombre"], c["dias"][0]) for c in datos["ciudades"].values()]
    tmax_ref = ciudades[0][1]["tmax"] if ciudades else None

    img = Image.new("RGBA", (W, H), FONDO_A)
    degradado(img)
    anillos(img, W // 2, 300, [180, 300, 430, 570, 720])
    d = ImageDraw.Draw(img, "RGBA")

    # Encabezado
    d.text((70, 60), "RADAR", font=fuente("Bold", 38), fill=BLANCO)
    d.text((70, 100), "LAGUNERO", font=fuente("Light", 38), fill=CIAN)
    f = datetime.strptime(hoy["fecha"], "%Y-%m-%d")
    fecha = "%s %d de %s" % (DIAS[f.weekday()], f.day, MESES[f.month - 1])
    ft = fuente("Medium", 23)
    d.text((W - 70 - d.textlength(fecha.upper(), font=ft), 78), fecha.upper(),
           font=ft, fill=GRIS)
    d.line([(70, 172), (W - 70, 172)], fill=CIAN_T, width=2)

    # Titular y cifra
    txt, color = veredicto(p, tmax_ref)
    tam = 74 if len(txt) <= 16 else 52
    centrar(d, txt, fuente("Bold", tam), 224, color)

    centrar(d, texto_pct(p), fuente("Bold", 132), 316, BLANCO)
    centrar(d, "de que caiga más de 1 mm de lluvia",
            fuente("Light", 29), 472, GRIS)

    # Rango entre centros: la honestidad, en una sola imagen
    vals = sorted(centros.values())
    lo, hi = redondear(vals[0]), redondear(vals[-1])
    bx, bw, by = 150, W - 300, 540
    barra(d, bx, by, bw, 18, 100, (255, 255, 255, 22))
    d.rounded_rectangle([bx + bw * lo / 100, by, bx + bw * hi / 100, by + 18],
                        radius=9, fill=CIAN + (110,))
    mx = bx + bw * redondear(p) / 100
    d.rounded_rectangle([mx - 3, by - 7, mx + 3, by + 25], radius=3, fill=BLANCO)
    d.text((bx, by + 34), "más seco %d%%" % lo, font=fuente("Light", 22), fill=GRIS)
    t2 = "más lluvioso %d%%" % hi
    d.text((bx + bw - d.textlength(t2, font=fuente("Light", 22)), by + 34), t2,
           font=fuente("Light", 22), fill=GRIS)

    # Los cuatro centros
    y = 630
    d.text((70, y), "LO QUE DICE CADA CENTRO", font=fuente("Bold", 25), fill=CIAN)
    y += 48
    for clave in ["gfs025", "icon_seamless", "ecmwf_ifs025", "gem_global"]:
        if clave not in centros:
            continue
        d.text((78, y), nombres.get(clave, clave), font=fuente("Medium", 27), fill=BLANCO)
        barra(d, 240, y + 10, W - 240 - 190, 16, centros[clave])
        v = texto_pct(centros[clave])
        d.text((W - 70 - d.textlength(v, font=fuente("Bold", 28)), y - 2), v,
               font=fuente("Bold", 28), fill=CIAN)
        y += 56

    conf = hoy["confianza_lluvia"]
    col = {"ALTA": VERDE, "MEDIA": AMBAR, "BAJA": ROJO}[conf]
    d.text((78, y + 6), "Diferencia entre ellos: %d puntos  ·  confianza %s"
           % (round(hoy["desacuerdo_pts"] or 0), conf.lower()),
           font=fuente("Light", 24), fill=col)

    # Temperatura por ciudad
    y += 76
    d.rounded_rectangle([70, y, W - 70, y + 148], radius=24, fill=PANEL,
                        outline=CIAN_T, width=1)
    ancho = (W - 140) / max(len(ciudades), 1)
    for i, (nombre, dia) in enumerate(ciudades):
        x0 = 70 + i * ancho
        centrar(d, nombre.upper(), fuente("Medium", 23), y + 26, GRIS, x0, x0 + ancho)
        centrar(d, "%.0f°" % dia["tmax"], fuente("Bold", 54), y + 58, AMBAR,
                x0, x0 + ancho)
        centrar(d, "mín %.0f°" % dia["tmin"], fuente("Light", 22), y + 116, GRIS,
                x0, x0 + ancho)

    # Método, en una línea
    y += 178
    d.rounded_rectangle([70, y, W - 70, y + 96], radius=22,
                        fill=(10, 30, 50, 220), outline=CIAN, width=2)
    centrar(d, "%d escenarios de %d centros meteorológicos"
            % (datos["miembros"], len(centros)), fuente("Bold", 30), y + 18, BLANCO)
    centrar(d, "Se cuenta cuántos superan 1 mm. Sin pesos ni ajustes.",
            fuente("Light", 24), y + 56, GRIS)

    # Pie
    centrar(d, "radarlagunero.com  ·  método y aciertos publicados",
            fuente("Medium", 24), H - 92, CIAN)
    centrar(d, "Avisos oficiales: SMN / CONAGUA  ·  datos de Open-Meteo (CC BY 4.0)",
            fuente("Light", 21), H - 56, GRIS)

    os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
    img.convert("RGB").save(salida, "PNG", optimize=True)
    return salida


def main():
    ap = argparse.ArgumentParser(description="Tarjeta de Radar Lagunero para redes")
    ap.add_argument("--datos", default="public/datos.json")
    ap.add_argument("--salida", default="public/tarjeta.png")
    args = ap.parse_args()

    if args.datos == "-":
        datos = json.load(sys.stdin)
    else:
        with open(args.datos, encoding="utf-8") as fh:
            datos = json.load(fh)

    ruta = construir(datos, args.salida)
    print("Tarjeta guardada en %s" % ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
