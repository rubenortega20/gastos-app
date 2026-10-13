"""Pruebas autocontenidas (sin datos personales). Ejecutar:  python -m unittest discover -s tests -v"""
import os
import unittest

from starlette.testclient import TestClient

from app import calc, db, expr, movs
from app import periodos as P
from app.main import crear_app


class TestExpr(unittest.TestCase):
    def test_formulas_del_excel(self):
        self.assertEqual(expr.evaluar("=33550-101"), 33449)
        self.assertEqual(expr.evaluar("=(24089+27990)"), 52079)
        self.assertEqual(expr.evaluar("=-8752-8723*4"), -43644)
        self.assertEqual(expr.evaluar("=25990*0"), 0)

    def test_formato_chileno(self):
        self.assertEqual(expr.evaluar("$ 33.550"), 33550)
        self.assertEqual(expr.evaluar("1.234,5"), 1234.5)

    def test_rechaza_codigo(self):
        for malo in ("__import__('os')", "abc", "", None, "2/0", "1+"):
            with self.assertRaises(ValueError):
                expr.evaluar(malo)


class TestPeriodos(unittest.TestCase):
    def test_aritmetica(self):
        self.assertEqual(P.sumar_meses("2026-11", 3), "2027-02")
        self.assertEqual(P.meses_entre("2026-08", "2026-12"), 4)
        self.assertEqual(P.de_fecha("2026-10-13"), "2026-10")
        self.assertEqual(P.etiqueta("2026-10"), "oct-26")


def base():
    c = db.conectar(":memory:")
    db.seed_minimo(c)
    c.execute("UPDATE config SET valor=2000000 WHERE clave='ingreso'")
    c.execute("DELETE FROM categorias")
    c.executemany("INSERT INTO categorias(nombre, presupuesto, aplica_pct, orden) VALUES (?,?,?,?)",
                  [("Arriendo", 600000, 1, 1), ("Súper", 100000, 0, 2), ("Deudas", 50000, 0, 3),
                   ("Suscripciones", 20000, 0, 4)])
    c.execute("INSERT OR REPLACE INTO tarjetas VALUES ('Visa', 1, 0)")
    c.execute("INSERT INTO periodos(periodo, ahorro_objetivo, saldo_inicial_cuenta) VALUES ('2026-10', 300000, 500000)")
    c.commit()
    return c


class TestCalculo(unittest.TestCase):
    def test_mi_gasto_y_presupuesto(self):
        c = base()
        movs.crear(c, {"monto": "10000", "categoria": "Súper", "tipo": "Compartido", "fecha": "2026-10-05", "tarjeta": "Visa"})
        movs.crear(c, {"monto": "=20000-5000", "categoria": "Súper", "fecha": "2026-10-06", "tarjeta": "Débito"})
        d = calc.dashboard(c, "2026-10")
        s = next(x for x in d["categorias"] if x["categoria"] == "Súper")
        self.assertAlmostEqual(s["real"], 10000 * 0.6 + 15000)
        arr = next(x for x in d["categorias"] if x["categoria"] == "Arriendo")
        self.assertAlmostEqual(arr["presupuesto"], 360000)          # 600000 * 60%
        self.assertAlmostEqual(d["saldo_cuenta"], 500000 - 15000)   # solo Débito, con "mi gasto"
        self.assertAlmostEqual(d["tarjetas"][0]["total"], 10000)    # facturación usa monto pagado completo

    def test_cuotas(self):
        c = base()
        c.execute("INSERT INTO cuotas_planes(compra,monto_total,cuota_mensual,total_cuotas,periodo_ref,cuota_ref,tarjeta) "
                  "VALUES ('TV',600,100,6,'2026-08',2,'Visa')")
        mes = lambda p: calc.cuotas_mes(c, p)
        self.assertEqual(mes("2026-07"), [])                         # antes de la referencia
        o = mes("2026-10")[0]
        self.assertEqual((o["cuota_actual"], o["cuotas_restantes"], o["saldo_pendiente"]), (4, 2, 200))
        self.assertEqual(mes("2026-12")[0]["saldo_pendiente"], 0)    # última cuota
        self.assertEqual(mes("2027-01"), [])                         # terminó
        d = calc.dashboard(c, "2026-10")
        self.assertEqual(d["cuotas_mensuales"], 100)
        self.assertEqual(next(x for x in d["categorias"] if x["categoria"] == "Deudas")["real"], 100)

    def test_sin_categoria_se_descuenta(self):
        c = base()
        movs.crear(c, {"monto": 50000, "fecha": "2026-10-01"}, estricto=False)
        d = calc.dashboard(c, "2026-10")
        self.assertEqual(d["sin_categoria"], 50000)
        self.assertEqual(d["ahorro_real"], d["ahorro_real_excel"] - 50000)

    def test_suscripciones_con_vigencia(self):
        c = base()
        c.execute("INSERT INTO suscripciones(nombre,monto,desde,hasta) VALUES ('A',1000,'2026-10','2026-11')")
        self.assertEqual(len(calc.suscripciones_mes(c, "2026-09")), 0)
        self.assertEqual(len(calc.suscripciones_mes(c, "2026-11")), 1)
        self.assertEqual(len(calc.suscripciones_mes(c, "2026-12")), 0)


