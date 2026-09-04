# Radar Lagunero

Pronóstico del tiempo para la Comarca Lagunera —Torreón, Gómez Palacio y
Lerdo— calculado contando, uno por uno, los **139 escenarios** que producen
los ensembles de cuatro centros meteorológicos independientes.

La diferencia con cualquier app de clima: aquí se publica **cuánto difieren
entre sí los centros**, y **qué tanto le atinamos** los días pasados. Cuando
no se sabe, se dice.

**radarlagunero.com**

## El método, en tres líneas

```
P(lluvia > umbral) = escenarios que superan el umbral / escenarios totales
```

Sin pesos, sin factores de corrección, sin ajustes a mano. Cualquiera con
acceso a la misma API pública puede repetir la cuenta y obtener el mismo
número. Esa es la única razón por la que una cifra así merece confianza.

| Centro | Institución | Miembros |
|---|---|---|
| GFS  | NOAA · Estados Unidos | 30 |
| ICON | DWD · Alemania | 39 |
| IFS  | ECMWF · Europa | 50 |
| GEM  | ECCC · Canadá | 20 |

El titular usa el umbral de **1 mm en 24 h** —la lluvia que se nota en la
calle— y se publican también 0.2, 5 y 20 mm. Las cifras se redondean al 5 %
más cercano: decir "57 %" fingiría una precisión que el método no tiene.

La **confianza** no es una opinión: es la distancia entre el centro más seco
y el más lluvioso.

## Piezas

| Archivo | Qué hace |
|---|---|
| `radar_lagunero.py` | Motor. Consulta los cuatro ensembles y los cinco modelos deterministas, calcula probabilidades por umbral, acumulados p50/p90, desacuerdo entre centros, riesgo de tolvanera y el pronóstico horario. `--dias`, `--ciudad`, `--json`, `--log` |
| `build_sitio.py` | Genera `public/index.html` con todo **ya renderizado en el HTML**, más `datos.json`, `robots.txt`, `sitemap.xml` y `CNAME` |
| `verificar.py` | Baja el METAR del aeropuerto de Torreón (MMTC), completa lo observado en la bitácora y calcula el marcador de aciertos |
| `tarjeta_radar.py` | Tarjeta 1080x1350 para Facebook e Instagram, que además es el `og:image` del sitio |
| `.github/workflows/publicar.yml` | Cada hora: reconstruye, verifica y despliega en GitHub Pages |
| `.github/workflows/bitacora.yml` | Cada día a las 06:00 de Torreón: guarda el pronóstico y completa lo observado |

## Correr en local

```bash
python3 radar_lagunero.py --dias 7      # en la terminal
python3 build_sitio.py                  # escribe public/
python3 verificar.py                    # observaciones y marcador
python3 tarjeta_radar.py                # public/tarjeta.png  (requiere Pillow)
```

Todo funciona con la biblioteca estándar salvo la tarjeta, que necesita
Pillow. Para que la tarjeta salga con la tipografía de la marca, deja los
`.ttf` de Poppins en `fonts/`; si no están, cae a otra fuente sin romperse.

## Por qué el HTML se genera y no se pinta con JavaScript

"Clima Torreón" tiene volumen de búsqueda todo el año. Google indexa lo que
viene en el HTML; un panel que se llena en el navegador se indexa vacío. Por
eso el pronóstico se escribe en el archivo y se vuelve a escribir cada hora.

## Verificación

`pronosticos_log.csv` guarda cada pronóstico emitido con su fecha y horizonte.
`observaciones_mmtc.csv` guarda el METAR del aeropuerto tal como llegó. Cuando
un día cierra, `verificar.py` los cruza y calcula:

- **Error medio en la temperatura máxima**, por anticipación.
- **Acierto en lluvia** y **puntaje de Brier**, contra el tiempo presente
  reportado en el METAR.
- **Fiabilidad**: de las veces que dijimos "60 %", ¿llovió el 60 % de las veces?

MMTC no reporta milímetros acumulados y no emite las 24 horas, así que se
verifica si llovió o no —nunca cuánto— y una lluvia de madrugada puede no
quedar registrada. El sitio lo dice.

## Fuentes y licencia

- Modelos numéricos vía [Open-Meteo](https://open-meteo.com/), CC BY 4.0.
  El plan gratuito es **de uso no comercial**: si el sitio llegara a mostrar
  publicidad o suscripciones, hace falta el plan de pago.
- Observaciones: METAR de MMTC, [NOAA Aviation Weather Center](https://aviationweather.gov/).
- Para fenómenos peligrosos, el aviso que cuenta es el del
  [SMN / CONAGUA](https://smn.conagua.gob.mx/) y Protección Civil.

## Criterios editoriales

- Solo fuentes primarias. Nunca se reproducen notas de otros medios.
- El portal interpreta y traduce modelos; la alerta formal la emite la autoridad.
- Si le erramos, se publica.
