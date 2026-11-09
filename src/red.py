# --- Red virtual: XML de libvirt y aritmética de IPv4 ------------------------------
#
# Lo comparten provision (que lee el XML con «virsh net-dumpxml») y, cuando se
# porte, diagnosis (que lo lee con la binding de libvirt). Aquí solo se analiza:
# los mensajes de error son de quien llama.

# Bits de cada octeto de una máscara (mask_to_prefix de ci-provision: suma los
# bits de cada octeto, sin exigir que sean contiguos)
BITS_DE_OCTETO = {"255": 8, "254": 7, "252": 6, "248": 5, "240": 4, "224": 3,
                  "192": 2, "128": 1, "0": 0}
IPV4_RE = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}")


def ipv4_valida(ip):
    """Cuatro números de 0 a 255 (con ceros a la izquierda si se quiere)."""
    return (IPV4_RE.fullmatch(ip) is not None
            and all(int(o, 10) <= 255 for o in ip.split(".")))


def ip_a_entero(ip):
    a, b, c, d = (int(o, 10) for o in ip.split("."))
    return (a << 24) + (b << 16) + (c << 8) + d


def entero_a_ip(n):
    return "%d.%d.%d.%d" % ((n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255, n & 255)


def mascara_a_prefijo(mascara):
    """255.255.255.0 → 24; None si algún octeto no es de máscara."""
    bits = 0
    for octeto in mascara.split("."):
        if octeto not in BITS_DE_OCTETO:
            return None
        bits += BITS_DE_OCTETO[octeto]
    return bits


def prefijo_por_clase(pasarela):
    """Sin máscara ni prefijo, libvirt aplica la máscara de la clase. Como en
    ci-provision, por el texto del primer octeto («010» no es de la clase A)."""
    primero = pasarela.split(".")[0]
    if re.fullmatch(r"[0-9]|[1-9][0-9]|1[01][0-9]|12[0-7]", primero):
        return 8
    if re.fullmatch(r"1[2-8][0-9]|19[01]", primero):
        return 16
    return 24


def analizar_xml_red(xml):
    """El primer bloque <ip> de IPv4 de la definición de una red de libvirt
    (los de IPv6 se descartan: sus rangos no son direcciones IPv4).

    Devuelve None si no hay ninguno, o un diccionario con los atributos tal
    cual vienen («address», «netmask», «prefix»; cadena vacía si faltan), los
    rangos DHCP («rangos», [(inicio, fin)]) y las IPs de las reservas por MAC
    («reservas»), sin validar."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return None
    for ip in raiz.findall("ip"):
        # Como ci-provision: un <ip> sin atributos no cuenta
        if ip.get("family") == "ipv6" or not ip.attrib:
            continue
        datos = {"address": ip.get("address", ""), "netmask": ip.get("netmask", ""),
                 "prefix": ip.get("prefix", ""), "rangos": [], "reservas": []}
        for dhcp in ip.findall("dhcp"):
            for r in dhcp.findall("range"):
                datos["rangos"].append((r.get("start", ""), r.get("end", "")))
            for h in dhcp.findall("host"):
                if h.get("ip") is not None:
                    datos["reservas"].append(h.get("ip"))
        return datos
    return None


class RedIPv4:
    """Una red virtual ya leída: pasarela, prefijo, rangos DHCP y reservas
    (todo IPv4 válido)."""

    def __init__(self, nombre, pasarela, prefijo, rangos=(), reservas=()):
        self.nombre = nombre
        self.pasarela = pasarela
        self.prefijo = prefijo
        self.rangos = list(rangos)       # [(inicio, fin)]
        self.reservas = list(reservas)   # [ip]

    @property
    def mascara_entera(self):
        return 0xFFFFFFFF ^ ((1 << (32 - self.prefijo)) - 1)

    @property
    def red_entera(self):
        return ip_a_entero(self.pasarela) & self.mascara_entera

    @property
    def difusion_entera(self):
        return self.red_entera | (~self.mascara_entera & 0xFFFFFFFF)

    def bloques_libres(self):
        """Hasta 3 bloques de IPs libres para asignación fija, como líneas
        «  A - B», o «  (ninguna)»."""
        ocupados = [(ip_a_entero(self.pasarela),) * 2]
        ocupados += [(ip_a_entero(a), ip_a_entero(b)) for a, b in self.rangos]
        ocupados += [(ip_a_entero(r),) * 2 for r in self.reservas]
        lineas = []
        actual = self.red_entera + 1
        for inicio, fin in sorted(ocupados):
            if len(lineas) >= 3:
                return lineas
            if inicio > actual:
                lineas.append("  %s - %s" % (entero_a_ip(actual), entero_a_ip(inicio - 1)))
            if fin >= actual:
                actual = fin + 1
        if len(lineas) < 3 and actual <= self.difusion_entera - 1:
            lineas.append("  %s - %s" % (entero_a_ip(actual), entero_a_ip(self.difusion_entera - 1)))
        return lineas or ["  (ninguna)"]

    def asignable(self, ip_entera):
        """¿Se puede asignar esta IP de forma fija? Dentro de la red, sin ser la
        de red, la de difusión ni la pasarela, y fuera del DHCP y las reservas."""
        if ip_entera & self.mascara_entera != self.red_entera:
            return False
        if ip_entera in (self.red_entera, self.difusion_entera, ip_a_entero(self.pasarela)):
            return False
        if any(ip_a_entero(a) <= ip_entera <= ip_a_entero(b) for a, b in self.rangos):
            return False
        return all(ip_entera != ip_a_entero(r) for r in self.reservas)

    def primer_hueco(self, cuantas):
        """Primer número N (de 2 a 250) con N, N+1... libres para «cuantas» IPs."""
        for n in range(2, 251):
            if all(self.asignable(self.red_entera + n + k) for k in range(cuantas)):
                return n
        return None
