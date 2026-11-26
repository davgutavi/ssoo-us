"""provision: si el alumno no tiene silo o red virtual, se le ofrece crearlos
(cada uno con su pregunta), como en las secciones 5.2 y 5.3 del manual. La
red es la primera 192.168.X.0/24 libre del servidor (libvirt simulado)."""

import contextlib
import io
import ipaddress
import os
import stat
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo
from test_provision_asistente import Asistido

ATRAS = su.ATRAS
RED_DE_OTRO = ("<network><name>otro-red</name><forward mode='nat'/>"
               "<ip address='192.168.%s.1' netmask='255.255.255.0'/></network>")


class LibvirtFalso:
    """virsh() con silos y redes en memoria; anota cada orden.

    inactivas: redes paradas (net-list solo las da con --all). fallan: órdenes
    que fallan siempre. redes_ocupadas: «192.168.X» en las que net-start falla
    (las usa algo que la búsqueda no ve)."""

    def __init__(self, redes=None, silos=None, fallan=(), inactivas=(), redes_ocupadas=()):
        self.redes = dict(redes or {})      # nombre → XML
        self.silos = dict(silos or {})      # nombre → [destino, activo]
        self.fallan = set(fallan)
        self.inactivas = set(inactivas)
        self.redes_ocupadas = set(redes_ocupadas)
        self.ordenes = []
        self.xml_definido = ""

    def __call__(self, *argumentos):
        orden, resto = argumentos[0], argumentos[1:]
        self.ordenes.append(argumentos)
        if orden in self.fallan:
            return 1, "", "error: %s ha fallado\n" % orden
        if orden == "net-list":
            todas = "--all" in resto
            return 0, "".join(n + "\n" for n in self.redes
                              if todas or n not in self.inactivas), ""
        if orden == "net-dumpxml":
            return (0, self.redes[resto[0]], "") if resto[0] in self.redes else (1, "", "no")
        if orden == "net-define":
            with open(resto[0], encoding="utf-8") as f:
                self.xml_definido = f.read()
            nombre = su.ET.fromstring(self.xml_definido).findtext("name")
            self.redes[nombre] = self.xml_definido
            self.inactivas.add(nombre)
            return 0, "", ""
        if orden == "net-start":
            if su.subred_de_xml(self.redes[resto[0]]).network_address.exploded.rsplit(".", 1)[0] \
                    in self.redes_ocupadas:
                return 1, "", "error: network is already in use by interface eth9\n"
            self.inactivas.discard(resto[0])
            return 0, "", ""
        if orden == "net-undefine":
            self.redes.pop(resto[0], None)
            return 0, "", ""
        if orden == "pool-list":
            return 0, "".join(n + "\n" for n in self.silos), ""
        if orden == "pool-info":
            if resto[0] not in self.silos:
                return 1, "", "error: failed to get pool '%s'\n" % resto[0]
            estado = "running" if self.silos[resto[0]][1] else "inactive"
            return 0, "Name:           %s\nState:          %s\n" % (resto[0], estado), ""
        if orden == "pool-dumpxml":
            return 0, ("<pool type='dir'><name>%s</name><target><path>%s</path></target></pool>"
                       % (resto[0], self.silos[resto[0]][0])), ""
        if orden == "pool-define-as":
            self.silos[resto[0]] = [resto[3], False]
            return 0, "", ""
        if orden == "pool-start":
            if self.silos[resto[0]][1]:
                return 1, "", "error: pool is already active\n"
            self.silos[resto[0]][1] = True
            return 0, "", ""
        return 0, "", ""

    def nombres(self):
        return [o[0] for o in self.ordenes]


