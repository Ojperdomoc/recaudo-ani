#!/usr/bin/env python3
"""
Prepara los datos de recaudo vehicular ANI para la aplicación HTML.

Lee el CSV original, limpia y agrega a serie mensual por peaje, y genera
`datos.js` (window.DATOS) que consume `index.html`.

Uso:
    python3 preparar_datos.py
    python3 preparar_datos.py --csv datos/Recaudo_Vehicular_ANI_20261113.csv --salida datos.js

Limpieza aplicada (documentada también en la app):
  1. Parseo de números con formato colombiano (puntos de miles).
  2. Eliminación de registros duplicados exactos (misma IdPeaje, Desde, Hasta y valores).
  3. Agregación mensual por peaje: suma de recaudo/FSV/sobrante de los registros
     del mismo mes (maneja meses divididos en dos registros, p. ej. CHICORAL mar-2022).
  4. Meses parciales (<28 días cubiertos): se calcula `recaudo_norm` equivalente
     a mes de 30.44 días para modelar; el valor bruto se conserva para totales.
  5. Se distingue mes faltante (sin registro, null) de mes en cero (registro con 0).
  6. Estado del peaje: activo / cerrado / sin_recaudo.
"""
import argparse
import calendar
import csv
import json
from collections import defaultdict
from datetime import datetime

