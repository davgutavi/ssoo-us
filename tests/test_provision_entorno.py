"""provision, fase 2: red, IPs, ficheros cloud-init, orden de virt-install y
qué se puede borrar. Sin libvirt: solo las partes que no lo necesitan."""

import os
import stat
import tempfile
import unittest

from comun import su


class TestIPv4(unittest.TestCase):

    def test_validas(self):
        for ip in ("192.168.7.2", "0.0.0.0", "255.255.255.255", "192.168.007.020"):
            self.assertTrue(su.ipv4_valida(ip), ip)
        for ip in ("192.168.7", "192.168.7.256", "1.2.3.4.5", "hola", "1.2.3.1234", " 1.2.3.4",
                   "1.2.3.4\n", "١.٢.٣.٤"):
            self.assertFalse(su.ipv4_valida(ip), repr(ip))

    def test_ida_y_vuelta(self):
        self.assertEqual(su.entero_a_ip(su.ip_a_entero("192.168.007.020")), "192.168.7.20")

    def test_mascaras(self):
        self.assertEqual(su.mascara_a_prefijo("255.255.255.0"), 24)
        self.assertEqual(su.mascara_a_prefijo("255.255.240.0"), 20)
        # Como ci-provision: suma los bits de cada octeto, aunque no sean contiguos
        self.assertEqual(su.mascara_a_prefijo("255.0.255.0"), 16)
        self.assertIsNone(su.mascara_a_prefijo("255.255.255.1"))
        self.assertIsNone(su.mascara_a_prefijo("255..255.0"))

    def test_prefijo_por_clase(self):
        self.assertEqual(su.prefijo_por_clase("10.0.0.1"), 8)
        self.assertEqual(su.prefijo_por_clase("172.16.0.1"), 16)
        self.assertEqual(su.prefijo_por_clase("192.168.7.1"), 24)
        self.assertEqual(su.prefijo_por_clase("010.0.0.1"), 24)   # el texto, como bash


class TestXMLDeLaRed(unittest.TestCase):

    def test_red_del_manual(self):
        datos = su.analizar_xml_red(
            "<network><name>alu0000-red</name><forward mode='nat'/>"
            "<ip address='192.168.7.1' netmask='255.255.255.0'><dhcp>"
            "<range start='192.168.7.128' end='192.168.7.254'/>"
            "<host mac='52:54:00:00:00:01' name='x' ip='192.168.7.10'/>"
            "<host mac='52:54:00:00:00:02' name='sin-ip'/></dhcp></ip></network>")
        self.assertEqual(datos, {"address": "192.168.7.1", "netmask": "255.255.255.0",
                                 "prefix": "", "rangos": [("192.168.7.128", "192.168.7.254")],
                                 "reservas": ["192.168.7.10"]})

    def test_ipv6_y_ip_sin_atributos_no_cuentan(self):
        xml = ("<network><ip family='ipv6' address='fd00::1' prefix='64'><dhcp>"
               "<range start='fd00::100' end='fd00::1ff'/></dhcp></ip><ip/>"
               "<ip address=\"10.1.1.1\" prefix=\"16\"/></network>")
        self.assertEqual(su.analizar_xml_red(xml)["address"], "10.1.1.1")
        self.assertIsNone(su.analizar_xml_red("<network><ip family='ipv6' address='fd00::1'/>"
                                              "</network>"))
        self.assertIsNone(su.analizar_xml_red("no es XML"))


