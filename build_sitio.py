#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Lagunero — Generador del sitio estatico
==============================================
Consulta los 5 modelos + el ensemble via radar_lagunero.py y escribe
public/index.html con el pronostico ya renderizado en el HTML.

Que el contenido este en el HTML (y no lo pinte JavaScript en el navegador)
es lo que permite competir por "clima Torreon" y aparecer en Google Discover.

USO:
    python3 build_sitio.py            # 7 dias, escribe en public/
    python3 build_sitio.py --dias 5

Solo biblioteca estandar.
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import radar_lagunero as rl

SITIO = "https://radarlagunero.com"
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

ORDEN = ["torreon", "gomez", "lerdo"]
BONITO = {"Torreon": "Torreón", "Gomez Palacio": "Gómez Palacio",
          "Lerdo": "Lerdo"}
SLUG = {"Torreon": "torreon", "Gomez Palacio": "gomez", "Lerdo": "lerdo"}

DIAS_LARGO = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes",
              "Sábado", "Domingo"]
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

ZONA_LOCAL = timezone(timedelta(hours=-6))   # America/Monterrey, CST


# --------------------------------------------------------------------------
# TEXTO
# --------------------------------------------------------------------------

def titular(a):
    """Titular corto. Mismo criterio que la tarjeta de redes."""
    p = a["ajustada"] or 0
    if p >= 70:
        return "Lluvia muy probable", "lluvia"
    if p >= 45:
        return "Puede llover hoy", "lluvia"
    if p >= 20:
        return "Lluvia aislada", "lluvia"
    if a["tmax"] and a["tmax"] >= 38:
        return "Calor extremo", "calor"
    return "Día seco", "calor"


def respuesta_faq(nombre, a):
    """Respuesta directa a la pregunta que la gente teclea en Google."""
    p = a["ajustada"] or 0
    mojados, total = a["det"]
    ens_m, ens_t = a["ens"]
    if p >= 70:
        base = "Sí, es muy probable que llueva"
    elif p >= 45:
        base = "Hay buenas posibilidades de que llueva"
    elif p >= 20:
        base = "Puede caer lluvia aislada"
    else:
        base = "No, lo más probable es que no llueva"
    return ("%s en %s. La probabilidad ajustada es de %.0f%%: %d de %d modelos "
            "numéricos dan lluvia y %d de %d miembros del ensemble del GFS "
            "también. La confianza del pronóstico es %s."
            % (base, nombre, p, mojados, total, ens_m, ens_t,
               a["confianza"].lower()))


def fecha_larga(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %d de %s de %d" % (DIAS_LARGO[d.weekday()], d.day,
                                  MESES[d.month - 1], d.year)


