"""Work out what each device is: its name, maker, type and what it's running.

Everything here asks devices on your own network to describe themselves, the
same way your phone finds a TV to cast to. Nothing is recorded or sent off
your network.

  - Names come from your router (reverse DNS), Apple/Bonjour (mDNS),
    Windows (NetBIOS) and smart TVs/speakers/routers (UPnP).
  - Makers come from the official IEEE registry (bugsweep/data/makers.tsv.gz).
  - "What it's running" checks a handful of well-known ports, e.g. 554 is
    used to stream video from cameras.
"""

import gzip
import platform
import re
import socket
import struct
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from bugsweep.core import PACKAGE_DIR, is_randomized

IS_WINDOWS = platform.system() == "Windows"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAKERS_FILE = PACKAGE_DIR / "data" / "makers.tsv.gz"

# port: (short name, plain-English meaning, is it a risk worth mentioning?)
PORTS = {
    21: ("File transfer (FTP)", "Shares files using an old method that doesn't encrypt passwords.", True),
    22: ("Remote login (SSH)", "Can be controlled remotely by someone with the password. Normal for computers and hobby boards.", False),
    23: ("Telnet", "Old, unencrypted remote control. Should almost never be switched on.", True),
    80: ("Web page", "Has a settings web page you can open in a browser.", False),
    443: ("Secure web page", "Has a settings web page (encrypted).", False),
    445: ("File sharing", "Shares files and folders with other computers.", False),
    554: ("Video stream (RTSP)", "Can stream live video. This is how most IP cameras send their picture.", False),
    1935: ("Live stream (RTMP)", "Can send a live audio/video stream.", False),
    5000: ("Web app / NAS", "Often a storage box (NAS) or a home-made web app.", False),
    7000: ("AirPlay", "Can receive music or screen-mirroring from Apple devices.", False),
    8008: ("Google Cast", "Can receive casting from phones (Chromecast, Google/Nest speakers and TVs).", False),
    8080: ("Web page (alternate)", "Has a web page or app, often a camera, router or home-made gadget.", False),
    8554: ("Video stream (RTSP)", "Can stream live video, typical of cameras and DIY camera boards.", False),
    9100: ("Printing", "Accepts print jobs, so it's almost certainly a printer.", False),
}

# Device types, most specific first. Each rule matches against
# "maker | name | model" in lower case.
TYPE_RULES = [
    ("Camera", r"hikvision|dahua|wyze|reolink|amcrest|arlo|\bring\b|axis comm|foscam|ezviz|lorex|swann|"
               r"uniview|hanwha|vivotek|\bcam\b|camera|ipcam|doorbell|\bnvr\b|\bdvr\b|blink"),
    ("Printer", r"printer|brother|canon|epson|seiko epson|lexmark|kyocera|xerox|ricoh|laserjet|officejet|deskjet"),
    ("TV or streaming box", r"\btv\b|television|roku|vizio|tcl|hisense|chromecast|apple ?tv|fire ?tv|firetv|bravia|webos|shield|tivo"),
    ("Speaker", r"sonos|bose|echo|alexa|homepod|nest audio|nest mini|google home|speaker|soundbar"),
    ("Game console", r"nintendo|playstation|xbox|sony interactive|valve"),
    ("Router or Wi-Fi", r"netgear|tp-link|tplink|ubiquiti|eero|arris|linksys|asustek|asus|mikrotik|cisco|aruba|"
                        r"ruckus|juniper|technicolor|sagemcom|zyxel|d-link|\brouter\b|\bap\b|wifi|wi-fi|access point|gateway|"
                        r"fortinet|meraki|plume|commscope|calix|actiontec"),
    ("Storage (NAS)", r"synology|qnap|western digital|\bnas\b|drobo|buffalo"),
    ("Desk phone", r"polycom|yealink|grandstream|voip|avaya|mitel|poly\b"),
    ("Phone or tablet", r"iphone|ipad|android|galaxy|pixel|oneplus|motorola|xiaomi|oppo|vivo mobile|huawei|phone"),
    ("Smart home gadget", r"tuya|philips lighting|signify|lifx|ecobee|nest labs|google nest|thermostat|smart ?plug|"
                          r"wemo|belkin|shelly|sonoff|itead|kasa|meross|govee|wiz|august|yale|chamberlain|myq|"
                          r"badge|sensor|bulb|light|fridge|appliance|lg innotek|ihome"),
    ("Computer", r"dell|lenovo|\bhp\b|hewlett|intel|azurewave|liteon|lite-on|hon hai|foxconn|"
                 r"realtek|murata|qualcomm|rivet|killer|laptop|desktop|macbook|imac|thinkpad|surface|-pc\b|\bpc\b|"
                 r"vmware|parallels|asrock|gigabyte|micro-star|msi|wistron|quanta|compal|pegatron|"
                 r"chongqing fugui|cloud network technology|universal global scientific|liteon|"
                 r"hui zhou gaoshengda|\bwnc\b|wistron neweb"),
    # Big brands that make many kinds of device. Only used when the name
    # didn't give it away, so the label says honestly what it could be.
    ("Samsung device (phone, TV or appliance)", r"samsung"),
    ("Google device (phone, Nest or Chromecast)", r"\bgoogle\b"),
    ("Amazon device (Echo, Fire TV, Kindle or Ring)", r"amazon"),
    ("Sony device (TV, PlayStation or phone)", r"\bsony\b"),
    ("LG device (TV, phone or appliance)", r"lg electronics"),
    ("Apple device (Mac, iPhone, iPad or Apple TV)", r"\bapple\b"),
    ("Microsoft device (PC, Surface or Xbox)", r"microsoft"),
    ("Router or Wi-Fi", r"virtual router"),
]
_TYPE_RULES = [(kind, re.compile(rx)) for kind, rx in TYPE_RULES]
PRIVATE_KIND = "Phone, tablet or laptop (private address)"
VRRP_MAKER = "Virtual router (business/shared network)"


