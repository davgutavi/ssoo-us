# --- provision: las pantallas del asistente ----------------------------------------
#
# Cada pantalla es un diálogo a pantalla completa de prompt_toolkit (paquete
# python3-prompt-toolkit de Ubuntu; no lo necesita nada más de ssoo-us), con
# botones «Atrás» y «Siguiente» y uso del ratón. Devuelven lo elegido, ATRAS (el
# botón, o Esc) o SALIR (Ctrl+C).
#
# Para los tests hay otra implementación con las mismas operaciones,
# PantallasGuion, que toma las respuestas de un archivo (SSOO_US_ASISTENTE_GUION)
# en lugar de la terminal y anota cada pantalla en otro (SSOO_US_ASISTENTE_REGISTRO).

ATRAS = "<atrás>"
SALIR = "<salir>"
ANCHO_TEXTO = 70
AYUDA_TECLAS = "↑↓ mover · Espacio marcar · Intro seguir · Tab botones · Esc atrás · ratón"

ESTILO_ASISTENTE = {
    "dialog": "bg:#005f87",
    "dialog frame.label": "bg:#ffffff #005f87 bold",
    "dialog.body": "bg:#e4e4e4 #1c1c1c",
    "dialog shadow": "bg:#00384f",
    "button": "bg:#bcbcbc #1c1c1c",
    "button.focused": "bg:#005f87 #ffffff bold",
    "radio-list": "bg:#e4e4e4",
    "checkbox-list": "bg:#e4e4e4",
    "radio-selected": "bg:#005f87 #ffffff",
    "checkbox-selected": "bg:#005f87 #ffffff",
    "radio-checked": "bold",
    "checkbox-checked": "bold",
    "text-area": "bg:#ffffff #000000",
    "ayuda": "#6c6c6c italic",
}


def envolver(texto, ancho=ANCHO_TEXTO):
    """Parte cada párrafo del texto a ese ancho (las etiquetas no lo hacen solas)."""
    lineas = []
    for parrafo in texto.split("\n"):
        lineas += textwrap.wrap(parrafo, ancho, break_on_hyphens=False,
                                break_long_words=False) or [""]
    return "\n".join(lineas)


def recortar(texto, ancho):
    """El texto, cortado con «…» si pasa de ese ancho."""
    return texto if len(texto) <= ancho else texto[:ancho - 1] + "…"


def prompt_toolkit_disponible():
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


class PantallasPT:
    """Las pantallas, en la terminal, con prompt_toolkit."""

    def __init__(self, titulo, entrada=None, salida=None):
        self.titulo = titulo
        self.entrada = entrada      # para los tests: una entrada y una salida falsas
        self.salida = salida

    def _mostrar(self, texto, cuerpo, botones, foco, ayuda=True):
        """Un diálogo: el texto, el cuerpo (una lista, un campo...) y los botones
        [(etiqueta, resultado o función)]. Devuelve el resultado del que se pulse."""
        from prompt_toolkit.application import Application, get_app
        from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
        from prompt_toolkit.key_binding.defaults import load_key_bindings
        from prompt_toolkit.layout import Dimension, HSplit, Layout, Window
        from prompt_toolkit.styles import Style
        from prompt_toolkit.widgets import Button, Dialog, Label

        def boton(etiqueta, resultado):
            def pulsar():
                get_app().exit(result=resultado() if callable(resultado) else resultado)
            return Button(etiqueta, handler=pulsar, width=max(12, len(etiqueta) + 4))

        piezas = [Label(envolver(texto))]
        if cuerpo is not None:
            piezas += [Window(height=1), cuerpo]
        if ayuda:
            piezas += [Window(height=1), Label(AYUDA_TECLAS, style="class:ayuda")]
        lista_botones = [boton(e, r) for e, r in botones]
        dialogo = Dialog(title=self.titulo, body=HSplit(piezas, padding=0),
                         buttons=lista_botones, with_background=True,
                         width=Dimension(min=50, preferred=ANCHO_TEXTO + 8))

        teclas = KeyBindings()

        @teclas.add("escape", eager=True)
        def _atras(event):
            event.app.exit(result=ATRAS)

        @teclas.add("c-c")
        def _salir(event):
            event.app.exit(result=SALIR)

        app = Application(layout=Layout(dialogo, focused_element=foco or lista_botones[-1]),
                          key_bindings=merge_key_bindings([load_key_bindings(), teclas]),
                          style=Style.from_dict(ESTILO_ASISTENTE), mouse_support=True,
                          full_screen=True, input=self.entrada, output=self.salida)
        return app.run()

    def _lista(self, opciones, inicial, varias, al_intro, aceptar_al_marcar=False):
        from prompt_toolkit.widgets import CheckboxList, RadioList

        base = CheckboxList if varias else RadioList

        class Lista(base):
            if aceptar_al_marcar:
                # Un menú: sin «( )»; la entrada en la que se está va resaltada
                open_character = close_character = ""

            def _handle_enter(self):
                base._handle_enter(self)
                if aceptar_al_marcar:      # un menú: elegir (o pulsar con el ratón) ya acepta
                    al_intro(self)

        if varias:
            lista = Lista(opciones, default_values=inicial or [])
        else:
            lista = Lista(opciones, default=inicial)
            if aceptar_al_marcar:
                lista.current_value = None     # ninguna marcada (sin «*»)
        if not aceptar_al_marcar:
            @lista.control.key_bindings.add("enter")
            def _intro(event):
                if not varias:
                    lista._handle_enter()      # Intro sobre una opción la elige
                al_intro(lista)
        return lista

    def menu(self, texto, opciones, inicial=None, atras="Atrás", seguir="Aceptar"):
        """Una entrada de una lista (Intro, o un clic sobre ella, ya la elige)."""
        from prompt_toolkit.application import get_app

        def resaltada(lista):
            return lista.values[lista._selected_index][0]

        lista = self._lista(opciones, inicial, False,
                            lambda l: get_app().exit(result=resaltada(l)),
                            aceptar_al_marcar=True)
        return self._mostrar(texto, lista, [(atras, ATRAS), (seguir, lambda: resaltada(lista))],
                             lista)

    def elegir_uno(self, texto, opciones, marcada):
        """Una opción de varias, marcada con Espacio o con el ratón."""
        from prompt_toolkit.application import get_app
        lista = self._lista(opciones, marcada, False,
                            lambda l: get_app().exit(result=l.current_value))
        return self._mostrar(texto, lista, [("Atrás", ATRAS),
                                            ("Siguiente", lambda: lista.current_value)], lista)

    def elegir_varios(self, texto, opciones, marcadas):
        """Las opciones marcadas (lista), en el orden en que se ofrecen."""
        from prompt_toolkit.application import get_app

        def elegidas(lista):
            return [v for v, _ in lista.values if v in lista.current_values]

        lista = self._lista(opciones, marcadas, True,
                            lambda l: get_app().exit(result=elegidas(l)))
        return self._mostrar(texto, lista, [("Atrás", ATRAS),
                                            ("Siguiente", lambda: elegidas(lista))], lista)

    def texto(self, pregunta, inicial="", oculto=False):
        """Una línea de texto (oculto: una contraseña)."""
        from prompt_toolkit.application import get_app
        from prompt_toolkit.widgets import TextArea

        def aceptar(buffer):
            get_app().exit(result=buffer.text)
            return True

        campo = TextArea(text=inicial, multiline=False, password=oculto,
                         accept_handler=aceptar, focus_on_click=True)
        campo.buffer.cursor_position = len(inicial)
        return self._mostrar(pregunta, campo, [("Atrás", ATRAS),
                                               ("Siguiente", lambda: campo.text)], campo)

    def aviso(self, texto, boton="Aceptar"):
        self._mostrar(texto, None, [(boton, None)], None, ayuda=False)

    def confirmar(self, texto, si="Ejecutar", no="Atrás"):
        """True si se acepta; ATRAS o SALIR si no."""
        return self._mostrar(texto, None, [(no, ATRAS), (si, True)], None, ayuda=False)


