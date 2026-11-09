"""El arnés de aceptación (tests/aceptacion) y la convivencia de los fuentes."""

import ast
import os
import re
import unittest

from comun import RAIZ, leer

ACEPTACION = os.path.join(RAIZ, "tests", "aceptacion")


class TestArnes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.nombres = re.findall(r'^@test "(.*)" \{$',
                                 leer(os.path.join(ACEPTACION, "ci-provision.bats")), re.M)

    def test_153_tests(self):
        self.assertEqual(len(self.nombres), 153)
        self.assertEqual(len(set(self.nombres)), 153, "hay nombres de test repetidos")

    def test_cada_test_en_una_fase(self):
        fases = {}
        for linea in leer(os.path.join(ACEPTACION, "fases.txt")).splitlines():
            if not linea or linea.startswith("#"):
                continue
            fase, nombre = linea.split("\t")
            self.assertIn(fase, "0123456", linea)
            self.assertNotIn(nombre, fases, "repetido en fases.txt: %s" % nombre)
            fases[nombre] = fase
        self.assertEqual(set(fases), set(self.nombres))

    def test_envoltorio(self):
        envoltorio = os.path.join(ACEPTACION, "ssoo-us-provision")
        self.assertTrue(os.access(envoltorio, os.X_OK))
        self.assertIn('provision "$@"', leer(envoltorio))

    def test_helpers_usa_el_envoltorio(self):
        helpers = leer(os.path.join(ACEPTACION, "helpers.bash"))
        self.assertIn('SCRIPT="$ACEPTACION_DIR/ssoo-us-provision"', helpers)
        self.assertNotIn("ci-provision.sh\"", helpers)


class TestFuentes(unittest.TestCase):

    def test_ningun_nombre_definido_en_dos_fuentes(self):
        # Los fuentes comparten el espacio de nombres: un nombre repetido en
        # otro fuente sustituiría al primero sin avisar (p. ej. error() de
        # ci-provision y error() de ci-diagnosis)
        dueno = {}
        directorio = os.path.join(RAIZ, "src")
        for archivo in sorted(os.listdir(directorio)):
            if not archivo.endswith(".py"):
                continue
            arbol = ast.parse(leer(os.path.join(directorio, archivo)))
            for nodo in arbol.body:
                if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
                    nombres = [nodo.name]
                elif isinstance(nodo, ast.Assign):
                    nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
                else:
                    continue
                for nombre in nombres:
                    self.assertNotIn(nombre, dueno, "%s está en %s y en %s"
                                     % (nombre, dueno.get(nombre), archivo))
                    dueno[nombre] = archivo


if __name__ == "__main__":
    unittest.main()