class Base(unittest.TestCase):

    def opciones(self, *argv, con_silo=False):
        s = Silo(*(argv or ("server1",)))
        self.addCleanup(s.tmp.cleanup)
        if not con_silo:
            os.rmdir(s.o.silo)
        return s.o

    def llamar(self, funcion, o, libvirt, tty=True, respuesta="s\n", rutas=(), tty_salida=None):
        with contextlib.redirect_stdout(io.StringIO()) as salida, \
                contextlib.redirect_stderr(io.StringIO()) as errores, \
                mock.patch.object(su, "virsh", libvirt), \
                mock.patch.object(su, "rutas_del_servidor", return_value=list(rutas)), \
                mock.patch.object(su.sys.stdin, "isatty", return_value=tty), \
                mock.patch.object(su.sys.stdout, "isatty",
                                  return_value=tty if tty_salida is None else tty_salida), \
                mock.patch.object(su.sys.stdin, "readline", return_value=respuesta):
            funcion(o)
        return salida.getvalue(), errores.getvalue()


class TestSilo(Base):

    def test_lo_crea_si_acepta(self):
        o, lv = self.opciones(), LibvirtFalso()
        salida, errores = self.llamar(su.ofrecer_crear_silo, o, lv)
        self.assertIn("No tienes silo: el directorio %s" % o.silo, errores)
        self.assertIn("'alu0000-imagenesMV' (sección 5.2 del manual)", errores)
        self.assertTrue(os.path.isdir(o.silo))
        self.assertEqual(lv.ordenes, [("pool-list", "--all", "--name"),
                                      ("pool-info", "alu0000-imagenesMV"),
                                      ("pool-define-as", "alu0000-imagenesMV", "dir",
                                       "--target", o.silo),
                                      ("pool-start", "alu0000-imagenesMV"),
                                      ("pool-autostart", "alu0000-imagenesMV")])
        self.assertIn("✔ Silo creado: %s" % o.silo, salida)
        self.assertIn("✔ Registrado en libvirt como 'alu0000-imagenesMV' (activo y con arranque "
                      "automático)", salida)
        self.assertNotIn("AVISO", salida)
        su.exigir_silo(o)

    def test_si_dice_que_no_error_30(self):
        o, lv = self.opciones(), LibvirtFalso()
        self.llamar(su.ofrecer_crear_silo, o, lv, respuesta="n\n")
        self.assertFalse(os.path.exists(o.silo))
        self.assertEqual(lv.nombres(), [])
        with self.assertRaises(su.ErrorProvision) as e:
            su.exigir_silo(o)
        self.assertEqual(e.exception.codigo, 30)

    def test_con_si_sin_preguntar(self):
        o = self.opciones("--si", "server1")
        salida, _ = self.llamar(su.ofrecer_crear_silo, o, LibvirtFalso(), tty=False)
        self.assertIn("¿Lo creo ahora? [s/N] s   (--si)", salida)
        self.assertTrue(os.path.isdir(o.silo))

    def test_sin_terminal_o_con_dry_run_no_se_ofrece(self):
        # Hace falta terminal en la entrada y en la salida: con una sola, no
        for argv, tty, tty_salida in ((("server1",), False, None), (("server1",), True, False),
                                      (("server1",), False, True),
                                      (("--dry-run", "server1"), True, None)):
            o, lv = self.opciones(*argv), LibvirtFalso()
            self.assertEqual(self.llamar(su.ofrecer_crear_silo, o, lv, tty=tty,
                                         tty_salida=tty_salida), ("", ""), (argv, tty, tty_salida))
            self.assertFalse(os.path.exists(o.silo))

    def test_un_fichero_con_ese_nombre_no_se_toca(self):
        o = self.opciones()
        with open(o.silo, "w") as f:
            f.write("no es un directorio\n")
        self.assertEqual(self.llamar(su.ofrecer_crear_silo, o, LibvirtFalso()), ("", ""))
        with self.assertRaises(su.ErrorProvision):
            su.exigir_silo(o)

    @unittest.skipIf(os.geteuid() == 0, "root puede escribir en cualquier directorio")
    def test_si_no_se_puede_crear_el_directorio_error_30(self):
        o = self.opciones("--si", "server1")
        os.chmod(o.home, 0o555)
        self.addCleanup(os.chmod, o.home, stat.S_IRWXU)
        with self.assertRaises(su.ErrorProvision) as e:
            self.llamar(su.ofrecer_crear_silo, o, LibvirtFalso(), tty=False)
        self.assertEqual(e.exception.codigo, 30)
        self.assertIn("No se ha podido crear el silo %s: Permission denied" % o.silo,
                      e.exception.mensaje)
        self.assertIn("mkdir -p %s" % o.silo, e.exception.mensaje)

    def test_si_libvirt_no_deja_registrarlo_avisa_y_queda_el_directorio(self):
        o = self.opciones("--si", "server1")
        salida, _ = self.llamar(su.ofrecer_crear_silo, o,
                                LibvirtFalso(fallan={"pool-define-as"}), tty=False)
        self.assertTrue(os.path.isdir(o.silo))
        self.assertIn("AVISO: no se ha podido registrar el silo en libvirt (virsh pool-define-as: "
                      "error: pool-define-as ha fallado)", salida)
        self.assertIn("sección 5.2 del manual", salida)
        self.assertNotIn("Registrado", salida)

    def test_si_no_arranca_dice_que_esta_registrado_pero_parado(self):
        o = self.opciones("--si", "server1")
        lv = LibvirtFalso(fallan={"pool-start"})
        salida, _ = self.llamar(su.ofrecer_crear_silo, o, lv, tty=False)
        self.assertIn("AVISO: el silo 'alu0000-imagenesMV' está registrado en libvirt, pero no se "
                      "ha podido arrancar (virsh pool-start: error: pool-start ha fallado)", salida)
        self.assertIn("virsh pool-start alu0000-imagenesMV", salida)
        self.assertNotIn("✔ Registrado", salida)
        self.assertNotIn("no se ha podido registrar", salida)
        # Se intenta igual que arranque solo
        self.assertEqual(lv.nombres()[-1], "pool-autostart")

    def test_si_no_arranca_solo_lo_dice(self):
        o = self.opciones("--si", "server1")
        salida, _ = self.llamar(su.ofrecer_crear_silo, o, LibvirtFalso(fallan={"pool-autostart"}),
                                tty=False)
        self.assertIn("✔ Registrado en libvirt como 'alu0000-imagenesMV' (activo).", salida)
        self.assertIn("virsh pool-autostart alu0000-imagenesMV", salida)

    def test_silo_de_libvirt_que_ya_apunta_aqui_solo_se_arranca(self):
        for activo in (False, True):
            o = self.opciones("--si", "server1")
            lv = LibvirtFalso(silos={"alu0000-imagenesMV": [o.silo, activo]})
            salida, _ = self.llamar(su.ofrecer_crear_silo, o, lv, tty=False)
            self.assertNotIn("pool-define-as", lv.nombres())
            self.assertEqual(lv.silos["alu0000-imagenesMV"], [o.silo, True])
            # Si ya estaba activo, pool-start falla, pero no es un fallo
            self.assertIn("✔ Registrado en libvirt como 'alu0000-imagenesMV' (activo y con "
                          "arranque automático)", salida)
            self.assertNotIn("AVISO", salida)

    def test_silo_con_otro_nombre_que_apunta_aqui_se_usa_ese(self):
        o = self.opciones("--si", "server1")
        lv = LibvirtFalso(silos={"otro-imagenesMV": ["/home/otro/imagenesMV", True],
                                 "imagenesMV": [o.silo + "/", False]})
        salida, _ = self.llamar(su.ofrecer_crear_silo, o, lv, tty=False)
        self.assertIn("Ya tenías en libvirt el silo 'imagenesMV', que apunta ahí: se usa ese.",
                      salida)
        self.assertNotIn("pool-define-as", lv.nombres())
        self.assertTrue(lv.silos["imagenesMV"][1])
        self.assertIn("✔ Registrado en libvirt como 'imagenesMV'", salida)

    def test_silo_de_libvirt_que_apunta_a_otro_sitio_no_se_cambia(self):
        o = self.opciones("--si", "server1")
        lv = LibvirtFalso(silos={"alu0000-imagenesMV": ["/home/alu0000/otro", True]})
        salida, _ = self.llamar(su.ofrecer_crear_silo, o, lv, tty=False)
        self.assertTrue(os.path.isdir(o.silo))
        self.assertNotIn("pool-define-as", lv.nombres())
        self.assertNotIn("pool-start", lv.nombres())
        self.assertIn("AVISO: ya tienes en libvirt un silo llamado 'alu0000-imagenesMV', que "
                      "apunta a /home/alu0000/otro.", salida)


