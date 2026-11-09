"""El archivo distribuible: al día respecto a src/, ejecutable y compatible
con Python 3.8."""

import ast
import os
import subprocess
import sys
import tempfile
import unittest

from comun import RAIZ, SCRIPT, leer


class TestDistribuible(unittest.TestCase):

    def test_al_dia_con_los_fuentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            salida = os.path.join(tmp, "ssoo-us")
            subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "build.py"), salida],
                           check=True, stdout=subprocess.DEVNULL)
            self.assertEqual(leer(salida), leer(SCRIPT),
                             "ssoo-us no está al día: ejecute python3 tools/build.py")

    def test_primera_linea(self):
        # El python3 del sistema, que es el que tiene PyYAML y el módulo libvirt
        self.assertEqual(leer(SCRIPT).split("\n", 1)[0], "#!/usr/bin/python3")

    def test_ejecutable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_sintaxis_de_python_3_8(self):
        ast.parse(leer(SCRIPT), feature_version=(3, 8))

    def test_todos_los_fuentes_en_el_orden(self):
        # Un fuente nuevo en src/ que no esté en ORDEN no llegaría al programa
        sys.path.insert(0, os.path.join(RAIZ, "tools"))
        try:
            import build
        finally:
            sys.path.pop(0)
        fuentes = sorted(n[:-3] for n in os.listdir(os.path.join(RAIZ, "src"))
                         if n.endswith(".py"))
        self.assertEqual(sorted(build.ORDEN), fuentes)
        self.assertEqual(build.ORDEN[0], "base")
        self.assertEqual(build.ORDEN[-1], "main")


if __name__ == "__main__":
    unittest.main()
