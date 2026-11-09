"""provision, fase 1: opciones, validaciones y nombres derivados."""

import contextlib
import io
import os
import pty
import sys
import unittest

from comun import SCRIPT, entorno_sin_libvirt, su


def opciones(*argv, entorno=None):
    """Las opciones ya validadas, como las deja provision antes del entorno."""
    o = su.Opciones(dict({"HOME": "/home/alu0000"}, **(entorno or {})))
    o.usuario = "alu0000"
    su.analizar_opciones(o, list(argv))
    su.validar_opciones(o)
    su.calcular_derivados(o)
    return o


def codigo_de_error(*argv, entorno=None):
    try:
        opciones(*argv, entorno=entorno)
    except su.ErrorProvision as e:
        return e.codigo
    return None


class TestDecimal(unittest.TestCase):

    def test_ceros_a_la_izquierda(self):
        self.assertEqual(su.decimal("08"), 8)
        self.assertEqual(su.decimal("010"), 10)

    def test_solo_cifras(self):
        # int() de Python aceptaría todos estos; bash no
        for texto in ("", " 8", "8 ", "+8", "-8", "1_0", "١٢", "8\n", "0x10"):
            self.assertIsNone(su.decimal(texto), repr(texto))


class TestOpciones(unittest.TestCase):

    def test_valores_por_defecto(self):
        o = opciones("server1")
        self.assertEqual((o.maquina, o.ip, o.ram_mb, o.vcpus, o.tam_disco),
                         ("server1", "", 2048, 2, "40G"))
        self.assertEqual((o.vm_name, o.host_name), ("alu0000-server1", "server1"))
        self.assertEqual(o.disco_main, "/home/alu0000/imagenesMV/server1.qcow2")
        self.assertEqual((o.imagen, o.os_variant), ("noble", "ubuntu24.04"))
        self.assertEqual(o.base_img, "/home/alu0000/imagenesMV/noble-server-cloudimg-amd64.img")
        self.assertEqual(o.esperas, {"WAIT_TIMEOUT": 300, "POLL_SECS": 3, "GRACE_SECS": 5,
                                     "SHUTDOWN_TIMEOUT": 120})

    def test_prefijo_en_dominio_y_disco(self):
        o = opciones("--prefijo", "demo", "server1", "192.168.7.2")
        self.assertEqual((o.vm_name, o.host_name, o.ip), ("demo-server1", "server1", "192.168.7.2"))
        self.assertEqual(os.path.basename(o.disco_main), "demo-server1.qcow2")

    def test_disco_y_tam(self):
        o = opciones("--disco", "otro.qcow2", "--tam", "0020g", "server1")
        self.assertEqual(os.path.basename(o.disco_main), "otro.qcow2")
        self.assertEqual((o.tam_disco, o.tam_explicito), ("20G", True))

    def test_cluster(self):
        o = opciones("--gluster-cluster", "--discos-nodo", "7", "--ip-inicial", "020")
        self.assertEqual((o.ram_mb, o.vcpus, o.cluster_ip_inicial), (1024, 1, 20))
        self.assertEqual(o.unidades_cluster, su.UNIDADES_POSIBLES_NODO)
        self.assertEqual(o.vm_name, "")

    def test_imagenes(self):
        o = opciones("--imagen", "debian12", "server1")
        self.assertEqual((o.os_variant, os.path.basename(o.base_img)), ("debian12", "debian12.qcow2"))
        o = opciones("--glusterfs", "--imagen", "ubuntu-base", "base",
                     entorno={"CI_PROVISION_DIR_COMPARTIDO": "/compartido"})
        self.assertEqual(o.base_img, "/compartido/ubuntu-base.qcow2")
        o = opciones("--base", "mia.qcow2", "server1")
        self.assertEqual((o.base_img, o.imagen), ("/home/alu0000/imagenesMV/mia.qcow2", ""))

    def test_eliminar(self):
        o = opciones("--eliminar", "server1", "server2")
        self.assertEqual(o.nombres, ["server1", "server2"])

    def test_tras_doble_guion_todo_es_posicional(self):
        self.assertEqual(codigo_de_error("--", "--dry-run"), 20)

    def test_errores(self):
        casos = [
            ((), 10), (("a", "b", "c"), 10), (("--noexiste", "s"), 12), (("-",), 12),
            (("--ram=1", "s"), 12), (("s", "--ram"), 11), (("--ram", "", "s"), 11),
            (("--red", "--si", "s"), 11), (("s_1",), 20), (("a" * 64,), 20),
            (("alu0000-server1",), 20), (("ALU0000-server1",), 20),
            (("--prefijo", "demo", "demo-x"), 20), (("--prefijo", "-x", "s"), 20),
            (("--ram", "511", "s"), 13), (("--vcpus", "x", "s"), 13), (("--tam", "1.5G", "s"), 15),
            (("--disco", "a/b", "s"), 16), (("--base", ".oculto", "s"), 16),
            (("--red", "-red", "s"), 40), (("--red", "r d", "s"), 40),
            (("--ssh-pass", "ñ", "s"), 14), (("--imagen", "x", "s"), 10),
            (("--gluster-cluster", "--ip-inicial", "251"), 13),
            (("--gluster-cluster", "--discos-nodo", "2"), 13),
            (("--listar", "--menu"), 10), (("--listar", "--si", "--dry-run", "--prefijo", "d"), None),
        ]
        for argv, esperado in casos:
            self.assertEqual(codigo_de_error(*argv), esperado, argv)

    def test_variables_de_espera(self):
        self.assertEqual(codigo_de_error("s", entorno={"CI_PROVISION_POLL_SECS": "0"}), 13)
        self.assertEqual(codigo_de_error("s", entorno={"CI_PROVISION_GRACE_SECS": "0"}), None)
        # Las de nombre genérico no se leen
        self.assertEqual(codigo_de_error("s", entorno={"POLL_SECS": "x"}), None)

    def test_mensaje_con_la_orden(self):
        try:
            opciones()
        except su.ErrorProvision as e:
            self.assertIn("provision [opciones] MAQUINA [IP]", e.mensaje)


