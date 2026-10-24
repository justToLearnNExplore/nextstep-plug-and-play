# NextStep Box (plug-and-play)

**A small box an elderly person plugs into their phone, Android or iPhone, so an AI agent can use the phone for them.** It's the hardware version of [NextStep](https://github.com/justToLearnNExplore/nextstep) by Team Northstar, and it reuses NextStep's backend on Google Cloud: Gemini planning, safety gates, learned routines, scam shield and the family view.

> Status: **Milestone 1**, box software running on a Mac against simulators. No hardware yet.

## Why a box?

On iPhone, no app may read or tap inside other apps. A box can do it from the outside: it acts as a **USB/Bluetooth mouse and keyboard** (hands) and receives the screen over **AirPlay or USB-C video** (eyes). On Android it uses **ADB** (USB debugging), so nothing has to be installed on the phone.

| | iPhone | Android |
|---|---|---|
| Eyes | AirPlay mirroring, or USB-C video out (iPhone 15+) | ADB: element list + screenshot |
| Hands | Box acts as mouse + keyboard (AssistiveTouch); keyboard shortcuts first (⌘-Space, ⌘-H) | ADB through one persistent shell |
| Brain | NextStep backend on Cloud Run (Gemini) | same |
| One-time setup | Turn on AssistiveTouch; choose Screen Mirroring → NextStep | Turn on USB debugging |

## Layout

```
box/
  __main__.py          CLI: python -m box "set an alarm for 7 am" --phone android
  runner.py            agent loop: plan → one yes → see / decide / act, with safety gates and timing
  backend.py           NextStep backend client (anonymous Firebase account, persistent HTTPS, warm-up)
  console.py           stand-in for the box's button, LED and speaker (terminal + macOS `say`)
  drivers/
    base.py            PhoneDriver interface + screen format (same as the NextStep app)
    android_adb.py     Android over ADB (no app on the phone)
    ios_sim.py         iPhone stand-in via Xcode's iOS Simulator + idb (needs Xcode; not yet run)
tests/
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
# Android emulator or phone with USB debugging on (adb devices shows it):
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"
```

`--yes` approves every question automatically (testing only), and `--quiet` turns speech off.

## Testing without hardware

| Part | Simulator |
|---|---|
| Android phone | Android emulator (ADB, exactly like a real phone) |
| iPhone | Xcode iOS Simulator + [idb](https://fbidb.io); a real iPhone can mirror to a Mac running UxPlay |
| Linux box (Pi Zero 2 W / Radxa Zero 3W) | the same Python code on a Mac, or a Docker container |
| ESP32 / Pico firmware | [Wokwi](https://wokwi.com) simulator (USB HID to a phone needs a real board) |

## First measurements (Android emulator, live backend)

"Set an alarm for 7 AM": **done in 45 s**, 6 steps (plan 4.7 s).

| Per step | Time | Next speed-up |
|---|---|---|
| See (element list) | ~1.1–1.5 s | faster tree reader than `uiautomator dump` |
| Think (Gemini via Cloud Run) | ~2.7 s | multi-step plans checked on the box; playbooks; skip AI on known steps |
| Act | ~1.9–2.6 s | shorter settle checks; batch actions |
| One tap / key over ADB | 57 ms | — |

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · iOS Simulator (after Xcode is installed)
2. Speed: faster screen reading, multi-step plans, playbooks, streaming voice
3. Hardware: Pi Zero 2 W / Radxa Zero 3W as USB mouse/keyboard + AirPlay receiver; mic, speaker, big button
4. Cheaper dongle (ESP32-S3 / P4) that uses the NextStep phone app as the brain
