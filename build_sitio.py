#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Generador del sitio
=====================================
Escribe public/index.html con el pronóstico ya renderizado en el HTML, más
datos.json (lo mismo, abierto y auditable), robots.txt y sitemap.xml.

Que el contenido viaje en el HTML —y no lo pinte JavaScript en el navegador—
es lo que permite competir por "clima Torreón" y entrar a Google Discover.

USO:  python3 build_sitio.py [--dias 7]
Solo biblioteca estándar.
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime

import radar_lagunero as rl

SITIO = "https://radarlagunero.com"
RAIZ = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(RAIZ, "public")
ORDEN = ["torreon", "gomez", "lerdo"]

DIAS_LARGO = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Icono de pestaña: los anillos del radar en SVG, sin pedir nada al servidor.
FAVICON = ("data:image/svg+xml,"
           "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='14' fill='%23091829'/%3E"
           "%3Cg fill='none' stroke='%2338BDF8' stroke-width='3'%3E"
           "%3Ccircle cx='32' cy='32' r='8'/%3E"
           "%3Ccircle cx='32' cy='32' r='17' opacity='.6'/%3E"
           "%3Ccircle cx='32' cy='32' r='26' opacity='.3'/%3E%3C/g%3E"
           "%3Ccircle cx='32' cy='32' r='4' fill='%2338BDF8'/%3E%3C/svg%3E")


# --------------------------------------------------------------------------
# TEXTO
# --------------------------------------------------------------------------

def veredicto(lluvia, temp):
    """Titular corto, decidido por la probabilidad de pasar de 1 mm — la
    lluvia que la gente nota — y no por 'cayó una gota'."""
    p = lluvia["prob_titular"]
    t = temp["tmax"]
    if p >= 70:
        return "Va a llover", "lluvia"
    if p >= 50:
        return "Más probable que llueva", "lluvia"
    if p >= 30:
        return "Puede llover", "lluvia"
    if p >= 12:
        return "Poca lluvia esperada", "seco"
    if t is not None and t >= 40:
        return "Calor extremo", "calor"
    if t is not None and t >= 36:
        return "Día seco y muy caluroso", "calor"
    return "Día seco", "seco"


def fecha_larga(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %d de %s de %d" % (DIAS_LARGO[d.weekday()], d.day,
                                  MESES[d.month - 1], d.year)


