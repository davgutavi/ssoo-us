"""El despachador de subcomandos: --version, -h y los subcomandos."""

import re
import unittest

from comun import lanzar, su


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

    def test_diagnosis_no_implementado(self):
        # Hasta que se porte: un código que no usan ci-provision ni ci-diagnosis
        for resto in ((), ("server1",), ("-h",), ("--version",)):
            codigo, salida, errores = lanzar("diagnosis", *resto)
            self.assertEqual(codigo, su.NO_IMPLEMENTADO, resto)
            self.assertEqual(salida, "")
            self.assertRegex(errores, re.escape("ssoo-us diagnosis: todavía no está implementado"))

    def test_provision_no_implementado_tras_las_opciones(self):
        # Fase 1: las opciones se validan; lo que sigue aún no está portado
        codigo, salida, errores = lanzar("provision", "--dry-run", "server1")
        self.assertEqual(codigo, su.NO_IMPLEMENTADO)
        self.assertIn("ssoo-us provision: todavía no está implementado", errores)

    def test_no_implementado_no_choca_con_otros_codigos(self):
        ci_provision = set(range(10, 46)) | {70, 71}
        ci_diagnosis = {0, 1, 2}
        self.assertNotIn(su.NO_IMPLEMENTADO, ci_provision | ci_diagnosis)


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