@lru_cache(maxsize=1)
def _makers():
    db = {}
    try:
        with gzip.open(MAKERS_FILE, "rt", encoding="utf-8") as f:
            for line in f:
                prefix, _, name = line.rstrip("\n").partition("\t")
                db[prefix] = name
    except OSError:
        pass
    return db


def lookup_maker(mac):
    flat = mac.replace(":", "")
    # 00:00:5E:00:01:xx / 02:xx are "virtual router" addresses (VRRP), used by
    # managed office, campus and apartment networks. IEEE lists them under
    # "ICANN, IANA Department", which would mean nothing to anyone.
    if flat.startswith(("00005E0001", "00005E0002")):
        return VRRP_MAKER
    db = _makers()
    for length in (9, 7, 6):
        name = db.get(flat[:length])
        if name:
            return name
    return ""


def guess_kind(device, is_dev_board=False):
    if device.is_self:
        return "This computer"
    if device.is_router:
        return "Your router"
    if is_dev_board:
        return "Hobby circuit board"
    ports = set(device.ports)
    services = set(getattr(device, "services", []) or [])
    if ports & {554, 8554}:
        return "Camera"
    if 9100 in ports or services & {"_ipp._tcp", "_printer._tcp"}:
        return "Printer"
    # What the device calls itself beats who made its chip: a Dell chip in
    # "spring-laptop" is a computer, a Samsung chip in "Kitchen TV" is a TV.
    for text in (f"{device.name} | {device.model}", device.maker):
        text = text.lower()
        for kind, rx in _TYPE_RULES:
            if rx.search(text):
                return kind
    if 8008 in ports or "_googlecast._tcp" in services:
        return "TV or streaming box"
    if 7000 in ports or services & {"_airplay._tcp", "_raop._tcp"}:
        return "TV or streaming box"
    if is_randomized(device.mac):
        return PRIVATE_KIND
    return "Unknown"


# ---- names ---------------------------------------------------------------

# How each lookup is described to people in the "Why no name?" section.
LOOKUP_LABELS = {
    "upnp": "Asked smart TVs, speakers and routers to announce themselves (UPnP)",
    "mdns_browse": "Listened for Apple, Google and printer announcements (Bonjour)",
    "mdns": "Asked the device for its name (Bonjour)",
    "netbios": "Asked the device for its name (Windows)",
    "rdns": "Asked your router for the device's name",
}
LOOKUP_SHORT = {"upnp": "UPnP", "mdns_browse": "Bonjour", "mdns": "Bonjour", "netbios": "Windows",
                "rdns": "router"}
NO_ANSWER = "no answer"
TOO_SLOW = "didn't answer in time"


