#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Tarjeta para redes
====================================
Genera public/tarjeta.png (1080x1350) para publicar en Facebook e Instagram.
Ese mismo archivo es el og:image del sitio, así que cada liga compartida sale
con imagen en vez del recuadro gris.

Criterios de diseño:
  · El dominio se lee sin esfuerzo: la gente ve la imagen en el muro, no la liga.
  · Nada por debajo de 26 px. A 1080 de ancho, en un celular la imagen se ve a
    ~400 px: todo lo que baje de 26 px se vuelve ilegible.
  · No se publican tres cifras iguales. Torreón, Gómez y Lerdo caen en la misma
    celda de los modelos globales; si la diferencia entre ellas no llega a 1 °C
    se publica una sola cifra para la comarca. Solo cuando de verdad difieren se
    abre el desglose por ciudad.

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

# Nada por debajo de esto se publica: a 1080 px de ancho, en un muro de celular
# la imagen se ve a ~400 px y 26 px se convierten en 10 px reales.
MIN_LEGIBLE = 26

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

_CACHE = {}


def fuente(peso, tam):
    clave = (peso, tam)
    if clave in _CACHE:
        return _CACHE[clave]
    f = None
    for patron in RUTAS_FUENTE:
        ruta = patron % peso
        if os.path.exists(ruta):
            f = ImageFont.truetype(ruta, tam)
            break
    if f is None:
        alt = RESPALDO.get(peso)
        f = ImageFont.truetype(alt, tam) if alt and os.path.exists(alt) \
            else ImageFont.load_default()
    _CACHE[clave] = f
    return f


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


def derecha(d, texto, f, x, y, color):
    d.text((x - d.textlength(texto, font=f), y), texto, font=f, fill=color)


def ajustar(d, texto, peso, tam, ancho_max, minimo=MIN_LEGIBLE):
    """Baja el tamaño hasta que el texto quepa, nunca por debajo de `minimo`."""
    while tam > minimo:
        if d.textlength(texto, font=fuente(peso, tam)) <= ancho_max:
            break
        tam -= 2
    return fuente(peso, tam)


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
    if p is None:
        return "—"
    if 0 < p < 2.5:
        return "<5%"
    if 97.5 < p < 100:
        return ">95%"
    return "%d%%" % redondear(p)


def temperatura_util(ciudades):
    """Decide si vale la pena desglosar la temperatura por ciudad.

    Devuelve (modo, filas). El modo es "comarca" cuando las tres coinciden
    dentro de 1 °C —publicar tres veces la misma cifra finge un detalle que los
    modelos globales no tienen— y "ciudades" cuando de verdad difieren.
    """
    filas = [(c["nombre"], c["dias"][0]) for c in ciudades.values()]
    if not filas:
        return "comarca", []
    maxs = [f[1]["tmax"] for f in filas]
    mins = [f[1]["tmin"] for f in filas]
    if (max(maxs) - min(maxs) < 1.0) and (max(mins) - min(mins) < 1.0):
        return "comarca", filas
    return "ciudades", filas


