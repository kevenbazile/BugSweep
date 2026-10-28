# Episode notes: "OpenAI Got Bugged. So I Wrote a Repo."

*Headline → Repo, Oct 2026. Long-form ~4:10, Short ~58 s.*
Opener: **"One headline. One repo. Sixty seconds. Let's ship it."**

What to record from this repo for the screen-recording session (set the editor and terminal font to 20pt+ first, 28pt+ for the Short crop).

| Shot | Script time | What to record | Command / file |
|---|---|---|---|
| B13 | 1:50 | MAC split into Vendor / Device | Use `24:0A:C4` \| `3B:7E:19` from the sample |
| B14 | 2:05 | Coding bugsweep, sped up 4x | `bugsweep/core.py`: `normalize_mac`, `match_vendor`, `check` |
| B15 | 2:20 | Vendor list, matching lines highlighted | `bugsweep/data/vendors.csv`: highlight the `24:0A:C4` row |
| B16 | 2:35 | baseline.json vs new scan, new row flashes red | `samples/sample_baseline.json` next to `samples/sample_scan.csv` (row `10.20.0.31` is missing from the baseline) |
| B17 | 2:55 | 40-device file scrolling fast | `samples/sample_scan.csv` |
| B18 | 3:00 | Terminal run, one red row of 40 | `python -m bugsweep demo`. Short: freeze before the result prints |
| B19 | 3:15 | "WHAT IT CAN'T DO" card | Never-joins-Wi-Fi devices; smart plugs use the same chips |
| B20 | 3:30 | GitHub page, star click | Your repo page |

Bonus shot for non-technical viewers: the app window (`python -m bugsweep`, then **Try the demo**) shows the same result as a red banner.

## Repo checklist (from the script)

- [x] README with a one-line pitch and an "only scan networks you own" note
- [ ] Demo GIF in the README (record B18, save as `docs/demo.gif`, then uncomment the line in README)
- [x] Vendor-prefix list in its own file (`bugsweep/data/vendors.csv`) so viewers can PR entries
- [ ] Tag the repo with the episode name and put the video link in the README (`[VIDEO LINK]`)
- [x] Sample scan file (40 devices, one dev board) so viewers can rerun the demo

## Legal language

Say "allegedly" or "according to the complaint" on every claim about the person. The charge is wiretapping (intercepting oral communications), not espionage. Don't call him a spy as fact.
