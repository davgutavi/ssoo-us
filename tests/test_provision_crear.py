"""provision, fase 3: confirmaciones y deshacer lo creado (sin libvirt)."""

import contextlib
import io
import os
import sys
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo


class TestConfirmar(unittest.TestCase):

    def test_con_si_no_pregunta(self):
        s = Silo("--si", "server1")
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            self.assertTrue(su.confirmar(s.o, "¿Eliminar?"))
        self.assertEqual(salida.getvalue(), "¿Eliminar? [s/N] s   (--si)\n")

    def test_sin_terminal_error_23(self):
        s = Silo("server1")
        with mock.patch.object(sys, "stdin", io.StringIO("s\n")):
            with self.assertRaises(su.ErrorProvision) as c:
                su.confirmar(s.o, "¿Eliminar?")
        self.assertEqual(c.exception.codigo, 23)
        self.assertIn("--si", c.exception.mensaje)

    def test_respuestas(self):
        s = Silo("server1")
        for texto, esperado in (("s\n", True), ("  Sí \n", True), ("SÍ\n", True), ("si\n", True),
                                ("n\n", False), ("\n", False), ("yes\n", False), ("s", False),
                                ("", False)):
            entrada = io.StringIO(texto)
            entrada.isatty = lambda: True
            with mock.patch.object(sys, "stdin", entrada), \
                    contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(su.confirmar(s.o, "¿Eliminar?"), esperado, repr(texto))


class TestDeshacer(unittest.TestCase):

    def test_solo_lo_de_esta_ejecucion(self):
        s = Silo("server1")
        for nombre in ("server1.qcow2", "otro.qcow2"):
            open(s.ruta(nombre), "w").close()
        su.generar_cloudinit(s.o, "alu0000-server1", "server1", "", "normal")
        s.o.discos_creados = [s.ruta("server1.qcow2"), s.ruta("server1-vdb.qcow2")]
        with contextlib.redirect_stderr(io.StringIO()) as errores:
            su.al_salir(s.o, 1, inesperado=True)
        self.assertEqual(sorted(os.listdir(s.o.silo)), ["otro.qcow2"])
        texto = errores.getvalue()
        self.assertIn("terminado de forma inesperada (código 1)", texto)
        self.assertIn("disco '%s' eliminado" % s.ruta("server1.qcow2"), texto)
        self.assertNotIn("server1-vdb", texto)     # no llegó a crearse
        self.assertIn("ficheros cloud-init", texto)

    def test_nada_que_deshacer(self):
        s = Silo("server1")
        with contextlib.redirect_stderr(io.StringIO()) as errores:
            su.al_salir(s.o, 21)
        self.assertEqual(errores.getvalue(), "")

    def test_creacion_completa_no_se_deshace(self):
        s = Silo("server1")
        open(s.ruta("server1.qcow2"), "w").close()
        s.o.discos_creados = [s.ruta("server1.qcow2")]
        s.o.creacion_completa = True
        with contextlib.redirect_stderr(io.StringIO()) as errores:
            su.al_salir(s.o, 130, interrumpido=True)
        self.assertTrue(os.path.exists(s.ruta("server1.qcow2")))
        self.assertIn("Interrumpido por el usuario.", errores.getvalue())
        self.assertIn("OJO: no se ha expulsado el medio", errores.getvalue())


if __name__ == "__main__":
    unittest.main()
