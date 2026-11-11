"""provision: el asistente (--menu). Las pantallas de prompt_toolkit con una
entrada simulada, y el flujo de cada caso con unas pantallas falsas."""

import contextlib
import io
import os
import signal
import unittest
from unittest import mock

from comun import su
from test_provision_entorno import Silo

try:
    import prompt_toolkit  # noqa: F401
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
except ImportError:
    prompt_toolkit = None

ATRAS, SALIR = su.ATRAS, su.SALIR
ABAJO, TAB, INTRO, ESC, CTRL_C = "\x1b[B", "\t", "\r", "\x1b", "\x03"


@unittest.skipIf(prompt_toolkit is None, "sin prompt_toolkit")
class TestPantallas(unittest.TestCase):
    """Las pantallas de verdad, con teclas simuladas."""

    def pantalla(self, teclas, metodo, *args, **kw):
        entrada = create_pipe_input()
        try:
            entrada.send_text(teclas)
            p = su.PantallasPT("ssoo-us", entrada=entrada, salida=DummyOutput())
            return getattr(p, metodo)(*args, **kw)
        finally:
            entrada.close()

    OPCIONES = [("a", "Primera"), ("b", "Segunda"), ("c", "Tercera")]

    def test_menu(self):
        self.assertEqual(self.pantalla(ABAJO + INTRO, "menu", "¿Qué?", self.OPCIONES), "b")
        self.assertEqual(self.pantalla(" ", "menu", "¿Qué?", self.OPCIONES, inicial="c"), "c")
        # Tab lleva a «Atrás»; Tab otra vez, a «Aceptar» (la entrada resaltada)
        self.assertEqual(self.pantalla(ABAJO + TAB + INTRO, "menu", "¿Qué?", self.OPCIONES), ATRAS)
        self.assertEqual(self.pantalla(ABAJO + TAB + TAB + INTRO, "menu", "¿Qué?", self.OPCIONES),
                         "b")

    def test_esc_y_ctrl_c(self):
        self.assertEqual(self.pantalla(ESC, "menu", "¿Qué?", self.OPCIONES), ATRAS)
        self.assertEqual(self.pantalla(CTRL_C, "texto", "Nombre:", "x"), SALIR)

    def test_elegir_uno(self):
        # Intro elige la resaltada; el botón «Siguiente» devuelve la marcada
        self.assertEqual(self.pantalla(ABAJO + INTRO, "elegir_uno", "?", self.OPCIONES, "a"), "b")
        self.assertEqual(self.pantalla(ABAJO + TAB + TAB + INTRO, "elegir_uno", "?",
                                       self.OPCIONES, "a"), "a")
        self.assertEqual(self.pantalla(ABAJO + " " + TAB + TAB + INTRO, "elegir_uno", "?",
                                       self.OPCIONES, "a"), "b")

    def test_elegir_varios(self):
        self.assertEqual(self.pantalla(" " + ABAJO + ABAJO + " " + INTRO, "elegir_varios", "?",
                                       self.OPCIONES, []), ["a", "c"])
        self.assertEqual(self.pantalla(INTRO, "elegir_varios", "?", self.OPCIONES, ["b"]), ["b"])

    def test_texto(self):
        self.assertEqual(self.pantalla("\x7f" * 7 + "web" + INTRO, "texto", "Nombre:", "server1"),
                         "web")
        self.assertEqual(self.pantalla(INTRO, "texto", "Nombre:", "server1"), "server1")
        self.assertEqual(self.pantalla("Secreta1" + INTRO, "texto", "Contraseña:", oculto=True),
                         "Secreta1")
        self.assertEqual(self.pantalla(TAB + INTRO, "texto", "Nombre:", "x"), ATRAS)

    def test_atras_guarda_lo_escrito(self):
        # Con el botón y con Esc: lo escrito queda en texto_al_volver
        for teclas in ("yz" + TAB + INTRO, "yz" + ESC):
            entrada = create_pipe_input()
            try:
                entrada.send_text(teclas)
                p = su.PantallasPT("ssoo-us", entrada=entrada, salida=DummyOutput())
                self.assertEqual(p.texto("IP:", "x"), ATRAS)
                self.assertEqual(p.texto_al_volver, "xyz")
            finally:
                entrada.close()

    def test_confirmar_y_aviso(self):
        self.assertIs(self.pantalla(INTRO, "confirmar", "¿Adelante?"), True)
        self.assertEqual(self.pantalla(TAB + INTRO, "confirmar", "¿Adelante?"), ATRAS)
        self.assertIsNone(self.pantalla(INTRO, "aviso", "Hecho."))


