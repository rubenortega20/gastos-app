# Análisis de `Orden_def.xlsx`

El libro es un **sistema de presupuesto mensual** con una hoja de captura (Movimientos), tres fuentes de gasto automático (Fijos, Suscripciones, Cuotas), un presupuesto por categoría y un Dashboard que compara todo para el mes elegido. La app replica esa lógica; esta nota explica cómo funciona el Excel y qué decisión se tomó en cada punto.

## Mapa de hojas

| Hoja | Rol | En la app |
|---|---|---|
| **Configuración** | Ingreso, % Rubén (nombre `Porc_Ruben` = 60%), listas desplegables (meses, categorías, tipos, tarjetas, %), gastos del depto, tabla de ahorro por mes | `config`, `categorias`, `tarjetas`, `depto_items`, `periodos` |
| **Movimientos** | Captura diaria (≈200 filas) | `movimientos` + pantalla *Agregar* |
| **Fijos** | Gastos que se repiten cada mes (arriendo, gasto común, auto, luz, agua, clases, CAE) + matriz de **suscripciones** por mes | `fijos`, `suscripciones` |
| **Cuotas** | Compras en cuotas (Orden 6 cuotas, Gym 12) y su saldo | `cuotas_planes` |
| **Presupuesto** | Presupuesto vs real por categoría, para el mes del Dashboard | `calc.presupuesto()` |
| **Dashboard** | Selector de mes (`B2`), KPIs, facturación por tarjeta, saldo cuenta | `calc.dashboard()` + pantalla *Resumen* |

## El patrón de un movimiento (hoja Movimientos, fila 4 en adelante)

| Col | Campo | Regla |
|---|---|---|
| A | Periodo | Primer día del mes (`mmm-yy`); el Excel no guarda el día |
| B | Descripción | Texto libre |
| C | Monto pagado | Número **o fórmula** (`=33550-101`, `=(24089+27990)`, `=-8752-8723*4`) |
| D | Categoría | Lista: las 13 categorías de Configuración |
| E | Tipo | `Personal` / `Compartido` |
| F | % mío | 100% si es personal, 60% si es compartido (lista: 100% / 60%) |
| G | Mi gasto | `= C × F` (en 17 filas se editó a mano: reembolsos `-21590`, cuotas `/14`, `×0`…) |
| H | Tarjeta | Falabella, Cencosud, Santander, Itau, Débito, Transferencia, Otro |

Datos actuales: 201 movimientos (ago-26: 48, sep-26: 113, oct-26: 40). Tarjetas más usadas: Falabella 124, Cencosud 42, Débito 34. Cerca del 92% de las filas tienen tipo y % coherentes (ver problemas).

**Cómo lo replica la app:** los mismos 7 campos, con las mismas listas; el *Tipo* decide el % (Personal 100%, Compartido el % de Configuración); el campo monto acepta las mismas operaciones; *Mi gasto* se calcula solo y se puede forzar a mano (`mi_gasto_manual`), conservando la nota con la fórmula original. Se agrega la **fecha** real y autocompletado: categoría, tipo y tarjeta se sugieren según el último gasto con la misma descripción.

## Cómo se calcula cada cosa

**Presupuesto (hoja Presupuesto, una fila por categoría)**
- *Presupuesto* (B): mezcla de fijos y fórmulas: Arriendo `660000×60%`, Auto `335140×60%`, Súper `250000×60%`, Gastos depto `=SUM(H7:H12)×60% + H13` (depto: GGCC, luz, agua, internet, bencina, TAG compartidos + internet de $12.990 personal), el resto números fijos.
- *Real* (F) = Gasto fijo (C: `SUMIFS(Fijos!F, categoría)`) + Movimientos (D: `SUMIFS(Movimientos!G, categoría, periodo)`) + Suscripciones/Cuotas (E).
- *Disponible* = Presupuesto − Real; *% usado* = Real / Presupuesto.
- La columna E está cableada a mano: solo la fila **Suscripciones** (total de la matriz de Fijos, `HLOOKUP`) y la fila **Deudas** (cuota del mes, `VLOOKUP`) la usan. En la app: las suscripciones siempre van a la categoría "Suscripciones" y las cuotas a "Deudas".

