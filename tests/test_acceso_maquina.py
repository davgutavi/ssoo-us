"""ssoo-us acceso: por qué no puede entrar por ssh en su máquina. Con libvirt,
ping, el puerto 22, ssh y el agente QEMU simulados."""

import base64
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import falso_libvirt as fl
from comun_diagnosis import Claves, cd, escribir

UVUS = "alu0000"
DOMINIO = UVUS + "-control2"
RECHAZO = (255, "", "administrador@192.168.7.140: Permission denied (publickey).\n")


class Agente:
    """Un agente QEMU simulado: archivos que se pueden leer, o sin agente."""

    def __init__(self, archivos=None, responde=True):
        self.archivos = archivos or {}
        self.responde = responde
        self.ordenes = []
        self.abiertos = {}

    def __call__(self, dominio, orden, espera=5):
        self.ordenes.append(orden["execute"])
        if not self.responde:
            return None, "error: Guest agent is not responding: QEMU guest agent is not connected"
        a = orden.get("arguments") or {}
        if orden["execute"] == "guest-file-open":
            if a["path"] not in self.archivos:
                return None, ("error: internal error: unable to execute QEMU agent command "
                              "'guest-file-open': failed to open file '%s' (mode: 'r'): "
                              "No such file or directory" % a["path"])
            handle = 1000 + len(self.abiertos)
            self.abiertos[handle] = self.archivos[a["path"]].encode()
            return handle, None
        if orden["execute"] == "guest-file-read":
            datos = self.abiertos[a["handle"]]
            trozo, self.abiertos[a["handle"]] = datos[:10], datos[10:]   # en trozos pequeños
            return {"count": len(trozo), "buf-b64": base64.b64encode(trozo).decode(),
                    "eof": not self.abiertos[a["handle"]]}, None
        if orden["execute"] == "guest-file-close":
            return {}, None
        if orden["execute"] == "guest-network-get-interfaces":
            return [{"name": "lo", "ip-addresses": [{"ip-address-type": "ipv4",
                                                     "ip-address": "127.0.0.1"}]},
                    {"name": "enp1s0", "ip-addresses": [{"ip-address-type": "ipv4",
                                                         "ip-address": "192.168.7.150"}]}], None
        return None, "orden no simulada"


