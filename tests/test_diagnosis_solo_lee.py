"""diagnosis solo lee, aunque viva en un programa que escribe (provision).

Revisión estática de los fuentes de diagnosis (src/diagnosis*.py), como la que
hacía ci-diagnosis sobre su archivo entero: no tienen con qué escribir, sus
órdenes externas pasan todas por ejecutar_lectura() (con lista blanca) y no
usan nada de provision, salvo lo que se comparte a propósito en base.py.
"""

import ast
import builtins
import glob
import os
import symtable
import unittest

from comun import RAIZ, leer, su

FUENTES = sorted(glob.glob(os.path.join(RAIZ, "src", "diagnosis*.py"))
                 + [os.path.join(RAIZ, "src", "acceso.py")])

# Llamadas que escribirían o cambiarían algo
PROHIBIDAS_OS = {"remove", "unlink", "rename", "replace", "rmdir", "mkdir", "makedirs",
                 "chmod", "chown", "lchown", "link", "symlink", "truncate", "system",
                 "popen", "kill", "utime", "removedirs", "renames"}

# Lo único de fuera de los fuentes de diagnosis que pueden usar: los módulos
# importados en base.py y lo que base.py comparte a propósito
COMPARTIDO = {"VERSION", "PROGRAMA", "leer_bytes", "IMAGEN_NOBLE", "INTERFAZ_VM",
              "DNS_DE_LA_US", "PASS_CONSOLA", "yaml"}


def modulos_de_base():
    nombres = set()
    for nodo in ast.parse(leer(os.path.join(RAIZ, "src", "base.py"))).body:
        if isinstance(nodo, ast.Import):
            nombres |= {(a.asname or a.name).split(".")[0] for a in nodo.names}
    return nombres


def definidos(arbol):
    nombres = set()
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
            nombres.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres |= {t.id for t in nodo.targets if isinstance(t, ast.Name)}
    return nombres


def globales_usados(tabla):
    """Nombres globales que usa el código (en cualquier función o clase)."""
    usados = set()
    for s in tabla.get_symbols():
        if s.is_referenced() and (s.is_global() or tabla.get_type() == "module"
                                  and not s.is_assigned() and not s.is_imported()):
            usados.add(s.get_name())
    for hija in tabla.get_children():
        usados |= globales_usados(hija)
    return usados


class TestSoloLee(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arboles = {os.path.basename(f): ast.parse(leer(f)) for f in FUENTES}

    def test_estan_todos(self):
        self.assertEqual(sorted(self.arboles), [
            "acceso.py", "diagnosis.py", "diagnosis_acceso.py", "diagnosis_archivos.py",
            "diagnosis_base.py", "diagnosis_claves.py", "diagnosis_disco.py",
            "diagnosis_servidor.py", "diagnosis_textos.py"])

    def test_sin_llamadas_de_os_que_escriben(self):
        for archivo, arbol in self.arboles.items():
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name)
                        and nodo.value.id == "os"):
                    self.assertNotIn(nodo.attr, PROHIBIDAS_OS, "os.%s en %s, línea %d"
                                     % (nodo.attr, archivo, nodo.lineno))

    def test_sin_shutil_ni_tempfile(self):
        for archivo, arbol in self.arboles.items():
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Name):
                    self.assertNotIn(nodo.id, ("shutil", "tempfile"), archivo)

    def test_open_solo_para_leer(self):
        for archivo, arbol in self.arboles.items():
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                        and nodo.func.id == "open"):
                    modos = [a for a in nodo.args[1:2]] + [k.value for k in nodo.keywords
                                                             if k.arg == "mode"]
                    for m in modos:
                        self.assertIsInstance(m, ast.Constant, "modo de open no literal")
                        self.assertNotRegex(m.value, "[wax+]", "open para escribir en %s, "
                                            "línea %d" % (archivo, nodo.lineno))

    def test_subprocess_solo_en_ejecutar_lectura(self):
        for archivo, arbol in self.arboles.items():
            for funcion in ast.walk(arbol):
                if (not isinstance(funcion, ast.FunctionDef)
                        or funcion.name == "ejecutar_lectura"):
                    continue
                for nodo in ast.walk(funcion):
                    if isinstance(nodo, ast.Name):
                        self.assertNotEqual(nodo.id, "subprocess", "subprocess fuera de "
                                            "ejecutar_lectura(), en %s (%s)"
                                            % (funcion.name, archivo))

    def test_nada_de_provision(self):
        # Ni ejecutar() (sin lista blanca), ni virsh, ni fallar()...: solo lo
        # definido en los fuentes de diagnosis, lo compartido y lo de Python
        propios = set()
        for arbol in self.arboles.values():
            propios |= definidos(arbol)
        permitidos = propios | COMPARTIDO | modulos_de_base() | set(dir(builtins))
        for f in FUENTES:
            usados = globales_usados(symtable.symtable(leer(f), f, "exec"))
            self.assertEqual(usados - permitidos, set(), os.path.basename(f))

    def test_lo_compartido_existe(self):
        for nombre in COMPARTIDO:
            self.assertTrue(hasattr(su, nombre), nombre)

    def test_ejecutar_lectura_rechaza_ordenes_fuera_de_la_lista(self):
        for orden in (["virsh", "list"], ["rm", "-f", "x"], ["sh", "-c", "true"],
                      ["virt-install"], ["qemu-img-falso"]):
            with self.assertRaises(ValueError):
                su.ejecutar_lectura(orden)

    def test_del_agente_qemu_solo_leer(self):
        def virsh(orden):
            return ["virsh", "-c", "qemu:///system", "qemu-agent-command", "alu0000-server1",
                    "--timeout", "5", su.json.dumps(orden)]
        permitidas = [{"execute": "guest-ping"},
                      {"execute": "guest-network-get-interfaces"},
                      {"execute": "guest-file-open", "arguments": {"path": "/x", "mode": "r"}},
                      {"execute": "guest-file-read", "arguments": {"handle": 1}},
                      {"execute": "guest-file-close", "arguments": {"handle": 1}}]
        for orden in permitidas:
            self.assertTrue(su.orden_de_agente_permitida(virsh(orden)), orden)
        prohibidas = [{"execute": "guest-exec", "arguments": {"path": "/bin/sh"}},
                      {"execute": "guest-file-open", "arguments": {"path": "/x", "mode": "w"}},
                      {"execute": "guest-file-open", "arguments": {"path": "/x"}},
                      {"execute": "guest-file-write", "arguments": {"handle": 1}},
                      {"execute": "guest-shutdown"}]
        for orden in prohibidas:
            self.assertFalse(su.orden_de_agente_permitida(virsh(orden)), orden)
            with self.assertRaises(ValueError):
                su.ejecutar_lectura(virsh(orden))
        # Ni otras órdenes de virsh, ni con otra forma
        for argv in (["virsh", "-c", "qemu:///system", "destroy", "x", "--timeout", "5", "{}"],
                     virsh({"execute": "guest-ping"})[:-1],
                     ["virsh", "qemu-agent-command", "x", '{"execute": "guest-ping"}']):
            self.assertFalse(su.orden_de_agente_permitida(argv), argv)

    def test_ejecutar_lectura_con_lc_all_c(self):
        # ssh-keygen sin argumentos válidos: el mensaje sale en inglés
        codigo, _, err = su.ejecutar_lectura(["ssh-keygen", "-l", "-f", "/no/existe"])
        self.assertNotEqual(codigo, 0)
        self.assertIn("No such file", err)


if __name__ == "__main__":
    unittest.main()