def _multicast_socket(local_ip=""):
    """A UDP socket whose multicast goes out of the adapter that has local_ip.

    Without this, PCs with extra adapters (VPN, Hyper-V, WSL) can send the
    request into a virtual network where nothing will ever answer.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if local_ip:
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
            s.bind((local_ip, 0))
        except OSError:
            pass
    return s


def _reverse_dns(ip):
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""
    return "" if name == ip else name.split(".")[0]


def _dns_name(data, offset):
    """Read a (possibly compressed) DNS name; returns (name, next_offset)."""
    labels, jumped, end = [], False, offset
    for _ in range(64):
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if not jumped:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | data[offset + 1]
            jumped = True
            continue
        labels.append(data[offset + 1:offset + 1 + length].decode("utf-8", "replace"))
        offset += 1 + length
    return ".".join(labels), (end if jumped else offset)


def _dns_records(data):
    """Every answer/authority/additional record in a DNS packet as (name, type, value)."""
    qd, an, ns, ar = struct.unpack(">HHHH", data[4:12])
    off = 12
    for _ in range(qd):
        _, off = _dns_name(data, off)
        off += 4
    records = []
    for _ in range(an + ns + ar):
        name, off = _dns_name(data, off)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[off:off + 10])
        off += 10
        rdata = data[off:off + rdlen]
        if rtype == 1 and rdlen == 4:
            value = socket.inet_ntoa(rdata)
        elif rtype == 12:
            value = _dns_name(data, off)[0]
        elif rtype == 33:
            value = _dns_name(data, off + 6)[0]
        elif rtype == 16:
            value, i = [], 0
            while i < rdlen:
                n = rdata[i]
                value.append(rdata[i + 1:i + 1 + n].decode("utf-8", "replace"))
                i += 1 + n
        else:
            value = None
        records.append((name, rtype, value))
        off += rdlen
    return records


def _strip_local(name):
    return name.removesuffix(".").removesuffix(".local")


def _mdns_name(ip, timeout=1.5):
    """Ask the device itself (Bonjour/mDNS) for its name, e.g. 'Jordans-iPhone'."""
    qname = b"".join(bytes([len(p)]) + p.encode() for p in reversed(ip.split("."))) + b"\x07in-addr\x04arpa\x00"
    packet = struct.pack(">HHHHHH", 0x4242, 0, 1, 0, 0, 0) + qname + struct.pack(">HH", 12, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(packet, (ip, 5353))
        data, _ = s.recvfrom(4096)
        for _, rtype, value in _dns_records(data):
            if rtype == 12 and value:
                return _strip_local(value)
    except (OSError, IndexError, struct.error, UnicodeError):
        pass
    finally:
        s.close()
    return ""


# Services that phones, TVs, speakers and printers announce over Bonjour.
MDNS_SERVICES = ["_services._dns-sd._udp", "_googlecast._tcp", "_airplay._tcp", "_raop._tcp",
                 "_ipp._tcp", "_printer._tcp", "_device-info._tcp", "_companion-link._tcp",
                 "_spotify-connect._tcp", "_hap._tcp", "_smb._tcp", "_workstation._tcp"]


def mdns_query(services):
    """One mDNS packet asking for every service type in `services`."""
    packet = struct.pack(">HHHHHH", 0, 0, len(services), 0, 0, 0)
    for svc in services:
        for label in (svc + ".local").split("."):
            packet += bytes([len(label)]) + label.encode()
        packet += b"\x00" + struct.pack(">HH", 12, 1)
    return packet


def parse_mdns_answers(packets):
    """Turn Bonjour answers into {ip: {"name", "model", "services"}}."""
    host_ip, host_case, instance_host, txt = {}, {}, {}, {}
    for data in packets:
        try:
            records = _dns_records(data)
        except (IndexError, struct.error):
            continue
        for name, rtype, value in records:
            if rtype == 1:
                host_ip[name.lower()] = value
                host_case[name.lower()] = name  # keep "Jordans-iPhone", not "jordans-iphone"
            elif rtype == 33:
                instance_host[name] = value.lower()
            elif rtype == 16:
                txt[name] = dict(item.partition("=")[::2] for item in value if "=" in item)
    found = {}
    for instance, host in instance_host.items():
        ip = host_ip.get(host)
        if not ip:
            continue
        info = found.setdefault(ip, {"name": "", "model": "", "services": []})
        label, _, service = instance.partition("._")
        service = "_" + service.removesuffix(".local") if service else ""
        if service and service not in info["services"]:
            info["services"].append(service)
        t = txt.get(instance, {})
        friendly = t.get("fn") or label
        if friendly and (not info["name"] or service == "_googlecast._tcp"):
            info["name"] = friendly
        info["model"] = info["model"] or t.get("md") or t.get("model") or t.get("ty") or ""
    for host, ip in host_ip.items():
        info = found.setdefault(ip, {"name": "", "model": "", "services": []})
        info["name"] = info["name"] or _strip_local(host_case[host])
    return found


def _mdns_browse(local_ip="", seconds=2.5):
    """Ask every Bonjour device on the network what it offers (multicast query)."""
    import time
    s = _multicast_socket(local_ip)
    s.settimeout(0.3)
    packets = []
    try:
        query = mdns_query(MDNS_SERVICES)
        s.sendto(query, ("224.0.0.251", 5353))
        stop = time.monotonic() + seconds
        resent = False
        while time.monotonic() < stop:
            if not resent and time.monotonic() > stop - seconds / 2:
                s.sendto(query, ("224.0.0.251", 5353))
                resent = True
            try:
                data, _ = s.recvfrom(9000)
                packets.append(data)
            except socket.timeout:
                continue
    except OSError:
        pass
    finally:
        s.close()
    return parse_mdns_answers(packets)


def netbios_query():
    """A NetBIOS 'node status' request for the wildcard name '*'."""
    encoded = b"".join(bytes([0x41 + (b >> 4), 0x41 + (b & 0x0F)]) for b in b"*" + b"\x00" * 15)
    return (struct.pack(">HHHHHH", 0x4242, 0, 1, 0, 0, 0) + b"\x20" + encoded + b"\x00"
            + struct.pack(">HH", 0x21, 1))


def parse_netbios(data):
    """The computer name from a NetBIOS node-status reply, or ''."""
    try:
        _, off = _dns_name(data, 12)
        rtype = struct.unpack(">H", data[off:off + 2])[0]
        if rtype != 0x21:
            return ""
        off += 10
        count = data[off]
        off += 1
        for i in range(count):
            entry = data[off + i * 18:off + i * 18 + 18]
            name, suffix, flags = entry[:15], entry[15], struct.unpack(">H", entry[16:18])[0]
            if suffix == 0x00 and not flags & 0x8000:
                return name.decode("ascii", "replace").strip()
    except (IndexError, struct.error):
        pass
    return ""


def _netbios_name(ip, timeout=1.5):
    """Ask a Windows PC (or NAS) for its computer name. Pure Python, works on any OS."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(netbios_query(), (ip, 137))
        data, _ = s.recvfrom(2048)
        return parse_netbios(data)
    except OSError:
        return ""
    finally:
        s.close()


