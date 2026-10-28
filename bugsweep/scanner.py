"""Read the devices your computer can see on your own network.

Your computer keeps a short list (the "ARP table") of nearby devices it has
talked to. We optionally ping every address on your local network first so
that list is complete, then read it with the built-in `arp -a` command.
Nothing is recorded, intercepted or sent anywhere.
"""

import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from bugsweep.core import Device, is_ignorable, normalize_mac

IS_WINDOWS = platform.system() == "Windows"
# Stop a console window flashing up for every ping when run from the app.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC = re.compile(r"\b([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})\b")


class ScanError(Exception):
    """Something went wrong in a way a non-technical person should be told about."""


def local_ip():
    """This computer's address on the local network.

    Connecting a UDP socket picks the right network card without sending
    any packets.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        raise ScanError("This computer doesn't seem to be connected to a network. "
                        "Check your Wi-Fi or cable, then try again.")
    finally:
        s.close()


def _ping(ip):
    cmd = ["ping", "-n", "1", "-w", "400", ip] if IS_WINDOWS else ["ping", "-c", "1", "-W", "1", ip]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=3, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        pass


def wake_network(net, extra=(), progress=None):
    """Ping every address in `net` so they all appear in the ARP table."""
    me = local_ip()
    hosts = [str(h) for h in net.hosts() if str(h) != me]
    hosts += [ip for ip in extra if ip and ip not in hosts]
    done = 0
    with ThreadPoolExecutor(max_workers=128) as pool:
        for _ in pool.map(_ping, hosts):
            done += 1
            if progress and done % 16 == 0:
                progress(done, len(hosts))


def parse_arp(text):
    """Pull (ip, mac) pairs out of `arp -a` output on Windows, macOS or Linux."""
    found = {}
    for line in text.splitlines():
        ip, mac = _IP.search(line), _MAC.search(line)
        if not (ip and mac):
            continue
        norm = normalize_mac(mac.group(1))
        if norm and not is_ignorable(norm):
            found.setdefault(norm, ip.group(1))
    return [Device(ip, mac) for mac, ip in found.items()]


def read_arp_table():
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=20,
                             creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        raise ScanError("Couldn't read the list of nearby devices from this computer.")
    return parse_arp(out)


def scan(thorough=True, progress=None, status=None, count=None, log=None):
    """Identify the devices on this computer's local network.

    Returns (devices, network_info). progress(done, total) reports the ping
    sweep, count(done, total) the name lookups, status(text) each stage and
    log(text) every lookup (for --debug).
    """
    import time
    from bugsweep.identify import VRRP_MAKER, default_gateway, enrich, own_mac, own_network

    started = time.monotonic()
    me = local_ip()
    network = own_network(me, smallest_prefix=0)
    sweep = own_network(me)  # trimmed to ~1,000 addresses on very large networks
    gateway = default_gateway()
    if thorough:
        if status:
            status(f"Looking for devices on your network ({sweep.num_addresses - 2:,} addresses)...")
        wake_network(sweep, extra=[gateway], progress=progress)
    devices = [d for d in read_arp_table() if ipaddress.ip_address(d.ip) in network]
    if not devices:
        raise ScanError("No other devices were found. Make sure this computer is on "
                        "the network you want to check, then try again.")
    # The ARP table never lists this computer itself, so add it for completeness.
    mine = own_mac(me)
    if mine and not any(d.ip == me for d in devices):
        devices.append(Device(me, mine, socket.gethostname(), is_self=True))
    enrich(devices, live=True, progress=status, self_ip=me, count=count, log=log)

    router = next((d for d in devices if d.is_router), None)
    info = {
        "self_ip": me, "self_mac": mine, "network": str(network), "size": network.num_addresses - 2,
        "swept": str(sweep) if thorough else "no (quick)", "gateway": gateway,
        "vrrp": bool(router and router.maker == VRRP_MAKER),
        "seconds": round(time.monotonic() - started, 1),
    }
    _save_last_scan(devices, info)
    return devices, info


def _save_last_scan(devices, info):
    """Keep the last check in ~/.bugsweep/last_scan.json so tech support can see what happened."""
    import json
    from dataclasses import asdict
    from datetime import datetime
    from bugsweep.core import USER_DIR
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        data = {"saved_at": datetime.now().isoformat(timespec="seconds"), "network": info,
                "devices": [asdict(d) for d in devices]}
        (USER_DIR / "last_scan.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def sweep_size():
    """How many addresses a thorough check will ping (for the progress bar)."""
    from bugsweep.identify import own_network
    return own_network(local_ip()).num_addresses - 2