**Dashboard (mes en B2)**
- Ahorro objetivo = `VLOOKUP(mes, tabla de ahorro)` (500.000 hasta dic-26, 700.000 desde ene-27).
- **Ahorro real** = `MAX(0, ingreso − Σ real)`; **Disponible** = `MAX(0, ingreso − ahorro objetivo − Σ real)`; tasa = ahorro real / ingreso; meta = objetivo / ingreso.
- Cuotas mensuales y saldo de deudas: `VLOOKUP` a la tabla resumen de Cuotas.
- **Facturación por tarjeta**: `SUMIFS(Movimientos!C, tarjeta, mes)` (monto pagado completo, no "mi gasto") **más cargos sumados a mano**: Falabella + suscripciones + Auto (335.140); Cencosud + cuota Gym; Santander + cuota Orden + **80.833 sin detalle**.
- Saldo cuenta Itaú = `113.410 − Σ Mi gasto de Débito` (113.410 está escrito dentro de la fórmula).

**Cuotas.** Una fila por compra *y por mes*; la cuota actual es `=anterior+1`, restantes = total − actual, saldo = cuota × restantes. La app guarda **una fila por compra** (mes de referencia + n° de cuota) y calcula cualquier mes. Verificado contra los 11 meses de la tabla resumen.

## Verificación

La app, alimentada con tu Excel, reproduce exactamente los valores de oct-26: ahorro real $531.322, disponible $31.322, total disponible por categoría $26.453, saldo cuenta $113.410, cuotas $298.303, saldo deudas $771.254, facturación Falabella $846.674 / Cencosud $467.165 / Santander $350.028, y el presupuesto de cada una de las 13 categorías. Los tests están en `tests/test_paridad_excel.py`.

## Problemas detectados en el Excel

1. **Movimientos sin categoría no cuentan.** 28 filas (14%) no tienen categoría; `SUMIFS` por categoría las ignora. En sep-26 son **$70.730** que no aparecen en el Presupuesto: el Excel muestra ahorro real $213.962 y el real es $143.232. La app los muestra como "sin categoría", los descuenta del ahorro real (`ahorro_real_excel` conserva el cálculo original) y exige categoría al registrar.
2. **Datos hardcodeados en fórmulas**: 113.410 (saldo), 80.833 (Santander), 660000/335140/250000 (presupuestos). Ahora son datos editables (Meses, Otros cargos, Categorías).
3. **Referencias fijas a Cuotas**: `Dashboard!B30/B31` apuntan a `Cuotas!D5` y `D4` (filas de agosto), así que solo son correctas por coincidencia de valores. La app asigna tarjeta a cada compra en cuotas.
4. **Suscripciones solo llenas en oct-26** (nov-27 en adelante = 0), por lo que el Dashboard de otros meses subestima. En la app son recurrentes con vigencia (desde/hasta); iCloud (`=10990*0`) queda como pausada.
5. **Inconsistencias Tipo/%**: 2 filas "Compartido" al 100%, 1 "Personal" al 60%, 10 sin tipo, 1 sin %.
6. **Monto total de "Orden" cambia** entre filas (1.550.000 → 1.250.000) mientras la cuota se mantiene; la app guarda el último.
7. **Ediciones manuales de "Mi gasto"** (17 filas) rompen la regla `C×F` sin dejar registro; la app las marca (`mi_gasto_manual`) y guarda la fórmula en la nota.
8. **Internet aparece dos veces** en gastos del depto (22.990 compartido y 12.990 personal): se importó tal cual.
9. **Filas prellenadas vacías** (periodo sin datos en filas 205-207) y rangos que terminan en jun-27 (`VLOOKUP` de Cuotas) o en dic-27 (lista de meses) — la app no tiene límite de meses.

## Decisiones de diseño
- *Periodo* = mes `AAAA-MM`; el selector del Dashboard pasa a ser el selector de mes de la app.
- Los montos usan pesos con decimales internos (el 60% genera fracciones) y se muestran redondeados, igual que el formato `$ #,##0`.
- La app **no copia tus datos al repositorio**: `data/*.db` y `*.xlsx` están en `.gitignore`. Importas tu Excel localmente con `python -m app.importer`.