class TestRedLibre(unittest.TestCase):

    def red(self, texto):
        return ipaddress.ip_network(texto)

    def test_primera_libre(self):
        self.assertEqual(su.primera_red_libre([]), "192.168.1")
        self.assertEqual(su.primera_red_libre([self.red("192.168.1.0/24"),
                                               self.red("192.168.2.128/25"),
                                               self.red("10.0.0.0/8")]), "192.168.3")
        # Una /16 que las cubre todas, y una /23 que ocupa dos
        self.assertIsNone(su.primera_red_libre([self.red("192.168.0.0/16")]))
        self.assertEqual(su.primera_red_libre([self.red("192.168.0.0/23")]), "192.168.2")

    def test_subred_de_xml(self):
        self.assertEqual(su.subred_de_xml(RED_DE_OTRO % "7"), self.red("192.168.7.0/24"))
        self.assertEqual(su.subred_de_xml("<network><ip address='10.1.2.1' prefix='16'/></network>"),
                         self.red("10.1.0.0/16"))
        # Sin máscara ni prefijo, la de su clase
        self.assertEqual(su.subred_de_xml("<network><ip address='192.168.5.1'/></network>"),
                         self.red("192.168.5.0/24"))
        for xml in ("<network/>", "no es XML", "<network><ip address='x' prefix='24'/></network>",
                    "<network><ip address='10.0.0.1' prefix='40'/></network>"):
            self.assertIsNone(su.subred_de_xml(xml), xml)

    def test_rutas_del_servidor(self):
        salida = ("default via 10.0.0.1 dev eth0 proto dhcp\n"
                  "10.0.0.0/24 dev eth0 proto kernel scope link src 10.0.0.5\n"
                  "192.168.3.0/24 dev virbr3 proto kernel scope link src 192.168.3.1\n"
                  "172.16.5.9 via 10.0.0.1 dev eth0\n"
                  "blackhole 192.168.4.0/24\n"
                  "unreachable 192.168.5.0/24 table 100\n"
                  "local 192.168.3.1 dev virbr3 table local proto kernel scope host\n")
        with mock.patch.object(su, "ejecutar", return_value=(0, salida, "")) as ejecutar:
            self.assertEqual(su.rutas_del_servidor(),
                             [self.red("10.0.0.0/24"), self.red("192.168.3.0/24"),
                              self.red("172.16.5.9/32"), self.red("192.168.4.0/24"),
                              self.red("192.168.5.0/24"), self.red("192.168.3.1/32")])
        # De todas las tablas, no solo de la principal
        self.assertEqual(ejecutar.call_args[0][0], ["ip", "-4", "route", "show", "table", "all"])
        # Sin la orden ip, ninguna
        with mock.patch.object(su, "ejecutar", return_value=(None, "", "")):
            self.assertEqual(su.rutas_del_servidor(), [])

    def test_la_red_nueva_es_la_del_manual(self):
        datos = su.analizar_xml_red(su.xml_red_nueva("alu0000-red", "192.168.4"))
        self.assertEqual((datos["address"], datos["netmask"], datos["rangos"]),
                         ("192.168.4.1", "255.255.255.0", [("192.168.4.128", "192.168.4.254")]))
        xml = su.xml_red_nueva("alu0000-red", "192.168.4")
        self.assertIn("<forward mode='nat'/>", xml)
        self.assertNotIn("ipv6", xml)


