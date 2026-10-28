# bugsweep

**A cheap first alarm for hidden Wi-Fi dev boards on networks you own.**

From the *Headline → Repo* episode **"OpenAI Got Bugged. So I Wrote a Repo."**. Watch it here: `[VIDEO LINK]`

<!-- Add the demo GIF here once it's recorded (shot B18): ![bugsweep flagging one dev board out of 40](docs/demo.gif) -->

> **Only scan networks you own, or ones you have written permission to check.**
> At work, that means asking your IT or security team first.

---

## Not technical? Start here

1. **Install Python** (one time only) from [python.org/downloads](https://www.python.org/downloads/).
   On Windows, tick **"Add python.exe to PATH"** before clicking *Install Now*.
2. **Download this project.** Click the green **Code** button on GitHub, then **Download ZIP**, then unzip it.
3. **Double-click** `Start BugSweep (Windows).bat` (or `Start BugSweep (Mac).command` on a Mac).
4. Click **Try the demo**, then **Check my network**.

There's a step-by-step guide with pictures-in-words in **[GETTING_STARTED.md](GETTING_STARTED.md)**.

**Need help?** Click **Get help** in the app, or see [Getting help](#getting-help) below. Please reach out to tech support rather than guessing; that's what we're here for.

---

## What it does

Every network chip has a MAC address, and the first half says who made it. bugsweep:

1. **Lists every device** on your network (`arp -a`, after a quick ping of your local addresses).
2. **Identifies each one:**
   - **name**, from your router, Bonjour/mDNS, Windows NetBIOS and UPnP (TVs, speakers, routers)
   - **chip maker**, from the full IEEE registry of 54,000+ companies
   - **type** (camera, printer, TV, phone, router...)
   - **what it's running**: a video stream port means a camera, and Telnet means old, unsafe remote access
3. **Flags what matters:**
   - **hobby circuit boards**: 419 prefixes from Espressif, Raspberry Pi, Arduino and others ([`vendors.csv`](bugsweep/data/vendors.csv))
   - **cameras**
   - **new devices** since your saved "normal" list
   - **devices it couldn't identify**
4. **Helps you find a device physically:**
   - a **live online tracker** (unplug things one at a time and watch it go OFFLINE)
   - a button to open the device's own web page
   - labels for "what is it" and "where is it" that are remembered on every future check
5. **Teaches good habits:** the *Protect yourself* tab has a personal check-up and a checklist covering router passwords, guest networks, hidden-camera spots and what to do in rentals.

It's **read-only and defensive**. It can't record, intercept or change anything, and nothing leaves your network. Your labels and "normal" list are stored in `~/.bugsweep/` on your computer.

A network can't report where a device physically sits, so no app can show a map. The tracker and labels are how you close that gap.

### What it can't do

- A device that **never joins your network** (it records to an SD card, or uses its own hotspot or Bluetooth) won't show up.
- A flag means **"worth a look," not proof.** The same chips are inside lots of normal smart plugs, bulbs and sensors.
- It checks your local network (`/24`) only. It's not a replacement for a professional sweep team.

## Command line

No installs or extra packages needed. It uses only Python's standard library (3.10+).

```sh
python -m bugsweep demo                  # the 40-device sample from the video
python -m bugsweep scan                  # check the network this computer is on
python -m bugsweep baseline              # save what's on the network now as "normal"
python -m bugsweep scan --save-report report.txt   # write a report for tech support
python -m bugsweep scan --file my_devices.csv      # check an exported device list instead
python -m bugsweep support               # show tech support contact details
python -m bugsweep scan --debug          # show every name lookup and what it returned
python -m bugsweep                       # open the app window
```

`scan` exits with code `2` when it flags a dev board, so you can use it in scripts or cron.

### Why some devices have no name

Names only appear when a device (or your router) is willing to share one. Many gadgets never do, and two things hide names on purpose:

- **Private hardware IDs.** Phones, tablets and laptops make up a random ID for each Wi-Fi network, so their maker can't be looked up. The app shows how to match the ID against the "Private Wi-Fi address" in your own phone's settings.
- **Shared networks.** Apartment, campus, hotel and office networks usually block devices from seeing each other. BugSweep spots this (very large network, a "virtual router" address, or only a handful of devices) and says so in a blue notice.

Click a device and look under **Why no name?** to see every lookup that was tried and its result. The last check is saved to `~/.bugsweep/last_scan.json`, and the support report includes a *Diagnostics* section.

Device files are CSV with `ip,mac,name` columns (or a JSON list of the same). Most routers can export one.

## Rerun the video demo

[`samples/sample_scan.csv`](samples/sample_scan.csv) holds 40 normal office devices with one ESP32 hidden in the middle (`10.20.0.31`).
[`samples/sample_baseline.json`](samples/sample_baseline.json) is the "normal" list it's compared against.

```sh
python -m bugsweep demo
```

## Contributing

- **New dev-board maker?** Add it to `DEV_BOARD_MAKERS` in [`tools/update_makers.py`](tools/update_makers.py), run `python tools/update_makers.py` to rebuild both maker lists from the [IEEE registry](https://standards-oui.ieee.org/), and open a PR.
- **Better type guesses?** The rules are in `TYPE_RULES` in [`bugsweep/identify.py`](bugsweep/identify.py).
- **Ideas from the video:** Bluetooth scanning, a router-export importer, scheduled checks with alerts.
- Run the tests: `python -m unittest discover -s tests`

## Getting help

If something isn't working, or you're not sure what a result means:

1. In the app, click **Save a report for tech support** (or run `python -m bugsweep scan --save-report report.txt`).
2. Click **Get help** and email the report to tech support. Contact details live in [`support.json`](support.json).

If you think you've found a real hidden recording device **at work**, don't unplug or move it. Tell your security or IT team. If it's at home and you feel unsafe, contact local law enforcement.

## About the episode

Facts in the video come from the DOJ criminal complaint as reported by AP, Al Jazeera, Help Net Security and Techstrong.ai. **Everything about the person is alleged** until a court decides otherwise. The charge is intercepting oral communications, not espionage.

## License

MIT. See [LICENSE](LICENSE).
