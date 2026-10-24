# NextStep Box (plug-and-play)

**A small box an elderly person plugs into their phone, Android or iPhone, so an AI agent can use the phone for them.** It's inspired by [NextStep](https://github.com/justToLearnNExplore/nextstep) by Team Northstar but is a separate project: the box has its **own brain** (Gemini, called directly from the box with its own API key) and shares no server, account or database with the NextStep app.

> Status: **Milestone 1**, box software running on a Mac against simulators. No hardware yet.

## Why a box?

On iPhone, no app may read or tap inside other apps. A box can do it from the outside: it acts as a **USB/Bluetooth mouse and keyboard** (hands) and receives the screen over **AirPlay or USB-C video** (eyes). On Android it uses **ADB** (USB debugging) and installs a tiny helper app over the cable by itself, so the user only turns on USB debugging once.

| | iPhone | Android |
|---|---|---|
| Eyes | AirPlay mirroring, or USB-C video out (iPhone 15+) | Helper app over ADB: element list in ~20 ms + screenshot |
| Hands | Box acts as mouse + keyboard (AssistiveTouch); keyboard shortcuts first (⌘-Space, ⌘-H) | Helper app: taps, swipes, typing in any language (plain ADB as fallback) |
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
    android_adb.py     Android over ADB; uses the helper app when it can, plain ADB otherwise
    android_helper.py  installs, starts and talks to the helper app
helper/                the Android helper app (one Java file, no Gradle): build.sh → helper/build/*.apk
    ios_sim.py         iPhone stand-in via Xcode's iOS Simulator + idb (needs Xcode; not yet run)
tests/
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q        # no key or phone needed: fake Gemini + scripted phone
helper/build.sh                      # Android helper app (needs JDK 17+ and the Android SDK)
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
2. **Playbooks skip the AI.** Web search, allowed links and opening apps jump straight to the right screen. Alarms are set in one step by the helper app through the Clock's own "set alarm" intent; without the helper, the box opens the alarm list directly.
3. **A few actions per call.** The operator returns up to 5 actions, each with the text it expects to see afterwards. The box re-reads the screen after each action and checks that text itself, and asks Gemini again only when the batch is used up or something unexpected appears.
4. **Numbers, not pixels.** The screen goes to Gemini as a numbered element list. The box maps `[n]` back to the element and, after the screen moves, finds it again by its label.
5. **Pictures only when needed.** A screenshot is sent on the first look, on sparse screens, after something unexpected, or when the brain asks. Never on screens with password fields or in payment apps.

Safety never depends on the model: taps that order, pay, send, book, delete or install always ask first; passwords, PINs, OTPs and payment apps are handed to the user; links outside an allowlist are blocked; tapping the same thing on an unchanged screen is caught (warn once, then stop).

## The Android helper app

Plain ADB has hard limits: `uiautomator dump` starts a new process for every look (~1.1 s), `input text` types English only, and the adb shell may not set alarms. So the box installs a 17 KB helper app (`helper/`) over the cable and talks to it while plugged in.

- **Only while plugged in.** The box starts it with `am instrument -w`; when the cable is pulled, adb drops and Android ends it. It has no app icon, no screen of its own and nothing that runs in the background.
- **Only the box can talk to it.** It listens on a local socket and accepts only adb (the shell user), not other apps on the phone.
- **No internet permission.** It can't send anything anywhere; the box decides what goes to Gemini.
- **Leaves the user's accessibility services alone** (TalkBack etc. keep running).
- **Never types into password fields**, on top of the box's own safety gates.
- **Falls back by itself.** If it can't be installed or stops, the box carries on with plain ADB; `--no-helper` forces that.

It is signed with a key made on first build in `~/.nextstep-box/` (never in the repo). The box reinstalls it whenever its version changes.

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
| Read the element list | 1.1 s | **20 ms** | helper app: accessibility tree already connected |
| Screenshot (720 px JPEG) | ~0.3 s | 0.2 s | helper app: captured and compressed on the phone |
| One tap / key | 84 ms | **~10 ms** | helper app: input injected directly |
| Set an alarm | 45 s (6 AI steps) | **instant, no AI steps** | helper app sends the Clock's "set alarm" intent |
| Type Hindi / Kannada | not possible | 23 ms | helper app sets the field's text |

Scripted 3-tap task on the Clock app (no Gemini, same steps): **10.7 s with plain ADB → 3.4 s with the helper**; time spent reading the screen 4.9 s → 0.24 s. Most of what's left is waiting for the app's own animations to finish.

Live Gemini timings come next, once the box's own key is set up.

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · iOS Simulator (after Xcode is installed)
2. Speed: box brain with batches + on-box checks ✅ · playbooks ✅ · faster settle ✅ · Android helper app (screen in 20 ms, any-language typing, one-step alarms) ✅ · streaming voice
3. Hardware: Pi Zero 2 W / Radxa Zero 3W as USB mouse/keyboard + AirPlay receiver; mic, speaker, big button
4. Cheaper dongle (ESP32-S3 / P4) with the brain running on a phone or a small hub