class TestRed(Base):

    def otras(self, *xs):
        return {"otro%s-red" % x: RED_DE_OTRO % x for x in xs}

    def test_la_crea_en_la_primera_libre_si_acepta(self):
        o = self.opciones(con_silo=True)
        lv = LibvirtFalso(self.otras(1, 2))
        salida, errores = self.llamar(su.ofrecer_crear_red, o, lv,
                                      rutas=[ipaddress.ip_network("192.168.3.0/24")])
        self.assertIn("→ No tienes red virtual: buscando una red libre en el servidor…", salida)
        self.assertIn("No tienes red virtual. Se creará 'alu0000-red': NAT, 192.168.4.0/24", errores)
        self.assertIn("no el que sale de tu DNI", errores)
        self.assertEqual(lv.nombres()[-3:], ["net-define", "net-start", "net-autostart"])
        self.assertIn("<range start='192.168.4.128' end='192.168.4.254'/>", lv.xml_definido)
        self.assertIn("✔ Red virtual creada: alu0000-red (192.168.4.0/24, NAT", salida)
        self.assertNotIn("AVISO", salida)
        # El fichero temporal de la definición no se queda
        self.assertFalse(os.path.exists(lv.ordenes[lv.nombres().index("net-define")][1]))
        # Y es la que encuentra después provision
        with mock.patch.object(su, "virsh", lv):
            self.assertEqual(su.redes_del_usuario(o), ["alu0000-red"])

    def test_las_redes_paradas_de_otros_tambien_estan_ocupadas(self):
        o = self.opciones(con_silo=True)
        lv = LibvirtFalso(self.otras(1, 2), inactivas={"otro1-red"})
        _, errores = self.llamar(su.ofrecer_crear_red, o, lv)
        self.assertIn("NAT, 192.168.3.0/24", errores)

    def test_si_dice_que_no_no_crea_nada(self):
        o, lv = self.opciones(con_silo=True), LibvirtFalso()
        self.llamar(su.ofrecer_crear_red, o, lv, respuesta="n\n")
        self.assertNotIn("net-define", lv.nombres())

    def test_no_se_ofrece_si_ya_tiene_una_o_eligio_otra(self):
        casos = ((("server1",), {"ALU0000_net": RED_DE_OTRO % 9}),
                 (("--red", "otra", "server1"), {}))
        for argv, redes in casos:
            o, lv = self.opciones(*argv, con_silo=True), LibvirtFalso(redes)
            self.assertEqual(self.llamar(su.ofrecer_crear_red, o, lv), ("", ""), argv)
            self.assertNotIn("net-define", lv.nombres())

    def test_sin_terminal_o_con_dry_run_no_se_ofrece(self):
        for argv, tty, tty_salida in ((("server1",), False, None), (("server1",), True, False),
                                      (("--dry-run", "server1"), True, None)):
            o, lv = self.opciones(*argv, con_silo=True), LibvirtFalso()
            self.assertEqual(self.llamar(su.ofrecer_crear_red, o, lv, tty=tty,
                                         tty_salida=tty_salida), ("", ""))
            self.assertNotIn("net-define", lv.nombres())

    def test_sin_ninguna_red_libre_lo_dice_con_el_error_40(self):
        o, lv = self.opciones(con_silo=True), LibvirtFalso()
        with self.assertRaises(su.ErrorProvision) as e:
            self.llamar(su.ofrecer_crear_red, o, lv, rutas=[ipaddress.ip_network("192.168.0.0/16")])
        self.assertEqual(e.exception.codigo, 40)
        self.assertIn("no queda ninguna red 192.168.X.0/24 libre", e.exception.mensaje)
        self.assertNotIn("net-define", lv.nombres())

    def test_si_no_arranca_prueba_con_la_siguiente_libre(self):
        o = self.opciones("--si", "server1", con_silo=True)
        lv = LibvirtFalso(redes_ocupadas={"192.168.1", "192.168.2"})
        salida, _ = self.llamar(su.ofrecer_crear_red, o, lv, tty=False)
        self.assertEqual(lv.nombres().count("net-undefine"), 2)
        self.assertIn("AVISO: 192.168.1.0/24, 192.168.2.0/24 ya estaba en uso", salida)
        self.assertIn("✔ Red virtual creada: alu0000-red (192.168.3.0/24", salida)
        self.assertNotIn("alu0000-red", lv.inactivas)

    def test_si_ninguna_arranca_se_deshace_y_error_40(self):
        o = self.opciones("--si", "server1", con_silo=True)
        lv = LibvirtFalso(fallan={"net-start"})
        with self.assertRaises(su.ErrorProvision) as e:
            self.llamar(su.ofrecer_crear_red, o, lv, tty=False)
        self.assertEqual(e.exception.codigo, 40)
        self.assertIn("Se ha deshecho", e.exception.mensaje)
        self.assertIn("192.168.1.0/24, 192.168.2.0/24, 192.168.3.0/24, 192.168.4.0/24, "
                      "192.168.5.0/24", e.exception.mensaje)
        self.assertNotIn("se buscará otra", e.exception.mensaje)
        self.assertEqual(lv.nombres().count("net-start"), su.INTENTOS_RED)
        self.assertEqual(lv.nombres()[-1], "net-undefine")
        self.assertNotIn("alu0000-red", lv.redes)

    def test_si_no_se_puede_definir_error_40(self):
        o = self.opciones("--si", "server1", con_silo=True)
        with self.assertRaises(su.ErrorProvision) as e:
            self.llamar(su.ofrecer_crear_red, o, LibvirtFalso(fallan={"net-define"}), tty=False)
        self.assertEqual(e.exception.codigo, 40)
        self.assertIn("sección 5.3 del manual", e.exception.mensaje)

    def test_sin_arranque_automatico_avisa(self):
        o = self.opciones("--si", "server1", con_silo=True)
        salida, _ = self.llamar(su.ofrecer_crear_red, o, LibvirtFalso(fallan={"net-autostart"}),
                                tty=False)
        self.assertIn("✔ Red virtual creada", salida)
        self.assertIn("virsh net-autostart alu0000-red", salida)


