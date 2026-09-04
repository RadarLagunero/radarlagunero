# Radar Lagunero

Pronóstico del tiempo para la Comarca Lagunera —Torreón, Gómez Palacio y
Lerdo— construido sobre el consenso de **cinco modelos numéricos
independientes** más el **ensemble del GFS de 31 miembros**.

La diferencia con cualquier app de clima: aquí se publica el nivel de acuerdo
entre modelos y la confianza del pronóstico. Cuando no se sabe, se dice.

## Piezas

| Archivo | Qué hace |
|---|---|
| `radar_lagunero.py` | Consulta GFS, ECMWF, ICON, GEM y ARPEGE vía Open-Meteo, más el ensemble. Calcula la probabilidad ajustada y la confianza. `--dias`, `--ciudad`, `--log`, `--json` |
| `build_sitio.py` | Genera `public/index.html` con el pronóstico **ya renderizado en el HTML**, más `datos.json`, `robots.txt` y `sitemap.xml` |
| `tarjeta_radar.py` | Toma el JSON y genera el PNG 1080x1350 para Facebook e Instagram (requiere Pillow) |
| `.github/workflows/actualizar.yml` | Cada hora regenera el sitio y hace commit. El push dispara el deploy en Netlify |
| `netlify.toml` | Publica `public/`. Netlify también regenera al desplegar |

## Correr en local

```bash
python3 build_sitio.py --dias 7      # escribe public/
open public/index.html
```

Para la tarjeta de redes:

```bash
python3 radar_lagunero.py --json | python3 tarjeta_radar.py
```

## Por qué el HTML se genera y no se pinta con JavaScript

"Clima Torreón" tiene volumen de búsqueda todo el año. Google indexa lo que
viene en el HTML; un panel que se llena en el navegador se indexa vacío. Por
eso el pronóstico se escribe en el archivo y se vuelve a escribir cada hora.

## Calibración local

`radar_lagunero.py --log` guarda cada pronóstico en `pronosticos_log.csv` con
las columnas de lo observado vacías. Llenándolas con el METAR de MMTC
(aeropuerto de Torreón, público) se puede calcular en dos o tres meses un
factor de corrección propio para la cuenca desértica, la isla de calor urbana
y el efecto de la sierra. Ese archivo es el activo real del proyecto.

## Criterios editoriales

- Solo fuentes primarias. Nunca se reproducen notas de otros medios.
- Para fenómenos peligrosos se cita siempre el aviso oficial del SMN/CONAGUA o
  de Protección Civil. El portal interpreta; la alerta formal la emite la
  autoridad.
- Datos de [Open-Meteo](https://open-meteo.com/), CC BY 4.0.