class TestContrasenaPorTeclado(unittest.TestCase):
    """--ssh-pass -: se lee de la terminal sin eco."""

    def lanzar_con_terminal(self, respuesta, *argv):
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(sys.executable, [sys.executable, SCRIPT, "provision"] + list(argv),
                      entorno_sin_libvirt())
        salida, enviada = b"", False
        while True:
            try:
                datos = os.read(fd, 4096)
            except OSError:
                break
            if not datos:
                break
            salida += datos
            if not enviada and b"Contrase" in salida:
                os.write(fd, respuesta + b"\n")
                enviada = True
        _, estado = os.waitpid(pid, 0)
        return os.WEXITSTATUS(estado), salida.decode("utf-8", "replace")

    def test_sin_eco(self):
        codigo, salida = self.lanzar_con_terminal(b"Secreta9", "--ssh-pass", "-", "server1")
        self.assertIn("Contraseña para administrador: ", salida)
        self.assertNotIn("Secreta9", salida)
        self.assertEqual(codigo, 38)   # siguió hasta libvirt

    def test_vacia(self):
        codigo, salida = self.lanzar_con_terminal(b"", "--ssh-pass", "-", "server1")
        self.assertEqual(codigo, 11)
        self.assertIn("La contraseña no puede estar vacía.", salida)

    def test_del_asistente_por_el_entorno(self):
        o = su.Opciones({"HOME": "/h"})
        os.environ["CI_PROVISION_SSH_PASS"] = "DelAsistente1"
        try:
            su.analizar_opciones(o, ["--ssh-pass", "-", "s"])
            self.assertEqual(o.ssh_pass, "DelAsistente1")
            self.assertNotIn("CI_PROVISION_SSH_PASS", os.environ)
        finally:
            os.environ.pop("CI_PROVISION_SSH_PASS", None)


class TestAyuda(unittest.TestCase):

    def test_ayuda_y_version_terminan_con_0(self):
        for opcion in ("-h", "--help", "--version"):
            with self.assertRaises(su.FinProvision) as c, \
                    contextlib.redirect_stdout(io.StringIO()) as salida:
                su.analizar_opciones(su.Opciones({"HOME": "/h"}), ["server1", opcion])
            self.assertTrue(salida.getvalue())
            self.assertEqual(c.exception.codigo, 0)

    def test_ayuda_completa(self):
        texto = su.texto_ayuda(su.Opciones({"HOME": "/h"}))
        self.assertIn("(por defecto\n                       10: .10 a .13)", texto)
        self.assertIn("/h/imagenesMV", texto)
        self.assertIn("/h/.ssh/id_rsa.pub", texto)


if __name__ == "__main__":
    unittest.main()