class TestRed(unittest.TestCase):

    def red(self, pasarela="192.168.7.1", rangos=(("192.168.7.128", "192.168.7.254"),),
            reservas=()):
        return su.RedIPv4("alu0000-red", pasarela, 24, rangos, reservas)

    def test_bloques_libres(self):
        self.assertEqual(self.red().bloques_libres(), ["  192.168.7.2 - 192.168.7.127"])
        self.assertEqual(self.red(reservas=["192.168.7.10"]).bloques_libres(),
                         ["  192.168.7.2 - 192.168.7.9", "  192.168.7.11 - 192.168.7.127"])
        self.assertEqual(self.red(rangos=[]).bloques_libres(), ["  192.168.7.2 - 192.168.7.254"])
        # Como mucho tres
        reservas = ["192.168.7.%d" % n for n in (5, 10, 15, 20)]
        self.assertEqual(len(self.red(reservas=reservas).bloques_libres()), 3)
        # Pasarela en .254 y DHCP en .1-.253: nada libre
        self.assertEqual(self.red("192.168.200.254", [("192.168.200.1", "192.168.200.253")])
                         .bloques_libres(), ["  (ninguna)"])

    def test_asignable(self):
        red = self.red(reservas=["192.168.7.10"])
        for ip, esperado in (("192.168.7.2", True), ("192.168.7.1", False), ("192.168.7.0", False),
                             ("192.168.7.255", False), ("192.168.7.128", False),
                             ("192.168.7.10", False), ("192.168.8.2", False)):
            self.assertEqual(red.asignable(su.ip_a_entero(ip)), esperado, ip)

    def test_primer_hueco_del_cluster(self):
        self.assertEqual(self.red().primer_hueco(4), 2)
        self.assertEqual(self.red(rangos=[("192.168.7.2", "192.168.7.127")]).primer_hueco(4), 128)
        self.assertIsNone(self.red(rangos=[("192.168.7.2", "192.168.7.254")]).primer_hueco(4))


class Silo:
    """Unas opciones con su silo en un directorio temporal."""

    def __init__(self, *argv):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = su.Opciones({"HOME": self.tmp.name})
        self.o.usuario = "alu0000"
        os.makedirs(self.o.silo)
        su.analizar_opciones(self.o, list(argv))
        su.validar_opciones(self.o)
        su.calcular_derivados(self.o)
        self.o.pubkey = "ssh-ed25519 AAAAC3Nza alu0000@portátil: 'casa'"
        self.o.red = su.RedIPv4("alu0000-red", "192.168.7.1", 24,
                                [("192.168.7.128", "192.168.7.254")])

    def ruta(self, nombre):
        return self.o.silo + "/" + nombre


class TestCloudInit(unittest.TestCase):

    def test_comillas(self):
        self.assertEqual(su.yaml_comillas("a'b: #c"), "'a''b: #c'")

    def test_permisos_y_contenido(self):
        s = Silo("--dry-run", "--ssh-pass", "x'y", "server1")
        su.generar_cloudinit(s.o, "alu0000-server1", "server1", "192.168.7.2", "normal")
        self.assertEqual(s.o.workdir, s.ruta("cloudinit-alu0000-server1.dry-run"))
        self.assertEqual(stat.S_IMODE(os.stat(s.o.workdir).st_mode), 0o700)
        for ruta in (s.o.user_data, s.o.meta_data, s.o.network_data):
            self.assertEqual(stat.S_IMODE(os.stat(ruta).st_mode), 0o600, ruta)
        with open(s.o.user_data, encoding="utf-8") as f:
            user_data = f.read()
        self.assertIn("      - 'ssh-ed25519 AAAAC3Nza alu0000@portátil: ''casa'''\n", user_data)
        self.assertIn("      password: 'x''y'\n", user_data)
        self.assertIn("ssh_pwauth: true\n", user_data)
        with open(s.o.network_data, encoding="utf-8") as f:
            self.assertIn("      - 192.168.7.2/24\n    routes:\n      - to: default\n"
                          "        via: 192.168.7.1\n", f.read())

    def test_sin_ip_no_hay_network_config(self):
        s = Silo("server1")
        su.generar_cloudinit(s.o, "alu0000-server1", "server1", "", "normal")
        self.assertEqual(s.o.network_data, "")
        self.assertEqual(sorted(os.listdir(s.o.workdir)), ["cip-meta.yaml", "cip-user.yaml"])
        self.assertEqual(s.o.dirs_creados, [s.o.workdir])

    def test_se_rehace_el_directorio(self):
        s = Silo("server1")
        os.makedirs(s.ruta("cloudinit-alu0000-server1"))
        with open(s.ruta("cloudinit-alu0000-server1/cip-net.yaml"), "w") as f:
            f.write("de antes")
        su.generar_cloudinit(s.o, "alu0000-server1", "server1", "", "normal")
        self.assertFalse(os.path.exists(s.ruta("cloudinit-alu0000-server1/cip-net.yaml")))

    def test_nodo_un_solo_write_files(self):
        s = Silo("--gluster-cluster", "--discos-nodo", "5")
        su.calcular_ips_cluster(s.o)
        su.generar_cloudinit(s.o, "alu0000-server2", "server2", "192.168.7.11", "nodo")
        with open(s.o.user_data, encoding="utf-8") as f:
            lineas = f.read().split("\n")
        self.assertEqual(lineas.count("write_files:"), 1)
        self.assertIn("      192.168.7.13 server4", lineas)
        self.assertEqual([l for l in lineas if "/etc/fstab" in l],
                         ["  - echo '/dev/%s /gluster%d xfs auto,async,nofail 0 0' >> /etc/fstab"
                          % (u, i + 1) for i, u in enumerate(("vdb", "vdc", "vdd"))])


