"""The point-and-click window. Built on tkinter, which ships with Python."""

import queue
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote

from bugsweep import __version__
from bugsweep.core import (DEFAULT_BASELINE, LEVELS, SHARED_NOTE, check, load_baseline, load_labels, report_text,
                           save_baseline, save_label)
from bugsweep.cli import DEMO_BASELINE, demo_devices
from bugsweep.identify import LOOKUP_LABELS, PORTS, check_ports, guess_kind, is_online
from bugsweep.support import contact_lines, get_setting, has_agreed, load_support, record_agreement, set_setting

FONT = "Segoe UI"
ROW_COLORS = {
    "alert": ("#fde2e1", "#8b1a1a"),
    "camera": ("#efe4fb", "#4b2a7a"),
    "new": ("#fff4cc", "#6b5000"),
    "unknown": ("#e8eef5", "#2c3e50"),
    "ok": ("#ffffff", "#222222"),
    "known": ("#e9f7ef", "#1e6b43"),
}
BANNER = {"alert": "#b83227", "camera": "#6c3fa0", "new": "#a86b00", "ok": "#2f7d4f", "idle": "#34495e"}

FILTERS = {
    "All devices": None,
    "Needs attention": {"alert", "camera", "new", "unknown"},
    "Hobby circuit boards": {"alert"},
    "Cameras": {"camera"},
    "New since 'normal'": {"new"},
    "Unidentified": {"unknown"},
    "Known (marked by you)": {"known"},
}

INTRO = ("Click 'Try the demo' to see how it works, or 'Check my network' to list every device on the "
         "network this computer is using. Only check networks you own or have permission to check.")

FIND_IT = (
    "Networks don't report where a device physically sits, so no app can put it on a map. "
    "These steps narrow it down:\n"
    "  1. Read its name, type and maker above. They're often enough (\"Samsung TV\", \"Brother printer\").\n"
    "  2. Click 'Open its web page'. Printers, cameras and routers often show their model there.\n"
    "  3. Click 'Live online tracker', then switch off or unplug gadgets one at a time. "
    "When the tracker says OFFLINE, the last thing you unplugged is this device.\n"
    "  4. Your router's app or settings page often shows which Wi-Fi band it uses and how strong its signal is "
    "(a strong signal means it's close to the router).\n"
    "  5. Once you know what and where it is, click 'Label it / set location' so you'll recognise it next time.\n"
    "At work, don't unplug or move things. Ask your IT team to locate it."
)

NEXT_STEPS = {
    "alert": "What you can do:\n"
             "  - At home: think about smart plugs, bulbs or gadgets added recently. Many use the same chips. "
             "If it's yours, click 'Label it' and tick 'I know this device'.\n"
             "  - At work: don't unplug or move anything. Tell your IT or security team.\n"
             "  - Still not sure? Click 'Get help' and send tech support a report.",
    "camera": "What you can do:\n"
              "  - Make sure you know exactly where this camera is and what it can see.\n"
              "  - In a rental or hotel, cameras in bedrooms or bathrooms are not OK. Report it to the host "
              "or platform, and the police if needed.\n"
              "  - If it's yours, change its default password and keep its app updated.",
    "new": "What you can do:\n"
           "  - If you recognise it (a visitor's phone, a new TV), it's fine. Click 'Label it' and tick "
           "'I know this device', or run a check and click 'Save as normal'.\n"
           "  - If you don't recognise it, use the steps below to find it.",
    "unknown": "What you can do:\n"
               "  - Try 'What is it running?' and 'Open its web page'. They often reveal what it is.\n"
               "  - Still a mystery? Use the live tracker below, or click 'Get help'.",
    "ok": "Nothing to do. If you like, label it with where it is so you'll recognise it next time.",
    "known": "Nothing to do. You've marked this as a device you know.",
}

TIPS = [
    ("router_pw", "Change your router's admin password",
     "Routers ship with simple default passwords that are published online. Change it in the router's "
     "settings page or app (the 'Open router settings' button can help)."),
    ("wifi_sec", "Use WPA2 or WPA3 Wi-Fi security with a long password",
     "Never 'Open' or 'WEP'. A long passphrase (4+ random words) is better than a short complicated one."),
    ("guest_net", "Put smart gadgets and guests on a guest network",
     "If a cheap gadget gets hacked, it can't reach your laptop or phone."),
    ("updates", "Turn on automatic updates",
     "For your router, phones, computers, cameras and smart gadgets. Most attacks use old, already-fixed bugs."),
    ("wps", "Turn off WPS and 'remote management' on your router",
     "Both are convenience features that make break-ins easier. You'll rarely miss them."),
    ("routine", "Check your network monthly, and after visitors or repair work",
     "Run 'Check my network', look at anything new, then click 'Save as normal'."),
    ("physical", "Do a quick physical look-around",
     "Hidden cameras and recorders often sit in USB chargers, clocks, smoke detectors, power strips and "
     "picture frames facing a bed, desk or meeting table. In a dark room, use your phone's flashlight to look "
     "for the small reflection of a camera lens."),
    ("rentals", "In rentals and hotels, check the Wi-Fi too",
     "Join the Wi-Fi, run a check, and look for cameras. Hidden cameras in private spaces are illegal in most "
     "places. Report them to the host, the booking platform and the police."),
    ("work", "At work, report, don't tamper",
     "If something looks wrong, tell IT or security. Unplugging or moving it can destroy evidence."),
    ("limits", "Know the limits",
     "A device that records to a memory card and never joins Wi-Fi won't appear in any network check. "
     "That's why the physical look-around matters."),
]

