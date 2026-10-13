"""API HTTP + PWA (Starlette). Ejecutar:  uvicorn app.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import hmac
import os
import sqlite3
from functools import wraps
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import calc, db, expr, movs
from . import periodos as P

STATIC = Path(__file__).parent / "static"

# tabla -> (columna clave, {columna: tipo}). Tipos: text, real, int, bool, periodo, tipo
RECURSOS: dict[str, tuple[str, dict[str, str]]] = {
    "fijos": ("id", {"concepto": "text", "monto": "real", "categoria": "text", "tipo": "tipo", "pct": "real",
                     "tarjeta": "text", "desde": "periodo", "hasta": "periodo", "activo": "bool"}),
    "suscripciones": ("id", {"nombre": "text", "monto": "real", "tarjeta": "text", "desde": "periodo",
                             "hasta": "periodo", "activo": "bool"}),
    "cuotas_planes": ("id", {"compra": "text", "monto_total": "real", "cuota_mensual": "real",
                             "total_cuotas": "int", "periodo_ref": "periodo", "cuota_ref": "int",
                             "tarjeta": "text", "activo": "bool"}),
    "cargos_tarjeta": ("id", {"periodo": "periodo", "tarjeta": "text", "descripcion": "text", "monto": "real"}),
    "depto_items": ("id", {"concepto": "text", "monto": "real", "compartido": "bool"}),
    "categorias": ("id", {"nombre": "text", "presupuesto": "real", "aplica_pct": "bool", "orden": "int",
                          "activa": "bool"}),
    "tarjetas": ("nombre", {"nombre": "text", "es_credito": "bool", "orden": "int"}),
    "periodos": ("periodo", {"periodo": "periodo", "ahorro_objetivo": "real", "ingreso": "real",
                             "saldo_inicial_cuenta": "real"}),
}
# al renombrar, tablas/columnas donde también hay que cambiar el nombre
RENOMBRAR = {
    "categorias": [("movimientos", "categoria"), ("fijos", "categoria")],
    "tarjetas": [("movimientos", "tarjeta"), ("fijos", "tarjeta"), ("suscripciones", "tarjeta"),
                 ("cuotas_planes", "tarjeta"), ("cargos_tarjeta", "tarjeta")],
}


# ------------------------------------------------------------------ utilidades HTTP
def clp(n: float) -> str:
    return "$" + f"{round(n):,}".replace(",", ".")


def autorizado(request: Request) -> bool:
    token = os.environ.get("APP_TOKEN", "")
    if not token:
        return True                                   # modo desarrollo: sin token
    dado = request.headers.get("authorization", "")
    dado = dado[7:] if dado.lower().startswith("bearer ") else (
        request.headers.get("x-token") or request.query_params.get("token") or "")
    return hmac.compare_digest(dado.encode(), token.encode())


def endpoint(fn):
    """Autenticación + manejo uniforme de errores. Los endpoints son async para serializar el acceso a SQLite."""
    @wraps(fn)
    async def envoltorio(request: Request):
        if not autorizado(request):
            return JSONResponse({"error": "No autorizado"}, status_code=401)
        try:
            return await fn(request)
        except movs.ErrorDatos as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except KeyError:
            return JSONResponse({"error": "No encontrado"}, status_code=404)
        except sqlite3.IntegrityError as e:
            return JSONResponse({"error": f"Dato duplicado o incompleto ({e})"}, status_code=400)
    return envoltorio


async def cuerpo(request: Request) -> dict:
    """Acepta JSON, formulario (Atajos de iOS) y parámetros en la URL."""
    datos: dict = dict(request.query_params)
    datos.pop("token", None)
    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        j = await request.json()
        if not isinstance(j, dict):
            raise ValueError("El cuerpo debe ser un objeto JSON")
        datos.update(j)
    elif "form" in ctype:
        datos.update({k: v for k, v in (await request.form()).items() if isinstance(v, str)})
    return datos


def conn_de(request: Request) -> sqlite3.Connection:
    return request.app.state.conn


def periodo_de(request: Request) -> str:
    return request.query_params.get("periodo") or P.hoy()


# ------------------------------------------------------------------ coerción de recursos
def _coercionar(valor, tipo: str):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == "text":
        return str(valor).strip()
    if tipo == "real":
        return expr.evaluar(valor)
    if tipo == "int":
        return int(expr.evaluar(valor))
    if tipo == "bool":
        return 0 if str(valor).strip().lower() in ("0", "false", "no", "off") else 1
    if tipo == "periodo":
        return P.validar(str(valor).strip()[:7])
    if tipo == "tipo":
        if valor not in calc.TIPOS:
            raise ValueError(f"Tipo inválido: {valor!r}")
        return valor
    raise ValueError(f"tipo desconocido {tipo}")


def _campos(recurso: str, datos: dict, parcial: bool) -> dict:
    _, cols = RECURSOS[recurso]
    return {c: _coercionar(datos[c], t) for c, t in cols.items() if (c in datos or not parcial)}


# ------------------------------------------------------------------ endpoints
@endpoint
async def salud(request):
    return JSONResponse({"ok": True})


@endpoint
async def opciones(request):
    c = conn_de(request)
    out = movs.opciones(c)
    out["periodo_actual"] = P.hoy()
    out["periodos"] = [r[0] for r in c.execute(
        "SELECT periodo FROM (SELECT periodo FROM movimientos UNION SELECT periodo FROM periodos) ORDER BY periodo")]
    return JSONResponse(out)


@endpoint
async def dashboard(request):
    return JSONResponse(calc.dashboard(conn_de(request), periodo_de(request)))


@endpoint
async def cuotas(request):
    c, p = conn_de(request), periodo_de(request)
    return JSONResponse({"periodo": p, "cuotas": calc.cuotas_mes(c, p),
                         "planes": [dict(r) for r in c.execute("SELECT * FROM cuotas_planes ORDER BY id")]})


@endpoint
async def mov_lista(request):
    c, p = conn_de(request), periodo_de(request)
    filas = movs.listar(c, p)
    return JSONResponse({"periodo": p, "total_mi_gasto": sum(f["mi_gasto"] for f in filas), "movimientos": filas})


@endpoint
async def mov_crear(request):
    fila, avisos = movs.crear(conn_de(request), await cuerpo(request))
    return JSONResponse({"movimiento": fila, "avisos": avisos}, status_code=201)


@endpoint
async def mov_editar(request):
    fila, avisos = movs.actualizar(conn_de(request), int(request.path_params["id"]), await cuerpo(request))
    return JSONResponse({"movimiento": fila, "avisos": avisos})


@endpoint
async def mov_borrar(request):
    if not movs.eliminar(conn_de(request), int(request.path_params["id"])):
        raise KeyError
    return JSONResponse({"ok": True})


@endpoint
async def sugerir(request):
    return JSONResponse(movs.sugerir(conn_de(request), request.query_params.get("descripcion", "")) or {})


@endpoint
async def rapido(request):
    """Acceso rápido (Atajos de iOS). Mínimo: monto. Si falta categoría/tarjeta se infiere de la descripción."""
    c = conn_de(request)
    fila, avisos = movs.crear(c, await cuerpo(request), estricto=False, usar_sugerencia=True)
    partes = [f"{fila['descripcion'] or fila['categoria'] or 'Gasto'} {clp(fila['monto'])}"]
    if fila["pct"] != 1.0:
        partes.append(f"tu parte {clp(fila['mi_gasto'])}")
    res = calc.resumen_categoria(c, fila["periodo"], fila["categoria"])
    if res and res["presupuesto"]:
        partes.append(f"{fila['categoria']}: quedan {clp(res['disponible'])} de {clp(res['presupuesto'])}"
                      if res["disponible"] >= 0 else f"{fila['categoria']}: te pasaste por {clp(-res['disponible'])}")
    return JSONResponse({"ok": True, "mensaje": " · ".join(partes), "movimiento": fila, "avisos": avisos},
                        status_code=201)


@endpoint
async def config_get(request):
    c = conn_de(request)
    return JSONResponse(calc.ajustes(c))


@endpoint
async def config_put(request):
    c = conn_de(request)
    datos = await cuerpo(request)
    for k in ("ingreso", "porc_ruben"):
        if k in datos:
            v = expr.evaluar(datos[k])
            if k == "porc_ruben" and not 0 <= v <= 1:
                raise ValueError("porc_ruben debe estar entre 0 y 1")
            c.execute("INSERT INTO config(clave, valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                      (k, v))
    c.commit()
    return JSONResponse(calc.ajustes(c))


def _recurso(request: Request) -> str:
    r = request.path_params["recurso"]
    if r not in RECURSOS:
        raise KeyError(r)
    return r


@endpoint
async def rec_lista(request):
    r = _recurso(request)
    pk, _ = RECURSOS[r]
    orden = {"categorias": "orden, id", "tarjetas": "orden, nombre", "periodos": "periodo"}.get(r, "id")
    return JSONResponse([dict(x) for x in conn_de(request).execute(f"SELECT * FROM {r} ORDER BY {orden}")])


@endpoint
async def rec_crear(request):
    r = _recurso(request)
    c = conn_de(request)
    pk, _ = RECURSOS[r]
    campos = _campos(r, await cuerpo(request), parcial=True)
    campos = {k: v for k, v in campos.items() if v is not None or k not in ("activo", "activa", "pct", "tipo")}
    cur = c.execute(f"INSERT INTO {r}({','.join(campos)}) VALUES ({','.join('?' * len(campos))})", list(campos.values()))
    c.commit()
    clave = campos.get(pk) if pk != "id" else cur.lastrowid
    return JSONResponse(dict(c.execute(f"SELECT * FROM {r} WHERE {pk}=?", (clave,)).fetchone()), status_code=201)


@endpoint
async def rec_editar(request):
    r = _recurso(request)
    c = conn_de(request)
    pk, _ = RECURSOS[r]
    clave = request.path_params["clave"]
    clave = int(clave) if pk == "id" else clave
    actual = c.execute(f"SELECT * FROM {r} WHERE {pk}=?", (clave,)).fetchone()
    if not actual:
        raise KeyError
    campos = _campos(r, await cuerpo(request), parcial=True)
    if campos:
        c.execute(f"UPDATE {r} SET {','.join(f'{k}=?' for k in campos)} WHERE {pk}=?", [*campos.values(), clave])
        nuevo = campos.get(pk, clave)
        if pk != "id" and nuevo != clave:             # renombre de clave natural (tarjeta, periodo)
            pass
        if r in RENOMBRAR and "nombre" in campos and campos["nombre"] != actual["nombre"]:
            for tabla, col in RENOMBRAR[r]:
                c.execute(f"UPDATE {tabla} SET {col}=? WHERE {col}=?", (campos["nombre"], actual["nombre"]))
        c.commit()
        clave = nuevo
    return JSONResponse(dict(c.execute(f"SELECT * FROM {r} WHERE {pk}=?", (clave,)).fetchone()))


@endpoint
async def rec_borrar(request):
    r = _recurso(request)
    c = conn_de(request)
    pk, _ = RECURSOS[r]
    clave = request.path_params["clave"]
    clave = int(clave) if pk == "id" else clave
    if c.execute(f"DELETE FROM {r} WHERE {pk}=?", (clave,)).rowcount == 0:
        raise KeyError
    c.commit()
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------ app
def crear_app(db_path: str | None = None) -> Starlette:
    conn = db.conectar(db_path)
    db.seed_minimo(conn)
    rutas = [
        Route("/api/salud", salud),
        Route("/api/opciones", opciones),
        Route("/api/dashboard", dashboard),
        Route("/api/cuotas", cuotas),
        Route("/api/sugerir", sugerir),
        Route("/api/rapido", rapido, methods=["POST", "GET"]),
        Route("/api/config", config_get, methods=["GET"]),
        Route("/api/config", config_put, methods=["PUT", "POST"]),
        Route("/api/movimientos", mov_lista, methods=["GET"]),
        Route("/api/movimientos", mov_crear, methods=["POST"]),
        Route("/api/movimientos/{id:int}", mov_editar, methods=["PUT"]),
        Route("/api/movimientos/{id:int}", mov_borrar, methods=["DELETE"]),
        Route("/api/r/{recurso}", rec_lista, methods=["GET"]),
        Route("/api/r/{recurso}", rec_crear, methods=["POST"]),
        Route("/api/r/{recurso}/{clave}", rec_editar, methods=["PUT"]),
        Route("/api/r/{recurso}/{clave}", rec_borrar, methods=["DELETE"]),
        Mount("/", app=StaticFiles(directory=str(STATIC), html=True), name="static"),
    ]
    app = Starlette(routes=rutas)
    app.state.conn = conn
    if not os.environ.get("APP_TOKEN"):
        print("AVISO: APP_TOKEN no definido; la API queda abierta. Defínelo antes de exponerla a internet.")
    return app


app = crear_app()