class TestOrdenVirtInstall(unittest.TestCase):

    def test_texto(self):
        s = Silo("--no-virt-viewer", "server1")
        s.o.user_data, s.o.meta_data, s.o.os_variant = "/u.yaml", "/m.yaml", "ubuntu24.04"
        su.construir_comando(s.o, "alu0000-server1", 2048, 2, ["/d1.qcow2", "/d2.qcow2"])
        self.assertEqual(su.texto_comando(s.o), [
            "  virt-install \\", "    --quiet \\", "    --name alu0000-server1 \\",
            "    --ram 2048 \\", "    --vcpus 2 \\", "    --import \\",
            "    --disk path=/d1.qcow2,format=qcow2,bus=virtio \\",
            "    --disk path=/d2.qcow2,format=qcow2,bus=virtio \\",
            "    --os-variant ubuntu24.04 \\", "    --network network=alu0000-red \\",
            "    --cloud-init user-data=/u.yaml,meta-data=/m.yaml \\",
            "    --graphics none \\", "    --noautoconsole"])


class TestBorrables(unittest.TestCase):
    """filtrar_borrables, sobre un mapa de respaldos y de dominios vecinos dado."""

    def test_cadenas_y_vecinos(self):
        s = Silo("server1")
        noble, base, copia, nieta, suelta, usada = (
            s.ruta(n) for n in ("noble-server-cloudimg-amd64.img", "base.qcow2", "copia.qcow2",
                                "nieta.qcow2", "suelta.qcow2", "usada.qcow2"))
        s.o.respaldos = {noble: "", base: noble, copia: base, nieta: copia, suelta: "",
                         usada: base}
        s.o.disco_usado_por = {usada: "alu0000-otra"}
        borrables, conservados = su.filtrar_borrables(s.o, [noble, base, copia, suelta, usada])
        # nieta se conserva (no se pide): copia y base también, por la cadena
        self.assertEqual(borrables, [suelta])
        self.assertEqual(conservados, [
            "noble-server-cloudimg-amd64.img: es una imagen cloud de partida (nunca se borra)",
            "usada.qcow2: lo usa la máquina 'alu0000-otra'",
            "base.qcow2: es la imagen base de usada.qcow2, que se conserva",
            "copia.qcow2: es la imagen base de nieta.qcow2, que se conserva"])

    def test_toda_la_cadena_se_puede_borrar(self):
        s = Silo("server1")
        base, copia = s.ruta("base.qcow2"), s.ruta("copia.qcow2")
        s.o.respaldos = {base: "", copia: base}
        self.assertEqual(su.filtrar_borrables(s.o, [copia, base]), ([copia, base], []))


if __name__ == "__main__":
    unittest.main()
