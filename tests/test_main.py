"""El despachador de subcomandos: --version, -h y los subcomandos."""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from comun import SCRIPT, entorno_sin_libvirt, lanzar, su


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
            self.assertTrue(salida.startswith("Uso: ssoo-us SUBCOMANDO"), opcion)
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
        self.assertTrue(salida.startswith("Uso: ssoo-us diagnosis "))

    def test_diagnosis_opcion_desconocida(self):
        codigo, salida, errores = lanzar("diagnosis", "--listar")
        self.assertEqual((codigo, salida), (2, ""))
        self.assertIn("ssoo-us diagnosis: opción desconocida: --listar", errores)
        self.assertIn("Consulte la ayuda con: ssoo-us diagnosis -h", errores)

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


class TestNombreDelPrograma(unittest.TestCase):
    """Cómo se nombra en los mensajes: como lo escribió el alumno, o «ssoo-us»
    si lo encontró en el PATH (instalado en el servidor)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, "bin")
        os.mkdir(self.bin)
        self.silo = os.path.join(self.tmp.name, "imagenesMV")
        os.mkdir(self.silo)
        for d in (self.bin, self.silo):
            with open(os.path.join(d, "ssoo-us"), "w") as f:
                f.write("#!/usr/bin/python3\n")
            os.chmod(os.path.join(d, "ssoo-us"), 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def nombre(self, argv0, path):
        with mock.patch.object(su.sys, "argv", [argv0]), \
                mock.patch.dict(os.environ, {"PATH": path}):
            return su.nombre_programa()

    def test_instalado(self):
        # Desde el PATH, Python recibe la ruta completa
        self.assertEqual(self.nombre(os.path.join(self.bin, "ssoo-us"), self.bin), "ssoo-us")

    def test_instalado_con_un_enlace(self):
        enlaces = os.path.join(self.tmp.name, "local")
        os.mkdir(enlaces)
        os.symlink(os.path.join(self.bin, "ssoo-us"), os.path.join(enlaces, "ssoo-us"))
        self.assertEqual(self.nombre(os.path.join(enlaces, "ssoo-us"), enlaces), "ssoo-us")

    def test_una_copia_en_el_silo(self):
        anterior = os.getcwd()
        os.chdir(self.silo)
        try:
            # Aunque haya otro ssoo-us instalado: se nombra el que se ha lanzado
            self.assertEqual(self.nombre("./ssoo-us", self.bin), "./ssoo-us")
            self.assertEqual(self.nombre("./ssoo-us", "/usr/bin:/bin"), "./ssoo-us")
        finally:
            os.chdir(anterior)

    def test_por_la_entrada_estandar(self):
        with mock.patch.object(su.sys, "argv", ["-"]):
            self.assertEqual(su.ruta_del_programa(), "ssoo-us")
        self.assertEqual(self.nombre("-", "/usr/bin:/bin"), "ssoo-us")

    def test_de_verdad_desde_el_path(self):
        # El programa de verdad, instalado en un directorio del PATH
        with open(SCRIPT, "rb") as f:
            datos = f.read()
        with open(os.path.join(self.bin, "ssoo-us"), "wb") as f:
            f.write(datos)
        entorno = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        for argumentos, flujo, esperado in (
                (["provision", "-h"], "stdout", "  ssoo-us provision [opciones] MAQUINA [IP]"),
                (["--nada"], "stderr", "Consulte la ayuda con: ssoo-us -h")):
            p = subprocess.run(["ssoo-us"] + argumentos, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno)
            texto = getattr(p, flujo).decode("utf-8")
            self.assertIn(esperado, texto)
            self.assertNotIn(self.bin, texto)


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