def _upnp_devices(local_ip="", seconds=3):
    """Ask TVs, speakers, routers etc. to announce themselves (UPnP/SSDP).

    Returns {ip: {"name", "maker", "model", "type"}}.
    """
    import time
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    s = _multicast_socket(local_ip)
    s.settimeout(0.5)
    locations = {}
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
        s.sendto(msg, ("239.255.255.250", 1900))
        stop = time.monotonic() + seconds
        while time.monotonic() < stop:
            try:
                data, (ip, _) = s.recvfrom(8192)
            except socket.timeout:
                continue
            m = re.search(rb"(?im)^location:\s*(\S+)", data)
            if m and ip not in locations:
                locations[ip] = m.group(1).decode("ascii", "replace")
    except OSError:
        pass
    finally:
        s.close()

    def describe(item):
        ip, url = item
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                root = ET.fromstring(r.read(200_000))
        except Exception:
            return ip, None
        def find(tag):
            el = root.find(f".//{{*}}device/{{*}}{tag}")
            return (el.text or "").strip() if el is not None else ""
        dtype = find("deviceType").split(":")
        return ip, {"name": find("friendlyName"), "maker": find("manufacturer"),
                    "model": " ".join(x for x in (find("modelName"), find("modelNumber")) if x),
                    "type": dtype[3] if len(dtype) > 3 else ""}

    with ThreadPoolExecutor(max_workers=16) as pool:
        return {ip: info for ip, info in pool.map(describe, locations.items()) if info}


