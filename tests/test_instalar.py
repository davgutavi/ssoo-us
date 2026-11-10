"""tools/instalar.sh: instala ssoo-us y ssoo-us-admin (en un directorio
temporal, con DESTINO, sin sudo)."""

import os
import subprocess
import tempfile
import unittest

from comun import RAIZ, SCRIPT, leer

INSTALAR = os.path.join(RAIZ, "tools", "instalar.sh")


@unittest.skipUnless(os.path.exists("/usr/bin/python3"), "sin /usr/bin/python3")
class TestInstalar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.destino = self.tmp.name
        for d in ("bin", "sbin"):
            os.mkdir(os.path.join(self.destino, d))

    def tearDown(self):
        self.tmp.cleanup()

    def instalar(self, *argumentos):
        p = subprocess.run(["bash", INSTALAR] + list(argumentos), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, DESTINO=self.destino))
        return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")

    def test_instala_y_actualiza(self):
        for vez, antes in ((1, "(no estaba)"), (2, "ssoo-us ")):
            codigo, salida, errores = self.instalar()
            self.assertEqual(codigo, 0, errores)
            self.assertIn("ssoo-us: " + antes, salida)
            ssoo_us = os.path.join(self.destino, "bin", "ssoo-us")
            admin = os.path.join(self.destino, "sbin", "ssoo-us-admin")
            self.assertEqual(leer(ssoo_us), leer(SCRIPT))
            self.assertEqual(leer(admin), leer(os.path.join(RAIZ, "tools", "ssoo-us-admin")))
            for f in (ssoo_us, admin):
                self.assertEqual(os.stat(f).st_mode & 0o777, 0o755, f)
            # Sin restos de la copia con otro nombre
            for d in ("bin", "sbin"):
                self.assertEqual(len(os.listdir(os.path.join(self.destino, d))), 1, vez)

    def test_quitar(self):
        self.instalar()
        codigo, salida, _ = self.instalar("--quitar")
        self.assertEqual(codigo, 0)
        self.assertEqual(os.listdir(os.path.join(self.destino, "bin")), [])
        self.assertEqual(os.listdir(os.path.join(self.destino, "sbin")), [])
        self.assertIn("Quitado:", salida)

    def test_sin_permiso(self):
        os.chmod(os.path.join(self.destino, "bin"), 0o555)
        try:
            codigo, _, errores = self.instalar()
        finally:
            os.chmod(os.path.join(self.destino, "bin"), 0o755)
        self.assertEqual(codigo, 1)
        self.assertIn("lánzalo con sudo", errores)

    def test_argumento_desconocido(self):
        self.assertEqual(self.instalar("--nada")[0], 2)


if __name__ == "__main__":
    unittest.main()
