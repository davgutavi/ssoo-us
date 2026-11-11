"""tools/instalar.sh: instala ssoo-us y ssoo-us-admin (en un directorio
temporal, con DESTINO, sin sudo)."""

import os
import subprocess
import tempfile
import unittest

from comun import RAIZ, SCRIPT, leer, su

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

    def instalar(self, *argumentos, ssoo_us=None):
        entorno = dict(os.environ, DESTINO=self.destino)
        if ssoo_us:
            entorno["SSOO_US"] = ssoo_us
        p = subprocess.run(["bash", INSTALAR] + list(argumentos), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno)
        return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")

    def otro_ssoo_us(self, version):
        """Una copia de ssoo-us con otra línea y, si se da, otra versión."""
        texto = leer(SCRIPT)
        if version:
            texto = texto.replace('VERSION = "%s"' % su.VERSION, 'VERSION = "%s"' % version, 1)
        ruta = os.path.join(self.tmp.name, "ssoo-us")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto + "# otra\n")
        return ruta

    def test_instala_y_actualiza(self):
        for vez, mensaje in ((1, "ssoo-us: (no estaba) → ssoo-us "),
                             (2, "ssoo-us: ya está instalada esta misma versión (ssoo-us ")):
            codigo, salida, errores = self.instalar()
            self.assertEqual(codigo, 0, errores)
            self.assertIn(mensaje, salida)
            ssoo_us = os.path.join(self.destino, "bin", "ssoo-us")
            admin = os.path.join(self.destino, "sbin", "ssoo-us-admin")
            self.assertEqual(leer(ssoo_us), leer(SCRIPT))
            self.assertEqual(leer(admin), leer(os.path.join(RAIZ, "tools", "ssoo-us-admin")))
            for f in (ssoo_us, admin):
                self.assertEqual(os.stat(f).st_mode & 0o777, 0o755, f)
            # Sin restos de la copia con otro nombre
            for d in ("bin", "sbin"):
                self.assertEqual(len(os.listdir(os.path.join(self.destino, d))), 1, vez)

    def test_cada_instalacion_con_su_version(self):
        self.instalar()
        # Distinto y con la misma versión: no se instala
        codigo, _, errores = self.instalar(ssoo_us=self.otro_ssoo_us(None))
        self.assertEqual(codigo, 1)
        self.assertIn("Sube VERSION en src/base.py", errores)
        self.assertEqual(leer(os.path.join(self.destino, "bin", "ssoo-us")), leer(SCRIPT))
        # Con otra versión, sí
        codigo, salida, errores = self.instalar(ssoo_us=self.otro_ssoo_us("9.9.9-dev"))
        self.assertEqual(codigo, 0, errores)
        self.assertIn("→ ssoo-us 9.9.9-dev", salida)

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
