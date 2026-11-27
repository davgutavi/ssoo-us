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


class TestResumenDelCluster(unittest.TestCase):
    """ci-provision 3.0.1 escribía «(nodosBASE)» y «--eliminar ... server4BASE»
    con --base (${BASE_OPT:- …} vale BASE_OPT); lo corrigió la 3.0.2."""

    def resumen(self, *argv):
        s = Silo("--gluster-cluster", *argv)
        su.calcular_ips_cluster(s.o)
        s.o.imagen = "noble"
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            su.print_summary_cluster(s.o)
        return salida.getvalue()

    def test_sin_base(self):
        texto = self.resumen()
        self.assertIn("(nodos e imagen base):", texto)
        self.assertIn("--eliminar server1 server2 server3 server4 gluster-base\n", texto)

    def test_con_base(self):
        texto = self.resumen("--prefijo", "demo", "--base", "mibase.qcow2")
        self.assertIn("(nodos):", texto)
        self.assertIn("provision --prefijo demo --eliminar server1 server2 server3 server4\n", texto)
        self.assertRegex(texto, r"IMPORTANTE: no borres /\S*/imagenesMV/mibase\.qcow2\.\n")


class TestPermisosDeLaImagenBase(unittest.TestCase):
    """La imagen cloud que se descarga (o se copia del directorio compartido)
    queda en 0644 aunque la umask sea 002: con la máquina encendida, libvirt le
    pone el grupo kvm, el de todos los alumnos."""

    def preparar(self, compartida):
        s = Silo("server1")
        self.addCleanup(s.tmp.cleanup)
        o = s.o
        o.base_img = s.ruta(su.IMAGEN_NOBLE)
        o.base_img_url = "https://ejemplo/" + su.IMAGEN_NOBLE
        o.dir_compartido = os.path.join(s.tmp.name, "compartido")
        os.makedirs(o.dir_compartido)
        if compartida:
            ruta = os.path.join(o.dir_compartido, su.IMAGEN_NOBLE)
            with open(ruta, "w") as f:
                f.write("imagen\n")
            os.chmod(ruta, 0o664)   # cp conserva el modo del original
        return o

    def bajar(self, o):
        def descargar(o, url, fichero, silencioso=False):
            with open(fichero, "w") as f:   # con la umask del proceso, como wget
                f.write("imagen\n")
            return 0
        anterior = os.umask(0o002)
        try:
            with mock.patch.object(su, "descargar", descargar), \
                    mock.patch.object(su, "verificar_suma"), \
                    contextlib.redirect_stdout(io.StringIO()):
                su.descargar_imagen_base(o)
        finally:
            os.umask(anterior)
        return su.stat.S_IMODE(os.stat(o.base_img).st_mode)

    def test_descargada_con_umask_002(self):
        self.assertEqual(self.bajar(self.preparar(compartida=False)), 0o644)

    def test_copiada_del_directorio_compartido_con_umask_002(self):
        self.assertEqual(self.bajar(self.preparar(compartida=True)), 0o644)


class TestPermisosDeLaCopiaDeUbuntuBase(unittest.TestCase):
    """El disco que se copia de ubuntu-base (664 en los servidores: cp conserva
    el modo) queda en 0644, como los que crea qemu-img."""

    def test_copia_en_0644(self):
        s = Silo("server1")
        self.addCleanup(s.tmp.cleanup)
        origen = os.path.join(s.tmp.name, "ubuntu-base.qcow2")
        su.ejecutar(["qemu-img", "create", "-q", "-f", "qcow2", origen, "1G"])
        os.chmod(origen, 0o664)
        anterior = os.umask(0o002)
        try:
            su.crear_disco_copia(s.o, s.ruta("server1.qcow2"), origen, "1G")
        finally:
            os.umask(anterior)
        self.assertEqual(su.stat.S_IMODE(os.stat(s.ruta("server1.qcow2")).st_mode), 0o644)
