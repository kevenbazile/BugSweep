# Getting started with BugSweep

*No tech experience needed. This takes about 10 minutes the first time.*

BugSweep looks at the list of gadgets connected to your Wi-Fi and points out any that look like a **hobby circuit board**, the kind of cheap part that can be turned into a hidden recorder.

It **cannot** see, hear or record anything itself. It just reads the list of connected devices.

> **Please only check networks you own**, like your home Wi-Fi. At work, ask your IT team first.

---

## Step 1: Install Python (one time only)

BugSweep runs on a free program called Python.

**Windows**
1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **Download Python** button.
3. Open the file you downloaded.
4. **Important:** at the bottom of the first screen, tick the box that says **"Add python.exe to PATH"**.
5. Click **Install Now** and wait for it to finish.

**Mac**
1. Go to **https://www.python.org/downloads/**
2. Click **Download Python**, open the file, and click **Continue** through the steps.

## Step 2: Get BugSweep

1. On the BugSweep GitHub page, click the green **Code** button, then **Download ZIP**.
2. Find the ZIP in your Downloads folder. Right-click it and choose **Extract All** (Windows), or double-click it (Mac).

## Step 3: Open it

- **Windows:** double-click **`Start BugSweep (Windows).bat`**.
  If a blue "Windows protected your PC" box appears, click **More info**, then **Run anyway**.
- **Mac:** right-click **`Start BugSweep (Mac).command`** and choose **Open**, then click **Open** again.

A window called **BugSweep** opens.

## Step 4: Try the demo

Click **Try the demo**. This uses a pretend office with 40 devices and one hidden circuit board, so you can see what a warning looks like. One row turns red.

## Step 5: Check your own network

1. Click **Check my network**.
2. The first time, you'll be asked to confirm it's your network. Click **Yes** if it is.
3. Wait up to a minute.

You'll see **every device** on your network, with its name, its type (phone, TV, printer, camera...), who made it and its network address.

**Click any device** and the panel on the right explains what it is, what it's running, what that means, and how to find where it is.

## What the colours mean

| Colour | Means | What to do |
|---|---|---|
| **Red: Needs a look** | Its chip comes from a hobby circuit-board maker | Click it and read the steps. Many smart plugs and bulbs use the same chips, so think about what you've added recently. |
| **Purple: Camera** | It looks like a camera | Make sure you know where it is and what it can see. |
| **Yellow: New** | It wasn't on your "normal" list | If you recognise it (a guest's phone, a new TV), that's fine. |
| **Blue-grey: Unidentified** | It didn't tell us what it is | Use the steps in the right-hand panel to find it. |
| **Green: Known** | You marked it as a device you know | Nothing. |

A red row is **not proof** of anything bad. It just means "worth a look."

Use the **Show:** menu to see only the devices that need attention, or type in **Search** to find one, for example "printer".

## Step 6: Find where a device is

Networks don't report where a device physically sits, so BugSweep helps you narrow it down:

1. **Read its name, type and maker.** That's often enough ("Samsung TV").
2. Click **Open its web page**. Printers, cameras and routers often show their model there.
3. Click **Live online tracker**, then unplug or switch off gadgets one at a time. When the tracker says **OFFLINE**, the last thing you unplugged is that device. *(At work, ask IT instead of unplugging things.)*
4. Click **Label it / set location** and type what it is and where it is ("Kitchen speaker, on the shelf"). BugSweep remembers it next time.

## Step 7: Save what's normal

Once you're happy with everything on the list, click **Save as normal**. Next time you check, anything new will be marked in yellow.

## Step 8: Protect yourself

Open the **Protect yourself** tab. You'll find a personal check-up based on your last check, and a checklist of simple habits: changing your router password, using a guest network for gadgets, where hidden cameras usually hide, and what to do in rentals. Tick them off as you go.

---

## Need help?

**Please reach out to tech support. Don't worry about asking "silly" questions.**

1. Click **Save a report for tech support**. A small text file is saved (to your Desktop by default).
2. Click **Get help**, then **Email support**, and attach the report.

The contact details are also in the `support.json` file in the BugSweep folder.

### Common problems

| Problem | Fix |
|---|---|
| Double-clicking the file just flashes and closes, or says Python isn't installed | Redo Step 1 and make sure you ticked **"Add python.exe to PATH"**. Then restart your computer. |
| "No other devices were found" | Make sure this computer is on the Wi-Fi you want to check, not a phone hotspot or VPN. |
| The check seems stuck | Give it up to 2 minutes. If it's still stuck, close the window and try again, then contact tech support. |
| I found something red at work | Don't unplug or move it. Tell your IT or security team. |
| I found something and I feel unsafe at home | Contact local law enforcement. |
