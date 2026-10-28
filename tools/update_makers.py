"""Rebuild bugsweep's maker lists from the official IEEE registry.

    python tools/update_makers.py

Writes:
  bugsweep/data/makers.tsv.gz  every registered prefix -> company (for "Chip maker")
  bugsweep/data/vendors.csv    the dev-board makers that get flagged
"""

import csv
import gzip
import io
import re
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "bugsweep" / "data"
SOURCES = [
    "https://standards-oui.ieee.org/oui/oui.csv",      # 24-bit blocks (most companies)
    "https://standards-oui.ieee.org/oui28/mam.csv",    # 28-bit blocks
    "https://standards-oui.ieee.org/oui36/oui36.csv",  # 36-bit blocks
]

# (match in IEEE company name, display name, note shown to people)
DEV_BOARD_MAKERS = [
    ("espressif", "Espressif",
     "Espressif chips (ESP32/ESP8266) power most cheap Wi-Fi dev boards, but are also inside many smart plugs, bulbs and sensors."),
    ("raspberry pi", "Raspberry Pi",
     "Raspberry Pi mini computers are popular with hobbyists and sometimes used as media players or home servers."),
    ("arduino", "Arduino", "Arduino boards are hobby electronics kits."),
    ("seeed technology", "Seeed Studio", "Seeed makes small hobby boards (XIAO, Wio) often built on ESP32 chips."),
    ("adafruit", "Adafruit", "Adafruit makes hobby electronics boards."),
    ("particle industries", "Particle", "Particle makes small Wi-Fi and cellular boards for gadget builders."),
    ("wiznet", "WIZnet", "WIZnet chips add networking to hobby and industrial boards."),
    ("ai-thinker", "Ai-Thinker", "Ai-Thinker makes cheap Wi-Fi modules (ESP-01, ESP32-CAM) used in DIY gadgets."),
    ("bouffalo", "Bouffalo Lab", "Bouffalo Lab chips are used in cheap Wi-Fi modules and some smart-home gadgets."),
]

_SUFFIX = re.compile(r"[\s,.]+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|gmbh|ag|sa|s\.a|"
                     r"pte|plc|bv|b\.v|oy|ab|as|srl|spa|kk|pty)\b\.?", re.I)


def tidy(name):
    """'Espressif Systems (Singapore) Pte. Ltd' -> 'Espressif Systems (Singapore)'."""
    name = " ".join(name.split())
    for _ in range(3):
        name = _SUFFIX.sub("", name).strip(" ,.")
    return name or "Unknown"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (bugsweep maker-list updater)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8")


def main():
    makers = {}
    for url in SOURCES:
        print("Downloading", url)
        for row in csv.DictReader(io.StringIO(fetch(url))):
            prefix = row["Assignment"].strip().upper()
            if re.fullmatch(r"[0-9A-F]{6,9}", prefix):
                makers[prefix] = row["Organization Name"].strip()
    if len(makers) < 30000:
        sys.exit(f"Only got {len(makers)} prefixes, refusing to overwrite.")

    with gzip.open(DATA / "makers.tsv.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        for prefix in sorted(makers):
            f.write(f"{prefix}\t{tidy(makers[prefix])}\n")

    with open(DATA / "vendors.csv", "w", newline="", encoding="utf-8") as f:
        f.write("# Dev-board makers that bugsweep flags. Generated from the IEEE registry by\n"
                "# tools/update_makers.py - edit DEV_BOARD_MAKERS there, or add rows by hand and send a PR.\n")
        w = csv.writer(f)
        w.writerow(["prefix", "vendor", "note"])
        total = 0
        for needle, display, note in DEV_BOARD_MAKERS:
            hits = sorted(p for p, n in makers.items() if needle in n.lower())
            total += len(hits)
            print(f"  {display}: {len(hits)} prefixes")
            for p in hits:
                w.writerow([":".join(p[i:i + 2] for i in range(0, len(p), 2)), display, note])
    print(f"Wrote {len(makers)} makers and {total} dev-board prefixes.")


if __name__ == "__main__":
    main()