class FalsasPantallas:
    """Responden lo que se les da, en orden, y anotan cada pantalla."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.vistas = []
        self.texto_al_volver = None

    def _r(self, tipo, texto, **datos):
        self.vistas.append(dict(datos, tipo=tipo, texto=texto))
        return self.respuestas.pop(0) if self.respuestas else SALIR

    def menu(self, texto, opciones, inicial=None, atras="Atrás", seguir="Aceptar"):
        return self._r("menu", texto, opciones=opciones, inicial=inicial)

    def elegir_uno(self, texto, opciones, marcada):
        return self._r("uno", texto, opciones=opciones, marcada=marcada)

    def elegir_varios(self, texto, opciones, marcadas):
        return self._r("varios", texto, opciones=opciones, marcadas=marcadas)

    def texto(self, pregunta, inicial="", oculto=False):
        """(ATRAS, "x"): vuelve atrás con «x» escrito en el campo."""
        r = self._r("texto", pregunta, inicial=inicial, oculto=oculto)
        self.texto_al_volver = None
        if isinstance(r, tuple):
            r, self.texto_al_volver = r
        return r

    def aviso(self, texto, boton="Aceptar"):
        self._r("aviso", texto)

    def confirmar(self, texto, si="Ejecutar", no="Atrás"):
        return self._r("confirmar", texto)


class Asistido(unittest.TestCase):
    """El asistente con pantallas falsas; lo que lanzaría se anota sin lanzarlo."""

    def asistente(self, respuestas, *argv, preparar=None, en_uso=None):
        s = Silo("--menu", *argv)
        self.addCleanup(s.tmp.cleanup)
        if preparar:
            preparar(s)
        p = FalsasPantallas(respuestas)
        lanzadas = []

        def call(orden, **kw):
            if orden[0] != "clear":
                lanzadas.append((orden[3:], kw.get("env", {})))
            return 0

        def comprobar_en_uso(o, ip, vm):
            if ip in (en_uso or ()):
                su.fallar(42, "Algo responde ya en la IP '%s'." % ip)

        red = su.RedIPv4("alu0000-red", "192.168.7.1", 24, [("192.168.7.128", "192.168.7.254")])
        with mock.patch.object(su, "red_del_usuario", return_value=red), \
                mock.patch.object(su, "comprobar_ip_en_uso", comprobar_en_uso), \
                mock.patch.object(su.subprocess, "call", call), \
                mock.patch.object(su, "pausa"), \
                contextlib.redirect_stdout(io.StringIO()) as salida:
            with self.assertRaises(su.FinProvision):
                su.Asistente(s.o, p).ejecutar()
        self.s = s
        return p.vistas, lanzadas, salida.getvalue()

    def de_tipo(self, vistas, tipo):
        return [v for v in vistas if v["tipo"] == tipo]


class TestMaquina(Asistido):

    def test_basica_por_defecto_ubuntu(self):
        vistas, lanzadas, salida = self.asistente(
            ["basica", "server1", "dhcp", "noble", [], True, "salir"])
        self.assertEqual([u["marcada"] for u in self.de_tipo(vistas, "uno")], ["dhcp", "noble"])
        self.assertEqual(len(self.de_tipo(vistas, "texto")), 1)   # con DHCP, sin paso de IP
        self.assertEqual([o for o, _ in lanzadas], [["server1"]])
        self.assertIn("→ %s server1" % su.orden_provision(), salida)
        self.assertIn("Sin cambios.", salida)

    def test_basica_debian_con_opciones(self):
        _, lanzadas, _ = self.asistente(
            ["basica", "server1", "dhcp", "debian12", ["extra-disks", "no-root"], True, "salir"])
        self.assertEqual(lanzadas[0][0],
                         ["--imagen", "debian12", "--extra-disks", "--no-root", "server1"])

    def test_server1_sugiere_la_ip_2_y_marca_los_discos(self):
        vistas, lanzadas, _ = self.asistente(
            ["extra", "server1", "fija", "192.168.7.2", "noble", ["extra-disks"], True, "salir"],
            "--si")
        self.assertEqual(self.de_tipo(vistas, "uno")[0]["marcada"], "fija")
        self.assertEqual(self.de_tipo(vistas, "texto")[1]["inicial"], "192.168.7.2")
        self.assertEqual(self.de_tipo(vistas, "varios")[0]["marcadas"], ["extra-disks"])
        self.assertEqual(lanzadas[0][0], ["--si", "--extra-disks", "server1", "192.168.7.2"])

    def test_atras_conserva_lo_escrito(self):
        # nombre → red → IP (se escribe la .30 y Atrás) → red (Atrás) → nombre →
        # red → IP, que sigue siendo la .30 → ... → confirmar (Atrás) → opciones
        vistas, lanzadas, _ = self.asistente(
            ["basica", "web", "fija", (ATRAS, "192.168.7.30"), ATRAS, "web2", "fija",
             "192.168.7.30", "noble", ["no-root"], ATRAS, ["limpiar"], True, "salir"])
        textos = self.de_tipo(vistas, "texto")
        self.assertEqual([t["inicial"] for t in textos],
                         ["server1", "192.168.7.2", "web", "192.168.7.30"])
        self.assertEqual(self.de_tipo(vistas, "uno")[1]["marcada"], "fija")
        self.assertEqual(self.de_tipo(vistas, "varios")[1]["marcadas"], ["no-root"])
        self.assertEqual(lanzadas[0][0], ["--limpiar", "web2", "192.168.7.30"])

    def test_atras_desde_el_primer_paso_vuelve_al_menu(self):
        vistas, lanzadas, _ = self.asistente(["basica", ATRAS, "salir"])
        self.assertEqual(lanzadas, [])
        menus = self.de_tipo(vistas, "menu")
        self.assertEqual(len(menus), 2)
        self.assertEqual(menus[1]["inicial"], "basica")   # vuelve a la misma entrada

    def test_no_confirmar_vuelve_al_ultimo_paso(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "s1", "dhcp", "noble", [], ATRAS, ["no-root"], True, "salir"])
        self.assertEqual(len(self.de_tipo(vistas, "confirmar")), 2)
        self.assertEqual(lanzadas[0][0], ["--no-root", "s1"])

    def test_nombre_no_valido(self):
        vistas, lanzadas, _ = self.asistente(["basica", "-h", None, ATRAS, "salir"])
        avisos = self.de_tipo(vistas, "aviso")
        self.assertIn("El nombre '-h' no es válido", avisos[0]["texto"])
        self.assertEqual(len(self.de_tipo(vistas, "texto")), 2)   # se vuelve a pedir
        self.assertEqual(lanzadas, [])

    def test_contrasena_fuera_de_la_orden(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "web", "dhcp", "noble", ["ssh-pass"], "Secreta1", True, "salir"], "--dry-run")
        orden, entorno = lanzadas[0]
        self.assertEqual(orden, ["--dry-run", "--ssh-pass", "-", "web"])
        self.assertEqual(entorno["CI_PROVISION_SSH_PASS"], "Secreta1")
        confirmacion = self.de_tipo(vistas, "confirmar")[0]["texto"]
        self.assertIn("--dry-run --ssh-pass •••••• web", confirmacion)
        self.assertNotIn("Secreta1", confirmacion)
        self.assertTrue(self.de_tipo(vistas, "texto")[1]["oculto"])

    def test_contrasena_vacia(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "web", "dhcp", "noble", ["ssh-pass"], "", None, ATRAS, [], True, "salir"])
        self.assertIn("Escribe una contraseña", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual(lanzadas[0][0], ["web"])

    def test_sin_contrasena_no_va_en_el_entorno(self):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("CI_PROVISION_SSH_PASS", None)
            _, lanzadas, _ = self.asistente(["basica", "web", "dhcp", "noble", [], True, "salir"])
        self.assertNotIn("CI_PROVISION_SSH_PASS", lanzadas[0][1])

    def test_ctrl_c_sale(self):
        _, lanzadas, salida = self.asistente(["basica", "web", SALIR])
        self.assertEqual(lanzadas, [])
        self.assertIn("Sin cambios.", salida)

    def test_prefijo_y_dry_run_en_lo_que_se_lanza(self):
        _, lanzadas, _ = self.asistente(["basica", "web", "dhcp", "noble", [], True, "salir"],
                                        "--dry-run", "--prefijo", "demo")
        self.assertEqual(lanzadas[0][0], ["--dry-run", "--prefijo", "demo", "web"])


class TestRed(Asistido):
    """DHCP o IP fija; con IP fija, la primera libre y el aviso en el mismo paso."""

    def test_ip_fija_propone_la_primera_libre(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "s1", "fija", "192.168.7.2", "noble", [], True, "salir"])
        ip = self.de_tipo(vistas, "texto")[1]
        self.assertEqual(ip["inicial"], "192.168.7.2")
        self.assertIn("IPs libres de tu red:\n  192.168.7.2 - 192.168.7.127", ip["texto"])
        self.assertEqual(lanzadas[0][0], ["s1", "192.168.7.2"])

    def test_atras_desde_la_ip_vuelve_a_la_red_sin_perderla(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "s1", "fija", (ATRAS, "192.168.7.20"), "fija", "192.168.7.20", "noble",
             [], True, "salir"])
        unos = self.de_tipo(vistas, "uno")
        self.assertEqual([u["marcada"] for u in unos[:2]], ["dhcp", "fija"])
        self.assertEqual(self.de_tipo(vistas, "texto")[2]["inicial"], "192.168.7.20")
        self.assertEqual(lanzadas[0][0], ["s1", "192.168.7.20"])

    def test_ip_que_no_vale_se_avisa_en_el_paso(self):
        vistas, lanzadas, _ = self.asistente(
            ["basica", "s1", "fija", "192.168.7.200", None, "10.0.0.5", None, "", None,
             "192.168.7.9", None, "192.168.7.10", "noble", [], True, "salir"],
            en_uso=["192.168.7.9"])
        avisos = [a["texto"] for a in self.de_tipo(vistas, "aviso")]
        self.assertIn("rango DHCP", avisos[0])
        self.assertIn("También puedes volver atrás y elegir DHCP.", avisos[0])
        self.assertIn("no pertenece a la red", avisos[1])
        self.assertIn("Escribe una IP", avisos[2])
        self.assertIn("Algo responde ya en la IP '192.168.7.9'", avisos[3])
        # El campo conserva lo último escrito
        self.assertEqual([t["inicial"] for t in self.de_tipo(vistas, "texto")[1:]],
                         ["192.168.7.2", "192.168.7.200", "10.0.0.5", "", "192.168.7.9"])
        self.assertEqual(lanzadas[0][0], ["s1", "192.168.7.10"])

    def test_dhcp_despues_de_escribir_la_ip(self):
        _, lanzadas, _ = self.asistente(
            ["basica", "s1", "fija", (ATRAS, "192.168.7.20"), "dhcp", "noble", [], True, "salir"])
        self.assertEqual(lanzadas[0][0], ["s1"])

    def test_server1_con_la_2_ocupada_propone_otra(self):
        red = su.RedIPv4("r", "192.168.7.1", 24, [("192.168.7.2", "192.168.7.99")])
        self.assertEqual(su.ip_sugerida(red, 2), "192.168.7.100")
        self.assertEqual(su.ip_sugerida(red), "192.168.7.100")
        red = su.RedIPv4("r", "192.168.7.1", 24, [("192.168.7.128", "192.168.7.254")])
        self.assertEqual(su.ip_sugerida(red, 2), "192.168.7.2")
        self.assertEqual(su.ip_sugerida(None, 2), "")


class TestOtrosCasos(Asistido):

    def test_cluster_elige_imagen_y_discos(self):
        vistas, lanzadas, _ = self.asistente(
            ["cluster", "debian12", ["discos-crea-entorno"], True, "salir"])
        self.assertEqual(self.de_tipo(vistas, "uno")[0]["marcada"], "noble")
        self.assertEqual(lanzadas[0][0], ["--gluster-cluster", "--imagen", "debian12",
                                          "--discos-nodo", "7"])

    def test_cluster_con_base_hecha(self):
        def con_base(s):
            open(su.disco_base_cluster(s.o), "w").close()
        vistas, lanzadas, _ = self.asistente(["cluster", "usar", ["limpiar"], True, "salir"],
                                             preparar=con_base)
        self.assertEqual(len(self.de_tipo(vistas, "uno")), 1)   # no pregunta la imagen
        self.assertEqual(lanzadas[0][0], ["--gluster-cluster", "--base", "gluster-base.qcow2",
                                          "--limpiar"])

    def test_base(self):
        vistas, lanzadas, _ = self.asistente(["base", "", None, ATRAS, "salir"])
        self.assertEqual(self.de_tipo(vistas, "texto")[0]["inicial"], "gluster-base")
        self.assertIn("El nombre '' no es válido", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual(lanzadas, [])

        _, lanzadas, _ = self.asistente(["base", "gb", "ubuntu-base", ["limpiar"], True, "salir"])
        self.assertEqual(lanzadas[0][0], ["--glusterfs", "--imagen", "ubuntu-base", "--limpiar",
                                          "gb"])

    def test_eliminar(self):
        with mock.patch.object(su, "dominios_propios",
                               return_value=["alu0000-server1", "alu0000-web"]), \
                mock.patch.object(su, "estado_dominio", return_value="apagada"):
            vistas, lanzadas, _ = self.asistente(["eliminar", [], None, ["web"], True, "salir"])
        varios = self.de_tipo(vistas, "varios")
        self.assertEqual(varios[0]["opciones"], [("server1", "server1  (apagada)"),
                                                 ("web", "web  (apagada)")])
        self.assertIn("No has marcado ninguna", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual(lanzadas[0][0], ["--eliminar", "web"])

    def test_eliminar_sin_maquinas(self):
        with mock.patch.object(su, "dominios_propios", return_value=[]):
            vistas, lanzadas, _ = self.asistente(["eliminar", None, "salir"])
        self.assertIn("No tienes máquinas", self.de_tipo(vistas, "aviso")[0]["texto"])
        self.assertEqual(lanzadas, [])

    def test_eliminar_todo(self):
        _, lanzadas, _ = self.asistente(["todo", True, "salir"])
        self.assertEqual(lanzadas[0][0], ["--eliminar-todo"])

    def test_salir_desde_el_menu(self):
        for respuesta in (ATRAS, SALIR, "salir"):
            _, lanzadas, salida = self.asistente([respuesta])
            self.assertEqual(lanzadas, [])
            self.assertIn("Sin cambios.", salida)


class TestLista(Asistido):

    def lista(self, *argv):
        s = Silo("--menu", *argv)
        self.addCleanup(s.tmp.cleanup)
        silo = s.o.silo
        discos = [silo + "/" + su.IMAGEN_NOBLE, silo + "/gluster-base-con-un-nombre-largo.qcow2"]
        with mock.patch.object(su, "dominios_propios", return_value=[s.o.prefijo_dominio + "-server1"]), \
                mock.patch.object(su, "estado_dominio", return_value="en ejecución"), \
                mock.patch.object(su, "ip_dominio", return_value="192.168.7.2"), \
                mock.patch.object(su, "discos_de_dominio", return_value=[silo + "/server1.qcow2"]), \
                mock.patch.object(su, "discos_sin_maquina", return_value=discos), \
                mock.patch.object(su, "respaldo_de", return_value=su.IMAGEN_NOBLE), \
                mock.patch.object(su, "copias_de", return_value=""), \
                mock.patch.object(su, "cargar_respaldos"):
            return su.Asistente(s.o, FalsasPantallas([])).filas_de_la_lista(), s

    def test_las_filas_caben(self):
        filas, s = self.lista()
        self.assertEqual([c for c, _ in filas],
                         ["m:%s-server1" % s.o.prefijo_dominio, "d:%s/%s" % (s.o.silo, su.IMAGEN_NOBLE),
                          "d:%s/gluster-base-con-un-nombre-largo.qcow2" % s.o.silo])
        for _, fila in filas:
            self.assertLessEqual(len(fila), su.ANCHO_LISTA, fila)
        self.assertEqual(filas[1][1], "%s  [imagen cloud] Ubuntu 24.04"
                         % su.IMAGEN_NOBLE)
        self.assertNotIn("imagen cloud imagen cloud", " ".join(f for _, f in filas))
        self.assertRegex(filas[0][1], r"^server1 +en ejecución +192\.168\.7\.2 +1 disco\(s\)$")

    def test_ficha_con_prefijo(self):
        s = Silo("--menu", "--prefijo", "demo")
        self.addCleanup(s.tmp.cleanup)
        p = FalsasPantallas([None])
        with mock.patch.object(su, "estado_dominio", return_value="apagada"), \
                mock.patch.object(su, "discos_de_dominio", return_value=[]):
            su.Asistente(s.o, p).ficha_maquina("demo-server1")
        self.assertIn("--prefijo demo --eliminar server1", p.vistas[0]["texto"])

    def test_recortar(self):
        self.assertEqual(su.recortar("abcdef", 4), "abc…")
        self.assertEqual(su.recortar("abc", 4), "abc")


class TestLanzar(unittest.TestCase):

    def test_ctrl_c_no_se_ignora_y_el_codigo(self):
        s = Silo("--menu")
        self.addCleanup(s.tmp.cleanup)
        manejadores = []

        def call(orden, **kw):
            if orden[0] != "clear":
                manejadores.append(signal.getsignal(signal.SIGINT))
            return 3

        with mock.patch.object(su.subprocess, "call", call), mock.patch.object(su, "pausa"), \
                contextlib.redirect_stdout(io.StringIO()) as salida:
            r = su.Asistente(s.o, FalsasPantallas([True])).lanzar(["web"])
        self.assertEqual(r, su.SIGUIENTE)
        # Mientras trabaja el hijo, Ctrl+C no se ignora (el hijo lo heredaría):
        # se atiende sin hacer nada
        self.assertNotIn(manejadores[0], (signal.SIG_IGN, signal.SIG_DFL))
        self.assertIn("(el comando ha terminado con el código 3)", salida.getvalue())

    def test_sin_prompt_toolkit_error_38(self):
        s = Silo("--menu")
        self.addCleanup(s.tmp.cleanup)
        with mock.patch.object(su, "prompt_toolkit_disponible", return_value=False), \
                mock.patch.dict(os.environ, {}):
            os.environ.pop("SSOO_US_ASISTENTE_GUION", None)
            with self.assertRaises(su.ErrorProvision) as e:
                su.asistente(s.o)
        self.assertEqual(e.exception.codigo, 38)
        self.assertIn("python3-prompt-toolkit", e.exception.mensaje)


class TestGuion(unittest.TestCase):
    """Las pantallas de los tests de aceptación (SSOO_US_ASISTENTE_GUION)."""

    def test_respuestas_y_registro(self):
        s = Silo("--menu")
        self.addCleanup(s.tmp.cleanup)
        guion = os.path.join(s.tmp.name, "guion")
        registro = os.path.join(s.tmp.name, "registro")
        with open(guion, "w") as f:
            f.write("b\n\na c\n<atrás>\nsi\n")
        p = su.PantallasGuion(guion, registro)
        opciones = [("a", "A"), ("b", "B"), ("c", "C")]
        self.assertEqual(p.menu("¿Qué?", opciones), "b")
        self.assertEqual(p.elegir_uno("Uno", opciones, "c"), "c")      # vacía: la marcada
        self.assertEqual(p.elegir_varios("Varios", opciones, []), ["a", "c"])
        self.assertEqual(p.texto("Nombre", "x"), ATRAS)
        self.assertIs(p.confirmar("¿Adelante?"), True)
        self.assertEqual(p.texto("Más"), SALIR)                        # sin más líneas
        with open(registro, encoding="utf-8") as f:
            lineas = f.read().splitlines()
        self.assertEqual(lineas[1], "elegir_uno: Uno | a=A ; b=B ; *c=C")
        self.assertEqual(lineas[3], "texto: Nombre | inicial=x")


if __name__ == "__main__":
    unittest.main()
