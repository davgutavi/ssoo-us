"""provision, fase 5: --listar, --eliminar y --eliminar-todo (libvirt simulado)."""

import contextlib
import io
import os
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo


def libvirt_simulado(dominios):
    """Un sustituto de virsh() con estos dominios: {nombre: (estado, [discos])}."""
    def virsh(*argumentos):
        orden, resto = argumentos[0], argumentos[1:]
        if orden == "list":
            return 0, "".join(d + "\n" for d in dominios) + "\n", ""
        if resto and resto[0] not in dominios:
            return 1, "", "error: failed to get domain '%s'\n" % resto[0]
        if orden == "dominfo":
            return 0, "Name: %s\n" % resto[0], ""
        if orden == "domstate":
            return 0, dominios[resto[0]][0] + "\n\n", ""
        if orden == "domblklist":
            filas = ["vd%s       %s" % (chr(ord("a") + i), f)
                     for i, f in enumerate(dominios[resto[0]][1])]
            return 0, " Target   Source\n------------------\n" + "\n".join(filas) + "\n\n", ""
        if orden == "domifaddr":
            return 0, "", ""
        return 0, "", ""
    return mock.patch.object(su, "virsh", virsh)


class TestTextos(unittest.TestCase):

    def test_rellenar_cuenta_caracteres(self):
        self.assertEqual(su.rellenar("en ejecución", 13), "en ejecución ")
        self.assertEqual(su.rellenar("abc", 2), "abc")

    def test_descripciones(self):
        s = Silo("--listar")
        s.o.respaldos = {s.ruta("server1.qcow2"): s.ruta("noble-server-cloudimg-amd64.img"),
                         s.ruta("base.qcow2"): s.ruta("debian12.qcow2"),
                         s.ruta("b.qcow2"): s.ruta("base.qcow2"),
                         s.ruta("a.qcow2"): s.ruta("base.qcow2"),
                         s.ruta("suelto.qcow2"): ""}
        self.assertEqual(su.descripcion_discos(s.o, []), "sin discos en el silo")
        self.assertEqual(
            su.descripcion_discos(s.o, [s.ruta("server1.qcow2"), s.ruta("server1-vdb.qcow2")]),
            "server1.qcow2 (copia de noble-server-cloudimg-amd64.img) + 1 discos extra")
        self.assertEqual(su.descripcion_disco_suelto(s.o, s.ruta("base.qcow2")),
                         "copia de debian12.qcow2; imagen base de: a.qcow2, b.qcow2")
        self.assertEqual(su.descripcion_disco_suelto(s.o, s.ruta("suelto.qcow2")), "disco suelto")
        self.assertIn("Debian 12", su.descripcion_disco_suelto(s.o, s.ruta("debian12.qcow2")))


class TestEliminar(unittest.TestCase):

    def test_plan(self):
        s = Silo("--eliminar", "server1", "ajena", "nada")
        for nombre in ("server1.qcow2", "server1-vdb.qcow2", "otra.qcow2"):
            open(s.ruta(nombre), "w").close()
        os.makedirs(s.ruta("cloudinit-alu0000-server1.dry-run"))
        s.o.respaldos = {}
        dominios = {"alu0000-server1": ("running", [s.ruta("server1.qcow2")]),
                    "alu0000-ajena": ("running", ["/otra/parte/ajena.qcow2"]),
                    "alu0000-otra": ("shut off", [s.ruta("otra.qcow2")])}
        with libvirt_simulado(dominios):
            plan = su.planificar_eliminacion(s.o, ["server1", "ajena", "nada"])
        self.assertEqual(plan.dominios, ["alu0000-server1"])
        self.assertEqual(plan.ficheros, [s.ruta("server1.qcow2"), s.ruta("server1-vdb.qcow2")])
        self.assertEqual(plan.dirs, [s.ruta("cloudinit-alu0000-server1.dry-run")])
        self.assertEqual(len(plan.conservados), 1)
        self.assertIn("máquina alu0000-ajena: sus discos no están en tu silo", plan.conservados[0])
        self.assertEqual(plan.sin_nada, ["nada"])

    def test_nada_que_eliminar_error_22(self):
        s = Silo("--si", "--eliminar", "server9")
        s.o.respaldos = {}
        with libvirt_simulado({}), self.assertRaises(su.ErrorProvision) as c:
            su.eliminar_maquinas(s.o, ["server9"])
        self.assertEqual(c.exception.codigo, 22)
        self.assertIn("'server9': no existe la máquina alu0000-server9", c.exception.mensaje)
        self.assertIn("provision --listar", c.exception.mensaje)

    def test_eliminar_todo_respeta_el_prefijo_y_las_imagenes_cloud(self):
        s = Silo("--si", "--prefijo", "demo", "--eliminar-todo")
        for nombre in ("demo-suelto.qcow2", "otro.qcow2", "debian12.qcow2"):
            open(s.ruta(nombre), "w").close()
        s.o.respaldos = {}
        with libvirt_simulado({}), contextlib.redirect_stdout(io.StringIO()) as salida:
            su.eliminar_todo(s.o)
        self.assertEqual(sorted(os.listdir(s.o.silo)), ["debian12.qcow2", "otro.qcow2"])
        self.assertIn("disco %s eliminado" % s.ruta("demo-suelto.qcow2"), salida.getvalue())


if __name__ == "__main__":
    unittest.main()
