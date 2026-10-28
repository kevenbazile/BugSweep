"""Matching logic: devices in, plain-language findings out.

A MAC address (hardware ID) looks like 24:0A:C4:3B:7E:19. The first half
(24:0A:C4) is the vendor prefix, which says who made the network chip. We
compare that prefix against companies that make cheap Wi-Fi dev boards.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
VENDORS_FILE = PACKAGE_DIR / "data" / "vendors.csv"
SAMPLES_DIR = REPO_DIR / "samples"
USER_DIR = Path.home() / ".bugsweep"
DEFAULT_BASELINE = USER_DIR / "baseline.json"
LABELS_FILE = USER_DIR / "labels.json"

_HEX = re.compile(r"[0-9a-fA-F]{1,2}")
_SEPARATED = re.compile(r"^[0-9a-fA-F]{1,2}([:-][0-9a-fA-F]{1,2}){5}$")
_DOTTED = re.compile(r"^[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$")
_PLAIN = re.compile(r"^[0-9a-fA-F]{12}$")


def normalize_mac(text):
    """Return a MAC as 'AA:BB:CC:DD:EE:FF', or None if it isn't one.

    Accepts aa-bb-cc-dd-ee-ff (Windows), a:b:c:d:e:f (macOS drops leading
    zeros), aabb.ccdd.eeff (Cisco) and aabbccddeeff.
    """
    text = (text or "").strip()
    if _SEPARATED.match(text):
        parts = [p.zfill(2) for p in _HEX.findall(text)]
    elif _DOTTED.match(text) or _PLAIN.match(text):
        flat = text.replace(".", "")
        parts = [flat[i:i + 2] for i in range(0, 12, 2)]
    else:
        return None
    return ":".join(parts).upper()


def is_randomized(mac):
    """True if the MAC is a 'private' address that phones and laptops make up.

    These have the locally-administered bit set, so their prefix never
    belongs to a real manufacturer.
    """
    return int(mac[1], 16) & 0b0010 != 0


def is_ignorable(mac):
    """Broadcast and multicast addresses aren't real devices."""
    return mac == "FF:FF:FF:FF:FF:FF" or int(mac[:2], 16) & 1 == 1


@dataclass
class Device:
    ip: str
    mac: str
    name: str = ""
    maker: str = ""          # company that made the network chip
    kind: str = ""           # best guess: "Printer", "Camera", ...
    model: str = ""          # what the device says it is (UPnP), if anything
    ports: list = field(default_factory=list)
    services: list = field(default_factory=list)   # Bonjour services, e.g. "_googlecast._tcp"
    found_by: list = field(default_factory=list)
    lookups: dict = field(default_factory=dict)    # name lookup -> what it returned ("no answer"...)
    is_self: bool = False
    is_router: bool = False


@dataclass
class Vendor:
    prefix: str  # hex digits only, e.g. "240AC4"
    name: str
    note: str = ""


LEVELS = {
    # level: (label in the table, sort order)
    "alert": ("Needs a look", 0),
    "camera": ("Camera", 1),
    "new": ("New", 2),
    "unknown": ("Unidentified", 3),
    "ok": ("OK", 4),
    "known": ("Known", 5),
}


@dataclass
class Finding:
    device: Device
    vendor: Vendor | None = None
    is_new: bool = False
    randomized: bool = False
    label: dict = field(default_factory=dict)  # {"what", "where", "known"} set by the person

    @property
    def is_dev_board(self):
        return self.vendor is not None

    @property
    def display_name(self):
        return self.label.get("what") or self.device.name or ""

    @property
    def level(self):
        if self.label.get("known") or self.device.is_self:
            return "known"
        if self.is_dev_board:
            return "alert"
        if self.device.kind == "Camera":
            return "camera"
        if self.is_new:
            return "new"
        if not self.device.name and self.device.kind in ("", "Unknown"):
            return "unknown"
        return "ok"

    def explain(self):
        """A few plain-English sentences about this device."""
        d = self.device
        if d.is_self:
            return "This is the computer you're using right now."
        parts = []
        if self.label.get("known"):
            parts.append("You marked this device as known, so it won't be flagged.")
        if self.is_dev_board:
            parts.append(f"The network chip in this device was made by {self.vendor.name}, a company whose "
                         f"chips are used in cheap hobby circuit boards. {self.vendor.note}")
        elif d.kind == "Camera":
            parts.append("This looks like a camera. That's normal if it's your security camera or doorbell, "
                         "but make sure you know where every camera on your network is.")
        elif d.is_router:
            parts.append("This is your router: the box that connects your network to the internet.")
        if self.is_new:
            parts.append("It wasn't here when you saved your 'normal' list.")
        if self.randomized:
            parts.append("It uses a private (made-up) hardware ID, which phones, tablets and laptops do to "
                         "protect your privacy. That's why the maker can't be shown.")
        if d.maker.startswith("Virtual router"):
            parts.append("Its address is a 'virtual router' address. Managed networks (offices, campuses, "
                         "apartment buildings) use these, so this network is probably shared.")
        if self.level == "unknown":
            parts.append("We couldn't work out what this is: it didn't share a name and its maker isn't a "
                         "consumer brand. Use the steps below to find it.")
        if not parts:
            parts.append("Nothing unusual about this one.")
        return " ".join(parts)


