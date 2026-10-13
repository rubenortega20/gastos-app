"""Alta/edición de movimientos: replica las listas desplegables y fórmulas de la hoja 'Movimientos'.

Reglas que en el Excel eran validaciones y fórmulas:
  - Categoría  (D): lista Configuración!B7:B19
  - Tipo       (E): Personal | Compartido
  - % mío      (F): 100% (Personal) o el % de Rubén (Compartido, 60%)
  - Mi gasto   (G): = Monto pagado * % mío   (o un valor manual)
  - Tarjeta    (H): lista Configuración!D7:D12
"""
from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from . import calc, expr
from . import periodos as P


_RE_OPERACION = re.compile(r"(?<=[\d)])\s*[-+*/x×]")   # 'a-b', '2*3'… (un '-' inicial no cuenta)


class ErrorDatos(ValueError):
    """Dato inválido del usuario (la API lo responde como 400)."""


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def hoy_local() -> str:
    tz = ZoneInfo(os.environ.get("APP_TZ", "America/Santiago"))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _resolver(valor: str | None, opciones: list[str], campo: str, estricto: bool) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    for o in opciones:
        if _norm(o) == _norm(valor):
            return o
    if estricto:
        raise ErrorDatos(f"{campo} desconocida: {valor!r}. Opciones: {', '.join(opciones)}")
    return None


def opciones(conn: sqlite3.Connection) -> dict:
    cfg = calc.ajustes(conn)
    return {
        "categorias": [r["nombre"] for r in conn.execute("SELECT nombre FROM categorias WHERE activa=1 ORDER BY orden, id")],
        "tarjetas": [r["nombre"] for r in conn.execute("SELECT nombre FROM tarjetas ORDER BY orden, nombre")],
        "tipos": list(calc.TIPOS),
        "porc_ruben": cfg["porc_ruben"],
        "pct_opciones": [1.0, cfg["porc_ruben"]],
    }


def sugerir(conn: sqlite3.Connection, descripcion: str) -> dict | None:
    """Autocompleta categoría/tipo/tarjeta con el último movimiento de igual descripción (o que la contenga)."""
    q = _norm(descripcion)
    if not q:
        return None
    rows = conn.execute("SELECT descripcion, categoria, tipo, tarjeta, pct FROM movimientos "
                        "WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY id DESC LIMIT 3000").fetchall()
    for modo in ("igual", "contiene"):
        for r in rows:
            d = _norm(r["descripcion"])
            if (modo == "igual" and d == q) or (modo == "contiene" and len(q) >= 3 and (q in d or d in q) and d):
                return {"categoria": r["categoria"], "tipo": r["tipo"], "tarjeta": r["tarjeta"], "pct": r["pct"],
                        "descripcion": r["descripcion"]}
    return None


