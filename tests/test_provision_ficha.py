"""provision: la ficha de la máquina (el resumen final, guardado en el silo) y
su borrado con --eliminar y --eliminar-todo."""

import contextlib
import io
import os
import stat
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo
from test_provision_gestion import libvirt_simulado


def resumen(o):
    print("-------------------------------------------")
    print("Máquina      : alu0000-server1")
    print("  (o con la contraseña: Secreta1)")


class TestFicha(unittest.TestCase):

    def silo(self, *argv):
        s = Silo(*argv)
        self.addCleanup(s.tmp.cleanup)
        s.o.argv = list(argv)
        return s

    def guardar(self, s, fichas):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            su.con_ficha(s.o, fichas, resumen)
        return salida.getvalue()

    def test_guarda_el_resumen(self):
        s = self.silo("--ssh-pass", "Secreta1", "server1")
        ruta = su.ruta_ficha(s.o, "server1")
        self.assertEqual(ruta, s.ruta("server1-ficha.txt"))
        salida = self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        # En pantalla, el resumen y dónde ha quedado
        self.assertTrue(salida.startswith("-----"))
        self.assertIn("Estos datos quedan guardados en %s" % ruta, salida)
        self.assertIn("cat %s" % ruta, salida)
        with open(ruta) as f:
            lineas = f.read().splitlines()
        self.assertEqual(lineas[0], "Ficha de la máquina alu0000-server1 "
                                    "(la escribe ssoo-us provision)")
        self.assertRegex(lineas[1], r"^Creada el \d\d-\d\d-\d{4} a las \d\d:\d\d con:$")
        # La orden, sin la contraseña de --ssh-pass (que sí va en el resumen)
        self.assertEqual(lineas[2], "  %s --ssh-pass •••••• server1" % su.orden_provision())
        self.assertIn("provision --listar", lineas[3])
        self.assertEqual(lineas[5:], ["-------------------------------------------",
                                      "Máquina      : alu0000-server1",
                                      "  (o con la contraseña: Secreta1)"])
        # Lleva contraseñas: solo para su dueño
        self.assertEqual(stat.S_IMODE(os.stat(ruta).st_mode), 0o600)
        self.assertTrue(su.es_ficha_nuestra(ruta))

    def test_ssh_pass_por_teclado_y_prefijo(self):
        # El asistente le pasa la contraseña por el entorno
        with mock.patch.dict(os.environ, {"CI_PROVISION_SSH_PASS": "Secreta1"}):
            s = self.silo("--prefijo", "demo", "--ssh-pass", "-", "web")
        ruta = su.ruta_ficha(s.o, "web")
        self.assertEqual(ruta, s.ruta("demo-web-ficha.txt"))
        self.guardar(s, [(ruta, "de la máquina demo-web")])
        with open(ruta) as f:
            texto = f.read()
        self.assertIn("--ssh-pass - web", texto)
        self.assertIn("provision --prefijo demo --listar", texto)

    def test_una_por_nodo(self):
        s = self.silo("--gluster-cluster")
        fichas = [(su.ruta_ficha(s.o, h), "del nodo alu0000-%s" % h) for h in ("server2", "server3")]
        salida = self.guardar(s, fichas)
        self.assertIn("una ficha por nodo", salida)
        self.assertIn("server2-ficha.txt  server3-ficha.txt", salida)
        for ruta, _ in fichas:
            self.assertTrue(su.es_ficha_nuestra(ruta))

    def test_no_pisa_un_fichero_del_alumno(self):
        s = self.silo("server1")
        ruta = su.ruta_ficha(s.o, "server1")
        with open(ruta, "w") as f:
            f.write("mis apuntes\n")
        salida = self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        self.assertIn("AVISO: no se guarda la ficha: ya existe %s" % ruta, salida)
        with open(ruta) as f:
            self.assertEqual(f.read(), "mis apuntes\n")
        # Ni un enlace
        os.remove(ruta)
        os.symlink(s.ruta("destino"), ruta)
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        self.assertFalse(os.path.exists(s.ruta("destino")))

    def test_sobrescribe_la_suya(self):
        s = self.silo("server1")
        ruta = su.ruta_ficha(s.o, "server1")
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        s.o.argv = ["--no-root", "server1"]
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        with open(ruta) as f:
            self.assertIn("--no-root server1", f.read())

    def test_no_ficha(self):
        s = self.silo("--no-ficha", "server1")
        ruta = su.ruta_ficha(s.o, "server1")
        salida = self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        self.assertNotIn("guardados", salida)
        self.assertFalse(os.path.exists(ruta))
        # La que quedara de otra máquina con ese nombre se quita; un fichero del
        # alumno, no
        s.o.no_ficha = False
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        s.o.no_ficha = True
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        self.assertFalse(os.path.exists(ruta))
        with open(ruta, "w") as f:
            f.write("mis apuntes\n")
        self.guardar(s, [(ruta, "de la máquina alu0000-server1")])
        self.assertTrue(os.path.exists(ruta))

    def test_no_ficha_solo_al_crear(self):
        for argv in (("--listar", "--no-ficha"), ("--eliminar", "server1", "--no-ficha")):
            with self.assertRaises(su.ErrorProvision) as e:
                Silo(*argv)
            self.assertEqual(e.exception.codigo, 10)