class PantallasGuion:
    """Las mismas pantallas, para los tests: cada respuesta es una línea del guion
    (la clave elegida; varias, separadas por espacios; el texto; «si» para
    confirmar; <atrás> o <salir>). Sin más líneas, SALIR. Cada pantalla se anota
    en el registro, en una línea: TIPO: texto | opciones (con * la marcada)."""

    def __init__(self, guion, registro=None):
        with open(guion, encoding="utf-8") as f:
            self.respuestas = f.read().split("\n")
        if self.respuestas and self.respuestas[-1] == "":
            self.respuestas.pop()
        self.registro = registro

    def _anotar(self, tipo, texto, detalle=""):
        if self.registro:
            with open(self.registro, "a", encoding="utf-8") as f:
                f.write("%s: %s%s\n" % (tipo, texto.replace("\n", " / "),
                                        " | " + detalle if detalle else ""))

    def _respuesta(self):
        return self.respuestas.pop(0) if self.respuestas else SALIR

    @staticmethod
    def _opciones(opciones, marcadas):
        return " ; ".join("%s%s=%s" % ("*" if v in marcadas else "", v, e) for v, e in opciones)

    def menu(self, texto, opciones, inicial=None, atras="Atrás", seguir="Aceptar"):
        self._anotar("menu", texto, self._opciones(opciones, [inicial]))
        return self._respuesta()

    def elegir_uno(self, texto, opciones, marcada):
        self._anotar("elegir_uno", texto, self._opciones(opciones, [marcada]))
        r = self._respuesta()
        return r if r in (ATRAS, SALIR) or r else marcada

    def elegir_varios(self, texto, opciones, marcadas):
        self._anotar("elegir_varios", texto, self._opciones(opciones, marcadas))
        r = self._respuesta()
        return r if r in (ATRAS, SALIR) else r.split()

    def texto(self, pregunta, inicial="", oculto=False):
        self._anotar("texto", pregunta, "inicial=%s" % ("•" * len(inicial) if oculto else inicial))
        return self._respuesta()

    def aviso(self, texto, boton="Aceptar"):
        self._anotar("aviso", texto)
        self._respuesta()

    def confirmar(self, texto, si="Ejecutar", no="Atrás"):
        self._anotar("confirmar", texto)
        r = self._respuesta()
        return True if r == "si" else (r if r in (ATRAS, SALIR) else ATRAS)


def pantallas_del_asistente():
    """Las del guion, en los tests; si no, las de la terminal."""
    guion = os.environ.get("SSOO_US_ASISTENTE_GUION")
    if guion:
        return PantallasGuion(guion, os.environ.get("SSOO_US_ASISTENTE_REGISTRO"))
    return PantallasPT("%s %s" % (PROGRAMA, VERSION))
