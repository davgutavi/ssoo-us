"""provision, fase 6: el asistente (--menu), sin whiptail ni procesos hijos."""

import contextlib
import io
import os
import signal
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo


class TestPiezas(unittest.TestCase):

    def test_etiquetas(self):
        self.assertEqual(su.etiquetas('"extra-disks" "no-root"'), ["extra-disks", "no-root"])
        self.assertEqual(su.etiquetas(""), [])

    def test_locale_utf8(self):
        for entorno, esperada in (({"LC_ALL": "es_ES.UTF-8"}, "es_ES.UTF-8"),
                                  ({"LANG": "en_US.utf8"}, "en_US.utf8"),
                                  ({"LC_ALL": "C"}, "C.UTF-8"), ({}, "C.UTF-8")):
            with mock.patch.dict(os.environ, entorno, clear=True):
                self.assertEqual(su.locale_utf8(), esperada, entorno)

    def test_nombres(self):
        with mock.patch.object(su, "wt", return_value=(0, "")) as wt:
            self.assertTrue(su.Asistente.nombre_valido("server-1"))
            for nombre in ("-x", "a b", "x-", "a" * 64, "ñ"):
                self.assertFalse(su.Asistente.nombre_valido(nombre), nombre)
        self.assertEqual(wt.call_count, 5)


class TestLanzar(unittest.TestCase):

    def lanzar(self, argv, argumentos, contrasena=""):
        s = Silo(*argv)
        a = su.Asistente(s.o)
        a.pass_asistente = contrasena
        llamadas = []

        def call(orden, **kw):
            if orden[0] == "clear":
                return 0
            llamadas.append((orden, kw.get("env", {}), signal.getsignal(signal.SIGINT)))
            return 3

        with mock.patch.object(su, "wt", return_value=(0, "")) as wt, \
                mock.patch.object(su.subprocess, "call", call), \
                mock.patch.object(su, "pausa"), \
                contextlib.redirect_stdout(io.StringIO()) as salida:
            a.lanzar(argumentos)
        return wt, llamadas, salida.getvalue()

    def test_la_contrasena_no_va_en_la_orden(self):
        wt, llamadas, salida = self.lanzar(["--menu", "--dry-run", "--si", "--prefijo", "demo"],
                                           ["--ssh-pass", "-", "web"], "Secreta1")
        self.assertIn("provision --dry-run --si --prefijo demo --ssh-pass •••••• web",
                      wt.call_args[0][1])
        orden, entorno, manejador = llamadas[0]
        self.assertEqual(orden[2:], ["provision", "--dry-run", "--si", "--prefijo", "demo",
                                     "--ssh-pass", "-", "web"])
        self.assertNotIn("Secreta1", " ".join(orden))
        self.assertEqual(entorno["CI_PROVISION_SSH_PASS"], "Secreta1")
        # Mientras trabaja el hijo, Ctrl+C no se ignora (el hijo lo heredaría):
        # se atiende sin hacer nada
        self.assertNotIn(manejador, (signal.SIG_IGN, signal.SIG_DFL))
        self.assertIn("(el comando ha terminado con el código 3)", salida)

    def test_sin_contrasena_no_se_pasa_por_el_entorno(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CI_PROVISION_SSH_PASS", None)
            _, llamadas, _ = self.lanzar(["--menu"], ["server1"])
        self.assertNotIn("CI_PROVISION_SSH_PASS", llamadas[0][1])


if __name__ == "__main__":
    unittest.main()
