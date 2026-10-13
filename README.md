# Gastos

App web móvil (PWA) en Python que replica tu Excel `Orden_def.xlsx`: registro de movimientos, presupuesto vs real, fijos, suscripciones, cuotas y dashboard. Se usa desde el iPhone (ícono en la pantalla de inicio + Atajo de Apple) y guarda todo en un archivo SQLite.

> Una app nativa de iOS no se escribe en Python; la vía práctica es un backend Python + una web app instalable (PWA) + Atajos de iOS. Ver `docs/ATAJO_IPHONE.md`.

Análisis completo del Excel y sus fallas: [`docs/ANALISIS_EXCEL.md`](docs/ANALISIS_EXCEL.md).

## Inicio rápido
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export APP_TOKEN="una-clave-larga"            # protege la API
python -m app.importer ruta/a/Orden_def.xlsx   # carga tu Excel a data/gastos.db
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Abre `http://localhost:8000` (la primera vez pide el token).

## Estructura
```
app/calc.py       presupuesto, dashboard, cuotas (las fórmulas del Excel)
app/movs.py       alta/edición de movimientos, sugerencias, validaciones
app/importer.py   Excel -> SQLite
app/main.py       API (Starlette) + sirve la PWA
app/static/       interfaz móvil (HTML/CSS/JS sin build)
tests/            unitarias + paridad con el Excel
docs/             análisis del Excel y guía del Atajo de iPhone
```

## API principal (encabezado `Authorization: Bearer <APP_TOKEN>`)
| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/rapido` | Acceso rápido (Atajos): `monto` + opcionales; infiere categoría/tarjeta/tipo |
| GET/POST | `/api/movimientos?periodo=AAAA-MM` | Listar / crear; `PUT`/`DELETE /api/movimientos/{id}` |
| GET | `/api/dashboard?periodo=AAAA-MM` | KPIs, presupuesto, tarjetas |
| GET | `/api/opciones`, `/api/sugerir?descripcion=` | Listas y autocompletado |
| CRUD | `/api/r/{fijos,suscripciones,cuotas_planes,cargos_tarjeta,depto_items,categorias,tarjetas,periodos}` | Tablas auxiliares |
| GET/PUT | `/api/config` | `ingreso`, `porc_ruben` |

## Tests
```bash
python -m unittest discover -s tests -v
XLSX_ORIGINAL=ruta/Orden_def.xlsx python -m unittest tests.test_paridad_excel -v   # paridad con tu Excel
```

## Publicarlo para usarlo en el iPhone
Debe estar accesible por HTTPS desde el teléfono: tu propio servidor/Raspberry con Tailscale o Cloudflare Tunnel, o un hosting con volumen persistente (Fly.io, Railway, Render con disco) usando el `Dockerfile`. Monta `/data` en un volumen para no perder la base y define `APP_TOKEN`. Haz respaldos copiando `data/gastos.db`.

## Versionado en GitHub
Crea el repositorio **privado** (contiene tu lógica financiera). `.gitignore` ya excluye `data/*.db` y `*.xlsx`: tus datos no se suben. Sugerencia de ramas/tags: `v0.1.0` = réplica del Excel (esta versión).

## Roadmap sugerido
- v0.2 importar cartolas/CSV del banco, gráficos por mes y comparación histórica
- v0.3 reglas de categorización automáticas y presupuestos distintos por mes
- v0.4 múltiples usuarios (Rubén y pareja: división real de gastos compartidos)
