"""Cálculos que en el Excel hacían las fórmulas de 'Presupuesto', 'Dashboard' y 'Cuotas'.

Equivalencias (hoja!celda del Excel -> función):
  Presupuesto!B  -> presupuesto_categoria()
  Presupuesto!C  -> fijos_por_categoria()      (SUMIFS Fijos!F por categoría)
  Presupuesto!D  -> movimientos_por_categoria() (SUMIFS Movimientos!G por categoría y periodo)
  Presupuesto!E  -> suscripciones_mes() / cuotas_mes() (HLOOKUP subs, VLOOKUP cuotas)
  Dashboard!*    -> dashboard()
  Cuotas!*       -> cuotas_mes()
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import periodos as P

TIPOS = ("Personal", "Compartido")
CAT_SUSCRIPCIONES = "Suscripciones"   # Presupuesto!E13 en el Excel
CAT_DEUDAS = "Deudas"                 # Presupuesto!E14 en el Excel
CAT_DEPTO = "Gastos depto"            # Presupuesto!B5 en el Excel


# ---------------------------------------------------------------- utilidades
def calcular_mi_gasto(monto: float, pct: float | None, override: float | None = None) -> float:
    """Movimientos!G = C*F, o un valor manual si la fila tenía una fórmula distinta."""
    if override is not None:
        return float(override)
    return float(monto) * (1.0 if pct is None else float(pct))


def ajustes(conn: sqlite3.Connection) -> dict[str, float]:
    d = {r["clave"]: r["valor"] for r in conn.execute("SELECT clave, valor FROM config")}
    d.setdefault("ingreso", 0.0)
    d.setdefault("porc_ruben", 0.6)
    return d


def info_periodo(conn: sqlite3.Connection, periodo: str) -> dict[str, Any]:
    """Ingreso, ahorro objetivo y saldo inicial de cuenta del mes."""
    P.validar(periodo)
    cfg = ajustes(conn)
    r = conn.execute("SELECT * FROM periodos WHERE periodo=?", (periodo,)).fetchone()
    ingreso = cfg["ingreso"] if r is None or r["ingreso"] is None else r["ingreso"]
    return {
        "ingreso": float(ingreso),
        "ahorro_objetivo": float(r["ahorro_objetivo"] or 0) if r else 0.0,
        "saldo_inicial_cuenta": float(r["saldo_inicial_cuenta"] or 0) if r else 0.0,
    }


def _vigente(desde: str | None, hasta: str | None, periodo: str) -> bool:
    return (not desde or desde <= periodo) and (not hasta or periodo <= hasta)


# ---------------------------------------------------------------- recurrentes
def fijos_mes(conn: sqlite3.Connection, periodo: str) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM fijos WHERE activo=1 ORDER BY id"):
        if _vigente(r["desde"], r["hasta"], periodo):
            d = dict(r)
            d["mi_gasto"] = d["monto"] * d["pct"]   # Fijos!F = B*E
            out.append(d)
    return out


def suscripciones_mes(conn: sqlite3.Connection, periodo: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM suscripciones WHERE activo=1 ORDER BY id")
            if _vigente(r["desde"], r["hasta"], periodo)]


def cuotas_mes(conn: sqlite3.Connection, periodo: str) -> list[dict]:
    """Cuotas que vencen en `periodo`. Equivale a las filas de la hoja 'Cuotas' de ese mes."""
    out = []
    for r in conn.execute("SELECT * FROM cuotas_planes WHERE activo=1 ORDER BY id"):
        n = r["cuota_ref"] + P.meses_entre(r["periodo_ref"], periodo)
        if r["cuota_ref"] <= n <= r["total_cuotas"]:
            restantes = r["total_cuotas"] - n                       # Cuotas!G = F - E
            out.append({
                "id": r["id"], "compra": r["compra"], "tarjeta": r["tarjeta"],
                "monto_total": r["monto_total"], "cuota_mensual": r["cuota_mensual"],
                "cuota_actual": n, "total_cuotas": r["total_cuotas"],
                "cuotas_restantes": restantes,
                "saldo_pendiente": r["cuota_mensual"] * restantes,   # Cuotas!H = D * G
            })
    return out


def cargos_tarjeta_mes(conn: sqlite3.Connection, periodo: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM cargos_tarjeta WHERE periodo=? ORDER BY id", (periodo,))]


# ---------------------------------------------------------------- presupuesto
def presupuesto_categoria(conn: sqlite3.Connection, cat: sqlite3.Row, porc: float) -> float:
    """Presupuesto!B. 'Gastos depto' = suma(compartidos)*porc + suma(personales) (Configuración!H7:H13)."""
    if cat["nombre"] == CAT_DEPTO:
        items = conn.execute("SELECT monto, compartido FROM depto_items").fetchall()
        if items:
            return sum(i["monto"] * (porc if i["compartido"] else 1.0) for i in items)
    return cat["presupuesto"] * (porc if cat["aplica_pct"] else 1.0)


def presupuesto(conn: sqlite3.Connection, periodo: str) -> dict[str, Any]:
    """Tabla 'Presupuesto vs Real' del mes."""
    P.validar(periodo)
    porc = ajustes(conn)["porc_ruben"]
    cats = conn.execute("SELECT * FROM categorias WHERE activa=1 ORDER BY orden, id").fetchall()

    fijos: dict[str, float] = {}
    for f in fijos_mes(conn, periodo):
        fijos[f["categoria"]] = fijos.get(f["categoria"], 0.0) + f["mi_gasto"]
    movs = {r["categoria"]: r["t"] for r in conn.execute(
        "SELECT categoria, SUM(mi_gasto) t FROM movimientos WHERE periodo=? GROUP BY categoria", (periodo,))}
    subs_total = sum(s["monto"] for s in suscripciones_mes(conn, periodo))
    cuotas_total = sum(c["cuota_mensual"] for c in cuotas_mes(conn, periodo))

    filas = []
    for c in cats:
        nombre = c["nombre"]
        pres = presupuesto_categoria(conn, c, porc)
        suscr = subs_total if nombre == CAT_SUSCRIPCIONES else 0.0
        cuot = cuotas_total if nombre == CAT_DEUDAS else 0.0
        fijo = fijos.get(nombre, 0.0)
        mov = movs.get(nombre, 0.0) or 0.0
        real = fijo + mov + suscr + cuot
        filas.append({
            "categoria": nombre, "presupuesto": pres, "fijo": fijo, "movimientos": mov,
            "suscripciones": suscr, "cuotas": cuot, "real": real,
            "disponible": pres - real, "pct_usado": (real / pres) if pres else 0.0,
        })

    nombres = {c["nombre"] for c in cats}
    sin_categoria = sum(v or 0.0 for k, v in movs.items() if k not in nombres)   # k None o desconocida
    return {
        "periodo": periodo, "filas": filas, "sin_categoria": sin_categoria,
        "total_presupuesto": sum(f["presupuesto"] for f in filas),
        "total_real": sum(f["real"] for f in filas),
        "total_disponible": sum(f["disponible"] for f in filas),
    }


# ---------------------------------------------------------------- dashboard
def dashboard(conn: sqlite3.Connection, periodo: str) -> dict[str, Any]:
    """Hoja 'Dashboard'.

    Diferencia deliberada con el Excel: el Excel NO cuenta los movimientos sin categoría
    (SUMIFS por categoría los ignora), por lo que 'Ahorro real' queda inflado. Aquí
    `ahorro_real` los descuenta y `ahorro_real_excel` conserva el cálculo original.
    """
    pr = presupuesto(conn, periodo)
    ip = info_periodo(conn, periodo)
    ingreso, objetivo = ip["ingreso"], ip["ahorro_objetivo"]
    total = pr["total_real"]
    sin_cat = pr["sin_categoria"]

    cuotas = cuotas_mes(conn, periodo)
    ahorro_excel = max(0.0, ingreso - total)                 # Dashboard!A8
    ahorro_real = max(0.0, ingreso - total - sin_cat)
    disponible = max(0.0, ingreso - objetivo - total - sin_cat)   # Dashboard!D8

    tarjetas = []
    for t in conn.execute("SELECT * FROM tarjetas WHERE es_credito=1 ORDER BY orden, nombre"):
        nombre = t["nombre"]
        movs = conn.execute("SELECT COALESCE(SUM(monto),0) FROM movimientos WHERE periodo=? AND tarjeta=?",
                            (periodo, nombre)).fetchone()[0]
        fij = sum(f["monto"] for f in fijos_mes(conn, periodo) if f["tarjeta"] == nombre)
        sus = sum(s["monto"] for s in suscripciones_mes(conn, periodo) if s["tarjeta"] == nombre)
        cuo = sum(c["cuota_mensual"] for c in cuotas if c["tarjeta"] == nombre)
        car = sum(c["monto"] for c in cargos_tarjeta_mes(conn, periodo) if c["tarjeta"] == nombre)
        tarjetas.append({"tarjeta": nombre, "movimientos": movs, "fijos": fij, "suscripciones": sus,
                         "cuotas": cuo, "otros_cargos": car, "total": movs + fij + sus + cuo + car})

    debito = conn.execute("SELECT COALESCE(SUM(mi_gasto),0) FROM movimientos WHERE periodo=? AND tarjeta='Débito'",
                          (periodo,)).fetchone()[0]

    return {
        "periodo": periodo, "etiqueta": P.etiqueta(periodo),
        "ingreso": ingreso, "ahorro_objetivo": objetivo,
        "ahorro_real": ahorro_real, "ahorro_real_excel": ahorro_excel,
        "disponible": disponible,
        "tasa_ahorro": (ahorro_real / ingreso) if ingreso else 0.0,
        "meta_ahorro": (objetivo / ingreso) if ingreso else 0.0,
        "cuotas_mensuales": sum(c["cuota_mensual"] for c in cuotas),
        "saldo_deudas": sum(c["saldo_pendiente"] for c in cuotas),
        "categorias": pr["filas"],
        "total_presupuesto": pr["total_presupuesto"], "total_real": total,
        "total_disponible": pr["total_disponible"],
        "sin_categoria": sin_cat,
        "tarjetas": tarjetas,
        "saldo_cuenta": ip["saldo_inicial_cuenta"] - debito,   # Dashboard!D30
        "saldo_inicial_cuenta": ip["saldo_inicial_cuenta"],
    }


def resumen_categoria(conn: sqlite3.Connection, periodo: str, categoria: str | None) -> dict | None:
    """Para el mensaje de confirmación del acceso rápido: cuánto queda en la categoría."""
    if not categoria:
        return None
    for f in presupuesto(conn, periodo)["filas"]:
        if f["categoria"] == categoria:
            return f
    return None
