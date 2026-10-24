# NextStep Box (plug-and-play)

**A small box an elderly person plugs into their phone, Android or iPhone, so an AI agent can use the phone for them.** It's inspired by [NextStep](https://github.com/justToLearnNExplore/nextstep) by Team Northstar but is a separate project: the box has its **own brain** (Gemini, called directly from the box with its own API key) and shares no server, account or database with the NextStep app.

> Status: **Milestone 1**, box software running on a Mac against simulators. No hardware yet.

## Why a box?

On iPhone, no app may read or tap inside other apps. A box can do it from the outside: it acts as a **USB/Bluetooth mouse and keyboard** (hands) and receives the screen over **AirPlay or USB-C video** (eyes). On Android it uses **ADB** (USB debugging), so nothing has to be installed on the phone.

| | iPhone | Android |
|---|---|---|
| Eyes | AirPlay mirroring, or USB-C video out (iPhone 15+) | ADB: element list + screenshot |
| Hands | Box acts as mouse + keyboard (AssistiveTouch); keyboard shortcuts first (⌘-Space, ⌘-H) | ADB through one persistent shell |
| Brain | On the box: Gemini plans once, then picks a few actions per screen; the box checks each result itself | same |
| One-time setup | Turn on AssistiveTouch; choose Screen Mirroring → NextStep Box | Turn on USB debugging |

## Layout

```
box/
  __main__.py          CLI: python -m box "set an alarm for 7 am" --phone android
  runner.py            agent loop: plan → one yes → playbook or see / decide / act, checked on the box
  phrases.py           everything the box says by itself, in English, Hindi and Kannada
  console.py           stand-in for the box's button, LED and speaker (terminal + macOS `say`)
  brain/
    gemini.py          Gemini client: key on the box only, retry once, then fall back to the next model
    schemas.py         Plan / Turn / Action: small structured answers (fewer tokens = faster)
    brain.py           planner + operator prompts; screen sent as a numbered element list
    safety.py          gates: auto / confirm (irreversible) / private (passwords, OTPs, payment apps) / blocked
    playbooks.py       shortcuts that skip step-by-step AI (alarm, web search, allowed links, open app)
  drivers/
    base.py            PhoneDriver interface + screen format
    android_adb.py     Android over ADB (no app on the phone)
    ios_sim.py         iPhone stand-in via Xcode's iOS Simulator + idb (needs Xcode; not yet run)
tests/
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q        # no key or phone needed: fake Gemini + scripted phone
```

The box needs its own Gemini API key (from a Google Cloud / AI Studio project of its own). Copy the key, then:

```bash
mkdir -p ~/.nextstep-box && pbpaste > ~/.nextstep-box/gemini.key && chmod 600 ~/.nextstep-box/gemini.key
```

(or set `NEXTSTEP_BOX_GEMINI_KEY`). The key never goes into the repo. Then, with an Android emulator or a phone with USB debugging on (`adb devices` shows it):

```bash
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"
```

`--yes` approves every question automatically (testing only), and `--quiet` turns speech off. `NEXTSTEP_LANG` picks the language (`en-IN`, `hi-IN`, `kn-IN`), and `NEXTSTEP_BOX_PLANNER_MODELS` / `NEXTSTEP_BOX_OPERATOR_MODELS` override the model lists (comma-separated, first one tried first).

## How the brain stays fast

1. **Plan once.** One Gemini call turns the request into a yes/no question and a precise goal, and picks a playbook if one fits.
2. **Playbooks skip the AI.** Web search, allowed links and opening apps jump straight to the right screen. Alarms use the Clock's own "set alarm" intent where allowed; otherwise the box opens the alarm list directly.
3. **A few actions per call.** The operator returns up to 5 actions, each with the text it expects to see afterwards. The box re-reads the screen after each action and checks that text itself, and asks Gemini again only when the batch is used up or something unexpected appears.
4. **Numbers, not pixels.** The screen goes to Gemini as a numbered element list. The box maps `[n]` back to the element and, after the screen moves, finds it again by its label.
5. **Pictures only when needed.** A screenshot is sent on the first look, on sparse screens, after something unexpected, or when the brain asks. Never on screens with password fields or in payment apps.

Safety never depends on the model: taps that order, pay, send, book, delete or install always ask first; passwords, PINs, OTPs and payment apps are handed to the user; links outside an allowlist are blocked; tapping the same thing on an unchanged screen is caught (warn once, then stop).

## Testing without hardware

| Part | Simulator |
|---|---|
| Android phone | Android emulator (ADB, exactly like a real phone) |
| iPhone | Xcode iOS Simulator + [idb](https://fbidb.io); a real iPhone can mirror to a Mac running UxPlay |
| Linux box (Pi Zero 2 W / Radxa Zero 3W) | the same Python code on a Mac, or a Docker container |
| ESP32 / Pico firmware | [Wokwi](https://wokwi.com) simulator (USB HID to a phone needs a real board) |

## Measurements (Android 10 emulator)

Baseline (first version, which used a remote server as its brain): "Set an alarm for 7 AM" **done in 45 s**, 6 steps of about 1.5 s see + 2.7 s think + 2.3 s act each.

| Piece | Before | Now | How |
|---|---|---|---|
| "Has the screen stopped moving?" (still screen) | 1.17 s | ~0.4 s | hash frames on the phone (50 ms) instead of pulling 8 MB frames over USB (350 ms) |
| Brain calls per action | 1 | < 1 | batches of up to 5 actions, results checked on the box (scripted run: 2 actions, 1 call) |
| Network hops per brain call | 2 (box → server → Gemini) | 1 | Gemini called from the box |
| Read the element list | 1.1 s | 1.1 s | `uiautomator dump` floor; see roadmap |
| One tap over the persistent ADB shell | 84 ms | 84 ms | — |

Live Gemini timings come next, once the box's own key is set up.

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · iOS Simulator (after Xcode is installed)
2. Speed: box brain with batches + on-box checks ✅ · playbooks ✅ · faster settle ✅ · faster screen reading (≈1.1 s → ~0.15 s, needs a small helper app on Android) · streaming voice
3. Hardware: Pi Zero 2 W / Radxa Zero 3W as USB mouse/keyboard + AirPlay receiver; mic, speaker, big button
4. Cheaper dongle (ESP32-S3 / P4) with the brain running on a phone or a small hub