@dataclass
class Report:
    findings: list
    source: str
    baseline_used: bool
    demo: bool = False
    network: dict = field(default_factory=dict)  # facts about the network, from scanner.scan
    created: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    @property
    def shared_reasons(self):
        """Why this looks like a shared network that hides devices (empty if it doesn't)."""
        if self.demo or not self.network:
            return []
        return shared_network_reasons(self.network.get("size", 0), self.network.get("vrrp", False),
                                      len(self.findings))

    @property
    def shared(self):
        return bool(self.shared_reasons)

    def by_level(self, level):
        return [f for f in self.findings if f.level == level]

    @property
    def alerts(self):
        return self.by_level("alert")

    @property
    def new_devices(self):
        return self.by_level("new")

    @property
    def cameras(self):
        return self.by_level("camera")

    def summary(self):
        total = len(self.findings)
        bits = []
        if self.alerts:
            n = len(self.alerts)
            bits.append(f"{n} {'looks' if n == 1 else 'look'} like a hobby circuit board")
        if self.cameras:
            n = len(self.cameras)
            bits.append(f"{n} {'is a camera' if n == 1 else 'are cameras'}")
        if self.new_devices:
            n = len(self.new_devices)
            bits.append(f"{n} {'is' if n == 1 else 'are'} new")
        if unknown := self.by_level("unknown"):
            n = len(unknown)
            bits.append(f"{n} couldn't be identified")
        if not bits:
            return f"All clear. {total} devices checked and nothing needs your attention."
        return f"{total} devices found: " + ", ".join(bits) + "."


SHARED_NOTE = ("This looks like a shared network (apartment building, campus, hotel or office). These hide "
               "other people's devices and their names on purpose, so BugSweep may not see every device and "
               "often can't get their names. On your own home Wi-Fi you'll see much more.")


def shared_network_reasons(size, vrrp, device_count):
    """Plain-English reasons a network looks shared/isolated, or [] if it looks like a home network."""
    reasons = []
    if size > 1024:
        reasons.append(f"it's very large ({size:,} addresses; home networks have about 254)")
    if vrrp:
        reasons.append("its router uses a 'virtual router' address, which managed networks use")
    if device_count <= 5:
        reasons.append(f"only {device_count} device{'s' if device_count != 1 else ''} could be seen")
    return reasons


