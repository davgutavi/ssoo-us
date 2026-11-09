"""provision genera y diagnosis revisa: lo que genera provision no puede dar
ningún ERROR en diagnosis.

El único AVISO que se admite es el del instance-id: provision le añade la
fecha (para que cloud-init vuelva a configurar un disco de partida que ya
fue una máquina con el mismo nombre), y diagnosis espera <uvus>-<máquina>,
como en el manual.
"""

import re
import unittest

from comun_diagnosis import Claves, cd, necesita_yaml
from test_provision_entorno import Silo

# (opciones de provision, dominio, hostname, IP, modo de generar_cloudinit)
CASOS = [
    (["server1"], "alu0000-server1", "server1", "192.168.7.2", "normal"),
    (["server1"], "alu0000-server1", "server1", "", "normal"),
    (["--ssh-pass", "Secreta1", "server1"], "alu0000-server1", "server1", "192.168.7.2",
     "normal"),
    (["--extra-disks", "server1"], "alu0000-server1", "server1", "192.168.7.2", "normal"),
    (["--glusterfs", "nodo1"], "alu0000-nodo1", "nodo1", "192.168.7.20", "gluster"),
    (["--gluster-cluster"], "alu0000-server2", "server2", "192.168.7.11", "nodo"),
]


def revisar(silo, dominio, host, red, clave):
    rs = []
    for nombre, ruta in (("user-data", silo.o.user_data), ("meta-data", silo.o.meta_data),
                         ("network-config", silo.o.network_data)):
        if not ruta:
            continue
        with open(ruta, "rb") as f:
            r, texto = cd.comprobar_texto(nombre, f.read())
        rs += r
        if nombre == "user-data":
            rs += cd.comprobar_user_data(texto, clave)
        elif nombre == "meta-data":
            rs += cd.comprobar_meta_data(texto, "alu0000", host)[0]
        else:
            rs += cd.comprobar_network_config(texto, red)[0]
    return rs


@necesita_yaml
class TestLoQueGeneraProvision(unittest.TestCase):

    def test_sin_errores(self):
        publica = Claves.publica("sin_frase")
        clave = cd.analizar_clave_publica(publica)
        red = cd.Red("alu0000-red", "192.168.7.0/24", "192.168.7.1",
                     [("192.168.7.128", "192.168.7.254")])
        for argv, dominio, host, ip, modo in CASOS:
            with self.subTest(argv=argv, modo=modo):
                s = Silo(*argv)
                s.o.pubkey = publica
                if modo == "nodo":
                    cd.calcular_ips_cluster(s.o)
                cd.generar_cloudinit(s.o, dominio, host, ip, modo)
                rs = revisar(s, dominio, host, red, clave)
                s.tmp.cleanup()
                self.assertEqual([r for r in rs if r.estado == cd.ERROR], [])
                avisos = [r for r in rs if r.estado == cd.AVISO]
                self.assertEqual([r.texto for r in avisos],
                                 ["El instance-id de meta-data no es %s" % dominio])
                self.assertRegex(avisos[0].detalle[0],
                                 r"^Tiene: %s-[0-9]{14}$" % re.escape(dominio))
                # Y lo demás se ha comprobado: la clave, el usuario, la red...
                self.assertGreater(len([r for r in rs if r.estado == cd.OK]), 5)


if __name__ == "__main__":
    unittest.main()
