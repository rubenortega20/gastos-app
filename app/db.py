"""SQLite: esquema y conexión. Un solo archivo (data/gastos.db) fácil de respaldar."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "gastos.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Hoja 'Configuración' (B2, E2): clave/valor. Claves: ingreso, porc_ruben
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor REAL NOT NULL
);

-- Hoja 'Configuración' J:K (Ahorro por mes) + saldo inicial de cuenta (Dashboard!D30, hardcodeado en el Excel)
CREATE TABLE IF NOT EXISTS periodos (
    periodo TEXT PRIMARY KEY,                 -- 'YYYY-MM'
    ahorro_objetivo REAL,
    ingreso REAL,                             -- NULL = usa config.ingreso
    saldo_inicial_cuenta REAL
);

-- Hoja 'Configuración' B7:B19 (Categorías) + columna B de 'Presupuesto'
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    presupuesto REAL NOT NULL DEFAULT 0,
    aplica_pct INTEGER NOT NULL DEFAULT 0,    -- 1 = presupuesto * porc_ruben (ej. Arriendo 660000*60%)
    orden INTEGER NOT NULL DEFAULT 0,
    activa INTEGER NOT NULL DEFAULT 1
);

-- Hoja 'Configuración' D7:D13 (Tarjetas). es_credito = aparece en 'Facturación por tarjeta'
CREATE TABLE IF NOT EXISTS tarjetas (
    nombre TEXT PRIMARY KEY,
    es_credito INTEGER NOT NULL DEFAULT 0,
    orden INTEGER NOT NULL DEFAULT 0
);

-- Hoja 'Configuración' G7:H13 (Gastos depto) -> base del presupuesto de la categoría 'Gastos depto'
CREATE TABLE IF NOT EXISTS depto_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concepto TEXT NOT NULL,
    monto REAL NOT NULL,
    compartido INTEGER NOT NULL DEFAULT 1     -- 1 = se multiplica por porc_ruben
);

-- Hoja 'Movimientos'
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,                      -- 'YYYY-MM-DD' (el Excel solo guarda el mes)
    periodo TEXT NOT NULL,                    -- 'YYYY-MM' derivado de fecha
    descripcion TEXT NOT NULL DEFAULT '',
    monto REAL NOT NULL,                      -- 'Monto pagado'
    monto_expr TEXT,                          -- texto original si fue fórmula (ej. '33550-101')
    categoria TEXT,
    tipo TEXT,                                -- Personal | Compartido
    pct REAL,                                 -- '% mío'
    mi_gasto REAL NOT NULL,                   -- 'Mi gasto' = monto*pct, o manual (override)
    mi_gasto_manual INTEGER NOT NULL DEFAULT 0,
    tarjeta TEXT,
    nota TEXT,
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_mov_periodo ON movimientos(periodo);

-- Hoja 'Fijos' A:H. Se repiten todos los meses entre desde y hasta.
CREATE TABLE IF NOT EXISTS fijos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concepto TEXT NOT NULL,
    monto REAL NOT NULL,                      -- 'Monto pagado'
    categoria TEXT,
    tipo TEXT NOT NULL DEFAULT 'Personal',
    pct REAL NOT NULL DEFAULT 1,
    tarjeta TEXT,                             -- si se cobra a una tarjeta (Auto -> Falabella)
    desde TEXT,
    hasta TEXT,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Hoja 'Fijos' J:Y (matriz Suscripciones x mes). Aquí: recurrentes con vigencia.
CREATE TABLE IF NOT EXISTS suscripciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    monto REAL NOT NULL,
    tarjeta TEXT,
    desde TEXT,
    hasta TEXT,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Hoja 'Cuotas': una fila por compra (el Excel tenía una fila por compra y mes).
-- Cuota N del periodo P = cuota_ref + meses(periodo_ref -> P). Solo existen N >= cuota_ref y N <= total_cuotas.
CREATE TABLE IF NOT EXISTS cuotas_planes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra TEXT NOT NULL,
    monto_total REAL NOT NULL DEFAULT 0,
    cuota_mensual REAL NOT NULL,
    total_cuotas INTEGER NOT NULL,
    periodo_ref TEXT NOT NULL,
    cuota_ref INTEGER NOT NULL,
    tarjeta TEXT,
    activo INTEGER NOT NULL DEFAULT 1
);

-- Cargos puntuales que se facturan a una tarjeta pero no son gasto propio (ej. los 80.833 de Santander en Dashboard!B31)
CREATE TABLE IF NOT EXISTS cargos_tarjeta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo TEXT NOT NULL,
    tarjeta TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    monto REAL NOT NULL
);
"""


def ruta_db() -> Path:
    return Path(os.environ.get("GASTOS_DB", DEFAULT_DB))


def conectar(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else ruta_db()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def seed_minimo(conn: sqlite3.Connection) -> None:
    """Valores por defecto si la base está vacía (sin datos personales)."""
    if conn.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
        conn.executemany("INSERT INTO config(clave, valor) VALUES (?, ?)", [("ingreso", 0), ("porc_ruben", 0.6)])
    if conn.execute("SELECT COUNT(*) FROM tarjetas").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO tarjetas(nombre, es_credito, orden) VALUES (?,?,?)",
            [("Débito", 0, 1), ("Transferencia", 0, 2), ("Otro", 0, 3)],
        )
    if conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        conn.execute("INSERT INTO categorias(nombre, presupuesto, orden) VALUES ('Otros', 0, 1)")
    conn.commit()