def fecha_corta(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %d" % (DIAS_CORTO[d.weekday()], d.day)


def num(v, fmt="%.0f", vacio="—"):
    return fmt % v if v is not None else vacio


def esc(s):
    return html.escape(str(s))


def pct(p):
    """Redondea al 5 % más cercano, pero nunca convierte en 0 algo que no lo es:
    decir '0%' cuando quedan 3 escenarios de 139 con aguacero sería mentir."""
    if p is None:
        return "—"
    if 0 < p < 2.5:
        return "&lt;5%"
    if 97.5 < p < 100:
        return "&gt;95%"
    return "%d%%" % rl.a_multiplo(p)


# --------------------------------------------------------------------------
# PIEZAS
# --------------------------------------------------------------------------

def barra(pct, clase=""):
    a = min(max(pct or 0, 0), 100)
    return '<div class="barra %s"><span style="width:%.0f%%"></span></div>' % (clase, a)


def bloque_centros(lluvia):
    """Cuatro centros, cuatro respuestas, a la vista. Nadie más publica esto."""
    filas = []
    for clave, nombre, inst in rl.ENSEMBLES:
        if clave not in lluvia["por_centro"]:
            filas.append('<li class="centro caido"><span class="cn">%s</span>'
                         '<span class="ci">%s</span>'
                         '<span class="cbar">sin datos en esta corrida</span></li>'
                         % (esc(nombre), esc(inst)))
            continue
        v = lluvia["por_centro"][clave]
        filas.append('<li class="centro"><span class="cn">%s</span>'
                     '<span class="ci">%s</span>'
                     '<span class="cbar">%s<b>%s</b></span></li>'
                     % (esc(nombre), esc(inst), barra(v), pct(v)))
    return '<ul class="centros">%s</ul>' % "".join(filas)


def escalera(lluvia):
    et = [(0.2, "Cae algo", "una llovizna que casi ni moja"),
          (1.0, "Llueve de verdad", "moja el pavimento"),
          (5.0, "Llueve fuerte", "se hacen charcos"),
          (20.0, "Aguacero", "riesgo de encharcamiento")]
    filas = []
    for u, tit, desc in et:
        p = lluvia["prob"][u]
        dest = " destacado" if u == rl.UMBRAL_TITULAR else ""
        filas.append('<li class="paso%s"><span class="pu">más de %s mm</span>'
                     '<span class="pt">%s <i>%s</i></span>'
                     '<span class="pb">%s<b>%s</b></span></li>'
                     % (dest, ("%g" % u), esc(tit), esc(desc),
                        barra(p), pct(p)))
    return '<ul class="escalera">%s</ul>' % "".join(filas)


def franja_horaria(horario):
    """Responde '¿a qué hora?'. De la hora actual en adelante."""
    h = horario["hourly"]
    ahora = datetime.now(rl.ZONA_LOCAL).replace(tzinfo=None, minute=0,
                                                second=0, microsecond=0)
    filas = []
    for i, t in enumerate(h["time"]):
        cuando = datetime.strptime(t, "%Y-%m-%dT%H:%M")
        if cuando < ahora:
            continue
        if len(filas) >= 18:
            break
        p = h["precipitation_probability"][i] or 0
        etiqueta = ("%s 0h" % DIAS_CORTO[cuando.weekday()].lower()
                    if cuando.hour == 0 else "%02dh" % cuando.hour)
        filas.append('<li%s><span class="hh">%s</span>'
                     '<span class="hbar"><i style="height:%d%%"></i></span>'
                     '<span class="hp">%d%%</span><span class="ht">%s°</span></li>'
                     % (' class="ahora"' if not filas else "", etiqueta,
                        max(int(p), 2), int(p), num(h["temperature_2m"][i])))
    if not filas:
        return ""
    return '<div class="franja-envoltura"><ul class="franja">%s</ul></div>' % "".join(filas)


def tabla_dias(fechas, lluvias, temps):
    filas = []
    for iso, a, t in zip(fechas, lluvias, temps):
        v = a["prob_titular"]
        filas.append("<tr><th>%s</th><td>%s° <i>%s°</i></td>"
                     "<td class='cel-barra'>%s<b>%s</b></td>"
                     "<td>%s mm</td><td><span class='eti e-%s'>%s</span></td></tr>"
                     % (esc(fecha_corta(iso)), num(t["tmax"]), num(t["tmin"]),
                        barra(v), pct(v), num(a["acumulado"]["p90"], "%.1f"),
                        a["confianza_lluvia"].lower(),
                        a["confianza_lluvia"].capitalize()))
    return ("<table class='dias'><thead><tr><th>Día</th><th>Máx/mín</th>"
            "<th>Prob. de más de 1 mm</th><th>Hasta</th><th>Confianza</th>"
            "</tr></thead><tbody>%s</tbody></table>" % "".join(filas))


def tarjetas_temp(datos):
    filas = []
    for clave in ORDEN:
        c = datos["ciudades"].get(clave)
        if not c:
            continue
        t = c["temps"][0]
        filas.append('<li><span class="tn">%s</span>'
                     '<span class="tt"><b>%s°</b> <i>%s°</i></span>'
                     '<span class="tr">rachas %s</span></li>'
                     % (esc(c["nombre"]), num(t["tmax"]), num(t["tmin"]),
                        num(t["rafaga"], "%.0f km/h")))
    return '<ul class="temps">%s</ul>' % "".join(filas)


def bloque_polvo(tol):
    clase = {"NULO": "ok", "BAJO": "ok", "MODERADO": "medio",
             "ALTO": "alto"}[tol["nivel"]]
    return """
      <div class="polvo %s">
        <div class="polvo-cab">
          <span class="pnivel">Riesgo de tolvanera: <b>%s</b></span>
          <p>%s</p>
        </div>
        <ul class="polvo-datos">
          <li><span>PM10 máximo</span><b>%.0f µg/m³</b></li>
          <li><span>Polvo en suspensión</span><b>%.0f µg/m³</b></li>
          <li><span>Visibilidad mínima</span><b>%.1f km</b></li>
          <li><span>Racha máxima</span><b>%.0f km/h</b></li>
        </ul>
      </div>""" % (clase, esc(tol["nivel"].capitalize()), esc(tol["texto"]),
                   tol["pm10"], tol["polvo"], tol["visibilidad_km"], tol["rafaga"])


def bloque_aciertos(m):
    """El marcador. Si todavía no hay nada, se dice; no se inventa."""
    if not m or not m.get("dias_verificados"):
        return """
        <div class="marcador vacio">
          <p class="mgrande">Empezamos a medir hoy</p>
          <p>Cada pronóstico que publicamos queda guardado con fecha y hora.
          Cuando el día pasa, lo comparamos contra lo que registró el observatorio
          del aeropuerto de Torreón y publicamos el resultado aquí, salga como
          salga. Todavía no hay días completos que calificar.</p>
        </div>"""

    hs = [h for h in m["por_horizonte"] if h["error_medio_tmax"] is not None][:5]
    filas = "".join(
        "<tr><th>%s</th><td>%s °C</td><td>%s</td><td>%s</td></tr>" % (
            "Mismo día" if h["horizonte_dias"] == 0 else "A %d día%s" % (
                h["horizonte_dias"], "s" if h["horizonte_dias"] > 1 else ""),
            num(h["error_medio_tmax"], "%.1f"),
            "%d%%" % h["acierto_lluvia_pct"] if h["acierto_lluvia_pct"] is not None else "—",
            h["n_dias"]) for h in hs)

    fiab = ""
    if m.get("fiabilidad"):
        fiab = ("<p class='mnota'>Fiabilidad — de las veces que dijimos cada cosa, "
                "cuántas ocurrió: %s</p>" % " · ".join(
                    "%s → %d%% (%d casos)" % (b["rango"], b["observado_pct"], b["n"])
                    for b in m["fiabilidad"]))

    return """
        <div class="marcador">
          <p class="mgrande">%d días verificados</p>
          <p>Del %s al %s, contra el observatorio del aeropuerto de Torreón.
          Error medio en la máxima: <b>%s °C</b>.</p>
          <table class="mtabla"><thead><tr><th>Anticipación</th>
          <th>Error en la máxima</th><th>Acierto en lluvia</th><th>Días</th>
          </tr></thead><tbody>%s</tbody></table>
          %s
        </div>""" % (m["dias_verificados"], esc(m["desde"]), esc(m["hasta"]),
                     num(m.get("error_medio_tmax_global"), "%.1f"), filas, fiab)


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

CSS = """
:root{--fondo:#091829;--fondo2:#102E4A;--panel:#11283F;--linea:#1E5C82;
 --cian:#38BDF8;--ambar:#F59E0B;--hueso:#F8FAFC;--gris:#94A3B8;
 --verde:#4ADE80;--rojo:#FB7185}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{font-family:'Poppins',system-ui,-apple-system,'Segoe UI',sans-serif;
 background:var(--fondo);color:var(--hueso);line-height:1.55;
 background-image:linear-gradient(180deg,var(--fondo) 0%,var(--fondo2) 100%);
 background-attachment:fixed}
.env{max-width:1000px;margin:0 auto;padding:0 20px}
a{color:var(--cian)}
b{font-weight:600}
.radar{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.radar span{position:absolute;left:50%;top:-140px;transform:translateX(-50%);
 border:1px solid rgba(56,189,248,.09);border-radius:50%}
header.top,main,footer{position:relative;z-index:1}

header.top{border-bottom:1px solid var(--linea);padding:18px 0 0}
.top .env:first-child{display:flex;justify-content:space-between;
 align-items:center;flex-wrap:wrap;gap:8px}
.marca{display:flex;align-items:baseline;gap:8px;letter-spacing:.06em}
.marca b{font-weight:700;font-size:1.2rem}
.marca span{font-weight:300;font-size:1.2rem;color:var(--cian)}
.sello{font-size:.75rem;color:var(--gris);text-align:right;line-height:1.4}
nav{display:flex;gap:22px;overflow-x:auto;padding:12px 0 0;margin-top:10px;
 border-top:1px solid rgba(30,92,130,.4)}
nav a{color:var(--gris);text-decoration:none;font-size:.78rem;letter-spacing:.08em;
 text-transform:uppercase;padding-bottom:10px;white-space:nowrap;
 border-bottom:2px solid transparent}
nav a:hover,nav a:focus{color:var(--cian);border-bottom-color:var(--cian)}

.hero{padding:40px 0 6px;text-align:center}
.hero .fecha{color:var(--gris);text-transform:uppercase;letter-spacing:.14em;
 font-size:.78rem}
.hero h1{font-size:clamp(1.9rem,6vw,3.2rem);font-weight:700;line-height:1.08;
 margin:10px 0 4px;color:var(--cian)}
.hero h1.calor{color:var(--ambar)}
.hero h1.seco{color:var(--hueso)}
.hero .sub{color:var(--gris);font-weight:300;font-size:1rem}
.cifra{margin:26px auto 0;max-width:430px}
.cifra .n{font-size:clamp(3rem,13vw,5rem);font-weight:700;line-height:1}
.cifra .q{color:var(--gris);font-weight:300;font-size:.95rem;margin-top:2px}
.rango{margin:20px auto 0;max-width:430px}
.rango .rb{position:relative;height:10px;border-radius:99px;
 background:rgba(255,255,255,.08);border:1px solid var(--linea)}
.rango .rb i{position:absolute;top:-1px;bottom:-1px;background:var(--cian);
 opacity:.35;border-radius:99px}
.rango .rb u{position:absolute;top:-5px;width:3px;height:18px;
 background:var(--hueso);border-radius:2px}
.rango .rt{display:flex;justify-content:space-between;color:var(--gris);
 font-size:.75rem;margin-top:8px}
.lectura{max-width:620px;margin:24px auto 0;font-weight:300;font-size:1.02rem}
.eti{display:inline-block;padding:3px 12px;border-radius:999px;font-size:.7rem;
 letter-spacing:.09em;text-transform:uppercase;border:1px solid currentColor}
.e-alta{color:var(--verde)}.e-media{color:var(--ambar)}.e-baja{color:var(--rojo)}

section{padding:34px 0;scroll-margin-top:20px}
h2{font-size:1rem;letter-spacing:.13em;text-transform:uppercase;color:var(--cian);
 font-weight:600;margin-bottom:6px}
h2+.intro{color:var(--gris);font-weight:300;font-size:.92rem;margin-bottom:18px;
 max-width:640px}
.caja{background:var(--panel);border:1px solid var(--linea);border-radius:18px;
 padding:20px 22px}
.barra{flex:1;height:10px;border-radius:99px;background:rgba(255,255,255,.08);
 border:1px solid var(--linea);overflow:hidden;min-width:60px}
.barra span{display:block;height:100%;background:var(--cian);border-radius:99px}

.centros,.escalera{list-style:none;display:grid;gap:10px}
.centro{display:grid;grid-template-columns:64px 1fr 190px;gap:14px;
 align-items:center;padding:12px 0;border-bottom:1px solid rgba(30,92,130,.4)}
.centro:last-child{border-bottom:0}
.centro .cn{font-weight:600}
.centro .ci{color:var(--gris);font-weight:300;font-size:.86rem}
.centro .cbar{display:flex;align-items:center;gap:10px}
.centro .cbar b{color:var(--cian);min-width:46px;text-align:right}
.centro.caido .cbar{color:var(--gris);font-size:.82rem;font-weight:300}

.paso{display:grid;grid-template-columns:120px 1fr 170px;gap:14px;
 align-items:center;padding:11px 0;border-bottom:1px solid rgba(30,92,130,.4)}
.paso:last-child{border-bottom:0}
.paso.destacado{background:rgba(56,189,248,.07);border-radius:12px;
 padding:11px 12px;border-bottom:0}
.paso .pu{color:var(--gris);font-size:.85rem;font-weight:300}
.paso .pt i{display:block;color:var(--gris);font-style:normal;font-size:.8rem;
 font-weight:300}
.paso .pb{display:flex;align-items:center;gap:10px}
.paso .pb b{color:var(--cian);min-width:46px;text-align:right}

.franja-envoltura{overflow-x:auto;padding-bottom:6px}
.franja{list-style:none;display:flex;gap:6px;min-width:max-content}
.franja li{width:46px;text-align:center;padding:8px 2px;border-radius:12px}
.franja li.ahora{background:rgba(56,189,248,.10);outline:1px solid var(--linea)}
.franja .hh{display:block;font-size:.7rem;color:var(--gris)}
.franja .hbar{display:block;height:56px;margin:6px auto;width:12px;
 background:rgba(255,255,255,.07);border-radius:4px;position:relative}
.franja .hbar i{position:absolute;bottom:0;left:0;right:0;background:var(--cian);
 border-radius:4px}
.franja .hp{display:block;font-size:.72rem;color:var(--cian);font-weight:600}
.franja .ht{display:block;font-size:.72rem;color:var(--ambar)}

.dias{width:100%;border-collapse:collapse;font-weight:300;font-size:.9rem}
.dias th,.dias td{padding:11px 10px;text-align:left;
 border-bottom:1px solid rgba(30,92,130,.4)}
.dias thead th{color:var(--cian);font-size:.72rem;letter-spacing:.08em;
 text-transform:uppercase;font-weight:500}
.dias tbody th{font-weight:500;white-space:nowrap}
.dias td i{color:var(--gris);font-style:normal}
.dias tbody td:nth-child(2){color:var(--ambar);white-space:nowrap}
.cel-barra{display:flex;align-items:center;gap:10px;min-width:150px}
.cel-barra b{color:var(--cian);min-width:42px;text-align:right}

.temps{list-style:none;display:grid;gap:10px;
 grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.temps li{background:var(--panel);border:1px solid var(--linea);
 border-radius:14px;padding:14px 16px}
.temps .tn{display:block;font-weight:600}
.temps .tt{display:block;margin:4px 0 2px;font-size:1.3rem;color:var(--ambar)}
.temps .tt i{color:var(--gris);font-style:normal;font-weight:300;font-size:1rem}
.temps .tr{display:block;color:var(--gris);font-size:.8rem;font-weight:300}

.polvo{border-radius:18px;padding:20px 22px;border:1px solid var(--linea);
 background:var(--panel)}
.polvo.medio{border-color:var(--ambar);background:rgba(245,158,11,.07)}
.polvo.alto{border-color:var(--rojo);background:rgba(251,113,133,.09)}
.pnivel{font-size:.78rem;letter-spacing:.1em;text-transform:uppercase;
 color:var(--gris)}
.pnivel b{color:var(--hueso);letter-spacing:0}
.polvo-cab p{margin-top:8px;font-weight:300}
.polvo-datos{list-style:none;display:grid;gap:8px;margin-top:16px;
 grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.polvo-datos li{display:flex;justify-content:space-between;gap:8px;
 padding:9px 12px;background:rgba(0,0,0,.18);border-radius:10px;font-size:.85rem}
.polvo-datos span{color:var(--gris);font-weight:300}

.marcador .mgrande{font-size:1.5rem;font-weight:600;color:var(--cian);
 margin-bottom:8px}
.marcador p{font-weight:300}
.mtabla{width:100%;border-collapse:collapse;margin-top:16px;font-size:.88rem}
.mtabla th,.mtabla td{padding:9px 10px;text-align:left;
 border-bottom:1px solid rgba(30,92,130,.4);font-weight:300}
.mtabla thead th{color:var(--cian);font-size:.7rem;letter-spacing:.08em;
 text-transform:uppercase;font-weight:500}
.mtabla tbody th{font-weight:500}
.mnota{color:var(--gris);font-size:.82rem;margin-top:14px}

.metodo ol{margin:0 0 0 18px;font-weight:300}
.metodo li{margin-bottom:10px}
.metodo code{background:rgba(0,0,0,.3);padding:1px 6px;border-radius:5px;
 font-size:.86em;color:var(--cian)}
.kv{display:flex;justify-content:space-between;gap:10px;padding:10px 0;
 flex-wrap:wrap;border-bottom:1px solid rgba(30,92,130,.4);font-weight:300;
 color:var(--gris)}
.kv:last-of-type{border-bottom:0}
.kv span{min-width:0}
.kv b{color:var(--hueso);font-weight:500;text-align:right;min-width:0;
 overflow-wrap:anywhere}

.aviso{border-left:3px solid var(--ambar);padding:14px 18px;color:var(--gris);
 font-weight:300;font-size:.92rem;background:rgba(245,158,11,.06);
 border-radius:0 12px 12px 0}
.aviso b{color:var(--hueso)}

.faq details{background:var(--panel);border:1px solid var(--linea);
 border-radius:14px;padding:15px 20px;margin-bottom:9px}
.faq summary{cursor:pointer;font-weight:500}
.faq p{color:var(--gris);font-weight:300;margin-top:9px}

footer{border-top:1px solid var(--linea);padding:28px 0 44px;margin-top:24px;
 color:var(--gris);font-weight:300;font-size:.84rem}
footer p{margin-bottom:7px}
.fcols{display:grid;gap:18px;margin-bottom:18px;
 grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
footer h3{color:var(--hueso);font-size:.75rem;letter-spacing:.1em;
 text-transform:uppercase;margin-bottom:8px;font-weight:600}

@media (max-width:640px){
 .centro{grid-template-columns:56px 1fr;row-gap:6px}
 .centro .cbar{grid-column:1/-1}
 .paso{grid-template-columns:1fr 1fr;row-gap:4px}
 .paso .pb{grid-column:1/-1}
 .dias thead{display:none}
 .dias tbody tr{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;
  padding:12px 0;border-bottom:1px solid rgba(30,92,130,.4)}
 .dias th,.dias td{border:0;padding:2px 0}
 .cel-barra{grid-column:1/-1}
}
"""


# --------------------------------------------------------------------------
# PÁGINA
# --------------------------------------------------------------------------

def pagina(datos, aciertos):
    fechas, lluvias = datos["fechas"], datos["lluvia"]
    hoy_iso, hoy = fechas[0], lluvias[0]
    principal = datos["ciudades"]["torreon"]
    t0 = principal["temps"][0]

    titulo, clase = veredicto(hoy, t0)
    p = rl.a_multiplo(hoy["prob_titular"])
    vals = sorted(hoy["por_centro"].values())
    lo, hi = rl.a_multiplo(vals[0]), rl.a_multiplo(vals[-1])

    anillos = "".join('<span style="width:%dpx;height:%dpx;margin-top:%dpx"></span>'
                      % (r * 2, r * 2, -r) for r in (170, 290, 420, 560, 720, 900))
    generado = datetime.fromisoformat(datos["generado"])
    n_mie, n_cen = hoy["n_miembros"], hoy["n_centros"]

    lect = rl.lectura(hoy, t0, principal["tolvanera"])
    pico = principal["hora_pico"]
    frase_hora = (" La hora de mayor probabilidad es alrededor de las %s."
                  % pico["hora"]) if pico else ""

    desc = ("Clima en Torreón, Gómez Palacio y Lerdo: %d%% de probabilidad de "
            "lluvia mayor a 1 mm hoy y máxima de %s °C. Calculado contando %d "
            "escenarios de %d centros meteorológicos, con el desacuerdo entre "
            "ellos a la vista." % (p, num(t0["tmax"]), n_mie, n_cen))

    faqs = [
        ("¿Cómo se calcula esta probabilidad?",
         "Los centros meteorológicos no corren su modelo una sola vez: lo corren "
         "decenas de veces, cambiando apenas las condiciones iniciales, para ver de "
         "cuántas maneras distintas puede terminar el día. Aquí se juntan esas "
         "corridas de cuatro centros —GFS (NOAA, Estados Unidos), ICON (DWD, "
         "Alemania), IFS (ECMWF, Europa) y GEM (ECCC, Canadá)— y se cuentan una por "
         "una: hoy son %d escenarios. La probabilidad es simplemente la fracción de "
         "esos escenarios en los que llueve más que el umbral. No hay pesos, ni "
         "fórmulas propias, ni correcciones a mano." % n_mie),
        ("¿Por qué el pronóstico de lluvia es igual para las tres ciudades?",
         "Porque a la resolución de los modelos globales, Torreón, Gómez Palacio y "
         "Lerdo caen prácticamente en la misma celda de la rejilla. Publicar tres "
         "cifras distintas de lluvia daría una falsa sensación de detalle. La "
         "temperatura y el viento sí se calculan ciudad por ciudad."),
        ("¿Qué tan bien le atinan?",
         "Cada pronóstico queda guardado con su fecha y se compara después contra lo "
         "que registró el observatorio del aeropuerto de Torreón. El marcador está "
         "publicado en esta misma página. Si le erramos, ahí se ve."),
    ]
    faq_html = "".join("<details%s><summary>%s</summary><p>%s</p></details>"
                       % (" open" if i == 0 else "", esc(q), esc(r))
                       for i, (q, r) in enumerate(faqs))

    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "@id": SITIO + "/#org", "name": "Radar Lagunero",
         "url": SITIO, "logo": SITIO + "/tarjeta.png",
         "areaServed": {"@type": "Place",
                        "name": "Comarca Lagunera, Coahuila y Durango, México"},
         "description": "Pronóstico del tiempo para la Comarca Lagunera calculado "
                        "con un ensemble multi-modelo de cuatro centros, con la "
                        "incertidumbre publicada y verificación contra observaciones."},
        {"@type": "WebSite", "@id": SITIO + "/#web", "url": SITIO,
         "name": "Radar Lagunero", "inLanguage": "es-MX",
         "publisher": {"@id": SITIO + "/#org"}},
        {"@type": "WebPage", "@id": SITIO + "/#pagina", "url": SITIO + "/",
         "name": "Clima en Torreón hoy — Radar Lagunero",
         "isPartOf": {"@id": SITIO + "/#web"},
         "datePublished": datos["generado"], "dateModified": datos["generado"]},
        {"@type": "FAQPage", "@id": SITIO + "/#faq",
         "isPartOf": {"@id": SITIO + "/#pagina"},
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": r}}
                        for q, r in faqs]},
    ]}

    return """<!DOCTYPE html>
<html lang="es-MX">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clima en Torreón hoy | %(titulo)s — Radar Lagunero</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(sitio)s/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="theme-color" content="#091829">
<link rel="icon" href="%(favicon)s">
<link rel="apple-touch-icon" href="%(favicon)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Radar Lagunero">
<meta property="og:locale" content="es_MX">
<meta property="og:title" content="Clima en Torreón hoy: %(titulo)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(sitio)s/">
<meta property="og:image" content="%(sitio)s/tarjeta.png">
<meta property="og:image:width" content="1080">
<meta property="og:image:height" content="1350">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" media="print" onload="this.media='all'"
 href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap">
<noscript><link rel="stylesheet"
 href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap"></noscript>
<style>%(css)s</style>
<script type="application/ld+json">%(ld)s</script>
</head>
<body>
<div class="radar" aria-hidden="true">%(anillos)s</div>

<header class="top">
  <div class="env">
    <div class="marca"><b>RADAR</b><span>LAGUNERO</span></div>
    <p class="sello">Actualizado %(sello)s<br>Torreón · Gómez Palacio · Lerdo</p>
  </div>
  <div class="env">
    <nav aria-label="Secciones">
      <a href="#hoy">Hoy</a><a href="#horas">Por horas</a>
      <a href="#centros">Los cuatro centros</a><a href="#dias">7 días</a>
      <a href="#polvo">Tolvaneras</a><a href="#aciertos">Aciertos</a>
      <a href="#preguntas">Preguntas</a>
    </nav>
  </div>
</header>

<main>
  <div class="env">

    <section class="hero" id="hoy">
      <p class="fecha">%(fecha)s</p>
      <h1 class="%(clase)s">%(titulo)s</h1>
      <p class="sub">en la Comarca Lagunera</p>
      <div class="cifra">
        <p class="n">%(pct)d%%</p>
        <p class="q">de que caiga más de 1 mm de lluvia</p>
      </div>
      <div class="rango">
        <div class="rb"><i style="left:%(lo)d%%;width:%(ancho)d%%"></i>
          <u style="left:calc(%(pct)d%% - 1px)"></u></div>
        <div class="rt"><span>Centro más seco: %(lo)d%%</span>
          <span>Más lluvioso: %(hi)d%%</span></div>
      </div>
      <p style="margin-top:16px"><span class="eti e-%(conf_l)s">Confianza %(conf)s</span></p>
      <p class="lectura">%(lectura)s%(frase_hora)s</p>
    </section>

    <section id="horas">
      <h2>Hora por hora</h2>
      <p class="intro">Cuándo es más probable que caiga, en Torreón. La barra es la
      probabilidad de esa hora; el número de abajo, los grados. Sirve para ubicar el
      momento del día: esta franja viene del modelo de referencia hora por hora, no
      del ensemble, así que su nivel puede no coincidir con el porcentaje de arriba.</p>
      %(franja)s
    </section>

    <section id="centros">
      <h2>Los cuatro centros, sin maquillar</h2>
      <p class="intro">Cada institución corre su propio ensemble con su propio
      modelo. Esto es lo que dice cada una sobre la probabilidad de pasar de 1 mm
      hoy. Cuando se separan mucho, el pronóstico es frágil, y aquí se ve antes que
      en ningún otro lado.</p>
      <div class="caja">
        %(centros)s
        <div class="kv" style="margin-top:14px"><span>Diferencia entre el más seco y el más lluvioso</span><b>%(desac)s puntos</b></div>
        <div class="kv"><span>Escenarios contados</span><b>%(nmie)d de %(ncen)d centros</b></div>
      </div>
    </section>

    <section id="cuanta">
      <h2>Cuánta agua, no sólo si llueve</h2>
      <p class="intro">Una probabilidad alta de llovizna no es lo mismo que un
      aguacero. Estos son los cuatro umbrales con la fracción de escenarios que
      llega a cada uno.</p>
      <div class="caja">
        %(escalera)s
        <div class="kv" style="margin-top:14px"><span>Acumulado más probable (mediana)</span><b>%(p50)s mm</b></div>
        <div class="kv"><span>Escenario lluvioso (9 de cada 10 quedan por debajo)</span><b>%(p90)s mm</b></div>
        <div class="kv"><span>El escenario más extremo de los %(nmie)d</span><b>%(pmax)s mm</b></div>
      </div>
    </section>

    <section id="dias">
      <h2>Los próximos días</h2>
      <p class="intro">La confianza baja conforme se aleja el pronóstico, porque los
      centros se separan más. Lo decimos en vez de esconderlo.</p>
      <div class="caja">%(tabla)s</div>
    </section>

    <section id="temperatura">
      <h2>Temperatura hoy por ciudad</h2>
      <p class="intro">Esto sí cambia entre ciudades. Es la mediana de cinco modelos
      deterministas: GFS, ECMWF, ICON, GEM y ARPEGE.</p>
      %(temps)s
    </section>

    <section id="polvo">
      <h2>Polvo y tolvaneras</h2>
      <p class="intro">El fenómeno que define a La Laguna y que casi nadie
      pronostica. Combina el polvo en suspensión, las partículas PM10, la
      visibilidad y las rachas previstas para hoy en Torreón.</p>
      %(polvo)s
    </section>

    <section id="aciertos">
      <h2>Qué tanto le atinamos</h2>
      <p class="intro">Publicar un pronóstico es fácil. Publicar los errores es lo
      que hace que el siguiente pronóstico valga algo.</p>
      <div class="caja">%(aciertos)s</div>
    </section>

    <section class="faq" id="preguntas">
      <h2>Preguntas frecuentes</h2>
      %(faq)s
    </section>

    <section id="avisos">
      <p class="aviso"><b>Para fenómenos peligrosos, el aviso que cuenta no es
      este.</b> Ante tolvaneras, granizo, inundaciones o tormentas severas, la alerta
      formal la emiten el <a href="https://smn.conagua.gob.mx/" rel="noopener">Servicio
      Meteorológico Nacional / CONAGUA</a> y Protección Civil de Coahuila y Durango.
      Radar Lagunero interpreta y traduce modelos numéricos; no sustituye a la
      autoridad ni debe usarse para decisiones de emergencia.</p>
    </section>

  </div>
</main>

<footer>
  <div class="env">
    <div class="fcols">
      <div>
        <h3>Qué es esto</h3>
        <p>Pronóstico del tiempo para la Comarca Lagunera calculado con un ensemble
        multi-modelo de cuatro centros meteorológicos, con la incertidumbre publicada
        y los aciertos a la vista.</p>
      </div>
      <div>
        <h3>Cómo se calcula</h3>
        <p>Se cuentan las corridas de los ensembles de cuatro centros
        meteorológicos —NOAA, DWD, ECMWF y ECCC— y la probabilidad es la fracción
        de esas corridas que supera el umbral. La temperatura es la mediana de
        cinco modelos deterministas, ciudad por ciudad.</p>
      </div>
      <div>
        <h3>Verificación</h3>
        <p>Cada pronóstico se guarda con fecha y hora y se compara después contra
        el observatorio del aeropuerto de Torreón (MMTC). El marcador está
        publicado en esta misma página.<br>
        Avisos oficiales: <a href="https://smn.conagua.gob.mx/" rel="noopener">SMN / CONAGUA</a>.</p>
      </div>
    </div>
    <p>Radar Lagunero · Torreón, Coahuila · %(anio)d</p>
  </div>
</footer>
</body>
</html>
""" % {
        "titulo": esc(titulo), "clase": clase,
        "desc": html.escape(desc, quote=True),
        "sitio": SITIO, "css": CSS, "favicon": FAVICON,
        "ld": json.dumps(ld, ensure_ascii=False),
        "anillos": anillos,
        "sello": generado.strftime("%d/%m/%Y a las %H:%M h"),
        "fecha": esc(fecha_larga(hoy_iso)),
        "pct": p, "lo": lo, "hi": hi, "ancho": max(hi - lo, 2),
        "conf": hoy["confianza_lluvia"].capitalize(),
        "conf_l": hoy["confianza_lluvia"].lower(),
        "lectura": esc(lect), "frase_hora": esc(frase_hora),
        "franja": franja_horaria(principal["horario"]),
        "centros": bloque_centros(hoy),
        "desac": num(hoy["desacuerdo"], "%.0f"),
        "nmie": n_mie, "ncen": n_cen,
        "escalera": escalera(hoy),
        "p50": num(hoy["acumulado"]["p50"], "%.1f"),
        "p90": num(hoy["acumulado"]["p90"], "%.1f"),
        "pmax": num(hoy["acumulado"]["max"], "%.1f"),
        "tabla": tabla_dias(fechas, lluvias, principal["temps"]),
        "temps": tarjetas_temp(datos),
        "polvo": bloque_polvo(principal["tolvanera"]),
        "aciertos": bloque_aciertos(aciertos),
        "faq": faq_html,
        "anio": generado.year,
    }


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Genera el sitio de Radar Lagunero")
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--salida", default=SALIDA)
    args = ap.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    destino = os.path.join(args.salida, "index.html")

    try:
        datos = rl.recolectar(max(1, min(args.dias, 14)))
    except Exception as e:                                # noqa: BLE001
        # Mejor dejar en línea el último pronóstico bueno que tumbar el sitio.
        # El sello de "Actualizado" delata la edad.
        if os.path.exists(destino):
            print("[!] Falló la consulta (%s). Se conserva el sitio anterior." % e,
                  file=sys.stderr)
            return 0
        print("[!] Falló la consulta y no hay sitio previo: %s" % e, file=sys.stderr)
        return 1

    aciertos = None
    ruta_ac = os.path.join(args.salida, "aciertos.json")
    if os.path.exists(ruta_ac):
        try:
            with open(ruta_ac, encoding="utf-8") as fh:
                aciertos = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass

    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(pagina(datos, aciertos))

    with open(os.path.join(args.salida, "datos.json"), "w", encoding="utf-8") as fh:
        json.dump(rl.a_json_publico(datos), fh, ensure_ascii=False, indent=2)

    with open(os.path.join(args.salida, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITIO)

    hoy = datetime.now(rl.ZONA_LOCAL).strftime("%Y-%m-%d")
    with open(os.path.join(args.salida, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 '  <url><loc>%s/</loc><lastmod>%s</lastmod>'
                 '<changefreq>hourly</changefreq><priority>1.0</priority></url>\n'
                 '</urlset>\n' % (SITIO, hoy))

    with open(os.path.join(args.salida, "CNAME"), "w", encoding="utf-8") as fh:
        fh.write("radarlagunero.com\n")

    print("Sitio generado (%d escenarios, %d centros)"
          % (datos["lluvia"][0]["n_miembros"], datos["lluvia"][0]["n_centros"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
