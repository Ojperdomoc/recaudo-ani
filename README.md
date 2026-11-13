# Aplicación interactiva de estimación de recaudo de peajes (ANI)

Aplicación web HTML autocontenida que estima el recaudo mensual de cada uno de los
**162 peajes** de la red vial colombiana y el **total nacional**, a partir de los datos
abiertos de la Agencia Nacional de Infrastructure (ANI).

## Cómo ejecutarla

### En línea (GitHub Pages)

La aplicación está publicada en GitHub Pages mediante el workflow
`.github/workflows/pages.yml`. Cada `push` a `main` redespliega el sitio:

👉 **https://ojperdomoc.github.io/recaudo-ani/**

> Nota: el workflow vive en `main` porque GitHub Pages despliega desde la rama por
> defecto del repositorio. El PR de esta rama incluye el workflow para que, al
> fusionarla, quede activo el despliegue automático.

### En local

```bash
python3 -m http.server 8000
# abrir http://localhost:8000/index.html
```

No requiere build, ni dependencias, ni conexión a internet: los datos están embebidos
en `datos.js` y los gráficos se dibujan con SVG nativo.

## Fuente de datos

`datos/Recaudo_Vehicular_ANI_20261113.csv` (ANI — datos abiertos), 17 134 registros originales con cobertura 2014-01 a 2026-05.

El script `preparar_datos.py` limpia el CSV y regenera `datos.js`:

```bash
python3 preparar_datos.py
```

### Limpieza aplicada

| Paso | Detalle |
|---|---|
| Duplicados | 164 duplicados exactos eliminados (p. ej. TURBACO 2022) |
| Meses divididos | Registros del mismo peaje y mes se suman (p. ej. CHICORAL mar-2022) |
| Meses parciales | 90 meses con < 28 días se normalizan a 30.44 días (`recaudo_norm`) |
| Cero ≠ faltante | Un mes con registro en 0 es distinto de un mes sin registro |
| Clasificación | `activo` (116), `cerrado` (38, sin recaudo desde antes de 2025-11), `sin_recaudo` (8) |

## División entrenamiento / prueba

Fija y sin solapamiento, tal como se solicitó:

- **Entrenamiento (primeros 10 años):** 2014-01 a 2023-12
- **Prueba (últimos años):** 2024-01 a 2026-05
- **Pronóstico futuro:** desde 2026-06 (horizonte configurable 1–24 meses)

## Modelos

Cuatro modelos base más un ensemble ponderado:

1. **OLS tendencia + estacionalidad** — `log(recaudo) ~ tiempo + dummies de mes`
2. **Holt-Winters amortiguado** — nivel + tendencia amortiguada (φ) + estacionalidad en log;
   con tope de 2.5× la mediana histórica para evitar proyecciones explosivas
3. **Descomposición clásica** — media móvil de 12 meses + índices estacionales
4. **Naive estacional** — promedio histórico del mismo mes (línea base)
5. **Ensemble ponderado** — los pesos se determinan por **validación rolling-origin**
   sobre los últimos 24 meses del entrenamiento (se reentrena en cada corte y se evalúa
   en el mes siguiente). **No usa información del periodo de prueba.**
   Mezcla 90/10 con el equiponderado para robustez ante ruido en la validación.

### Detección de cambios estructurales

Antes de pronosticar se compara el promedio de los últimos 12 meses con el de los 12
anteriores. Si el nivel cambia fuera de `[0.55, 1.8]` y el nuevo nivel se mantiene
estable, se considera una **ruptura estructural** (nueva concesión, tarifario,
reubicación) y el modelo se ajusta solo con el régimen reciente. La interfaz muestra una
alerta explicativa. Ejemplos detectados: TURBACO (caída del 88% en 2023), PAPIROS,
COROZAL, ARMERO.

## Métricas

| Métrica | Uso |
|---|---|
| **WAPE** | Métrica de referencia: error absoluto ponderado por magnitud, robusta ante meses de cierre con recaudo ≈ 0 |
| **MAPE** | Calculado solo sobre meses con recaudo representativo (≥ 5% del promedio) |
| **sMAPE** | Versión simétrica, incluye todos los meses |
| **MASE** | Error escalado por el benchmark naive estacional; < 1 indica mejora sobre naive |
| MAE, RMSE, sesgo, R² | Diagnóstico complementario |

El **IC 95%** es proporcional al nivel pronosticado:
`pronóstico ± 1.96 · WAPE · (0.75 + 0.25·√h)`.

## Resultados de la evaluación (2024–2026, entrenado solo con 2014–2023)

| Métrica | Total nacional | Mediana de los 112 peajes activos evaluables |
|---|---|---|
| WAPE (ensemble) | 24.6 % | **18.0 %** |
| Peajes con WAPE < 25 % | — | 78 de 112 |
| OLS (mejor modelo individual para el total) | 17.9 % | — |

## Pestañas de la aplicación

1. **Estimación** — selector de peaje con búsqueda, botón *Ver total nacional*,
   selector de modelo, horizonte (1–24 meses), casillas de IC 95 %, exclusión de
   COVID-19, reentrenamiento con todo el historial y predicción en el periodo de prueba.
   KPIs, gráfico SVG con tooltip, tabla de pronóstico con IC y tabla comparativa de modelos.
2. **Resumen estadístico** — total por año, estacionalidad, top-15 peajes, calidad de datos,
   y tabla por peaje (total, promedio, mediana, desviación, CV, CAGR, mes pico/valle,
   % ceros, WAPE en prueba) ordenable y exportable a CSV.
3. **Reporte por peaje** — botón *Generar reporte*: informe imprimible/PDF con ficha del
   peaje, gráfico, interpretación automática, pronóstico a 12 meses con IC, evaluación
   punto a punto y descargas en HTML / CSV / JSON.
4. **Metodología** — limpieza, modelos, detección de rupturas, métricas y limitaciones.

## Limitaciones

- Los cambios de nivel no anticipables (tarifas, nuevas concessiones, cierres parciales)
  degradan cualquier modelo entrenado con datos previos al cambio.
- Los peajes con historia corta (< 24 meses) tienen pronósticos poco fiables.
- COVID-19 (abr–may 2020) distorsiona el ajuste; se puede excluir con la casilla habilitada.
- `RecaudoFSV` y `RecaudoSobrante` se muestran como contexto; el objetivo modelado es
  `Recaudo`.

## Estructura

```
index.html              Aplicación completa (CSS + JS en línea, gráficos SVG propios)
datos.js                Datos generados: window.DATOS (162 peajes, serie mensual 2014-01..2026-05)
preparar_datos.py       Limpia el CSV y regenera datos.js
datos/                  Copia del CSV original de la ANI
```