class TestValidarEntorno(Base):
    """El orden: silo, clave, red. Al ver o eliminar máquinas no se ofrece nada."""

    def test_el_orden_es_silo_clave_red(self):
        o = self.opciones("server1", con_silo=True)
        orden = []

        class Parar(Exception):
            pass

        def anotar(que, parar=False):
            def f(*_):
                orden.append(que)
                if parar:
                    raise Parar()
            return f
        with mock.patch.object(su.shutil, "which", return_value="/usr/bin/x"), \
                mock.patch.object(su, "virsh_ok", return_value=True), \
                mock.patch.object(su, "ofrecer_crear_silo", anotar("silo")), \
                mock.patch.object(su, "ofrecer_crear_clave", anotar("clave")), \
                mock.patch.object(su, "comprobar_clave_publica", anotar("comprobar clave")), \
                mock.patch.object(su, "ofrecer_crear_red", anotar("red", parar=True)):
            with self.assertRaises(Parar):
                su.validar_entorno(o)
        self.assertEqual(orden, ["silo", "clave", "comprobar clave", "red"])

    def test_listar_sin_silo_sigue_siendo_error_30(self):
        o, lv = self.opciones("--listar"), LibvirtFalso()
        with mock.patch.object(su.shutil, "which", return_value="/usr/bin/x"):
            with self.assertRaises(su.ErrorProvision) as e:
                self.llamar(su.validar_entorno, o, lv)
        self.assertEqual(e.exception.codigo, 30)
        self.assertNotIn("pool-define-as", lv.nombres())

    def test_menu_no_lo_comprueba_lo_hace_el_asistente(self):
        o, lv = self.opciones("--menu"), LibvirtFalso()
        with mock.patch.object(su.shutil, "which", return_value="/usr/bin/x"):
            self.assertEqual(self.llamar(su.validar_entorno, o, lv), ("", ""))