def preparar(conn: sqlite3.Connection, datos: dict, estricto: bool = True, usar_sugerencia: bool = False) -> tuple[dict, list[str]]:
    """Valida y completa un movimiento. Devuelve (fila_lista_para_insertar, advertencias)."""
    avisos: list[str] = []
    op = opciones(conn)

    try:
        monto = expr.evaluar(datos.get("monto"))
    except ValueError as e:
        raise ErrorDatos(str(e)) from e
    bruto = datos.get("monto")
    monto_expr = str(bruto).strip().lstrip("=") if isinstance(bruto, str) and _RE_OPERACION.search(bruto) else None

    fecha = (datos.get("fecha") or hoy_local())[:10]
    try:
        periodo = P.de_fecha(fecha)
    except ValueError as e:
        raise ErrorDatos(f"Fecha inválida: {fecha!r} (usa AAAA-MM-DD)") from e

    desc = (datos.get("descripcion") or "").strip()
    cat = _resolver(datos.get("categoria"), op["categorias"], "Categoría", estricto)
    tipo = _resolver(datos.get("tipo"), op["tipos"], "Tipo", estricto)
    tarjeta = _resolver(datos.get("tarjeta"), op["tarjetas"], "Tarjeta", estricto)
    pct = datos.get("pct")
    pct = None if pct in (None, "") else float(pct)

    if usar_sugerencia and desc:
        s = sugerir(conn, desc)
        if s:
            cat = cat or s["categoria"]
            tipo = tipo or s["tipo"]
            tarjeta = tarjeta or s["tarjeta"]
            if pct is None and datos.get("tipo") in (None, ""):
                pct = s["pct"]
    if datos.get("categoria") and not cat:
        avisos.append(f"Categoría {datos.get('categoria')!r} no existe; quedó sin categoría")
    if not cat:
        avisos.append("Sin categoría: no se cuenta en el presupuesto hasta que la asignes")

    tipo = tipo or "Personal"
    if pct is None:                                   # Personal = 100%, Compartido = % de Rubén
        pct = op["porc_ruben"] if tipo == "Compartido" else 1.0
    if not (0 <= pct <= 1):
        raise ErrorDatos("El % mío debe estar entre 0 y 1 (ej. 0.6)")

    manual = datos.get("mi_gasto") not in (None, "")
    override = None
    if manual:
        try:
            override = expr.evaluar(datos["mi_gasto"])
        except ValueError as e:
            raise ErrorDatos(str(e)) from e
    fila = {
        "fecha": fecha, "periodo": periodo, "descripcion": desc, "monto": monto, "monto_expr": monto_expr,
        "categoria": cat, "tipo": tipo, "pct": pct, "tarjeta": tarjeta,
        "mi_gasto": calc.calcular_mi_gasto(monto, pct, override), "mi_gasto_manual": 1 if manual else 0,
        "nota": (datos.get("nota") or None),
    }
    return fila, avisos


COLS = ["fecha", "periodo", "descripcion", "monto", "monto_expr", "categoria", "tipo", "pct",
        "mi_gasto", "mi_gasto_manual", "tarjeta", "nota"]


def crear(conn: sqlite3.Connection, datos: dict, estricto: bool = True, usar_sugerencia: bool = False) -> tuple[dict, list[str]]:
    fila, avisos = preparar(conn, datos, estricto, usar_sugerencia)
    cur = conn.execute(f"INSERT INTO movimientos({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                       [fila[c] for c in COLS])
    conn.commit()
    return obtener(conn, cur.lastrowid), avisos


def obtener(conn: sqlite3.Connection, mid: int) -> dict | None:
    r = conn.execute("SELECT * FROM movimientos WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def actualizar(conn: sqlite3.Connection, mid: int, datos: dict) -> tuple[dict, list[str]]:
    actual = obtener(conn, mid)
    if not actual:
        raise KeyError(mid)
    fusion = {**actual, **datos}
    if "tipo" in datos and "pct" not in datos:       # cambiar Personal<->Compartido recalcula el % mío
        fusion["pct"] = None
    # si cambia monto o pct y no hay override explícito, recalcula 'mi gasto'
    if "mi_gasto" not in datos:
        fusion["mi_gasto"] = None if not actual["mi_gasto_manual"] or "monto" in datos or "pct" in datos else actual["mi_gasto"]
    fila, avisos = preparar(conn, fusion, estricto=False)
    if "monto" not in datos:
        fila["monto_expr"] = actual["monto_expr"]
    conn.execute(f"UPDATE movimientos SET {','.join(f'{c}=?' for c in COLS)} WHERE id=?",
                 [fila[c] for c in COLS] + [mid])
    conn.commit()
    return obtener(conn, mid), avisos


def eliminar(conn: sqlite3.Connection, mid: int) -> bool:
    cur = conn.execute("DELETE FROM movimientos WHERE id=?", (mid,))
    conn.commit()
    return cur.rowcount > 0


def listar(conn: sqlite3.Connection, periodo: str) -> list[dict]:
    P.validar(periodo)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM movimientos WHERE periodo=? ORDER BY fecha DESC, id DESC", (periodo,))]