def load_vendors(path=VENDORS_FILE):
    vendors = {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = (line for line in f if line.strip() and not line.lstrip().startswith("#"))
        for row in csv.DictReader(rows):
            prefix = re.sub(r"[^0-9A-Fa-f]", "", row["prefix"]).upper()
            if len(prefix) >= 6:
                vendors[prefix] = Vendor(prefix, row["vendor"].strip(), (row.get("note") or "").strip())
    return vendors


def match_vendor(mac, vendors):
    """Longest-prefix match, so 28- and 36-bit blocks beat the 24-bit ones."""
    flat = mac.replace(":", "")
    for length in (9, 7, 6):
        hit = vendors.get(flat[:length])
        if hit:
            return hit
    return None


def load_devices(path):
    """Read a device list from .csv or .json.

    Columns: ip, mac, name, and optionally model and ports (e.g. "80;554").
    """
    path = Path(path)
    if path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    devices = []
    for row in rows:
        mac = normalize_mac(row.get("mac", ""))
        if mac and not is_ignorable(mac):
            ports = row.get("ports") or []
            if isinstance(ports, str):
                ports = [int(p) for p in re.findall(r"\d+", ports)]
            devices.append(Device(row.get("ip", "").strip(), mac, (row.get("name") or "").strip(),
                                  model=(row.get("model") or "").strip(), ports=ports))
    return devices


def load_baseline(path=DEFAULT_BASELINE):
    """Return {mac: name} from a saved baseline, or None if there isn't one."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("devices", {})
    except FileNotFoundError:
        return None


def save_baseline(devices, path=DEFAULT_BASELINE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "devices": {d.mac: d.name for d in sorted(devices, key=lambda d: d.mac)},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def load_labels(path=LABELS_FILE):
    """{mac: {"what": "Living room TV", "where": "Above the fireplace", "known": True}}"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_label(mac, what="", where="", known=False, path=LABELS_FILE):
    labels = load_labels(path)
    entry = {k: v for k, v in (("what", what.strip()), ("where", where.strip()), ("known", known)) if v}
    if entry:
        labels[mac] = entry
    else:
        labels.pop(mac, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2)
    return entry


def check(devices, vendors=None, baseline=None, labels=None, source="", demo=False, network=None):
    """Classify every device. Anything needing attention sorts to the top."""
    vendors = load_vendors() if vendors is None else vendors
    labels = {} if labels is None else labels
    findings = []
    for d in devices:
        findings.append(Finding(
            device=d,
            vendor=match_vendor(d.mac, vendors),
            is_new=baseline is not None and d.mac not in baseline,
            randomized=is_randomized(d.mac),
            label=labels.get(d.mac, {}),
        ))
    findings.sort(key=lambda f: (LEVELS[f.level][1], _ip_key(f.device.ip)))
    return Report(findings, source, baseline is not None, demo, network or {})


def _ip_key(ip):
    try:
        return tuple(int(x) for x in ip.split("."))
    except ValueError:
        return (999,)


def report_text(report, support=None):
    """A plain-text report people can email to tech support."""
    from bugsweep import __version__
    from bugsweep.identify import PORTS
    import platform

    lines = [
        "BugSweep report",
        "===============",
        f"Created:   {report.created}",
        f"Version:   {__version__}",
        f"Computer:  {platform.system()} {platform.release()}",
        f"Source:    {report.source}",
        f"Compared with saved 'normal' list: {'yes' if report.baseline_used else 'no'}",
        "",
        f"Result: {report.summary()}",
        "",
    ]
    for f in report.findings:
        d = f.device
        lines.append(f"[{LEVELS[f.level][0]:>12}]  {d.ip:<16} {d.mac}  {f.display_name or '(no name)'}")
        lines.append(f"{'':16}Type: {d.kind or 'Unknown'}   Maker: {d.maker or 'unknown'}"
                     + (f"   Model: {d.model}" if d.model else ""))
        if f.label.get("where"):
            lines.append(f"{'':16}Location (your note): {f.label['where']}")
        if d.ports:
            lines.append(f"{'':16}Running: " + ", ".join(f"{PORTS[p][0]} ({p})" for p in d.ports if p in PORTS))
        if f.level not in ("ok", "known"):
            lines.append(f"{'':16}{f.explain()}")
        if d.lookups:
            lines.append(f"{'':16}Name lookups: " + "; ".join(f"{k}: {v}" for k, v in d.lookups.items()))
        lines.append("")
    if report.network:
        n = report.network
        lines += [
            "Diagnostics (for tech support)",
            "------------------------------",
            f"This computer:  {n.get('self_ip', '?')} on adapter {n.get('self_mac', '?')}",
            f"Network:        {n.get('network', '?')} ({n.get('size', 0):,} addresses), "
            f"checked {n.get('swept', '?')}",
            f"Router:         {n.get('gateway') or 'not found'}" + (" (virtual router)" if n.get("vrrp") else ""),
            f"Looks shared:   {'yes - ' + '; '.join(report.shared_reasons) if report.shared else 'no'}",
            f"Took:           {n.get('seconds', '?')} seconds",
            "",
        ]
    if support:
        lines += [f"Questions? Contact {support.get('name', 'tech support')}: "
                  + ", ".join(v for k, v in support.items() if k in ("email", "phone", "website") and v)]
    return "\n".join(lines) + "\n"