class TestAsistente(Asistido):

    def test_sin_silo_ofrece_crearlo_antes_de_las_pantallas_de_crear(self):
        lv = LibvirtFalso()
        with mock.patch.object(su, "virsh", lv):
            vistas, lanzadas, _ = self.asistente(
                ["basica", True, None, "server1", "dhcp", "noble", [], True, "salir"],
                preparar=lambda s: os.rmdir(s.o.silo))
        confirmar = self.de_tipo(vistas, "confirmar")[0]["texto"]
        self.assertIn("No tienes silo: el directorio %s" % self.s.o.silo, confirmar)
        self.assertIn("✔ Silo creado", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertTrue(os.path.isdir(self.s.o.silo))
        self.assertIn("pool-define-as", lv.nombres())
        self.assertEqual([o for o, _ in lanzadas], [["server1"]])

    def test_sin_silo_atras_vuelve_al_menu_sin_crear_nada(self):
        vistas, lanzadas, _ = self.asistente(["basica", ATRAS, "salir"],
                                             preparar=lambda s: os.rmdir(s.o.silo))
        self.assertFalse(os.path.exists(self.s.o.silo))
        self.assertEqual([v["tipo"] for v in vistas], ["menu", "confirmar", "menu"])
        self.assertEqual(lanzadas, [])

    def test_sin_silo_ver_y_eliminar_dicen_que_no_hay_silo(self):
        vistas, lanzadas, _ = self.asistente(["listar", None, "eliminar", None, "todo", None,
                                              "salir"], preparar=lambda s: os.rmdir(s.o.silo))
        avisos = self.de_tipo(vistas, "aviso")
        self.assertEqual(len(avisos), 3)
        for aviso in avisos:
            self.assertIn("No tienes silo (%s)" % self.s.o.silo, aviso["texto"])
        self.assertEqual(lanzadas, [])
        self.assertFalse(os.path.exists(self.s.o.silo))

    def test_sin_red_ofrece_crearla(self):
        creadas = []

        def crear_red(o, base):
            creadas.append(base)
            return ["✔ Red virtual creada: alu0000-red (%s.0/24)" % base]
        vistas, lanzadas, _ = self.asistente(
            ["basica", True, None, "server1", "dhcp", "noble", [], True, "salir"],
            red_nueva="192.168.9", crear_red=crear_red)
        self.assertIn("Se creará 'alu0000-red': NAT, 192.168.9.0/24",
                      self.de_tipo(vistas, "confirmar")[0]["texto"])
        self.assertEqual(creadas, ["192.168.9"])
        self.assertIn("✔ Red virtual creada", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual([o for o, _ in lanzadas], [["server1"]])

    def test_sin_red_con_dry_run_no_la_ofrece(self):
        # Sin pantalla de crear la red: la primera es ya la del nombre (y ahí, salir)
        vistas, _, _ = self.asistente(["basica"], "--dry-run", red_nueva="192.168.9",
                                      crear_red=lambda o, base: self.fail("no debe crearla"))
        self.assertEqual(self.de_tipo(vistas, "confirmar"), [])
        self.assertEqual(vistas[-1]["tipo"], "texto")

    def test_sin_red_libre_avisa_y_vuelve_al_menu(self):
        vistas, lanzadas, _ = self.asistente(["basica", None, "salir"],
                                             red_nueva=su.ErrorProvision(40, "sin red libre"))
        self.assertIn("sin red libre", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual(lanzadas, [])

    def test_el_orden_es_silo_clave_red(self):
        with mock.patch.object(su, "virsh", LibvirtFalso()):
            vistas, _, _ = self.asistente(["basica", True, None, True, None, ATRAS, "salir"],
                                          clave=False, red_nueva="192.168.9",
                                          crear_red=lambda o, base: ["✔ Red virtual creada"],
                                          preparar=lambda s: os.rmdir(s.o.silo))
        preguntas = [v["texto"] for v in self.de_tipo(vistas, "confirmar")]
        self.assertEqual(len(preguntas), 3, preguntas)
        self.assertIn("No tienes silo", preguntas[0])
        self.assertIn("No tienes clave SSH", preguntas[1])
        self.assertIn("No tienes red virtual", preguntas[2])


if __name__ == "__main__":
    unittest.main()