class TestEliminarFicha(unittest.TestCase):

    def silo_con_fichas(self, *argv):
        s = Silo(*argv)
        self.addCleanup(s.tmp.cleanup)
        s.o.argv, s.o.respaldos = [], {}
        for m, dominio in (("server1", "alu0000-server1"), ("viejo", "alu0000-viejo"),
                           ("otro", "otrousuario-otro")):
            with contextlib.redirect_stdout(io.StringIO()):
                su.guardar_fichas(s.o, [(su.ruta_ficha(s.o, m), "de la máquina " + dominio)], "")
        with open(s.ruta("apuntes-ficha.txt"), "w") as f:
            f.write("mío\n")
        return s

    def test_eliminar_la_borra_con_la_maquina(self):
        s = self.silo_con_fichas("--si", "--eliminar", "server1")
        open(s.ruta("server1.qcow2"), "w").close()
        dominios = {"alu0000-server1": ("shut off", [s.ruta("server1.qcow2")])}
        with libvirt_simulado(dominios), contextlib.redirect_stdout(io.StringIO()) as salida:
            su.eliminar_maquinas(s.o, ["server1"])
        self.assertIn("  ficha    %s" % s.ruta("server1-ficha.txt"), salida.getvalue())
        self.assertIn("✔ ficha %s eliminada" % s.ruta("server1-ficha.txt"), salida.getvalue())
        self.assertEqual(sorted(os.listdir(s.o.silo)),
                         ["apuntes-ficha.txt", "otro-ficha.txt", "viejo-ficha.txt"])

    def test_solo_la_ficha_tambien_se_elimina(self):
        s = self.silo_con_fichas("--si", "--eliminar", "viejo", "apuntes")
        with libvirt_simulado({}), contextlib.redirect_stdout(io.StringIO()):
            su.eliminar_maquinas(s.o, ["viejo", "apuntes"])
        self.assertFalse(os.path.exists(s.ruta("viejo-ficha.txt")))
        self.assertTrue(os.path.exists(s.ruta("apuntes-ficha.txt")))

    def test_eliminar_todo_borra_las_suyas(self):
        s = self.silo_con_fichas("--si", "--eliminar-todo")
        with libvirt_simulado({}), contextlib.redirect_stdout(io.StringIO()):
            su.eliminar_todo(s.o)
        # Las de sus máquinas (aunque ya no existan); ni la de otro prefijo ni
        # un fichero suyo que se llame parecido
        self.assertEqual(sorted(os.listdir(s.o.silo)), ["apuntes-ficha.txt", "otro-ficha.txt"])


if __name__ == "__main__":
    unittest.main()