# Ports checked during a network check: the ones that say most about a device.
QUICK_PORTS = [554, 8554, 9100, 8008, 7000, 80, 443, 23, 21, 22]


def _port_open(ip, port, timeout=0.4):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _open_ports(ip, timeout=0.6, ports=None):
    ports = list(PORTS) if ports is None else ports
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        flags = list(pool.map(lambda p: _port_open(ip, p, timeout), ports))
    return [p for p, ok in zip(ports, flags) if ok]


def check_ports(device):
    """Fill in device.ports. Used by the 'What is it running?' button."""
    device.ports = _open_ports(device.ip)
    return device.ports


# ---- network facts --------------------------------------------------------

def default_gateway():
    """The router's address, or '' if we can't tell."""
    try:
        if IS_WINDOWS:
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True,
                                 timeout=5, creationflags=_NO_WINDOW).stdout
            m = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
        elif platform.system() == "Darwin":
            out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", out)
        else:
            out = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def my_mac_addresses():
    """MAC addresses of this computer, so we can label it 'This computer'."""
    from bugsweep.core import normalize_mac
    macs = set()
    try:
        cmd = ["getmac", "/fo", "csv", "/nh"] if IS_WINDOWS else ["ifconfig", "-a"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW).stdout
        for token in re.findall(r"[0-9A-Fa-f]{1,2}(?:[:-][0-9A-Fa-f]{1,2}){5}", out):
            if (mac := normalize_mac(token)):
                macs.add(mac)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return macs