def fecha_corta(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return "%s %d" % (DIAS_CORTO[d.weekday()], d.day)


def num(v, fmt="%.0f", vacio="—"):
    return fmt % v if v is not None else vacio


# --------------------------------------------------------------------------
# PIEZAS HTML
# --------------------------------------------------------------------------

def barra(pct):
    ancho = min(max(pct or 0, 0), 100)
    return ('<div class="barra"><span style="width:%.0f%%"></span></div>'
            % ancho)


def puntos(mojados, total):
    p = "".join('<i class="%s"></i>' % ("on" if i < mojados else "off")
                for i in range(total))
    return '<span class="puntos">%s</span>' % p


def tarjeta_ciudad(nombre, a, iso, principal=False):
    txt, clase = titular(a)
    p = a["ajustada"] or 0
    detalle = []
    if a["lluvia"] is not None:
        detalle.append("lluvia estimada %.1f mm" % a["lluvia"])
    if a["rafaga"] is not None and a["rafaga"] >= 35:
        detalle.append("rachas %.0f km/h" % a["rafaga"])
    return """
      <article class="ciudad%s">
        <header>
          <h3>%s</h3>
          <p class="temps"><b>%s°</b> <span>/ %s°</span></p>
        </header>
        <p class="titularin %s">%s</p>
        <div class="fila-barra">%s<b class="pct">%.0f%%</b></div>
        <p class="detalle">%s</p>
        <p class="confianza c-%s">Confianza %s · acuerdo %d/%d modelos</p>
      </article>""" % (
        " destacada" if principal else "",
        html.escape(nombre),
        num(a["tmax"]), num(a["tmin"]),
        clase, html.escape(txt),
        barra(p), p,
        html.escape(" · ".join(detalle) or "sin lluvia estimada"),
        a["confianza"].lower(), a["confianza"].lower(),
        a["det"][0], a["det"][1])


def tabla_modelos(a, nombre):
    filas = []
    for f in a["filas"]:
        filas.append(
            "<tr><td>%s</td><td>%s°</td><td>%s°</td><td>%s mm</td>"
            "<td>%s</td><td>%s</td></tr>" % (
                html.escape(f["modelo"]),
                num(f["tmax"], "%.1f"), num(f["tmin"], "%.1f"),
                num(f["lluvia"], "%.1f"),
                num(f["prob"], "%.0f%%"), num(f["rafaga"], "%.0f km/h")))
    return """
        <h3 class="subt">Los cinco modelos para hoy en %s</h3>
        <table class="modelos">
          <thead><tr><th>Modelo</th><th>Máx</th><th>Mín</th><th>Lluvia</th>
          <th>Prob.</th><th>Rachas</th></tr></thead>
          <tbody>%s</tbody>
          <tfoot><tr><th>Consenso (mediana)</th><th>%s°</th><th>%s°</th>
          <th>%s mm</th><th>%.0f%%</th><th>%s</th></tr></tfoot>
        </table>""" % (
        html.escape(nombre), "".join(filas),
        num(a["tmax"], "%.1f"), num(a["tmin"], "%.1f"),
        num(a["lluvia"], "%.1f"), a["ajustada"] or 0,
        num(a["rafaga"], "%.0f km/h"))


def tira_dias(fechas, analisis):
    celdas = []
    for iso, a in zip(fechas, analisis):
        p = a["ajustada"] or 0
        celdas.append(
            '<li><span class="dia">%s</span>'
            '<span class="t">%s° <i>%s°</i></span>'
            '%s<span class="p">%.0f%%</span>'
            '<span class="cf c-%s">%s</span></li>' % (
                fecha_corta(iso), num(a["tmax"]), num(a["tmin"]),
                barra(p), p, a["confianza"].lower(),
                a["confianza"].capitalize()))
    return '<ul class="tira">%s</ul>' % "".join(celdas)


# --------------------------------------------------------------------------
# PAGINA
# --------------------------------------------------------------------------

CSS = """
:root{
  --fondo:#091829; --fondo2:#102E4A; --panel:#11283F; --linea:#1E5C82;
  --cian:#38BDF8; --ambar:#F59E0B; --hueso:#F8FAFC; --gris:#94A3B8;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Poppins',system-ui,-apple-system,'Segoe UI',sans-serif;
  background:var(--fondo);color:var(--hueso);line-height:1.55;
  background-image:linear-gradient(180deg,var(--fondo) 0%,var(--fondo2) 100%);
  background-attachment:fixed;
}
.env{max-width:1080px;margin:0 auto;padding:0 20px}
a{color:var(--cian)}

/* anillos de radar: la marca de agua de la marca */
.radar{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.radar span{
  position:absolute;left:50%;top:-120px;transform:translateX(-50%);
  border:1px solid rgba(56,189,248,.10);border-radius:50%;
}
main,header.top,footer{position:relative;z-index:1}

header.top{padding:26px 0 18px;border-bottom:1px solid var(--linea)}
.marca{display:flex;align-items:baseline;gap:9px;letter-spacing:.06em}
.marca b{font-weight:700;font-size:1.35rem}
.marca span{font-weight:300;font-size:1.35rem;color:var(--cian)}
.top .env{display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:10px}
.sello{font-size:.78rem;color:var(--gris);text-align:right}

.hero{padding:46px 0 8px;text-align:center}
.hero .fecha{color:var(--gris);text-transform:uppercase;letter-spacing:.14em;
  font-size:.8rem}
.hero h1{font-size:clamp(2rem,6vw,3.4rem);font-weight:700;line-height:1.1;
  margin:12px 0 6px;color:var(--cian)}
.hero h1.calor{color:var(--ambar)}
.hero .sub{color:var(--gris);font-weight:300;font-size:clamp(1rem,2.6vw,1.3rem)}
.hero .prob{font-size:clamp(3rem,12vw,5.5rem);font-weight:700;line-height:1;
  margin:18px 0 2px}
.hero .prob small{font-size:.9rem;font-weight:300;color:var(--gris);
  display:block;letter-spacing:.1em;text-transform:uppercase;margin-top:6px}
.lectura{max-width:640px;margin:22px auto 0;color:var(--hueso);
  font-weight:300;font-size:1.05rem}

.badge{display:inline-block;padding:4px 13px;border-radius:999px;
  font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;
  border:1px solid currentColor;margin-top:16px}
.c-alta{color:#4ADE80}.c-media{color:var(--ambar)}.c-baja{color:#FB7185}

section{padding:38px 0}
h2{font-size:1.05rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--cian);font-weight:600;margin-bottom:18px}
h2 small{display:block;text-transform:none;letter-spacing:0;color:var(--gris);
  font-weight:300;font-size:.9rem;margin-top:6px}

.ciudades{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.ciudad{background:var(--panel);border:1px solid var(--linea);border-radius:18px;
  padding:20px 22px}
.ciudad.destacada{border-color:var(--cian)}
.ciudad header{display:flex;justify-content:space-between;align-items:baseline;
  gap:10px}
.ciudad h3{font-size:1.15rem;font-weight:600}
.temps{color:var(--ambar);font-size:1.15rem;font-weight:500}
.temps span{color:var(--gris);font-weight:300}
.titularin{font-size:.9rem;color:var(--gris);margin-top:2px}
.fila-barra{display:flex;align-items:center;gap:12px;margin:14px 0 8px}
.pct{color:var(--cian);font-size:1.3rem;font-weight:700;min-width:62px;
  text-align:right}
.barra{flex:1;height:12px;border-radius:99px;background:rgba(255,255,255,.09);
  border:1px solid var(--linea);overflow:hidden}
.barra span{display:block;height:100%;background:var(--cian);border-radius:99px}
.detalle{font-size:.85rem;color:var(--gris);font-weight:300}
.confianza{font-size:.76rem;margin-top:10px;letter-spacing:.05em;
  text-transform:uppercase}

.pestanas{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.pestanas button{background:transparent;border:1px solid var(--linea);
  color:var(--gris);padding:7px 16px;border-radius:999px;cursor:pointer;
  font-family:inherit;font-size:.85rem}
.pestanas button[aria-selected="true"]{border-color:var(--cian);
  color:var(--cian);background:rgba(56,189,248,.08)}

.panel-ciudad[hidden]{display:none}
.tira{list-style:none;display:grid;gap:10px;
  grid-template-columns:repeat(auto-fit,minmax(112px,1fr))}
.tira li{background:var(--panel);border:1px solid var(--linea);border-radius:14px;
  padding:14px 12px;text-align:center}
.tira .dia{display:block;font-size:.78rem;color:var(--gris);
  text-transform:uppercase;letter-spacing:.08em}
.tira .t{display:block;margin:8px 0 10px;color:var(--ambar);font-weight:500}
.tira .t i{color:var(--gris);font-style:normal;font-weight:300}
.tira .p{display:block;margin-top:8px;color:var(--cian);font-weight:600}
.tira .cf{display:block;font-size:.7rem;margin-top:4px;letter-spacing:.06em;
  text-transform:uppercase}

.metodo{background:rgba(10,30,50,.75);border:1px solid var(--cian);
  border-radius:20px;padding:26px 24px}
.metodo .kv{display:flex;justify-content:space-between;align-items:center;
  gap:14px;padding:11px 0;border-bottom:1px solid rgba(30,92,130,.5);
  font-weight:300;color:var(--gris);flex-wrap:wrap}
.metodo .kv:last-of-type{border-bottom:0}
.metodo .kv b{color:var(--hueso);font-weight:500}
.puntos{display:inline-flex;gap:7px;margin-left:auto}
.puntos i{width:13px;height:13px;border-radius:50%;border:2px solid var(--cian);
  display:block}
.puntos i.on{background:var(--cian)}

.subt{margin:26px 0 0;font-size:.8rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--gris);font-weight:400}
.modelos{width:100%;border-collapse:collapse;margin-top:10px;font-size:.86rem;
  font-weight:300;display:block;overflow-x:auto;white-space:nowrap}
.modelos th,.modelos td{padding:9px 12px;text-align:right;
  border-bottom:1px solid rgba(30,92,130,.45)}
.modelos th:first-child,.modelos td:first-child{text-align:left}
.modelos thead th{color:var(--cian);font-weight:500;font-size:.74rem;
  letter-spacing:.08em;text-transform:uppercase}
.modelos tfoot th{color:var(--hueso);font-weight:600;border-bottom:0;
  border-top:1px solid var(--cian)}

.faq details{background:var(--panel);border:1px solid var(--linea);
  border-radius:14px;padding:16px 20px;margin-bottom:10px}
.faq summary{cursor:pointer;font-weight:500}
.faq p{color:var(--gris);font-weight:300;margin-top:10px}

.aviso{border-left:3px solid var(--ambar);padding:12px 18px;color:var(--gris);
  font-weight:300;font-size:.92rem;background:rgba(245,158,11,.06);
  border-radius:0 12px 12px 0}

footer{border-top:1px solid var(--linea);padding:30px 0 46px;margin-top:26px;
  color:var(--gris);font-weight:300;font-size:.85rem;text-align:center}
footer p{margin-bottom:8px}
"""

JS = """
document.querySelectorAll('[data-tabs]').forEach(function(g){
  var btns=g.querySelectorAll('button[data-ciudad]');
  btns.forEach(function(b){
    b.addEventListener('click',function(){
      var c=b.dataset.ciudad;
      btns.forEach(function(x){
        x.setAttribute('aria-selected', x===b ? 'true':'false');});
      document.querySelectorAll(g.dataset.tabs+' .panel-ciudad')
        .forEach(function(p){p.hidden = p.dataset.ciudad!==c;});
    });
  });
});
"""


def pagina(datos, generado):
    ciudades = [(rl.CIUDADES[k][0], datos[k]) for k in ORDEN if k in datos]
    nombre_p, d_p = ciudades[0]
    hoy_iso = d_p["fechas"][0]
    hoy = d_p["analisis"][0]
    txt, clase = titular(hoy)
    p_hoy = hoy["ajustada"] or 0

    # --- anillos de radar
    anillos = "".join(
        '<span style="width:%dpx;height:%dpx;margin-top:%dpx"></span>'
        % (r * 2, r * 2, -r) for r in (180, 300, 430, 570, 720, 900))

    # --- tarjetas de hoy
    tarjetas = "".join(
        tarjeta_ciudad(BONITO.get(n, n), d["analisis"][0], hoy_iso, i == 0)
        for i, (n, d) in enumerate(ciudades))

    # --- pestanas + 7 dias + tabla por ciudad
    pest = "".join(
        '<button role="tab" data-ciudad="%s" aria-selected="%s">%s</button>'
        % (SLUG[n], "true" if i == 0 else "false", BONITO.get(n, n))
        for i, (n, d) in enumerate(ciudades))
    paneles = "".join(
        '<div class="panel-ciudad" data-ciudad="%s"%s>%s%s</div>' % (
            SLUG[n], "" if i == 0 else " hidden",
            tira_dias(d["fechas"], d["analisis"]),
            tabla_modelos(d["analisis"][0], BONITO.get(n, n)))
        for i, (n, d) in enumerate(ciudades))

    # --- FAQ (y su schema)
    faqs = []
    for n, d in ciudades:
        a = d["analisis"][0]
        faqs.append(("¿Va a llover hoy en %s?" % BONITO.get(n, n),
                     respuesta_faq(BONITO.get(n, n), a)))
    faqs.append((
        "¿Cómo calcula Radar Lagunero la probabilidad de lluvia?",
        "Consultamos cinco modelos numéricos independientes —GFS (Estados "
        "Unidos), ECMWF (Europa), ICON (Alemania), GEM (Canadá) y ARPEGE "
        "(Francia)— más el ensemble del GFS de 31 miembros. La probabilidad "
        "ajustada pondera la fracción de miembros del ensemble con lluvia "
        "(50%), la probabilidad media que reportan los modelos (30%) y la "
        "fracción de modelos deterministas que dan lluvia (20%). Publicamos "
        "también el nivel de acuerdo entre modelos y la confianza del "
        "pronóstico, incluso cuando es baja."))
    faq_html = "".join(
        "<details%s><summary>%s</summary><p>%s</p></details>"
        % (" open" if i == 0 else "", html.escape(q), html.escape(r))
        for i, (q, r) in enumerate(faqs))

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": SITIO + "/#org",
             "name": "Radar Lagunero", "url": SITIO,
             "areaServed": "Comarca Lagunera, Coahuila y Durango, México",
             "description": "Pronóstico del tiempo para la Comarca Lagunera "
                            "basado en el consenso de cinco modelos numéricos "
                            "y el ensemble del GFS."},
            {"@type": "WebSite", "@id": SITIO + "/#web", "url": SITIO,
             "name": "Radar Lagunero", "inLanguage": "es-MX",
             "publisher": {"@id": SITIO + "/#org"}},
            {"@type": "WebPage", "@id": SITIO + "/#pagina", "url": SITIO + "/",
             "name": "Clima en Torreón hoy — Radar Lagunero",
             "isPartOf": {"@id": SITIO + "/#web"},
             "datePublished": generado.isoformat(),
             "dateModified": generado.isoformat()},
            {"@type": "FAQPage", "@id": SITIO + "/#faq",
             "isPartOf": {"@id": SITIO + "/#pagina"},
             "mainEntity": [
                 {"@type": "Question", "name": q,
                  "acceptedAnswer": {"@type": "Answer", "text": r}}
                 for q, r in faqs]},
        ],
    }

    desc = ("Clima en Torreón, Gómez Palacio y Lerdo: %.0f%% de probabilidad "
            "de lluvia hoy, máxima de %s°. Consenso de 5 modelos numéricos "
            "y ensemble del GFS, con la confianza del pronóstico a la vista."
            % (p_hoy, num(hoy["tmax"])))

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
<meta property="og:type" content="website">
<meta property="og:site_name" content="Radar Lagunero">
<meta property="og:locale" content="es_MX">
<meta property="og:title" content="Clima en Torreón hoy: %(titulo)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(sitio)s/">
<meta property="og:image" content="%(sitio)s/tarjeta.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap">
<style>%(css)s</style>
<script type="application/ld+json">%(ld)s</script>
</head>
<body>
<div class="radar" aria-hidden="true">%(anillos)s</div>