MESES = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def parse_num(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    return float(s.replace(".", "").replace(",", ""))


def parse_fecha(s):
    # Formato: "2015 Aug 21 12:00:00 AM"
    return datetime.strptime(s.strip(), "%Y %b %d %I:%M:%S %p")


def add_months(y, m, k):
    idx = (y * 12 + (m - 1)) + k
    return idx // 12, idx % 12 + 1


def month_range(y0, m0, y1, m1):
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append((y, m))
        y, m = add_months(y, m, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="datos/Recaudo_Vehicular_ANI_20261113.csv")
    ap.add_argument("--salida", default="datos.js")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
    n_original = len(raw)

    # --- Deduplicación exacta ---
    vistos = set()
    filas = []
    n_dup = 0
    for r in raw:
        clave = (r["IdPeaje"], r["Desde"], r["Hasta"], r["Recaudo"], r["RecaudoFsv"], r["RecaudoSobrante"])
        if clave in vistos:
            n_dup += 1
            continue
        vistos.add(clave)
        filas.append(r)

    # --- Agregación mensual por peaje ---
    # agg[(id, nombre, y, m)] = dict(...)
    agg = {}
    nombres = {}
    for r in filas:
        pid = r["IdPeaje"].strip()
        nombre = r["Peaje"].strip()
        nombres[pid] = nombre
        d0 = parse_fecha(r["Desde"])
        d1 = parse_fecha(r["Hasta"])
        dias = (d1 - d0).days + 1
        k = (pid, d0.year, d0.month)
        a = agg.setdefault(k, {"recaudo": 0.0, "fsv": 0.0, "sobrante": 0.0, "dias": 0, "n_reg": 0})
        a["recaudo"] += parse_num(r["Recaudo"])
        a["fsv"] += parse_num(r["RecaudoFsv"])
        a["sobrante"] += parse_num(r["RecaudoSobrante"])
        a["dias"] += dias
        a["n_reg"] += 1

    # --- Construir series por peaje ---
    por_peaje = defaultdict(list)
    for (pid, y, m), a in agg.items():
        por_peaje[pid].append((y, m, a))

    global_min = min((y, m) for (_, y, m) in agg.keys())
    global_max = max((y, m) for (_, y, m) in agg.keys())

    peajes = []
    total_mensual = []
    # Total nacional mensual (suma de recaudo bruto)
    tot = defaultdict(float)
    tot_fsv = defaultdict(float)
    tot_sob = defaultdict(float)
    for (pid, y, m), a in agg.items():
        tot[(y, m)] += a["recaudo"]
        tot_fsv[(y, m)] += a["fsv"]
        tot_sob[(y, m)] += a["sobrante"]
    for (y, m) in month_range(global_min[0], global_min[1], global_max[0], global_max[1]):
        total_mensual.append({
            "y": y, "m": m,
            "recaudo": round(tot.get((y, m), 0.0), 2),
            "fsv": round(tot_fsv.get((y, m), 0.0), 2),
            "sobrante": round(tot_sob.get((y, m), 0.0), 2),
        })

    for pid in sorted(por_peaje.keys(), key=lambda p: nombres[p]):
        lst = sorted(por_peaje[pid], key=lambda t: (t[0], t[1]))
        y0, m0 = lst[0][0], lst[0][1]
        y1, m1 = lst[-1][0], lst[-1][1]
        mapa = {(y, m): a for (y, m, a) in lst}
        meses = []
        n_ceros = 0
        n_parciales = 0
        n_faltantes = 0
        ultimo_no_cero = None
        for (y, m) in month_range(y0, m0, y1, m1):
            a = mapa.get((y, m))
            if a is None:
                n_faltantes += 1
                meses.append({"y": y, "m": m, "recaudo": None, "recaudo_norm": None,
                              "fsv": None, "sobrante": None, "dias": 0, "parcial": False,
                              "n_reg": 0, "faltante": True})
                continue
            dim = calendar.monthrange(y, m)[1]
            dias = min(a["dias"], dim)
            parcial = dias < 28
            if parcial:
                n_parciales += 1
            rec = round(a["recaudo"], 2)
            if rec == 0:
                n_ceros += 1
            else:
                ultimo_no_cero = (y, m)
            if parcial and dias > 0 and rec > 0:
                rec_norm = round(rec * 30.44 / dias, 2)
            else:
                rec_norm = rec
            meses.append({
                "y": y, "m": m, "recaudo": rec, "recaudo_norm": rec_norm,
                "fsv": round(a["fsv"], 2), "sobrante": round(a["sobrante"], 2),
                "dias": dias, "parcial": parcial, "n_reg": a["n_reg"], "faltante": False,
            })
        # Estado
        no_ceros = [x for x in meses if x["recaudo"] not in (None, 0)]
        if not no_ceros:
            estado = "sin_recaudo"
        elif ultimo_no_cero is not None and ultimo_no_cero < (2025, 11):
            estado = "cerrado"
        else:
            estado = "activo"
        peajes.append({
            "id": pid, "nombre": nombres[pid], "estado": estado,
            "inicio": f"{y0:04d}-{m0:02d}", "fin": f"{y1:04d}-{m1:02d}",
            "n_meses": len(meses), "n_ceros": n_ceros, "n_parciales": n_parciales,
            "n_faltantes": n_faltantes, "meses": meses,
        })

    datos = {
        "meta": {
            "fuente": "Recaudo_Vehicular_ANI_20261113.csv (ANI — datos abiertos)",
            "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "rango": f"{global_min[0]:04d}-{global_min[1]:02d} a {global_max[0]:04d}-{global_max[1]:02d}",
            "split": {"train_hasta": "2023-12", "test_desde": "2024-01",
                      "descripcion": "Entrenamiento: primeros 10 años (2014-01 a 2023-12). Prueba: últimos años (2024-01 a 2026-05)."},
            "n_filas_originales": n_original,
            "n_duplicados_eliminados": n_dup,
            "n_peajes": len(peajes),
            "nota": "recaudo_norm = recaudo ajustado a mes de 30.44 días cuando el registro es parcial (<28 días). Los modelos usan recaudo_norm; los totales usan recaudo bruto.",
        },
        "peajes": peajes,
        "total_mensual": total_mensual,
    }

    with open(args.salida, "w", encoding="utf-8") as f:
        f.write("// Generado automáticamente por preparar_datos.py — no editar a mano.\n")
        f.write("window.DATOS = ")
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"OK: {args.salida} | peajes={len(peajes)} filas={n_original} duplicados={n_dup} "
          f"rango={global_min}..{global_max}")


if __name__ == "__main__":
    main()