def _adapter_block(ip):
    """The `ipconfig /all` (or `ifconfig`) section for the adapter that has this address."""
    try:
        cmd = ["ipconfig", "/all"] if IS_WINDOWS else ["ifconfig", "-a"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    # Adapters are separated by unindented header lines on every OS.
    for block in re.split(r"\n(?=\S)", out):
        if re.search(rf"(?<![\d.]){re.escape(ip)}(?![\d.])", block):
            return block
    return ""


def own_mac(ip):
    """Hardware ID of the network adapter that has this computer's address."""
    from bugsweep.core import normalize_mac
    m = re.search(r"[0-9A-Fa-f]{1,2}(?:[:-][0-9A-Fa-f]{1,2}){5}", _adapter_block(ip))
    return (normalize_mac(m.group(0)) or "") if m else ""


def own_network(ip, smallest_prefix=22):
    """The local network this address is on, e.g. 192.168.1.0/24.

    Very large networks (offices, campuses) are trimmed to the 1,022 addresses
    around this computer so a check still finishes in about a minute.
    """
    import ipaddress
    block = _adapter_block(ip)
    m = (re.search(r"(?:Subnet Mask|netmask|Mask)[ .:]*?(\d+\.\d+\.\d+\.\d+)", block, re.I)
         or re.search(r"netmask (0x[0-9a-f]{8})", block, re.I))
    mask = m.group(1) if m else "255.255.255.0"
    if mask.startswith("0x"):
        mask = str(ipaddress.IPv4Address(int(mask, 16)))
    try:
        net = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    except ValueError:
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
    if net.prefixlen < smallest_prefix:
        net = ipaddress.ip_network(f"{ip}/{smallest_prefix}", strict=False)
    return net


def is_online(ip):
    """One ping. Some phones ignore pings while asleep, so 'offline' isn't certain."""
    cmd = ["ping", "-n", "1", "-w", "800", ip] if IS_WINDOWS else ["ping", "-c", "1", "-W", "1", ip]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=4, creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "ttl=" in out.lower()


# ---- putting it together ----------------------------------------------------

def _run(pool, jobs, budget, on_done=None):
    """Run {key: (fn, args)} for up to `budget` seconds.

    Returns {key: result}; anything unfinished gets TOO_SLOW instead of
    silently disappearing.
    """
    from concurrent.futures import TimeoutError as FutureTimeout, as_completed
    futures = {pool.submit(fn, *args): key for key, (fn, args) in jobs.items()}
    results = {}
    try:
        for fut in as_completed(futures, timeout=budget):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception:
                results[key] = None
            if on_done:
                on_done(key, results[key])
    except FutureTimeout:
        pass
    for fut, key in futures.items():
        if key not in results:
            fut.cancel()
            results[key] = TOO_SLOW
            if on_done:
                on_done(key, TOO_SLOW)
    return results


def _found(value):
    return isinstance(value, str) and value not in ("", NO_ANSWER, TOO_SLOW)


def enrich(devices, live=True, progress=None, self_ip="", count=None, log=None):
    """Fill in maker/type for every device, and (when live) names, models and ports.

    progress(text) reports each stage, count(done, total) how many devices have
    been asked for their names, and log(text) every single lookup (--debug).
    """
    import time
    from bugsweep.core import load_vendors, match_vendor
    vendors = load_vendors()
    for d in devices:
        if not d.maker:
            d.maker = lookup_maker(d.mac) or ("Private address" if is_randomized(d.mac) else "")

    if live:
        started = time.monotonic()
        gateway = default_gateway()
        mine = my_mac_addresses()
        for d in devices:
            d.is_router = d.is_router or d.ip == gateway
            d.is_self = d.is_self or d.mac in mine or d.ip == self_ip
        others = [d for d in devices if not d.is_self]
        if progress:
            progress(f"Asking {len(others)} devices for their names...")

        # Names. Every lookup has its own short timeout, and the phase as a
        # whole gets a budget that grows with the network, so nobody's name is
        # cut off because the list was long.
        jobs = {("*", "upnp"): (_upnp_devices, (self_ip,)),
                ("*", "mdns_browse"): (_mdns_browse, (self_ip,))}
        for d in others:
            jobs[(d.ip, "rdns")] = (_reverse_dns, (d.ip,))
            jobs[(d.ip, "mdns")] = (_mdns_name, (d.ip,))
            jobs[(d.ip, "netbios")] = (_netbios_name, (d.ip,))
        pending = {d.ip: 3 for d in others}
        done = [0]

        def on_name(key, result):
            ip, method = key
            if log:
                shown = f"{len(result)} device(s) answered" if isinstance(result, dict) else (result or NO_ANSWER)
                log(f"  {ip:<15} {method:<12} -> {shown}")
            if ip in pending:
                pending[ip] -= 1
                if pending[ip] == 0:
                    done[0] += 1
                    if count:
                        count(done[0], len(others))

        pool = ThreadPoolExecutor(max_workers=64)
        names = _run(pool, jobs, min(60, max(15, len(others) * 0.5)), on_name)
        pool.shutdown(wait=False, cancel_futures=True)
        upnp = names[("*", "upnp")] if isinstance(names[("*", "upnp")], dict) else {}
        bonjour = names[("*", "mdns_browse")] if isinstance(names[("*", "mdns_browse")], dict) else {}

        # What each device is running (camera stream, printer port...).
        if progress:
            progress("Checking what each device is running...")
        port_jobs = {(d.ip, p): (_port_open, (d.ip, p)) for d in others for p in QUICK_PORTS}
        pool = ThreadPoolExecutor(max_workers=128)
        ports = _run(pool, port_jobs, min(30, max(8, len(others) * 0.2)))
        pool.shutdown(wait=False, cancel_futures=True)

        for d in others:
            u, b = upnp.get(d.ip, {}), bonjour.get(d.ip, {})
            d.ports = [p for p in QUICK_PORTS if ports.get((d.ip, p)) is True]
            d.services = b.get("services", [])
            raw = {"upnp": u.get("name"), "mdns_browse": b.get("name"), "mdns": names[(d.ip, "mdns")],
                   "netbios": names[(d.ip, "netbios")], "rdns": names[(d.ip, "rdns")]}
            d.lookups = {k: (v if _found(v) or v == TOO_SLOW else NO_ANSWER) for k, v in raw.items()}
            d.name = d.name or next((v for v in d.lookups.values() if _found(v)), "")
            d.model = d.model or " ".join(x for x in (u.get("maker"), u.get("model")) if x) or b.get("model", "")
            d.found_by = sorted({LOOKUP_SHORT[k] for k, v in d.lookups.items() if _found(v)})
        if log:
            log(f"Identification took {time.monotonic() - started:.1f}s "
                f"(UPnP answers: {len(upnp)}, Bonjour answers: {len(bonjour)})")

    for d in devices:
        if not d.kind:
            d.kind = guess_kind(d, is_dev_board=match_vendor(d.mac, vendors) is not None)
    return devices