def construir(datos, salida="public/tarjeta.png"):
    hoy = datos["comarca"][0]
    p = hoy["prob_pct"]["1.0"]
    centros = hoy["por_centro_pct"]
    nombres = {c["clave"]: c["nombre"] for c in datos["centros"]}
    acum = hoy.get("acumulado_mm") or {}

    modo, filas = temperatura_util(datos["ciudades"])
    tmax_ref = filas[0][1]["tmax"] if filas else None

    img = Image.new("RGBA", (W, H), FONDO_A)
    degradado(img)
    anillos(img, W // 2, 300, [180, 300, 430, 570, 720])
    d = ImageDraw.Draw(img, "RGBA")

    # ------------------------------------------------------------------
    # Retícula vertical. Se define de arriba abajo con alturas explícitas
    # para que ningún bloque invada al siguiente cuando cambien las cifras.
    # ------------------------------------------------------------------
    Y_TITULAR   = 190
    Y_CIFRA     = 272
    Y_SUBTITULO = 430
    Y_RANGO     = 500
    Y_HORAS     = 556          # franja "¿a qué hora?"
    ALTO_BARRAS = 126
    Y_RESUMEN   = 812          # una línea con el desacuerdo entre centros
    Y_LLUVIA    = 856          # panel "si llueve, ¿cuánta?"
    ALTO_LLUVIA = 132
    Y_ACUMULADO = 1000
    Y_TEMP      = 1048
    ALTO_TEMP   = 124
    Y_BANDA     = H - 166      # franja del dominio

    # ---------------------------------------------------------- Encabezado
    d.text((70, 52), "RADAR", font=fuente("Bold", 40), fill=BLANCO)
    d.text((70, 94), "LAGUNERO", font=fuente("Light", 40), fill=CIAN)
    f = datetime.strptime(hoy["fecha"], "%Y-%m-%d")
    fecha = "%s %d de %s" % (DIAS[f.weekday()], f.day, MESES[f.month - 1])
    derecha(d, fecha.upper(), fuente("Medium", MIN_LEGIBLE), W - 70, 74, GRIS)
    d.line([(70, 168), (W - 70, 168)], fill=CIAN_T, width=2)

    # ---------------------------------------------------- Titular y cifra
    txt, color = veredicto(p, tmax_ref)
    centrar(d, txt, ajustar(d, txt, "Bold", 74, W - 140, minimo=44),
            Y_TITULAR, color)
    centrar(d, texto_pct(p), fuente("Bold", 126), Y_CIFRA, BLANCO)
    centrar(d, "de que caiga más de 1 mm de lluvia",
            fuente("Light", 30), Y_SUBTITULO, GRIS)

    # Rango entre centros: el desacuerdo, dibujado. Las cifras exactas de los
    # extremos no se rotulan aquí porque vienen abajo, centro por centro.
    vals = sorted(centros.values())
    lo, hi = redondear(vals[0]), redondear(vals[-1])
    bx, bw = 150, W - 300
    barra(d, bx, Y_RANGO, bw, 18, 100, (255, 255, 255, 22))
    d.rounded_rectangle([bx + bw * lo / 100, Y_RANGO,
                         bx + bw * hi / 100, Y_RANGO + 18], radius=9,
                        fill=CIAN + (110,))
    mx = bx + bw * redondear(p) / 100
    d.rounded_rectangle([mx - 3, Y_RANGO - 7, mx + 3, Y_RANGO + 25],
                        radius=3, fill=BLANCO)

    # ------------------------------------------------------ ¿A qué hora?
    # Lo que la gente realmente pregunta. La serie viene del modelo determinista
    # de referencia, no del ensemble, así que las barras marcan el MOMENTO del
    # día, no el nivel: se dice en la propia tarjeta para no fingir precisión.
    horas = datos.get("por_hora") or []
    if horas:
        pico = max(horas, key=lambda x: x["prob_pct"])
        tope = max(2, max(x["prob_pct"] for x in horas))

        d.text((70, Y_HORAS), "¿A QUÉ HORA?", font=fuente("Bold", MIN_LEGIBLE),
               fill=CIAN)
        if pico["prob_pct"] > 0:
            derecha(d, "más probable cerca de las %s" % pico["hora"],
                    fuente("Medium", MIN_LEGIBLE), W - 70, Y_HORAS, BLANCO)

        base = Y_HORAS + 42 + ALTO_BARRAS          # línea de piso de las barras
        paso = (W - 140) / len(horas)
        ancho_b = min(paso - 10, 56)
        for i, x in enumerate(horas):
            cx = 70 + i * paso + (paso - ancho_b) / 2
            alto = max(4, ALTO_BARRAS * x["prob_pct"] / tope)
            es_pico = x is pico and pico["prob_pct"] > 0
            d.rounded_rectangle([cx, base - alto, cx + ancho_b, base],
                                radius=6, fill=BLANCO if es_pico else CIAN + (105,))
            # una etiqueta cada tres horas: más que eso no se lee en el muro
            if i % 3 == 0:
                centrar(d, x["hora"][:2] + "h", fuente("Light", MIN_LEGIBLE),
                        base + 10, GRIS, cx - 12, cx + ancho_b + 12)

        d.line([(70, base), (W - 70, base)], fill=CIAN_T, width=2)
        centrar(d, "Marca el momento del día, no el nivel",
                fuente("Light", MIN_LEGIBLE), base + 48, GRIS)

    # Los cuatro centros ya no se desglosan aquí —eso vive en el sitio—, pero el
    # desacuerdo entre ellos sí se queda: es lo que sostiene la confianza.
    vals_o = sorted(centros.values())
    conf = hoy["confianza_lluvia"]
    col = {"ALTA": VERDE, "MEDIA": AMBAR, "BAJA": ROJO}.get(conf, GRIS)
    lo_o, hi_o = redondear(vals_o[0]), redondear(vals_o[-1])
    if lo_o == hi_o:
        resumen = "Los %d centros coinciden en %d%%  ·  confianza %s" % (
            len(centros), lo_o, conf.lower())
    else:
        resumen = "Los %d centros van de %d%% a %d%%  ·  confianza %s" % (
            len(centros), lo_o, hi_o, conf.lower())
    centrar(d, resumen, fuente("Light", 27), Y_RESUMEN, col)

    # ---------------------------------------------------- ¿Cuánta lluvia?
    # Esto sí cambia todos los días: qué tan probable es que solo caigan gotas,
    # que se note, o que sea un aguacero de verdad.
    d.rounded_rectangle([70, Y_LLUVIA, W - 70, Y_LLUVIA + ALTO_LLUVIA],
                        radius=22, fill=PANEL, outline=CIAN_T, width=1)
    d.text((98, Y_LLUVIA + 14), "SI LLUEVE, ¿CUÁNTA?",
           font=fuente("Bold", MIN_LEGIBLE), fill=CIAN)
    escala = [("Gotas", "0.2"), ("Se nota", "1.0"),
              ("Fuerte", "5.0"), ("Aguacero", "20.0")]
    ancho = (W - 200) / len(escala)
    for i, (etiqueta, umbral) in enumerate(escala):
        v = hoy["prob_pct"].get(umbral)
        x0 = 100 + i * ancho
        # El umbral del titular va en cian para que se vea que la cifra grande
        # de arriba es esta misma columna, no un número aparte.
        titular = umbral == "1.0"
        tinta = CIAN if titular else (BLANCO if v else GRIS)
        centrar(d, texto_pct(v), fuente("Bold", 42), Y_LLUVIA + 48, tinta,
                x0, x0 + ancho)
        centrar(d, etiqueta, fuente("Medium" if titular else "Light", MIN_LEGIBLE),
                Y_LLUVIA + 94, CIAN if titular else GRIS, x0, x0 + ancho)

    if acum.get("p50") is not None:
        centrar(d, "Lo más probable: %.1f mm  ·  si se pone feo: %.1f mm"
                % (acum["p50"], acum.get("p90") or acum["p50"]),
                fuente("Light", MIN_LEGIBLE), Y_ACUMULADO, GRIS)

    # ------------------------------------------------------- Temperatura
    # Una sola cifra cuando las tres ciudades coinciden: publicar 35°, 35° y 35°
    # no informa a nadie, solo llena espacio.
    d.rounded_rectangle([70, Y_TEMP, W - 70, Y_TEMP + ALTO_TEMP],
                        radius=22, fill=PANEL, outline=CIAN_T, width=1)
    raf = filas[0][1].get("rafaga_kmh") if filas else None

    if modo == "comarca" and filas:
        dia = filas[0][1]
        centrar(d, "TODA LA COMARCA", fuente("Medium", MIN_LEGIBLE),
                Y_TEMP + 10, GRIS)
        d.text((140, Y_TEMP + 44), "máx %.0f°" % dia["tmax"],
               font=fuente("Bold", 54), fill=AMBAR)
        derecha(d, "mín %.0f°" % dia["tmin"], fuente("Bold", 54), W - 140,
                Y_TEMP + 44, BLANCO)
        if raf:
            centrar(d, "ráfagas", fuente("Light", MIN_LEGIBLE),
                    Y_TEMP + 50, GRIS)
            centrar(d, "%.0f km/h" % raf, fuente("Medium", MIN_LEGIBLE),
                    Y_TEMP + 80, GRIS)
    else:
        ancho = (W - 140) / max(len(filas), 1)
        for i, (nombre, dia) in enumerate(filas):
            x0 = 70 + i * ancho
            centrar(d, nombre.upper(), fuente("Medium", MIN_LEGIBLE),
                    Y_TEMP + 10, GRIS, x0, x0 + ancho)
            centrar(d, "%.0f°" % dia["tmax"], fuente("Bold", 50),
                    Y_TEMP + 40, AMBAR, x0, x0 + ancho)
            centrar(d, "mín %.0f°" % dia["tmin"], fuente("Light", MIN_LEGIBLE),
                    Y_TEMP + 92, GRIS, x0, x0 + ancho)

    # ------------------------------------------------------------- Pie
    # La franja del dominio: es lo que convierte una imagen compartida en una
    # visita al sitio. Va grande, con contraste y de ancho completo.
    d.rectangle([0, Y_BANDA, W, H], fill=(7, 20, 36))
    d.line([(0, Y_BANDA), (W, Y_BANDA)], fill=CIAN, width=3)
    centrar(d, "radarlagunero.com", fuente("Bold", 60), Y_BANDA + 14, CIAN)
    centrar(d, "%d escenarios de %d centros  ·  método y aciertos publicados"
            % (datos["miembros"], len(centros)),
            fuente("Light", MIN_LEGIBLE), Y_BANDA + 92, BLANCO)
    centrar(d, "Avisos oficiales: SMN / CONAGUA y Protección Civil",
            fuente("Light", MIN_LEGIBLE), Y_BANDA + 124, GRIS)

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