<header class="top">
  <div class="env">
    <div class="marca"><b>RADAR</b><span>LAGUNERO</span></div>
    <p class="sello">Actualizado %(sello)s<br>Comarca Lagunera · Coahuila y Durango</p>
  </div>
</header>

<main>
  <div class="env">

    <section class="hero">
      <p class="fecha">%(fecha)s</p>
      <h1 class="%(clase)s">%(titulo)s</h1>
      <p class="sub">en Torreón, Gómez Palacio y Lerdo</p>
      <p class="prob">%(pct).0f%%<small>Probabilidad ajustada</small></p>
      <p><span class="badge c-%(conf_l)s">Confianza %(conf)s</span></p>
      <p class="lectura">%(lectura)s</p>
    </section>

    <section id="ciudades">
      <h2>Hoy en la comarca<small>Mediana de los cinco modelos para cada ciudad.</small></h2>
      <div class="ciudades">%(tarjetas)s</div>
    </section>

    <section id="dias">
      <h2>Los próximos días<small>La confianza baja conforme se aleja el pronóstico. Lo decimos en vez de esconderlo.</small></h2>
      <div class="pestanas" role="tablist" data-tabs="#dias">%(pestanas)s</div>
      %(paneles)s
    </section>

    <section id="metodo">
      <h2>Cómo lo calculamos</h2>
      <div class="metodo">
        <div class="kv"><span>Modelos numéricos que coinciden en lluvia</span>%(puntos)s<b>%(det)s</b></div>
        <div class="kv"><span>Miembros del ensemble del GFS con lluvia</span><b>%(ens)s</b></div>
        <div class="kv"><span>Dispersión entre modelos en la máxima</span><b>%(disp)s</b></div>
        <div class="kv"><span>Confianza del pronóstico</span><b class="c-%(conf_l)s">%(conf)s</b></div>
        <p class="detalle" style="margin-top:16px">La probabilidad ajustada pondera el ensemble al 50%%, la probabilidad media de los modelos al 30%% y el acuerdo entre modelos deterministas al 20%%. El ensemble pesa más porque es la única fuente que mide la incertidumbre de verdad.</p>
      </div>
    </section>

    <section class="faq" id="preguntas">
      <h2>Preguntas frecuentes</h2>
      %(faq)s
    </section>

    <section id="avisos">
      <p class="aviso"><b>Fenómenos peligrosos.</b> Para tolvaneras, granizo o inundaciones, la alerta formal la emiten el <a href="https://smn.conagua.gob.mx/" rel="noopener">SMN / CONAGUA</a> y Protección Civil. Radar Lagunero interpreta y traduce los modelos; no sustituye el aviso oficial.</p>
    </section>

  </div>
