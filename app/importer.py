"""Importa el Excel 'Orden_def.xlsx' a la base SQLite.

Uso:  python -m app.importer ruta/al/Orden_def.xlsx [--db data/gastos.db] [--mantener]

Lee cada hoja tal como está diseñada hoy (ver docs/ANALISIS_EXCEL.md). Usa el valor calculado de las
celdas (data_only) y la fórmula original solo para detectar patrones (ej. '=660000*Porc_Ruben').
"""
from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import openpyxl

from . import calc, db
from . import periodos as P

# Dashboard!B29:B31 suma a cada tarjeta cargos fijos referenciando celdas a mano; aquí se vuelve un dato.
TARJETA_FIJOS = {"Auto": "Falabella"}                 # Dashboard!B29 suma Fijos!B6 (Auto)
TARJETA_SUSCRIPCIONES = "Falabella"                   # Dashboard!B29 suma Fijos!K10 (total suscripciones)
TARJETA_CUOTAS = {"Gym": "Cencosud", "Orden": "Santander"}   # Dashboard!B30 (Cuotas!D5) y B31 (Cuotas!D4)
TARJETAS_CREDITO = {"Falabella", "Cencosud", "Santander"}    # Las 3 que muestra 'Facturación por tarjeta'
GASTOS_DEPTO_PERSONALES = {"Internet (personal)"}             # ver nota abajo


def _periodo(v) -> str | None:
    if isinstance(v, (datetime, date)):
        return P.de_fecha(v)
    return None


def _limpiar(conn) -> None:
    for t in ("movimientos", "fijos", "suscripciones", "cuotas_planes", "cargos_tarjeta",
              "depto_items", "categorias", "tarjetas", "periodos", "config"):
        conn.execute(f"DELETE FROM {t}")


