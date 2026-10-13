"""Utilidades de periodo. Un periodo es un mes con formato 'YYYY-MM' (en el Excel: 1er día del mes)."""
from __future__ import annotations

import re
from datetime import date, datetime

_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validar(periodo: str) -> str:
    if not isinstance(periodo, str) or not _RE.match(periodo):
        raise ValueError(f"Periodo inválido: {periodo!r} (usa YYYY-MM)")
    return periodo


def de_fecha(f: date | datetime | str) -> str:
    """'2026-10-13' / date / datetime -> '2026-10'."""
    if isinstance(f, str):
        f = datetime.strptime(f[:10], "%Y-%m-%d")
    return f"{f.year:04d}-{f.month:02d}"


def a_indice(periodo: str) -> int:
    y, m = validar(periodo).split("-")
    return int(y) * 12 + int(m) - 1


def de_indice(i: int) -> str:
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def sumar_meses(periodo: str, n: int) -> str:
    return de_indice(a_indice(periodo) + n)


def meses_entre(desde: str, hasta: str) -> int:
    """Meses de `desde` a `hasta` (positivo si hasta es posterior)."""
    return a_indice(hasta) - a_indice(desde)


def hoy() -> str:
    return de_fecha(date.today())


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def etiqueta(periodo: str) -> str:
    """'2026-10' -> 'oct-26' (igual que el formato mmm-yy del Excel)."""
    y, m = validar(periodo).split("-")
    return f"{MESES[int(m) - 1]}-{y[2:]}"