class TestAPI(unittest.TestCase):
    def setUp(self):
        os.environ.pop("APP_TOKEN", None)
        self.app = crear_app(":memory:")
        c = self.app.state.conn
        c.execute("DELETE FROM categorias")
        c.executemany("INSERT INTO categorias(nombre, presupuesto, orden) VALUES (?,?,?)", [("Súper", 100000, 1), ("Ocio", 50000, 2)])
        c.commit()
        self.cli = TestClient(self.app)

    def test_rapido_aprende_de_la_descripcion(self):
        r = self.cli.post("/api/rapido", json={"monto": "10.000", "descripcion": "Jumbo", "categoria": "super",
                                                "tipo": "Compartido", "tarjeta": "debito", "fecha": "2026-10-02"})
        self.assertEqual(r.status_code, 201)
        r2 = self.cli.post("/api/rapido", data={"monto": "5000", "descripcion": "jumbo", "fecha": "2026-10-03"})  # formulario (Atajos)
        m = r2.json()["movimiento"]
        self.assertEqual((m["categoria"], m["tipo"], m["tarjeta"], m["pct"]), ("Súper", "Compartido", "Débito", 0.6))
        self.assertIn("Súper: quedan", r2.json()["mensaje"])

    def test_validaciones(self):
        self.assertEqual(self.cli.post("/api/movimientos", json={"monto": "abc"}).status_code, 400)
        self.assertEqual(self.cli.post("/api/movimientos", json={"monto": "1", "categoria": "Nada"}).status_code, 400)
        self.assertEqual(self.cli.delete("/api/movimientos/999").status_code, 404)

    def test_editar_tipo_recalcula_pct(self):
        m = self.cli.post("/api/movimientos", json={"monto": "1000", "categoria": "Ocio", "fecha": "2026-10-01"}).json()["movimiento"]
        n = self.cli.put(f"/api/movimientos/{m['id']}", json={"tipo": "Compartido"}).json()["movimiento"]
        self.assertAlmostEqual(n["mi_gasto"], 600)

    def test_token(self):
        os.environ["APP_TOKEN"] = "secreto"
        try:
            self.assertEqual(self.cli.get("/api/opciones").status_code, 401)
            self.assertEqual(self.cli.get("/api/opciones", headers={"Authorization": "Bearer secreto"}).status_code, 200)
            self.assertEqual(self.cli.get("/api/opciones?token=mal").status_code, 401)
        finally:
            os.environ.pop("APP_TOKEN", None)

    def test_crud_generico_y_renombre(self):
        r = self.cli.post("/api/r/fijos", json={"concepto": "Luz", "monto": "20000", "categoria": "Súper", "pct": "0.6", "tipo": "Compartido"})
        self.assertEqual(r.status_code, 201)
        self.cli.post("/api/movimientos", json={"monto": "1", "categoria": "Ocio", "fecha": "2026-10-01"})
        cid = next(c["id"] for c in self.cli.get("/api/r/categorias").json() if c["nombre"] == "Ocio")
        self.cli.put(f"/api/r/categorias/{cid}", json={"nombre": "Entretención"})
        self.assertEqual(self.cli.get("/api/movimientos?periodo=2026-10").json()["movimientos"][0]["categoria"], "Entretención")
        self.assertEqual(self.cli.post("/api/r/nada", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
