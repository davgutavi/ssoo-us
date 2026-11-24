"""provision: la clave pública del alumno. Si no tiene ninguna, se le ofrece
crearla (ssh-keygen de verdad, en un HOME temporal); si tiene la privada sin
la pública, se le dice cómo recuperarla, sin generar otra."""

import contextlib
import io
import os
import shutil
import stat
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo


@unittest.skipIf(shutil.which("ssh-keygen") is None, "sin ssh-keygen")
class TestCrearClave(unittest.TestCase):

    def silo(self, *argv):
        s = Silo(*(argv or ("server1",)))
        self.addCleanup(s.tmp.cleanup)
        return s.o

    def ofrecer(self, o, tty=True, respuesta="s\n"):
        # Primero la redirección: el isatty que cuenta es el de lo que queda en sys.stdout
        with contextlib.redirect_stdout(io.StringIO()) as salida, \
                contextlib.redirect_stderr(io.StringIO()) as errores, \
                mock.patch.object(su.sys.stdin, "isatty", return_value=tty), \
                mock.patch.object(su.sys.stdout, "isatty", return_value=tty), \
                mock.patch.object(su.sys.stdin, "readline", return_value=respuesta):
            su.ofrecer_crear_clave(o)
        return salida.getvalue(), errores.getvalue()

    def test_sin_ninguna_la_crea_si_acepta(self):
        o = self.silo()
        self.assertTrue(su.se_puede_crear_la_clave(o))
        salida, errores = self.ofrecer(o)
        self.assertIn("No tienes clave SSH (%s/.ssh/id_rsa)" % o.home, errores)
        self.assertIn("[s/N]", errores)
        self.assertIn("✔ Clave SSH creada", salida)
        privada = o.home + "/.ssh/id_rsa"
        self.assertEqual(stat.S_IMODE(os.stat(privada).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(o.home + "/.ssh").st_mode), 0o700)
        su.comprobar_clave_publica(o)
        self.assertTrue(o.pubkey.startswith("ssh-rsa "))
        # Sin contraseña: ssh-keygen -y la lee sin preguntar
        self.assertEqual(su.ejecutar(["ssh-keygen", "-y", "-P", "", "-f", privada])[0], 0)

    def test_si_dice_que_no_error_31(self):
        o = self.silo()
        salida, _ = self.ofrecer(o, respuesta="n\n")
        self.assertNotIn("creada", salida)
        self.assertFalse(os.path.exists(o.home + "/.ssh/id_rsa"))
        with self.assertRaises(su.ErrorProvision) as e:
            su.comprobar_clave_publica(o)
        self.assertEqual(e.exception.codigo, 31)

    def test_con_si_sin_preguntar(self):
        o = self.silo("--si", "server1")
        salida, _ = self.ofrecer(o, tty=False)
        self.assertIn("[s/N] s   (--si)", salida)
        self.assertTrue(os.path.isfile(o.home + "/.ssh/id_rsa.pub"))

    def test_sin_terminal_o_con_dry_run_no_hace_nada(self):
        for argv, tty in ((("server1",), False), (("--dry-run", "server1"), True)):
            o = self.silo(*argv)
            salida, errores = self.ofrecer(o, tty=tty)
            self.assertEqual((salida, errores), ("", ""))
            self.assertFalse(os.path.exists(o.home + "/.ssh"))

    def test_con_la_privada_no_se_ofrece_y_dice_como_recuperarla(self):
        o = self.silo()
        os.makedirs(o.home + "/.ssh")
        su.ejecutar(["ssh-keygen", "-q", "-t", "rsa", "-N", "", "-f", o.home + "/.ssh/id_rsa"])
        os.remove(o.home + "/.ssh/id_rsa.pub")
        self.assertFalse(su.se_puede_crear_la_clave(o))
        self.assertEqual(self.ofrecer(o), ("", ""))
        with self.assertRaises(su.ErrorProvision) as e:
            su.comprobar_clave_publica(o)
        self.assertEqual(e.exception.codigo, 31)
        self.assertIn("pero sí la privada", e.exception.mensaje)
        self.assertIn("ssh-keygen -y -f %s/.ssh/id_rsa > %s/.ssh/id_rsa.pub"
                      % (o.home, o.home), e.exception.mensaje)

    def test_con_otra_ruta_no_se_ofrece(self):
        o = self.silo()
        o.pubkey_path = o.home + "/otra.pub"
        self.assertFalse(su.se_puede_crear_la_clave(o))

    def test_si_ssh_keygen_falla(self):
        o = self.silo()
        with mock.patch.object(su, "ejecutar", return_value=(1, "", "algo ha ido mal")):
            with self.assertRaises(su.ErrorProvision) as e:
                su.crear_clave(o)
        self.assertEqual(e.exception.codigo, 31)
        self.assertIn("algo ha ido mal", e.exception.mensaje)


if __name__ == "__main__":
    unittest.main()
