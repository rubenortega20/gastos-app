"""Evaluador seguro de montos.

En el Excel el 'Monto pagado' a veces es una fórmula (=33550-101, =(24089+27990), =-8752-8723*4).
La app acepta lo mismo en el campo monto: números o expresiones con + - * / y paréntesis.
También entiende formato chileno: '$ 33.550' o '1.234,5'.
"""
from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(\.\d{3})+(,\d+)?(?![\d.,])")


def _normalizar(texto: str) -> str:
    t = texto.strip().lstrip("=").replace("$", "").replace(" ", "").replace("x", "*").replace("×", "*")

    def _fix(m: re.Match) -> str:
        return m.group(0).replace(".", "").replace(",", ".")

    t = _THOUSANDS.sub(_fix, t)
    # coma decimal simple: 12,5 -> 12.5
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    return t


def _eval(nodo: ast.AST) -> float:
    if isinstance(nodo, ast.Expression):
        return _eval(nodo.body)
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
        return float(nodo.value)
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPS:
        return _OPS[type(nodo.op)](_eval(nodo.left), _eval(nodo.right))
    if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, (ast.UAdd, ast.USub)):
        v = _eval(nodo.operand)
        return v if isinstance(nodo.op, ast.UAdd) else -v
    raise ValueError("Monto inválido: usa números u operaciones simples (ej. 33550-101)")


def evaluar(valor) -> float:
    """Convierte número o texto con operaciones simples a float. Lanza ValueError si no es válido."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValueError("Monto vacío")
    if isinstance(valor, bool):
        raise ValueError("Monto inválido")
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = _normalizar(str(valor))
    try:
        return _eval(ast.parse(texto, mode="eval"))
    except (SyntaxError, ZeroDivisionError, RecursionError) as e:
        raise ValueError(f"Monto inválido: {valor!r}") from e
