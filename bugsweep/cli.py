"""Command line: `python -m bugsweep <command>`. With no command, opens the app window."""

import argparse
import os
import sys
from pathlib import Path

from bugsweep import __version__
from bugsweep.core import (DEFAULT_BASELINE, LEVELS, SAMPLES_DIR, SHARED_NOTE, check, load_baseline, load_devices,
                           load_labels, report_text, save_baseline)
from bugsweep.support import contact_lines, has_agreed, load_support, record_agreement

RED, YELLOW, GREEN, MAGENTA, CYAN, DIM, RESET = (
    "\033[91m", "\033[93m", "\033[92m", "\033[95m", "\033[96m", "\033[2m", "\033[0m")
DEMO_SCAN = SAMPLES_DIR / "sample_scan.csv"
DEMO_BASELINE = SAMPLES_DIR / "sample_baseline.json"


def _color_ok():
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if os.name == "nt":
        os.system("")  # turns on colour support in the Windows console
    return True


def _confirm_ownership(args):
    if has_agreed() or args.yes:
        return True
    print("Only scan networks you own or have permission to check (your home, or work with IT's OK).")
    if input("Type 'yes' to confirm: ").strip().lower() == "yes":
        record_agreement()
        return True
    print("Okay, nothing was scanned.")
    return False


def _get_devices(args):
    """Returns (devices, source description, network info)."""
    from bugsweep.identify import enrich
    if args.file:
        return enrich(load_devices(args.file), live=False), str(args.file), {}
    from bugsweep.scanner import scan
    print("Checking your network... (this takes about a minute)")
    devices, info = scan(thorough=not args.quick, status=print, log=print if args.debug else None)
    return devices, "live scan of this computer's network", info


def print_report(report, color):
    c = (lambda code: code) if color else (lambda code: "")
    colors = {"alert": RED, "camera": MAGENTA, "new": YELLOW, "unknown": YELLOW, "ok": DIM, "known": GREEN}
    print(f"\n{'RESULT':<14} {'IP':<15} {'NAME':<24} {'TYPE':<22} MAKER")
    for f in report.findings:
        d = f.device
        tag = "DEV BOARD" if f.level == "alert" else LEVELS[f.level][0]
        print(f"{c(colors[f.level])}{tag:<14}{c(RESET)} {d.ip:<15} {(f.display_name or '-')[:24]:<24} "
              f"{(d.kind or 'Unknown')[:22]:<22} {(d.maker or 'unknown')[:30]}")
    color_code = RED if report.alerts else MAGENTA if report.cameras else YELLOW if report.new_devices else GREEN
    print(f"\n{c(color_code)}{report.summary()}{c(RESET)}")
    for f in report.alerts + report.cameras:
        print(f"  - {f.device.ip}: {f.explain()}")
    if report.alerts or report.cameras:
        print("\nA flag means 'worth a look', not proof of anything. If you can't tell what it is,")
        print(f"contact tech support: {', '.join(l for l in contact_lines()[2:])}")
    if report.shared:
        print(f"\n{c(CYAN)}Note: {SHARED_NOTE}\n  Why we think so: {'; '.join(report.shared_reasons)}.{c(RESET)}")


def cmd_scan(args):
    if not args.file and not _confirm_ownership(args):
        return 1
    devices, source, info = _get_devices(args)
    baseline = load_baseline(args.baseline)
    report = check(devices, baseline=baseline, labels=load_labels(), source=source, network=info)
    print_report(report, _color_ok())
    if baseline is None:
        print(f"{DIM if _color_ok() else ''}Tip: run 'baseline' once to save what's normal, "
              f"so new devices get flagged too.{RESET if _color_ok() else ''}")
    if args.save_report:
        Path(args.save_report).write_text(report_text(report, load_support()), encoding="utf-8")
        print(f"Report saved to {args.save_report}")
    return 2 if report.alerts else 0


def cmd_baseline(args):
    if not args.file and not _confirm_ownership(args):
        return 1
    devices, _, _ = _get_devices(args)
    path = save_baseline(devices, args.baseline)
    print(f"Saved {len(devices)} devices as your 'normal' list: {path}")
    return 0


def demo_devices():
    from bugsweep.identify import enrich
    devices = load_devices(DEMO_SCAN)
    for d in devices:
        d.is_router = d.ip == "10.20.0.1"
    return enrich(devices, live=False)


def cmd_demo(args):
    print("Demo: 40 devices from a pretend office network, with one dev board hidden inside.")
    report = check(demo_devices(), baseline=load_baseline(DEMO_BASELINE), source=str(DEMO_SCAN), demo=True)
    print_report(report, _color_ok())
    return 2 if report.alerts else 0


def cmd_help(args):
    print("\n".join(contact_lines()))
    return 0


def cmd_gui(args):
    from bugsweep.gui import run
    run()
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="bugsweep", description=(
        "Flag hobby Wi-Fi circuit boards (ESP32, Raspberry Pi...) on a network you own. "
        "Run with no command to open the app window."))
    p.add_argument("--version", action="version", version=f"bugsweep {__version__}")
    sub = p.add_subparsers(dest="command")

    def common(sp):
        sp.add_argument("--file", type=Path, help="read devices from a .csv/.json file instead of scanning")
        sp.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="where the 'normal' list lives")
        sp.add_argument("--quick", action="store_true", help="skip the ping sweep (faster, may miss devices)")
        sp.add_argument("--yes", action="store_true", help="confirm you own the network (skip the prompt)")
        sp.add_argument("--debug", action="store_true", help="show every name lookup and what it returned")

    sp = sub.add_parser("scan", help="check the network and flag dev boards and new devices")
    common(sp)
    sp.add_argument("--save-report", metavar="FILE", help="also save a plain-text report for tech support")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("baseline", help="save the devices on the network now as 'normal'")
    common(sp)
    sp.set_defaults(func=cmd_baseline)

    sub.add_parser("demo", help="run the 40-device sample from the video").set_defaults(func=cmd_demo)
    sub.add_parser("support", help="show tech support contact details").set_defaults(func=cmd_help)
    sub.add_parser("gui", help="open the app window").set_defaults(func=cmd_gui)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    func = getattr(args, "func", cmd_gui)
    try:
        return func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # show a friendly message instead of a traceback
        print(f"\nSomething went wrong: {e}")
        print("If this keeps happening, contact tech support:")
        print("\n".join(contact_lines()[2:]))
        return 1
