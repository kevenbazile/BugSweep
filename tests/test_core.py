import json
import tempfile
import unittest
from pathlib import Path

from bugsweep.core import (Device, check, is_randomized, load_baseline, load_devices, load_vendors,
                           match_vendor, normalize_mac, report_text, save_baseline)
from bugsweep.cli import DEMO_BASELINE, DEMO_SCAN, main
from bugsweep.scanner import parse_arp

WINDOWS_ARP = """
Interface: 192.168.1.23 --- 0x7
  Internet Address      Physical Address      Type
  192.168.1.1           a4-83-e7-11-22-33     dynamic
  192.168.1.40          24-0a-c4-3b-7e-19     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""

MAC_ARP = """
? (192.168.1.1) at a4:83:e7:11:22:33 on en0 ifscope [ethernet]
? (192.168.1.40) at 24:a:c4:3b:7e:19 on en0 ifscope [ethernet]
? (192.168.1.99) at (incomplete) on en0 ifscope [ethernet]
"""


class NormalizeTest(unittest.TestCase):
    def test_formats(self):
        for raw in ("24:0a:c4:3b:7e:19", "24-0A-C4-3B-7E-19", "24:a:c4:3b:7e:19",
                    "240a.c43b.7e19", "240AC43B7E19"):
            self.assertEqual(normalize_mac(raw), "24:0A:C4:3B:7E:19", raw)

    def test_rejects_junk(self):
        for raw in ("", "hello", "24:0a:c4", "(incomplete)", "zz:zz:zz:zz:zz:zz"):
            self.assertIsNone(normalize_mac(raw))

    def test_randomized(self):
        self.assertTrue(is_randomized("B2:93:9C:E8:6F:84"))
        self.assertFalse(is_randomized("24:0A:C4:3B:7E:19"))


class VendorTest(unittest.TestCase):
    def setUp(self):
        self.vendors = load_vendors()

    def test_known_boards(self):
        self.assertEqual(match_vendor("24:0A:C4:00:00:01", self.vendors).name, "Espressif")
        self.assertEqual(match_vendor("B8:27:EB:00:00:01", self.vendors).name, "Raspberry Pi")

    def test_ordinary_device(self):
        self.assertIsNone(match_vendor("F0:18:98:00:00:01", self.vendors))

    def test_vendor_file_is_clean(self):
        for prefix in self.vendors:
            self.assertRegex(prefix, r"^[0-9A-F]{6,9}$")


class DemoTest(unittest.TestCase):
    """The repo must reproduce the video: 40 devices, exactly one board."""

    def test_sample_has_one_board_in_forty(self):
        devices = load_devices(DEMO_SCAN)
        self.assertEqual(len(devices), 40)
        report = check(devices, baseline=load_baseline(DEMO_BASELINE))
        self.assertEqual(len(report.alerts), 1)
        self.assertEqual(report.alerts[0].device.mac, "24:0A:C4:3B:7E:19")
        self.assertEqual(report.new_devices, [])

    def test_demo_command_exit_code(self):
        self.assertEqual(main(["demo"]), 2)


class BaselineTest(unittest.TestCase):
    def test_new_device_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            laptop = Device("10.0.0.2", "F0:18:98:00:00:01", "laptop")
            save_baseline([laptop], path)
            self.assertIn(laptop.mac, json.loads(path.read_text())["devices"])
            visitor = Device("10.0.0.3", "3C:22:FB:00:00:02", "")
            report = check([laptop, visitor], baseline=load_baseline(path))
            self.assertEqual([f.device for f in report.new_devices], [visitor])

    def test_missing_baseline(self):
        self.assertIsNone(load_baseline(Path(tempfile.gettempdir()) / "does-not-exist.json"))


class ArpTest(unittest.TestCase):
    def test_windows(self):
        devices = parse_arp(WINDOWS_ARP)
        self.assertEqual([d.mac for d in devices], ["A4:83:E7:11:22:33", "24:0A:C4:3B:7E:19"])

    def test_macos(self):
        devices = parse_arp(MAC_ARP)
        self.assertEqual([(d.ip, d.mac) for d in devices],
                         [("192.168.1.1", "A4:83:E7:11:22:33"), ("192.168.1.40", "24:0A:C4:3B:7E:19")])


class IdentifyTest(unittest.TestCase):
    def test_every_demo_device_has_a_type(self):
        from bugsweep.cli import demo_devices
        for d in demo_devices():
            self.assertNotIn(d.kind, ("", "Unknown"), d)

    def test_makers(self):
        from bugsweep.identify import lookup_maker
        self.assertEqual(lookup_maker("24:0A:C4:3B:7E:19"), "Espressif")
        self.assertEqual(lookup_maker("B2:93:9C:E8:6F:84"), "")  # private address

    def test_kinds(self):
        from bugsweep.identify import guess_kind
        cases = [
            (Device("1", "00:00:00:00:00:01", "lobby-cam", maker="Hangzhou Hikvision Digital Technology"), "Camera"),
            (Device("1", "00:00:00:00:00:01", "", maker="Anything", ports=[554]), "Camera"),
            (Device("1", "00:00:00:00:00:01", "", maker="Brother industries"), "Printer"),
            (Device("1", "00:00:00:00:00:01", "voip-phone-1", maker="Polycom"), "Desk phone"),
            (Device("1", "00:00:00:00:00:01", "spring-laptop", maker="Dell"), "Computer"),
            (Device("1", "B2:00:00:00:00:01", ""), "Phone, tablet or laptop (private address)"),
            (Device("1", "00:00:00:00:00:01", "", is_router=True), "Your router"),
            # Big brands with no telling name get an honest "could be" label...
            (Device("1", "00:00:00:00:00:01", "", maker="Samsung Electronics"), "Samsung device (phone, TV or appliance)"),
            (Device("1", "00:00:00:00:00:01", "", maker="Google"), "Google device (phone, Nest or Chromecast)"),
            (Device("1", "00:00:00:00:00:01", "", maker="Amazon Technologies"), "Amazon device (Echo, Fire TV, Kindle or Ring)"),
            # ...but the device's own name wins over its chip maker.
            (Device("1", "00:00:00:00:00:01", "Kitchen TV", maker="Samsung Electronics"), "TV or streaming box"),
            (Device("1", "00:00:00:00:00:01", "ceo-macbook", maker="Apple"), "Computer"),
            (Device("1", "00:00:00:00:00:01", "", services=["_ipp._tcp"]), "Printer"),
            (Device("1", "00:00:00:00:00:01", "", maker="Virtual router (business/shared network)"), "Router or Wi-Fi"),
        ]
        for device, kind in cases:
            self.assertEqual(guess_kind(device), kind, device)

    def test_vrrp_maker(self):
        from bugsweep.identify import VRRP_MAKER, lookup_maker
        self.assertEqual(lookup_maker("00:00:5E:00:01:34"), VRRP_MAKER)
        self.assertEqual(lookup_maker("00:00:5E:00:02:01"), VRRP_MAKER)


def _dns_name_bytes(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def _rr(name, rtype, rdata):
    import struct
    return _dns_name_bytes(name) + struct.pack(">HHIH", rtype, 1, 120, len(rdata)) + rdata


class NameLookupTest(unittest.TestCase):
    def test_netbios_reply(self):
        import struct
        from bugsweep.identify import netbios_query, parse_netbios
        query = netbios_query()
        self.assertEqual(len(query), 50)
        names = [(b"WORKGROUP".ljust(15), 0x00, 0x8400),  # group name: skipped
                 (b"FRONT-DESK-PC".ljust(15), 0x00, 0x0400),
                 (b"FRONT-DESK-PC".ljust(15), 0x20, 0x0400)]
        body = bytes([len(names)]) + b"".join(n + bytes([s]) + struct.pack(">H", f) for n, s, f in names)
        reply = (struct.pack(">HHHHHH", 0x4242, 0x8400, 0, 1, 0, 0) + query[12:12 + 34]
                 + struct.pack(">HHIH", 0x21, 1, 0, len(body)) + body)
        self.assertEqual(parse_netbios(reply), "FRONT-DESK-PC")
        self.assertEqual(parse_netbios(b"\x00" * 5), "")

    def test_mdns_answers(self):
        import socket
        import struct
        from bugsweep.identify import parse_mdns_answers
        inst = "Lounge TV._googlecast._tcp.local"
        txt = b"".join(bytes([len(x)]) + x for x in (b"fn=Lounge TV", b"md=Chromecast"))
        records = [
            _rr("_googlecast._tcp.local", 12, _dns_name_bytes(inst)),
            _rr(inst, 33, struct.pack(">HHH", 0, 0, 8009) + _dns_name_bytes("abc123.local")),
            _rr(inst, 16, txt),
            _rr("abc123.local", 1, socket.inet_aton("192.168.1.50")),
            _rr("Jordans-iPhone.local", 1, socket.inet_aton("192.168.1.60")),
        ]
        packet = struct.pack(">HHHHHH", 0, 0x8400, 0, len(records), 0, 0) + b"".join(records)
        found = parse_mdns_answers([packet, b"junk"])
        self.assertEqual(found["192.168.1.50"]["name"], "Lounge TV")
        self.assertEqual(found["192.168.1.50"]["model"], "Chromecast")
        self.assertEqual(found["192.168.1.50"]["services"], ["_googlecast._tcp"])
        self.assertEqual(found["192.168.1.60"]["name"], "Jordans-iPhone")

    def test_slow_ports_dont_lose_names(self):
        """The old bug: one shared 15 s timeout cancelled name lookups on bigger networks."""
        import time
        from unittest import mock
        import bugsweep.identify as ident
        devices = [Device(f"10.0.0.{i}", f"F0:18:98:00:00:{i:02X}") for i in range(2, 42)]

        def slow_port(ip, port, timeout=0.4):
            time.sleep(0.05)
            return False
        with mock.patch.object(ident, "_reverse_dns", lambda ip: f"host-{ip.rsplit('.', 1)[1]}"), \
             mock.patch.object(ident, "_mdns_name", lambda ip: ""), \
             mock.patch.object(ident, "_netbios_name", lambda ip: ""), \
             mock.patch.object(ident, "_upnp_devices", lambda ip="": {}), \
             mock.patch.object(ident, "_mdns_browse", lambda ip="": {}), \
             mock.patch.object(ident, "_port_open", slow_port), \
             mock.patch.object(ident, "default_gateway", lambda: "10.0.0.2"), \
             mock.patch.object(ident, "my_mac_addresses", lambda: set()):
            counts = []
            ident.enrich(devices, live=True, count=lambda done, total: counts.append((done, total)))
        self.assertTrue(all(d.name.startswith("host-") for d in devices))
        self.assertEqual(devices[0].kind, "Your router")
        self.assertEqual(devices[5].lookups["mdns"], "no answer")
        self.assertEqual(devices[5].found_by, ["router"])
        self.assertEqual(counts[-1], (40, 40))


class SharedNetworkTest(unittest.TestCase):
    def test_reasons(self):
        from bugsweep.core import shared_network_reasons
        self.assertEqual(shared_network_reasons(254, False, 24), [])
        self.assertEqual(len(shared_network_reasons(8190, True, 3)), 3)

    def test_report_flag(self):
        devices = [Device("10.0.0.2", "F0:18:98:00:00:01", "laptop")]
        self.assertTrue(check(devices, network={"size": 8190, "vrrp": True}).shared)
        self.assertFalse(check(devices, network={"size": 8190}, demo=True).shared)
        self.assertFalse(check(devices).shared)

    def test_demo_levels(self):
        from bugsweep.cli import demo_devices
        report = check(demo_devices(), baseline=load_baseline(DEMO_BASELINE))
        self.assertEqual([f.device.ip for f in report.cameras], ["10.20.0.38"])
        self.assertEqual(report.findings[0].level, "alert")


class LabelTest(unittest.TestCase):
    def test_known_stops_flagging(self):
        from bugsweep.core import load_labels, save_label
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            board = Device("10.0.0.9", "24:0A:C4:3B:7E:19", "")
            self.assertEqual(check([board]).findings[0].level, "alert")
            save_label(board.mac, "Smart plug", "Kitchen", True, path=path)
            f = check([board], labels=load_labels(path)).findings[0]
            self.assertEqual((f.level, f.display_name, f.label["where"]), ("known", "Smart plug", "Kitchen"))
            save_label(board.mac, path=path)  # clearing everything removes the entry
            self.assertEqual(load_labels(path), {})


class ReportTest(unittest.TestCase):
    def test_report_mentions_support(self):
        from bugsweep.cli import demo_devices
        report = check(demo_devices(), baseline=load_baseline(DEMO_BASELINE), source="demo")
        text = report_text(report, {"name": "Help Desk", "email": "help@example.com"})
        self.assertIn("[Needs a look]  10.20.0.31", text)
        self.assertIn("Type: Camera", text)
        self.assertIn("help@example.com", text)


if __name__ == "__main__":
    unittest.main()