def importar(conn, xlsx: str | Path, reset: bool = True) -> dict[str, int]:
    f = openpyxl.load_workbook(xlsx)                    # fórmulas
    v = openpyxl.load_workbook(xlsx, data_only=True)    # valores calculados
    n: dict[str, int] = {}
    if reset:
        _limpiar(conn)

    # --------------------------------------------------------------- Configuración
    cf, cv = f["Configuración"], v["Configuración"]
    conn.executemany("INSERT OR REPLACE INTO config(clave, valor) VALUES (?,?)",
                     [("ingreso", float(cv["B2"].value or 0)), ("porc_ruben", float(cv["E2"].value or 0.6))])

    # Ahorro por mes (J7:K22) y saldo inicial de cuenta (Dashboard!D30 = 113410 - SUMIFS(...))
    for r in range(7, cv.max_row + 1):
        p = _periodo(cv[f"J{r}"].value)
        if p and cv[f"K{r}"].value is not None:
            conn.execute("INSERT OR REPLACE INTO periodos(periodo, ahorro_objetivo) VALUES (?,?)",
                         (p, float(cv[f"K{r}"].value)))
    n["periodos"] = conn.execute("SELECT COUNT(*) FROM periodos").fetchone()[0]

    df, dv = f["Dashboard"], v["Dashboard"]
    p_dash = _periodo(dv["B2"].value)
    m = re.match(r"^=\s*(\d+)\s*-", str(df["D30"].value or ""))
    if p_dash and m:
        conn.execute("INSERT INTO periodos(periodo, saldo_inicial_cuenta) VALUES (?,?) "
                     "ON CONFLICT(periodo) DO UPDATE SET saldo_inicial_cuenta=excluded.saldo_inicial_cuenta",
                     (p_dash, float(m.group(1))))

    # Tarjetas (D7:D13)
    for i, r in enumerate(range(7, 14)):
        nombre = cv[f"D{r}"].value
        if nombre:
            conn.execute("INSERT OR REPLACE INTO tarjetas(nombre, es_credito, orden) VALUES (?,?,?)",
                         (nombre, 1 if nombre in TARJETAS_CREDITO else 0, i))
    n["tarjetas"] = conn.execute("SELECT COUNT(*) FROM tarjetas").fetchone()[0]

    # Categorías (B7:B19) + presupuesto (Presupuesto!B, filas 4..16 en el mismo orden)
    pf, pv = f["Presupuesto"], v["Presupuesto"]
    for i, r in enumerate(range(7, 20)):
        nombre = cv[f"B{r}"].value
        if not nombre:
            continue
        fila = 4 + i
        fx, val = pf[f"B{fila}"].value, pv[f"B{fila}"].value
        base, aplica = float(val or 0), 0
        mm = re.match(r"^=\s*(\d+(?:\.\d+)?)\s*\*\s*'?Configuración'?!Porc_Ruben\s*$", str(fx))
        if mm:                                           # ej. =660000*Porc_Ruben -> 660000 * 60%
            base, aplica = float(mm.group(1)), 1
        conn.execute("INSERT INTO categorias(nombre, presupuesto, aplica_pct, orden) VALUES (?,?,?,?)",
                     (nombre, base, aplica, i))
    n["categorias"] = conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]

    # Gastos depto (G7:H13): Presupuesto!B5 = SUM(H7:H12)*Porc_Ruben + H13  (H13 es 100% mío)
    for r in range(7, 14):
        concepto, monto = cv[f"G{r}"].value, cv[f"H{r}"].value
        if concepto and monto is not None:
            conn.execute("INSERT INTO depto_items(concepto, monto, compartido) VALUES (?,?,?)",
                         (concepto, float(monto), 0 if r == 13 else 1))
    n["depto_items"] = conn.execute("SELECT COUNT(*) FROM depto_items").fetchone()[0]

    # --------------------------------------------------------------- Movimientos
    mf, mv = f["Movimientos"], v["Movimientos"]
    cont = 0
    for r in range(4, mf.max_row + 1):
        monto = mv[f"C{r}"].value
        per = _periodo(mv[f"A{r}"].value)
        if monto is None or per is None:
            continue                                      # filas pre-armadas vacías (205-207 y más abajo)
        expr = mf[f"C{r}"].value
        expr = expr.lstrip("=") if isinstance(expr, str) and expr.startswith("=") else None
        pct = mv[f"F{r}"].value
        gf, gv = mf[f"G{r}"].value, mv[f"G{r}"].value
        manual = isinstance(gf, str) and gf.replace(" ", "") != f"=C{r}*F{r}"
        mi = float(gv) if gv is not None else calc.calcular_mi_gasto(monto, pct)
        nota = f"Excel: {gf}" if manual else None
        conn.execute(
            "INSERT INTO movimientos(fecha, periodo, descripcion, monto, monto_expr, categoria, tipo, pct, "
            "mi_gasto, mi_gasto_manual, tarjeta, nota) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"{per}-01", per, mv[f"B{r}"].value or "", float(monto), expr, mv[f"D{r}"].value,
             mv[f"E{r}"].value, float(pct) if pct is not None else None, mi, 1 if manual else 0,
             mv[f"H{r}"].value, nota))
        cont += 1
    n["movimientos"] = cont

    # --------------------------------------------------------------- Fijos
    ff, fv = f["Fijos"], v["Fijos"]
    cont = 0
    for r in range(4, 40):
        concepto = fv[f"A{r}"].value
        if not concepto or fv[f"B{r}"].value is None:
            continue
        conn.execute("INSERT INTO fijos(concepto, monto, categoria, tipo, pct, tarjeta) VALUES (?,?,?,?,?,?)",
                     (concepto, float(fv[f"B{r}"].value), fv[f"C{r}"].value, fv[f"D{r}"].value or "Personal",
                      float(fv[f"E{r}"].value if fv[f"E{r}"].value is not None else 1.0),
                      TARJETA_FIJOS.get(concepto)))
        cont += 1
    n["fijos"] = cont

    # Suscripciones: matriz J4:J9 x K3:Y3. El Excel solo tiene la 1ª columna llenada (oct-26).
    desde = _periodo(fv["K3"].value)
    cont = 0
    for r in range(4, 10):
        nombre = fv[f"J{r}"].value
        if not nombre:
            continue
        monto = fv[f"K{r}"].value or 0
        activo = 1
        mm = re.match(r"^=\s*(\d+(?:\.\d+)?)\s*\*\s*0\s*$", str(ff[f"K{r}"].value or ""))
        if mm:                                            # =10990*0 -> suscripción pausada
            monto, activo = float(mm.group(1)), 0
        conn.execute("INSERT INTO suscripciones(nombre, monto, tarjeta, desde, activo) VALUES (?,?,?,?,?)",
                     (nombre, float(monto), TARJETA_SUSCRIPCIONES, desde, activo))
        cont += 1
    n["suscripciones"] = cont

    # --------------------------------------------------------------- Cuotas
    cf2, cv2 = f["Cuotas"], v["Cuotas"]
    planes: dict[str, dict] = {}
    for r in range(4, 40):
        compra = cv2[f"B{r}"].value
        per = _periodo(cv2[f"A{r}"].value)
        if not compra or not per:
            continue
        if compra not in planes:                          # primera fila = referencia
            planes[compra] = {"periodo_ref": per, "cuota_ref": int(cv2[f"E{r}"].value),
                              "total": int(cv2[f"F{r}"].value), "cuota": float(cv2[f"D{r}"].value)}
        planes[compra]["monto_total"] = float(cv2[f"C{r}"].value or 0)   # el último valor manda
    for compra, d in planes.items():
        conn.execute("INSERT INTO cuotas_planes(compra, monto_total, cuota_mensual, total_cuotas, periodo_ref, "
                     "cuota_ref, tarjeta) VALUES (?,?,?,?,?,?,?)",
                     (compra, d["monto_total"], d["cuota"], d["total"], d["periodo_ref"], d["cuota_ref"],
                      TARJETA_CUOTAS.get(compra)))
    n["cuotas_planes"] = len(planes)

    # Cargo suelto sumado a mano en Dashboard!B31 (+80833)
    mm = re.search(r"\+\s*(\d+)\s*$", str(df["B31"].value or ""))
    if mm and p_dash:
        conn.execute("INSERT INTO cargos_tarjeta(periodo, tarjeta, descripcion, monto) VALUES (?,?,?,?)",
                     (p_dash, "Santander", "Cargo sumado a mano en el Excel (sin detalle)", float(mm.group(1))))
        n["cargos_tarjeta"] = 1

    conn.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Importa Orden_def.xlsx a la base de datos")
    ap.add_argument("xlsx")
    ap.add_argument("--db", default=None, help="ruta del .db (por defecto data/gastos.db o $GASTOS_DB)")
    ap.add_argument("--mantener", action="store_true", help="no borrar datos existentes antes de importar")
    a = ap.parse_args()
    conn = db.conectar(a.db)
    res = importar(conn, a.xlsx, reset=not a.mantener)
    for k, val in res.items():
        print(f"{k:16s} {val}")


if __name__ == "__main__":
    main()