</main>

<footer>
  <div class="env">
    <p><b>Radar Lagunero</b> · Torreón, Gómez Palacio y Lerdo</p>
    <p>Consenso de 5 modelos numéricos independientes + ensemble del GFS de 31 miembros.</p>
    <p>Datos de <a href="https://open-meteo.com/" rel="noopener">Open-Meteo</a> (CC BY 4.0). Avisos oficiales: SMN / CONAGUA.</p>
    <p>Datos abiertos de este pronóstico: <a href="/datos.json">datos.json</a></p>
  </div>
</footer>
<script>%(js)s</script>
</body>
</html>
""" % {
        "titulo": html.escape(txt),
        "clase": clase,
        "desc": html.escape(desc, quote=True),
        "sitio": SITIO,
        "css": CSS,
        "js": JS,
        "ld": json.dumps(ld, ensure_ascii=False),
        "anillos": anillos,
        "sello": generado.strftime("%d/%m/%Y a las %H:%M h"),
        "fecha": html.escape(fecha_larga(hoy_iso)),
        "pct": p_hoy,
        "conf": hoy["confianza"].capitalize(),
        "conf_l": hoy["confianza"].lower(),
        "lectura": html.escape(rl.lectura(hoy)),
        "tarjetas": tarjetas,
        "pestanas": pest,
        "paneles": paneles,
        "puntos": puntos(hoy["det"][0], hoy["det"][1]),
        "det": "%d de %d" % hoy["det"],
        "ens": "%d de %d" % hoy["ens"],
        "disp": (("%.1f °C" % hoy["dispersion_t"])
                 if hoy["dispersion_t"] is not None else "—"),
        "faq": faq_html,
    }


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def recolectar(dias):
    datos = {}
    for clave in ORDEN:
        nombre, lat, lon = rl.CIUDADES[clave]
        diario = rl.traer_modelos(lat, lon, dias)
        ens = rl.traer_ensemble(lat, lon, dias)
        fechas = diario["time"]
        analisis = [rl.analizar_dia(diario, i, ens[i])
                    for i in range(len(fechas))]
        datos[clave] = {"nombre": nombre, "fechas": fechas,
                        "analisis": analisis}
    return datos


def json_publico(datos, generado):
    out = {"generado": generado.isoformat(),
           "fuente": "Open-Meteo — 5 modelos + ensemble GFS (31 miembros)",
           "licencia": "CC BY 4.0",
           "ciudades": {}}
    for clave, d in datos.items():
        out["ciudades"][clave] = {
            "nombre": BONITO.get(d["nombre"], d["nombre"]),
            "dias": [{
                "fecha": f,
                "tmax": a["tmax"], "tmin": a["tmin"],
                "lluvia_mm": a["lluvia"], "rafaga_kmh": a["rafaga"],
                "prob_ajustada": a["ajustada"],
                "confianza": a["confianza"],
                "acuerdo_modelos": "%d/%d" % a["det"],
                "ensemble": "%d/%d" % a["ens"],
                "lectura": rl.lectura(a),
            } for f, a in zip(d["fechas"], d["analisis"])]}
    return out


def main():
    ap = argparse.ArgumentParser(description="Genera el sitio de Radar Lagunero")
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--salida", default=SALIDA)
    args = ap.parse_args()

    generado = datetime.now(ZONA_LOCAL)
    try:
        datos = recolectar(max(1, min(args.dias, 14)))
    except Exception as e:                       # noqa: BLE001
        # Si la API falla, es preferible dejar en linea el ultimo pronostico
        # bueno que tumbar el sitio. El sello de "Actualizado" delata la edad.
        anterior = os.path.join(args.salida, "index.html")
        if os.path.exists(anterior):
            print("[!] Falló la consulta (%s). Se conserva el sitio anterior."
                  % e, file=sys.stderr)
            return 0
        print("[!] Falló la consulta y no hay sitio previo: %s" % e,
              file=sys.stderr)
        return 1

    os.makedirs(args.salida, exist_ok=True)

    with open(os.path.join(args.salida, "index.html"), "w",
              encoding="utf-8") as fh:
        fh.write(pagina(datos, generado))

    with open(os.path.join(args.salida, "datos.json"), "w",
              encoding="utf-8") as fh:
        json.dump(json_publico(datos, generado), fh,
                  ensure_ascii=False, indent=2)

    with open(os.path.join(args.salida, "robots.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITIO)

    with open(os.path.join(args.salida, "sitemap.xml"), "w",
              encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 '  <url><loc>%s/</loc><lastmod>%s</lastmod>'
                 '<changefreq>hourly</changefreq><priority>1.0</priority></url>\n'
                 '</urlset>\n' % (SITIO, generado.strftime("%Y-%m-%d")))

    print("Sitio generado en %s (%s)"
          % (args.salida, generado.strftime("%Y-%m-%d %H:%M")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
