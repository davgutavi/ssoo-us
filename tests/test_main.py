"""El despachador de subcomandos: --version, -h y los subcomandos."""

import os
import tempfile
import unittest

from comun import entorno_sin_libvirt, lanzar, su


class TestDespachador(unittest.TestCase):

    def test_version(self):
        codigo, salida, errores = lanzar("--version")
        self.assertEqual(codigo, 0)
        self.assertRegex(salida, r"^ssoo-us \d+\.\d+\.\d+(-dev)?\n$")
        self.assertEqual(salida, "ssoo-us %s\n" % su.VERSION)
        self.assertEqual(errores, "")

    def test_ayuda(self):
        for opcion in ("-h", "--help", "--ayuda"):
            codigo, salida, errores = lanzar(opcion)
            self.assertEqual(codigo, 0, opcion)
            self.assertTrue(salida.startswith("Uso: ./ssoo-us SUBCOMANDO"), opcion)
            for subcomando in su.SUBCOMANDOS:
                self.assertIn("  %s " % subcomando, salida)
            self.assertEqual(errores, "")

    def test_ayuda_en_80_columnas(self):
        for linea in su.USO.splitlines():
            self.assertLessEqual(len(linea), 80, linea)

    def test_sin_argumentos(self):
        codigo, salida, errores = lanzar()
        self.assertEqual(codigo, 2)
        self.assertEqual(salida, "")
        self.assertIn("Uso:", errores)

    def test_subcomando_desconocido(self):
        codigo, salida, errores = lanzar("provisionar")
        self.assertEqual(codigo, 2)
        self.assertEqual(salida, "")
        self.assertIn("subcomando desconocido: provisionar", errores)
        self.assertIn("provision, diagnosis", errores)

    def test_opcion_desconocida(self):
        codigo, _, errores = lanzar("--listar")
        self.assertEqual(codigo, 2)
        self.assertIn("opción desconocida: --listar", errores)

    def test_diagnosis_version_y_ayuda(self):
        self.assertEqual(lanzar("diagnosis", "--version"), (0, "ssoo-us %s\n" % su.VERSION, ""))
        codigo, salida, _ = lanzar("diagnosis", "-h")
        self.assertEqual(codigo, 0)
        self.assertTrue(salida.startswith("Uso: ./ssoo-us diagnosis "))

    def test_diagnosis_opcion_desconocida(self):
        codigo, salida, errores = lanzar("diagnosis", "--listar")
        self.assertEqual((codigo, salida), (2, ""))
        self.assertIn("ssoo-us diagnosis: opción desconocida: --listar", errores)
        self.assertIn("Consulte la ayuda con: ./ssoo-us diagnosis --ayuda", errores)

    def test_diagnosis_sin_el_modulo_libvirt(self):
        # Un libvirt que no se puede importar, aquí y en un servidor que sí lo tiene
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "libvirt.py"), "w") as f:
                f.write("raise ImportError('simulado')\n")
            codigo, salida, errores = lanzar("diagnosis", "server1",
                                             entorno=dict(os.environ, PYTHONPATH=d))
        self.assertEqual((codigo, salida), (2, ""))
        self.assertIn("ssoo-us diagnosis: falta el módulo libvirt de Python", errores)

    def test_provision_llega_a_libvirt(self):
        codigo, _, errores = lanzar("provision", "--dry-run", "server1",
                                    entorno=entorno_sin_libvirt())
        self.assertEqual(codigo, 38)
        self.assertIn("ERROR [38] No se puede conectar con libvirt", errores)


class TestEjecutar(unittest.TestCase):

    def test_lc_all_c_y_uri_del_sistema(self):
        codigo, salida, _ = su.ejecutar(["/bin/sh", "-c",
                                         'echo "$LC_ALL $LIBVIRT_DEFAULT_URI"'])
        self.assertEqual(codigo, 0)
        self.assertEqual(salida, "C qemu:///system\n")

    def test_sin_teclado(self):
        # Sin entrada, la orden lee /dev/null: no se queda esperando
        codigo, salida, _ = su.ejecutar(["/bin/cat"], timeout=5)
        self.assertEqual((codigo, salida), (0, ""))

    def test_con_entrada(self):
        self.assertEqual(su.ejecutar(["/bin/cat"], entrada="hola\n")[:2], (0, "hola\n"))

    def test_orden_que_no_existe(self):
        self.assertEqual(su.ejecutar(["/no/existe"]), (None, "", ""))


if __name__ == "__main__":
    unittest.main()