GLOSSARY = [
    ("Network address (IP)", "The device's 'house number' on your network, e.g. 192.168.1.23. It can change over time."),
    ("Hardware ID (MAC)", "A permanent ID built into the device's network chip. The first half shows who made the chip."),
    ("Chip maker", "The company that made the network chip. Often the same as the brand (Apple, Samsung); "
                   "sometimes a parts supplier (Espressif, Realtek)."),
    ("Private address", "Phones, tablets and laptops make up a random hardware ID to protect your privacy, "
                        "so their maker can't be shown. That's normal."),
    ("Hobby circuit board", "A cheap Wi-Fi board (like an ESP32) that anyone can program. Also used inside "
                            "many legitimate smart plugs and bulbs."),
    ("'Save as normal'", "Remembers the devices on your network today, so future checks can point out anything new."),
]


class App:
    def __init__(self, root):
        self.root = root
        self.support = load_support()
        self.report = None
        self.live_devices = None
        self.network_info = {}
        self.events = queue.Queue()
        self.selected = None
        self.trackers = {}

        root.title("BugSweep - see every device on your network")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(1320, int(sw * 0.9)), min(860, int(sh * 0.85))
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max((sh - h) // 3, 0)}")
        root.minsize(900, 560)
        self._style()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook = nb
        self.devices_tab = ttk.Frame(nb, padding=8)
        self.protect_tab = ttk.Frame(nb, padding=0)
        self.help_tab = ttk.Frame(nb, padding=0)
        nb.add(self.devices_tab, text="  Devices  ")
        nb.add(self.protect_tab, text="  Protect yourself  ")
        nb.add(self.help_tab, text="  Help  ")

        self._build_devices_tab(self.devices_tab)
        self._build_protect_tab()
        self._build_help_tab()
        root.bind("<Configure>", self._rewrap)
        root.after(100, self._poll_events)

    # ---- layout ------------------------------------------------------------

    def _style(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Big.TButton", font=(FONT, 12), padding=(14, 8))
        style.configure("Action.TButton", font=(FONT, 10), padding=(8, 5))
        style.configure("Treeview", font=(FONT, 10), rowheight=26)
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"))
        style.configure("TNotebook.Tab", font=(FONT, 11), padding=(10, 5))
        style.map("Treeview", background=[("selected", "#2c3e50")], foreground=[("selected", "white")])

    def _build_devices_tab(self, tab):
        head = ttk.Frame(tab)
        head.pack(fill="x")
        title = ttk.Frame(head)
        title.pack(side="left")
        tk.Label(title, text="BugSweep", font=(FONT, 20, "bold")).pack(anchor="w")
        tk.Label(title, text="See every device on your network, and spot the ones that shouldn't be there.",
                 font=(FONT, 10), fg="#555").pack(anchor="w")
        ttk.Button(head, text="Get help", style="Big.TButton", command=self.show_help).pack(side="right")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(8, 0))
        self.demo_btn = ttk.Button(bar, text="Try the demo", style="Big.TButton", command=self.run_demo)
        self.scan_btn = ttk.Button(bar, text="Check my network", style="Big.TButton", command=self.run_scan)
        self.save_btn = ttk.Button(bar, text="Save as normal", style="Big.TButton", command=self.save_normal,
                                   state="disabled")
        self.report_btn = ttk.Button(bar, text="Save report for tech support", style="Big.TButton",
                                     command=self.save_report, state="disabled")
        for b in (self.demo_btn, self.scan_btn, self.save_btn, self.report_btn):
            b.pack(side="left", padx=(0, 8))

        self.banner = tk.Label(tab, text=INTRO, font=(FONT, 11, "bold"), fg="white", bg=BANNER["idle"],
                               justify="left", anchor="w", padx=12, pady=10, wraplength=1000)
        self.banner.pack(fill="x", pady=8)
        self.progress = ttk.Progressbar(tab, mode="determinate")
        # Shown under the banner when the network looks shared and hides devices.
        self.notice = tk.Label(tab, text="", font=(FONT, 10), fg="#0b3d5c", bg="#dceefb", justify="left",
                               anchor="w", padx=12, pady=8, wraplength=1000)

        filt = ttk.Frame(tab)
        filt.pack(fill="x", pady=(0, 6))
        ttk.Label(filt, text="Show:", font=(FONT, 10)).pack(side="left")
        self.filter_var = tk.StringVar(value="All devices")
        box = ttk.Combobox(filt, textvariable=self.filter_var, values=list(FILTERS), state="readonly", width=24)
        box.pack(side="left", padx=(4, 16))
        box.bind("<<ComboboxSelected>>", lambda e: self._fill_table())
        ttk.Label(filt, text="Search:", font=(FONT, 10)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._fill_table())
        ttk.Entry(filt, textvariable=self.search_var, width=28).pack(side="left", padx=4)
        self.count_label = ttk.Label(filt, text="", foreground="#666")
        self.count_label.pack(side="left", padx=12)
        legend = ttk.Frame(filt)
        legend.pack(side="right")
        for level in ("alert", "camera", "new", "unknown", "known"):
            bg, fg = ROW_COLORS[level]
            tk.Label(legend, text=f" {LEVELS[level][0]} ", bg=bg, fg=fg, font=(FONT, 9, "bold"),
                     relief="solid", bd=1).pack(side="left", padx=2)

        # tk (not ttk) PanedWindow, because it supports minimum sizes: neither
        # the device list nor the details panel can ever be squeezed to nothing.
        panes = tk.PanedWindow(tab, orient="horizontal", sashwidth=8, sashrelief="raised", bd=0,
                               opaqueresize=True, bg="#d0d4d9")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        # Most useful columns first, so they stay visible in a narrow window.
        cols = (("status", "Result", 95), ("name", "Device name", 150), ("kind", "Type", 190),
                ("ip", "Address", 120), ("maker", "Chip maker", 150), ("where", "Location (your note)", 150))
        self.tree = ttk.Treeview(left, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for key, text, width in cols:
            self.tree.heading(key, text=text, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, minwidth=70, anchor="w", stretch=key in ("name", "kind", "maker", "where"))
        for level, (bg, fg) in ROW_COLORS.items():
            self.tree.tag_configure(level, background=bg, foreground=fg)
        ys = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.edit_label())
        self.tree.bind("<Return>", lambda e: self.edit_label())
        panes.add(left, minsize=420, stretch="always")

        right = ttk.Frame(panes, padding=(10, 0, 0, 0))
        self.detail_title = tk.Label(right, text="Device details", font=(FONT, 14, "bold"), anchor="w",
                                     justify="left")
        self.detail_title.pack(fill="x")
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=6)
        self.action_btns = {}
        for i, (key, text, cmd) in enumerate((
                ("label", "Label it / set location", self.edit_label),
                ("known", "Mark as known", self.toggle_known),
                ("track", "Live online tracker", self.open_tracker),
                ("web", "Open its web page", self.open_web),
                ("ports", "What is it running?", self.check_running),
                ("copy", "Copy details", self.copy_details))):
            b = ttk.Button(actions, text=text, style="Action.TButton", command=cmd, state="disabled")
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            self.action_btns[key] = b
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        text_frame = ttk.Frame(right)
        text_frame.pack(fill="both", expand=True)
        self.detail = tk.Text(text_frame, wrap="word", font=(FONT, 10), relief="flat", padx=8, pady=6,
                              bg="#fbfbfb", height=10, cursor="arrow")
        ds = ttk.Scrollbar(text_frame, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=ds.set)
        self.detail.pack(side="left", fill="both", expand=True)
        ds.pack(side="right", fill="y")
        self.detail.tag_configure("h", font=(FONT, 11, "bold"), spacing1=8, spacing3=2)
        self.detail.tag_configure("k", font=(FONT, 10, "bold"))
        self.detail.tag_configure("muted", foreground="#666")
        self.detail.tag_configure("warn", foreground="#8b1a1a", font=(FONT, 10, "bold"))
        self._write_detail([("Click any device in the list to see what it is, who made it, and how to find "
                             "where it is.", "")])
        panes.add(right, minsize=340, stretch="always")
        self.panes = panes
        self._sash_placed = False
        panes.bind("<Configure>", self._place_sash)

    def _place_sash(self, event):
        """Put the divider at 60% once the window has its real size (not before: then it's 1px wide)."""
        if not self._sash_placed and event.width > 800:
            self.panes.sash_place(0, int(event.width * 0.6), 1)
            self._sash_placed = True

    def _scroll_page(self, parent):
        """A vertically scrolling frame for the text-heavy tabs."""
        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=16)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def wheel(e):
            canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_protect_tab(self):
        page = self._scroll_page(self.protect_tab)
        self.wrap_labels = []
        tk.Label(page, text="Protect yourself", font=(FONT, 18, "bold")).pack(anchor="w")
        self._para(page, "Simple habits that keep your home or office network, and the people in it, safe. "
                         "Tick them off as you go; BugSweep remembers.")

        tk.Label(page, text="Your check-up", font=(FONT, 13, "bold")).pack(anchor="w", pady=(14, 4))
        self.checkup = ttk.Frame(page)
        self.checkup.pack(fill="x")
        self._fill_checkup()

        tk.Label(page, text="Good habits", font=(FONT, 13, "bold")).pack(anchor="w", pady=(18, 4))
        done = get_setting("tips_done", {}) or {}
        self.tip_vars = {}
        for key, title, body in TIPS:
            row = ttk.Frame(page)
            row.pack(fill="x", pady=4)
            var = tk.BooleanVar(value=bool(done.get(key)))
            self.tip_vars[key] = var
            ttk.Checkbutton(row, variable=var, command=self._save_tips).pack(side="left", anchor="n", padx=(0, 6))
            col = ttk.Frame(row)
            col.pack(side="left", fill="x", expand=True)
            tk.Label(col, text=title, font=(FONT, 11, "bold"), anchor="w").pack(anchor="w")
            self._para(col, body, size=10, fg="#444")

    def _build_help_tab(self):
        page = self._scroll_page(self.help_tab)
        tk.Label(page, text="Help", font=(FONT, 18, "bold")).pack(anchor="w")
        box = tk.Frame(page, bg="#eef3f8", padx=14, pady=12)
        box.pack(fill="x", pady=(8, 12))
        tk.Label(box, text=self.support["name"], font=(FONT, 13, "bold"), bg="#eef3f8").pack(anchor="w")
        self._para(box, "\n".join(contact_lines(self.support)), bg="#eef3f8")
        row = tk.Frame(box, bg="#eef3f8")
        row.pack(anchor="w", pady=(8, 0))
        self._support_buttons(row)

        tk.Label(page, text="What the colours mean", font=(FONT, 13, "bold")).pack(anchor="w", pady=(10, 4))
        meanings = {
            "alert": "Its chip comes from a hobby circuit-board maker. Worth a look, not proof of anything.",
            "camera": "It looks like a camera. Make sure you know where it is and what it can see.",
            "new": "It wasn't on your saved 'normal' list.",
            "unknown": "It didn't tell us its name and its maker isn't a consumer brand.",
            "ok": "Identified, nothing unusual.",
            "known": "You marked it as a device you know.",
        }
        for level, text in meanings.items():
            r = ttk.Frame(page)
            r.pack(fill="x", pady=2)
            bg, fg = ROW_COLORS[level]
            tk.Label(r, text=f" {LEVELS[level][0]} ", bg=bg, fg=fg, font=(FONT, 10, "bold"), width=14,
                     relief="solid", bd=1).pack(side="left", padx=(0, 10))
            self._para(r, text, side="left")

        tk.Label(page, text="Words you'll see", font=(FONT, 13, "bold")).pack(anchor="w", pady=(16, 4))
        for term, text in GLOSSARY:
            tk.Label(page, text=term, font=(FONT, 10, "bold")).pack(anchor="w", pady=(4, 0))
            self._para(page, text, size=10, fg="#444")

        tk.Label(page, text="Common problems", font=(FONT, 13, "bold")).pack(anchor="w", pady=(16, 4))
        for q, a in (
                ("'No other devices were found'", "Make sure this computer is on the Wi-Fi you want to check, "
                                                  "not a phone hotspot or VPN."),
                ("Lots of devices have no name", "Normal. Many gadgets don't announce a name. The type and maker "
                                                 "columns usually tell you enough; label them as you identify them."),
                ("A device I unplugged still shows", "Your computer remembers devices for a few minutes. "
                                                     "Run the check again later."),
                ("The web page shows a security warning", "Common for home devices. Don't type any passwords "
                                                          "unless you know what the device is."),
        ):
            tk.Label(page, text=q, font=(FONT, 10, "bold")).pack(anchor="w", pady=(4, 0))
            self._para(page, a, size=10, fg="#444")
        tk.Label(page, text=f"BugSweep v{__version__}. Read-only: it can't record, listen to or change "
                            "anything on your devices.", fg="#888").pack(anchor="w", pady=(20, 0))

    def _support_buttons(self, row, parent=None):
        bg = row.cget("bg") if isinstance(row, tk.Frame) else None
        if self.support.get("email"):
            ttk.Button(row, text="Email support", command=self.email_support).pack(side="left", padx=(0, 8))
        if self.support.get("phone"):
            tk.Label(row, text=f"Call {self.support['phone']}", font=(FONT, 10, "bold"), bg=bg).pack(side="left", padx=(0, 8))
        if self.support.get("website"):
            ttk.Button(row, text="Support website",
                       command=lambda: webbrowser.open(self.support["website"])).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Save a report to send",
                   command=lambda: self.save_report(parent)).pack(side="left", padx=(0, 8))

    def _para(self, parent, text, size=11, fg="#222", side=None, bg=None):
        kw = {"bg": bg} if bg else {}
        lbl = tk.Label(parent, text=text, font=(FONT, size), fg=fg, justify="left", anchor="w",
                       wraplength=900, **kw)
        lbl.pack(side=side or "top", anchor="w", fill="x" if not side else None)
        if not hasattr(self, "wrap_labels"):
            self.wrap_labels = []
        self.wrap_labels.append(lbl)
        return lbl

    def _rewrap(self, event):
        if event.widget is not self.root:
            return
        width = max(event.width - 80, 400)
        self.banner.configure(wraplength=width)
        self.notice.configure(wraplength=width)
        for lbl in getattr(self, "wrap_labels", []):
            try:
                lbl.configure(wraplength=width - 120)
            except tk.TclError:
                pass

    # ---- check-up --------------------------------------------------------

    def _fill_checkup(self):
        for w in self.checkup.winfo_children():
            w.destroy()
        r = self.report
        items = []
        if not r or r.demo:
            items.append(("info", "Run 'Check my network' on the Devices tab to get a personal check-up.", None))
        else:
            if r.shared:
                items.append(("info", f"{SHARED_NOTE} (Why we think so: {'; '.join(r.shared_reasons)}.)", None))
            n_alert, n_cam = len(r.alerts), len(r.cameras)
            n_unknown = len(r.by_level("unknown"))
            items.append(("bad" if n_alert else "good",
                          f"{n_alert} hobby circuit board{'s' if n_alert != 1 else ''} found." if n_alert
                          else "No hobby circuit boards found.", "Hobby circuit boards" if n_alert else None))
            items.append(("warn" if n_cam else "good",
                          f"{n_cam} camera{'s' if n_cam != 1 else ''} on your network. Make sure you know where "
                          "each one is." if n_cam else "No cameras detected on the network.",
                          "Cameras" if n_cam else None))
            items.append(("warn" if n_unknown else "good",
                          f"{n_unknown} device{'s' if n_unknown != 1 else ''} couldn't be identified. Label "
                          "them as you find them." if n_unknown else "Every device was identified.",
                          "Unidentified" if n_unknown else None))
            risky = [f for f in r.findings if any(PORTS.get(p, ("", "", False))[2] for p in f.device.ports)]
            if risky:
                names = ", ".join(f.display_name or f.device.ip for f in risky[:4])
                items.append(("warn", f"{len(risky)} device(s) use old, unencrypted remote access (Telnet/FTP): "
                                      f"{names}. Turn it off in their settings if you can.", None))
            items.append(("good" if r.baseline_used else "info",
                          "You have a saved 'normal' list, so new devices get flagged." if r.baseline_used
                          else "Tip: click 'Save as normal' after checking, so new devices get flagged next time.",
                          None))
            router = next((f for f in r.findings if f.device.is_router), None)
            if router:
                items.append(("info", f"Your router is at {router.device.ip}. Make sure its admin password "
                                      "isn't the default.", ("router", router.device.ip)))
        icons = {"good": ("OK", "#2f7d4f"), "warn": ("!", "#a86b00"), "bad": ("!!", "#b83227"), "info": ("i", "#34495e")}
        for kind, text, link in items:
            row = ttk.Frame(self.checkup)
            row.pack(fill="x", pady=3)
            mark, color = icons[kind]
            tk.Label(row, text=mark, bg=color, fg="white", font=(FONT, 9, "bold"), width=3).pack(side="left", padx=(0, 8))
            self._para(row, text, size=10, side="left")
            if isinstance(link, tuple):
                ttk.Button(row, text="Open router settings",
                           command=lambda ip=link[1]: webbrowser.open(f"http://{ip}")).pack(side="left", padx=8)
            elif link:
                ttk.Button(row, text="Show me", command=lambda f=link: self._show_filter(f)).pack(side="left", padx=8)

    def _show_filter(self, name):
        self.filter_var.set(name)
        self._fill_table()
        self.notebook.select(self.devices_tab)

    def _save_tips(self):
        set_setting("tips_done", {k: v.get() for k, v in self.tip_vars.items()})

    # ---- actions -----------------------------------------------------------

    def run_demo(self):
        self.live_devices = None
        self.show_report(check(demo_devices(), baseline=load_baseline(DEMO_BASELINE), labels={},
                               source="Demo: sample office network (40 devices)", demo=True))

    def run_scan(self):
        from bugsweep.identify import own_network
        from bugsweep.scanner import ScanError, local_ip
        try:
            me = local_ip()
            full = own_network(me, smallest_prefix=0)
        except ScanError as e:
            messagebox.showerror("Not connected", str(e))
            return
        big = full.num_addresses > 1024
        if not has_agreed() or big:
            text = ("Only check networks you own or have permission to check, like your home Wi-Fi, "
                    "or your work network with your IT team's OK.\n\n"
                    "BugSweep only lists devices and asks them what they are. It can't see or record what "
                    "they do.\n\n")
            if big:
                text += (f"Heads up: this network is very large ({full.num_addresses - 2:,} addresses). "
                         "That usually means a shared network, like an apartment building, school, hotel or "
                         "office. Other people's devices may show up.\n\n")
            if not messagebox.askyesno("Before we start", text + "Is this a network you own or have permission to check?"):
                return
            record_agreement()
        from bugsweep.scanner import sweep_size
        self.progress.configure(mode="determinate", maximum=max(sweep_size(), 1), value=0)
        self._set_busy(True, "Looking for devices on your network... this usually takes about a minute.")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        from bugsweep.scanner import scan
        try:
            devices, info = scan(progress=lambda done, total: self.events.put(("progress", done)),
                                 status=lambda text: self.events.put(("status", text)),
                                 count=lambda done, total: self.events.put(("ident", (done, total))))
            self.events.put(("scanned", (devices, info)))
        except Exception as e:
            self.events.put(("error", e))

    def _poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.progress["value"] = value
                elif kind == "status":
                    self._set_banner(value, "idle")
                    if "running" in value:
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(12)
                elif kind == "ident":
                    done, total = value
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=max(total, 1), value=done)
                    self._set_banner(f"Asking each device for its name... {done} of {total} done.", "idle")
                elif kind == "scanned":
                    self._set_busy(False)
                    self.live_devices, self.network_info = value
                    self.show_report(self._live_report())
                elif kind == "error":
                    self._set_busy(False)
                    self._set_banner("The check didn't finish.", "alert")
                    messagebox.showerror("Something went wrong", f"{value}\n\nIf this keeps happening, click 'Get help'.")
                elif kind == "ports":
                    finding = value
                    finding.device.kind = guess_kind(finding.device, finding.is_dev_board)
                    self._refresh_row(finding)
                    if self.selected is finding:
                        self.action_btns["ports"].configure(state="normal", text="What is it running?")
                        self._show_details(finding)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _live_report(self):
        return check(self.live_devices, baseline=load_baseline(DEFAULT_BASELINE), labels=load_labels(),
                     source="This computer's network", network=self.network_info)

    def save_normal(self):
        if not self.live_devices:
            return
        if not messagebox.askyesno(
                "Save as normal?",
                f"Save these {len(self.live_devices)} devices as what's normal on your network?\n\n"
                "Next time, anything that wasn't here today will be marked 'New'. "
                "Only do this if you're happy with everything on the list."):
            return
        save_baseline(self.live_devices, DEFAULT_BASELINE)
        self.show_report(self._live_report())
        messagebox.showinfo("Saved", "Done. Future checks will point out anything new.")

    def save_report(self, parent=None):
        parent = parent or self.root
        if not self.report:
            messagebox.showinfo("Nothing to save yet", "Run the demo or check your network first.", parent=parent)
            return
        desktop = Path.home() / "Desktop"
        path = filedialog.asksaveasfilename(
            parent=parent, title="Save report", initialdir=desktop if desktop.exists() else Path.home(),
            initialfile="bugsweep-report.txt", defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if path:
            Path(path).write_text(report_text(self.report, self.support), encoding="utf-8")
            messagebox.showinfo("Report saved", f"Saved to:\n{path}\n\nAttach this file when you email tech support.",
                                parent=parent)

    def show_help(self):
        self.notebook.select(self.help_tab)

    def email_support(self):
        summary = self.report.summary() if self.report else "(I haven't run a check yet.)"
        body = (f"Hi,\n\nI need help with BugSweep (version {__version__}).\n\n"
                f"My last result: {summary}\n\nWhat I need help with:\n\n"
                "(If you saved a report, please attach it.)\n")
        webbrowser.open(f"mailto:{self.support['email']}?subject={quote('BugSweep help')}&body={quote(body)}")

    # ---- per-device actions --------------------------------------------------

    def _need_real(self):
        if self.report and self.report.demo:
            messagebox.showinfo("Demo device", "This is a pretend device from the demo, so it can't be contacted. "
                                               "Run 'Check my network' to use this on your real devices.")
            return False
        return True

    def edit_label(self):
        f = self.selected
        if not f:
            return
        win = tk.Toplevel(self.root)
        win.title("Label this device")
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=16)
        frame.pack()
        ttk.Label(frame, text=f"{f.display_name or 'This device'}  ({f.device.kind}, {f.device.ip})",
                  font=(FONT, 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        what = tk.StringVar(value=f.label.get("what", ""))
        where = tk.StringVar(value=f.label.get("where", ""))
        known = tk.BooleanVar(value=bool(f.label.get("known")))
        ttk.Label(frame, text="What is it?").grid(row=1, column=0, sticky="w")
        e1 = ttk.Entry(frame, textvariable=what, width=40)
        e1.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="e.g. Living room TV, Mum's iPad", foreground="#777").grid(row=2, column=1, sticky="w")
        ttk.Label(frame, text="Where is it?").grid(row=3, column=0, sticky="w")
        ttk.Entry(frame, textvariable=where, width=40).grid(row=3, column=1, pady=3)
        ttk.Label(frame, text="e.g. Kitchen, behind the fridge", foreground="#777").grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(frame, text="I know this device. Stop flagging it.", variable=known).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        if self.report and self.report.demo:
            ttk.Label(frame, text="Demo labels aren't saved.", foreground="#a86b00").grid(row=6, column=0, columnspan=2, sticky="w")

        def save():
            if self.report and self.report.demo:
                f.label = {k: v for k, v in (("what", what.get().strip()), ("where", where.get().strip()),
                                             ("known", known.get())) if v}
            else:
                f.label = save_label(f.device.mac, what.get(), where.get(), known.get())
            win.destroy()
            self._after_label_change(f)

        btns = ttk.Frame(frame)
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=save).pack(side="right", padx=6)
        e1.focus_set()
        win.bind("<Return>", lambda e: save())

    def toggle_known(self):
        f = self.selected
        if not f:
            return
        new = not f.label.get("known")
        if self.report.demo:
            f.label = {**f.label, "known": new} if new else {k: v for k, v in f.label.items() if k != "known"}
        else:
            f.label = save_label(f.device.mac, f.label.get("what", ""), f.label.get("where", ""), new)
        self._after_label_change(f)

    def _after_label_change(self, f):
        self._refresh_row(f)
        self._update_banner()
        self._fill_checkup()
        self._show_details(f)

    def open_web(self):
        f = self.selected
        if not f or not self._need_real():
            return
        ports = set(f.device.ports)
        scheme = "https" if 443 in ports and 80 not in ports else "http"
        port = ":8080" if 8080 in ports and not ports & {80, 443} else ""
        messagebox.showinfo("Opening in your browser",
                            "If a page loads, it often shows the device's brand and model.\n\n"
                            "If your browser shows a security warning, that's common for home devices. "
                            "Don't type any passwords unless you know what the device is.")
        webbrowser.open(f"{scheme}://{f.device.ip}{port}")

    def check_running(self):
        f = self.selected
        if not f or not self._need_real():
            return
        self.action_btns["ports"].configure(state="disabled", text="Checking...")

        def work():
            check_ports(f.device)
            self.events.put(("ports", f))
        threading.Thread(target=work, daemon=True).start()

    def copy_details(self):
        if not self.selected:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.detail.get("1.0", "end").strip())
        self.action_btns["copy"].configure(text="Copied!")
        self.root.after(1500, lambda: self.action_btns["copy"].configure(text="Copy details"))

    def open_tracker(self):
        f = self.selected
        if not f or not self._need_real():
            return
        if f.device.mac in self.trackers:
            self.trackers[f.device.mac].lift()
            return
        Tracker(self, f)

    # ---- display ---------------------------------------------------------------

    def _set_busy(self, busy, message=None):
        state = "disabled" if busy else "normal"
        for b in (self.demo_btn, self.scan_btn):
            b.configure(state=state)
        if busy:
            self.save_btn.configure(state="disabled")
            self.progress.pack(fill="x", after=self.banner, pady=(0, 6))
            self._set_banner(message, "idle")
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _set_banner(self, text, key):
        self.banner.configure(text=text, bg=BANNER[key])

    def _update_banner(self):
        r = self.report
        key = "alert" if r.alerts else "camera" if r.cameras else "new" if r.new_devices else "ok"
        text = r.summary()
        if r.alerts:
            text += "  A flag means 'worth a look', not proof. Click a row for details and next steps."
        elif not r.baseline_used and not r.demo:
            text += "  Tip: click 'Save as normal' so future checks can spot new devices."
        else:
            text += "  Click any device to see what it is and where to find it."
        if r.demo:
            text = "DEMO (pretend office): " + text
        self._set_banner(text, key)

    def show_report(self, report):
        self.report = report
        self.selected = None
        self.filter_var.set("All devices")
        self.search_var.set("")
        self._fill_table()
        self._update_banner()
        if report.shared:
            self.notice.configure(text=f"Why so few names? {SHARED_NOTE}\nWhy we think so: "
                                       f"{'; '.join(report.shared_reasons)}.")
            self.notice.pack(fill="x", after=self.banner, pady=(0, 8))
        else:
            self.notice.pack_forget()
        self._fill_checkup()
        self.save_btn.configure(state="normal" if self.live_devices else "disabled")
        self.report_btn.configure(state="normal")
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])

    def _row_values(self, f):
        d = f.device
        # Same order as the columns: Result, Device name, Type, Address, Chip maker, Location.
        name = f.display_name or ("Router" if d.is_router else "(no name)")
        return (LEVELS[f.level][0], name, d.kind or "Unknown", d.ip, d.maker or "Unknown",
                f.label.get("where", ""))

    def _fill_table(self):
        if not self.report:
            return
        wanted = FILTERS.get(self.filter_var.get())
        term = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for i, f in enumerate(self.report.findings):
            if wanted and f.level not in wanted:
                continue
            values = self._row_values(f)
            if term and term not in " ".join(values + (f.device.mac, f.device.model)).lower():
                continue
            self.tree.insert("", "end", iid=str(i), tags=(f.level,), values=values)
            shown += 1
        total = len(self.report.findings)
        self.count_label.configure(text=f"Showing {shown} of {total} devices")
        if self.selected is not None:
            idx = str(self.report.findings.index(self.selected))
            if self.tree.exists(idx):
                self.tree.selection_set(idx)

    def _refresh_row(self, f):
        idx = str(self.report.findings.index(f))
        if self.tree.exists(idx):
            self.tree.item(idx, values=self._row_values(f), tags=(f.level,))

    def _sort_by(self, key):
        items = [(self.tree.set(iid, key), iid) for iid in self.tree.get_children()]
        if key == "status":
            order = {v[0]: v[1] for v in LEVELS.values()}
            items.sort(key=lambda x: order.get(x[0], 9))
        elif key == "ip":
            items.sort(key=lambda x: [int(p) if p.isdigit() else 0 for p in x[0].split(".")])
        else:
            items.sort(key=lambda x: (x[0] in ("", "(no name)", "Unknown"), x[0].lower()))
        for n, (_, iid) in enumerate(items):
            self.tree.move(iid, "", n)

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel or not self.report:
            return
        self._show_details(self.report.findings[int(sel[0])])

    def _write_detail(self, chunks):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        for text, tag in chunks:
            self.detail.insert("end", text, tag)
        self.detail.configure(state="disabled")
        self.detail.yview_moveto(0)

    def _show_details(self, f):
        self.selected = f
        d = f.device
        demo = self.report.demo
        for key, btn in self.action_btns.items():
            btn.configure(state="normal")
        self.action_btns["known"].configure(text="Unmark as known" if f.label.get("known") else "Mark as known")
        if d.is_self:
            self.action_btns["known"].configure(state="disabled")
            self.action_btns["track"].configure(state="disabled")
        if demo:
            for key in ("track", "web", "ports"):
                self.action_btns[key].configure(state="disabled")

        if f.display_name:
            title = f.display_name
        elif d.is_router or d.is_self:
            title = d.kind
        else:
            title = f"Unnamed {d.kind.lower() if d.kind else 'device'}"
        self.detail_title.configure(text=title,
                                    fg=ROW_COLORS[f.level][1] if f.level not in ("ok",) else "#222")
        c = [(f"{LEVELS[f.level][0]}", "warn" if f.level in ("alert", "camera") else "k"),
             (f"  ·  {d.kind or 'Unknown type'}\n", "k")]
        if demo:
            c.append(("Demo device (pretend). Buttons that contact a real device are greyed out; labels still work.\n", "muted"))

        c.append(("What it is\n", "h"))
        rows = [("Name", d.name or "(didn't share a name)"),
                ("Your label", f.label.get("what", "")),
                ("Type (best guess)", d.kind or "Unknown"),
                ("Chip maker", d.maker or "Unknown"),
                ("Says it is", d.model),
                ("Name found via", ", ".join(d.found_by))]
        for k, v in rows:
            if v:
                c += [(f"{k}: ", "k"), (f"{v}\n", "")]

        c.append(("Where it is\n", "h"))
        c += [("Location (your note): ", "k"),
              (f"{f.label['where']}\n" if f.label.get("where") else "not set yet. Click 'Label it / set location'.\n",
               "" if f.label.get("where") else "muted"),
              ("Network address: ", "k"), (f"{d.ip}\n", ""),
              ("Hardware ID: ", "k"), (f"{d.mac}" + ("  (private address)" if f.randomized else "") + "\n", "")]
        if f.randomized and not d.is_self:
            c += [("Is it your phone or laptop? ", "k"),
                  ("Compare the hardware ID above with the 'Private Wi-Fi address' on your device:\n"
                   "  - iPhone/iPad: Settings > Wi-Fi > tap (i) next to this network\n"
                   "  - Android: Settings > Wi-Fi > this network > (gear) > Privacy / MAC address\n"
                   "  - Windows: Settings > Network > Wi-Fi > Hardware properties\n"
                   "  - Mac: System Settings > Wi-Fi > Details next to this network\n"
                   "If they match, click 'Label it / set location' and tick 'I know this device'.\n", "")]

        if not d.name and d.lookups:
            c.append(("Why no name?\n", "h"))
            c.append(("BugSweep asked for this device's name in every way it knows:\n", ""))
            for method, outcome in d.lookups.items():
                c += [(f"  - {LOOKUP_LABELS.get(method, method)}: ", ""), (f"{outcome}\n", "muted")]
            c.append(("Many devices simply don't share a name, and phones and shared networks hide them on "
                      "purpose. The type, maker and the steps below usually tell you enough.\n", ""))

        c.append(("What it's running\n", "h"))
        if d.ports:
            for p in d.ports:
                name, meaning, risky = PORTS.get(p, (f"Port {p}", "", False))
                c += [(f"{name}: ", "warn" if risky else "k"), (f"{meaning}\n", "")]
        elif demo:
            c.append(("Nothing notable.\n", "muted"))
        else:
            c.append(("Nothing found yet. Click 'What is it running?' to check again.\n", "muted"))

        c.append(("What this means\n", "h"))
        c.append((f.explain() + "\n", ""))
        c.append(("\n" + NEXT_STEPS[f.level] + "\n", ""))
        if not d.is_self:
            c.append(("How to find where it is\n", "h"))
            c.append((FIND_IT + "\n", ""))
        self._write_detail(c)