class Acceso(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        os.mkdir(os.path.join(self.home, ".ssh"), 0o700)
        Claves.preparar()
        with open(Claves.sin_frase, "rb") as f:
            escribir(os.path.join(self.home, ".ssh", "id_rsa"), f.read(), 0o600)
        escribir(os.path.join(self.home, ".ssh", "id_rsa.pub"), Claves.publica("sin_frase"))

    def tearDown(self):
        self.tmp.cleanup()

    def revisar(self, dominios, nombre="control2", ip=None, agente=None, ssh=RECHAZO,
                puerto="abierto"):
        conn = fl.Conexion(dominios=dominios)
        self.agente = agente or Agente({cd.CLAVES_EN_LA_MAQUINA: Claves.publica("portatil")})
        self.ssh = []

        def ssh_simulado(ip_, home, known_hosts, estricto):
            self.ssh.append(known_hosts)
            return ssh(known_hosts) if callable(ssh) else ssh

        with mock.patch.object(cd, "preguntar_al_agente", self.agente), \
                mock.patch.object(cd, "responde_ping", return_value=True), \
                mock.patch.object(cd, "probar_puerto", return_value=puerto), \
                mock.patch.object(cd, "_ssh", ssh_simulado):
            informe, _ = cd.revisar_acceso(conn, UVUS, self.home, nombre, ip)
        return informe

    def textos(self, informe):
        """La salida, con los párrafos partidos unidos (para buscar frases)."""
        return " ".join(" ".join(cd.formatear_informe(informe)).split())

    def encendida(self, **kw):
        kw.setdefault("lease", "192.168.7.140")
        return fl.Dominio(DOMINIO, activo=True, red=UVUS + "-red", **kw)


class TestMaquina(Acceso):

    def test_no_existe(self):
        informe = self.revisar([fl.Dominio(UVUS + "-server1"), fl.Dominio("zzz9999-control2")])
        texto = self.textos(informe)
        self.assertIn("No existe la máquina control2", texto)
        self.assertIn("Sus máquinas: alu0000-server1.", texto)
        self.assertEqual(informe.codigo_salida(), 1)

    def test_nombres(self):
        for nombre in ("control2", DOMINIO):
            self.assertIn("La máquina %s está encendida" % DOMINIO,
                          self.textos(self.revisar([self.encendida()], nombre)))
        otra = fl.Dominio("demo-server1", activo=True, lease="192.168.7.141")
        self.assertIn("demo-server1 está encendida", self.textos(self.revisar([otra],
                                                                             "demo-server1")))

    def test_apagada(self):
        informe = self.revisar([fl.Dominio(DOMINIO)])
        texto = self.textos(informe)
        self.assertIn("La máquina %s está apagada" % DOMINIO, texto)
        self.assertIn("virsh start %s" % DOMINIO, texto)
        self.assertEqual(self.agente.ordenes, [])        # ni se intenta
        self.assertEqual(informe.codigo_salida(), 1)

    def test_en_pausa(self):
        texto = self.textos(self.revisar([fl.Dominio(DOMINIO, estado=3)]))
        self.assertIn("está en pausa", texto)
        self.assertIn("virsh resume %s" % DOMINIO, texto)


class TestRed(Acceso):

    def test_ip_del_dhcp(self):
        self.assertIn("IP 192.168.7.140 (del DHCP de su red)",
                      self.textos(self.revisar([self.encendida()])))

    def test_ip_por_arp_y_por_el_agente(self):
        texto = self.textos(self.revisar([self.encendida(lease=None, arp="192.168.7.142")]))
        self.assertIn("IP 192.168.7.142 (de las tablas ARP del servidor)", texto)
        texto = self.textos(self.revisar([self.encendida(lease=None)]))
        self.assertIn("IP 192.168.7.150 (de su agente QEMU)", texto)

    def test_ip_indicada(self):
        texto = self.textos(self.revisar([self.encendida()], ip=cd.ipaddress.ip_address(
            "192.168.7.9")))
        self.assertIn("IP 192.168.7.9 (de --ip)", texto)

    def test_sin_ip_mira_igualmente_la_clave(self):
        # El agente simulado da IP; sin ninguna:
        agente = Agente({cd.CLAVES_EN_LA_MAQUINA: Claves.publica("portatil")})
        with mock.patch.object(cd, "ip_por_agente", return_value=None):
            texto = self.textos(self.revisar([self.encendida(lease=None)], agente=agente))
        self.assertIn("No se encuentra la IP de la máquina", texto)
        self.assertIn("La máquina no tiene ninguna de sus claves", texto)

    def test_puerto_rechazado(self):
        texto = self.textos(self.revisar([self.encendida()], puerto="rechazado"))
        self.assertIn("La máquina rechaza la conexión al puerto 22", texto)
        self.assertIn("modo de emergencia", texto)
        self.assertEqual(self.ssh, [])                   # no se prueba ssh

    def test_puerto_sin_respuesta(self):
        texto = self.textos(self.revisar([self.encendida()], puerto="sin respuesta"))
        self.assertIn("Nada responde en el puerto 22 de 192.168.7.140", texto)
        self.assertIn("virsh domifaddr %s --source lease" % DOMINIO, texto)


class TestSsh(Acceso):

    def test_entra(self):
        informe = self.revisar([self.encendida()], ssh=(0, "control2\n", ""))
        texto = self.textos(informe)
        self.assertIn("Puede entrar: ssh administrador@192.168.7.140 funciona", texto)
        self.assertNotIn("LA CLAVE DE LA MÁQUINA", texto)   # no hace falta mirarla
        self.assertEqual(informe.codigo_salida(), 0)

    def test_contesta_otra_maquina(self):
        texto = self.textos(self.revisar([self.encendida()], ssh=(0, "server1\n", "")))
        self.assertIn("ha contestado una máquina que se llama server1, no control2", texto)

    def test_known_hosts(self):
        cambio = (255, "", "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@\n")
        # Una entrada para la IP: ssh se prueba en modo estricto
        escribir(os.path.join(self.home, ".ssh", "known_hosts"),
                 "192.168.7.140 %s\n" % Claves.publica("portatil").rsplit(" ", 1)[0])
        texto = self.textos(self.revisar(
            [self.encendida()],
            ssh=lambda kh: (0, "control2\n", "") if kh == "/dev/null" else cambio))
        self.assertIn("known_hosts tiene otra clave para 192.168.7.140 [D4]", texto)
        self.assertIn('ssh-keygen -f "%s" -R "192.168.7.140"'
                      % os.path.join(self.home, ".ssh", "known_hosts"), texto)
        self.assertIn("Quitando esa línea de known_hosts, podrá entrar", texto)
        self.assertNotIn("LA CLAVE DE LA MÁQUINA", texto)       # no hace falta mirarla

    def test_permisos_de_la_clave_privada(self):
        texto = self.textos(self.revisar([self.encendida()], ssh=(
            255, "", "WARNING: UNPROTECTED PRIVATE KEY FILE!\nPermissions 0644 ...\n")))
        self.assertIn("ssh no usa ~/.ssh/id_rsa: tiene permisos demasiado abiertos [B10]", texto)
        self.assertIn("chmod 600 ~/.ssh/id_rsa", texto)

    def test_otro_mensaje(self):
        texto = self.textos(self.revisar([self.encendida()], ssh=(255, "", "algo raro\n")))
        self.assertIn("ssh dice: algo raro", texto)
        self.assertIn("ssh -v administrador@192.168.7.140", texto)


class TestClave(Acceso):

    def test_clave_cambiada(self):
        # El caso del control2: la máquina tiene una clave que ya no es la suya
        informe = self.revisar([self.encendida()])
        texto = self.textos(informe)
        self.assertIn("La máquina rechaza su clave: «Permission denied (publickey)» [B5]", texto)
        self.assertIn("La máquina no tiene ninguna de sus claves [B5]", texto)
        portatil = cd.analizar_clave_publica(Claves.publica("portatil"))
        actual = cd.analizar_clave_publica(Claves.publica("sin_frase"))
        self.assertIn("En la máquina: %s" % portatil.describir(), texto)
        self.assertIn("Suya: %s (~/.ssh/id_rsa.pub)" % actual.huella, texto)
        # La orden para añadirla, entera y en una sola línea, sin el comentario
        self.assertIn("              echo '%s' >> /home/administrador/.ssh/authorized_keys"
                      % cd.linea_de_la_clave(actual), cd.formatear_informe(informe))
        self.assertIn("virsh console %s" % DOMINIO, texto)
        self.assertIn("s1st3mas", texto)
        self.assertEqual(self.agente.ordenes,
                         ["guest-file-open"] + ["guest-file-read"] * (
                             len(Claves.publica("portatil")) // 10 + 1) + ["guest-file-close"])

    def test_tiene_la_clave_de_otro_archivo_suyo(self):
        escribir(os.path.join(self.home, ".ssh", "id_rsa_antigua.pub"), Claves.publica("portatil"))
        with open(Claves.portatil, "rb") as f:
            escribir(os.path.join(self.home, ".ssh", "id_rsa_antigua"), f.read(), 0o600)
        texto = self.textos(self.revisar([self.encendida()]))
        self.assertIn("La máquina tiene otra clave suya (~/.ssh/id_rsa_antigua.pub), no la de "
                      "~/.ssh/id_rsa.pub", texto)
        self.assertIn("ssh -i ~/.ssh/id_rsa_antigua administrador@192.168.7.140", texto)

    def test_tiene_su_clave_pero_ssh_la_rechaza(self):
        agente = Agente({cd.CLAVES_EN_LA_MAQUINA:
                         "# un comentario\n" + Claves.publica("portatil") + "\n"
                         + 'from="192.168.7.1" ' + Claves.publica("sin_frase") + "\n"})
        texto = self.textos(self.revisar([self.encendida()], agente=agente))
        self.assertIn("La máquina tiene su clave de ~/.ssh/id_rsa.pub", texto)
        self.assertIn("La máquina tiene su clave, pero ssh la rechaza", texto)
        self.assertIn("chmod 700 /home/administrador/.ssh", texto)

    def test_sin_authorized_keys(self):
        texto = self.textos(self.revisar([self.encendida()], agente=Agente({})))
        self.assertIn("En la máquina, administrador no tiene authorized_keys", texto)
        self.assertIn(">> /home/administrador/.ssh/authorized_keys", texto)

    def test_sin_agente(self):
        informe = self.revisar([self.encendida()], agente=Agente(responde=False))
        texto = self.textos(informe)
        self.assertIn("no responde su agente QEMU", texto)
        self.assertIn("ssoo-us diagnosis %s --acceso" % DOMINIO, texto)
        self.assertEqual(informe.codigo_salida(), 1)     # por el rechazo de ssh

    def test_lectura_por_el_agente(self):
        agente = Agente({"/x": "a" * 25})
        with mock.patch.object(cd, "preguntar_al_agente", agente):
            self.assertEqual(cd.leer_por_agente(DOMINIO, "/x"), ("a" * 25, None))
            self.assertEqual(cd.leer_por_agente(DOMINIO, "/no"), (None, "no existe"))
        self.assertEqual(agente.ordenes, ["guest-file-open", "guest-file-read",
                                          "guest-file-read", "guest-file-read",
                                          "guest-file-close", "guest-file-open"])

    def test_pregunta_solo_lo_permitido(self):
        llamadas = []

        def ejecutar(argv, timeout=30, entrada=None):
            llamadas.append(argv)
            self.assertTrue(cd.orden_de_agente_permitida(argv), argv)
            return 0, json.dumps({"return": 7}), ""

        with mock.patch.object(cd, "ejecutar_lectura", ejecutar):
            self.assertEqual(cd.preguntar_al_agente(
                DOMINIO, {"execute": "guest-file-open",
                          "arguments": {"path": "/x", "mode": "r"}}), (7, None))
        self.assertEqual(llamadas[0][:5], ["virsh", "-c", "qemu:///system",
                                           "qemu-agent-command", DOMINIO])


class TestOrden(unittest.TestCase):

    def ejecutar(self, argv, conn=None):
        salida, errores = io.StringIO(), io.StringIO()
        parches = [contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores)]
        if conn is not None:
            parches.append(fl.instalado(conn))
        with contextlib.ExitStack() as pila:
            for p in parches:
                pila.enter_context(p)
            codigo = cd.acceso(argv)
        return codigo, salida.getvalue(), errores.getvalue()

    def test_ayuda_version_y_errores(self):
        codigo, salida, _ = self.ejecutar(["-h"])
        self.assertEqual(codigo, 0)
        self.assertTrue(salida.startswith("Uso: ssoo-us acceso MAQUINA"))
        self.assertEqual(self.ejecutar(["--version"])[:2], (0, "ssoo-us %s\n" % cd.VERSION))
        for argv, texto in ((["--nada"], "opción desconocida"), (["a", "b"], "sobra «b»"),
                            (["x", "--ip", "nada"], "no es una dirección IP"),
                            ([], "indique la máquina")):
            codigo, _, errores = self.ejecutar(argv)
            self.assertEqual(codigo, 2, argv)
            self.assertIn(texto, errores)

    def test_sin_libvirt(self):
        with mock.patch.dict("sys.modules", {"libvirt": None}):
            codigo, _, errores = self.ejecutar(["control2"])
        self.assertEqual(codigo, 2)
        self.assertIn("avise al profesor", errores)

    def test_de_principio_a_fin(self):
        conn = fl.Conexion(dominios=[fl.Dominio(DOMINIO)])
        with mock.patch.dict(os.environ, {"CI_DIAGNOSIS_USUARIO": UVUS}):
            codigo, salida, _ = self.ejecutar(["control2"], conn)
        self.assertEqual(codigo, 1)
        self.assertIn("ssoo-us acceso %s · " % cd.VERSION, salida)
        self.assertIn("· usuario: alu0000 · máquina: %s" % DOMINIO, salida)
        self.assertIn("ERROR  La máquina %s está apagada" % DOMINIO, salida)
        self.assertTrue(conn.cerrada)


if __name__ == "__main__":
    unittest.main()