class Tracker:
    """A small window that pings one device every 2 seconds, to help find it physically."""

    def __init__(self, app, finding):
        self.app, self.f = app, finding
        d = finding.device
        self.win = tk.Toplevel(app.root)
        self.win.title(f"Live tracker: {finding.display_name or d.ip}")
        self.win.geometry("520x460")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        app.trackers[d.mac] = self.win
        self.running = True
        self.last = None
        self.events = queue.Queue()

        frame = ttk.Frame(self.win, padding=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=finding.display_name or "Unnamed device", font=(FONT, 14, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"{d.kind}  ·  {d.maker or 'unknown maker'}  ·  {d.ip}", fg="#555").pack(anchor="w")
        self.status = tk.Label(frame, text="Checking...", font=(FONT, 26, "bold"), fg="white", bg="#7f8c8d",
                               pady=16)
        self.status.pack(fill="x", pady=12)
        tk.Label(frame, justify="left", wraplength=480, font=(FONT, 10), text=(
            "How to use this: switch off or unplug gadgets one at a time, waiting about 10 seconds each. "
            "When this turns OFFLINE, the last thing you switched off is this device.\n"
            "Phones and laptops may show OFFLINE while asleep. At work, ask IT instead of unplugging things.")
        ).pack(anchor="w")
        tk.Label(frame, text="History", font=(FONT, 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.log = tk.Listbox(frame, height=8, font=(FONT, 10))
        self.log.pack(fill="both", expand=True)
        ttk.Button(frame, text="Stop and close", command=self.close).pack(anchor="e", pady=(8, 0))

        threading.Thread(target=self._loop, daemon=True).start()
        self.win.after(200, self._poll)

    def _loop(self):
        while self.running:
            self.events.put(is_online(self.f.device.ip))
            for _ in range(20):
                if not self.running:
                    return
                time.sleep(0.1)

    def _poll(self):
        if not self.running:
            return
        try:
            while True:
                up = self.events.get_nowait()
                self.status.configure(text="ONLINE" if up else "OFFLINE", bg="#2f7d4f" if up else "#7f8c8d")
                if up != self.last:
                    self.log.insert(0, f"{time.strftime('%H:%M:%S')}   {'came online' if up else 'went offline'}")
                    if self.last is not None:
                        self.win.bell()
                    self.last = up
        except queue.Empty:
            pass
        self.win.after(200, self._poll)

    def close(self):
        self.running = False
        self.app.trackers.pop(self.f.device.mac, None)
        self.win.destroy()


def run():
    root = tk.Tk()
    App(root)
    root.mainloop()
