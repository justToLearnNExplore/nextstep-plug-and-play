# How the box works

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
  console.py           stand-in for the box's face: the terminal, Enter as the button, speech.py as the speaker
  voice.py             the box's ears (Mac mic via ffmpeg, Pi mic via arecord); questions answered aloud
  speech.py            its voice: macOS `say` (Rishi, Lekha) or, on the Pi, Piper / espeak-ng (also Kannada)
  face.py              the Pi's button and light (gpiozero); nothing on a Mac
  serve.py             plug in and talk: waits for the phone, says hello, listens, does it, listens again
  brain/
    llm.py             picks the model route from the keys on the box
    gemini.py          Gemini direct (Google AI Studio key): retry once, then fall back to the next model
    gateway.py         Gemini via Vercel AI Gateway (OpenAI-compatible API, strict JSON schema), same fallback
    schemas.py         Plan / Turn / Action: small structured answers (fewer tokens = faster)
    brain.py           planner + operator prompts; screen sent as a numbered element list
    safety.py          gates: auto / confirm (irreversible) / private (passwords, OTPs, payment apps) / blocked
    playbooks.py       shortcuts that skip step-by-step AI (alarm, timer, call, message, YouTube, directions,
                       volume, battery, explain my screen, what did I miss, scam check, camera help, web search...)
    scam.py            scam rules + the list of official sites (only these are ever offered or opened)
    popups.py          "Rate us" / "Update available" pop-ups closed by rule, without the AI
    routines.py        learned routines: a task that worked is replayed next time by button names
  drivers/
    base.py            PhoneDriver interface + screen format
    android_adb.py     Android over ADB; uses the helper app when it can, plain ADB otherwise
    android_helper.py  installs, starts and talks to the helper app
    iphone_mirroring.py         a real iPhone through macOS iPhone Mirroring (picture + mouse and keyboard)
    iphone_mirroring_helper.swift  its Mac side: window, clicks, keys, text recognition (built on first use)
    ios_sim.py         iPhone stand-in via Xcode's iOS Simulator + idb (needs Xcode; not yet run)
helper/                the Android helper app (one Java file, no Gradle): build.sh → helper/build/*.apk
pi/                    the Raspberry Pi box: setup.sh, the start-at-power-on service, install-from-mac.sh
HARDWARE.md            the first real box: parts, wiring, setup
tests/
```

## How the brain stays fast

1. **Plan once.** One Gemini call turns the request into a yes/no question and a precise goal, and picks a playbook if one fits. A spoken request goes to Gemini as the recording itself: no separate speech-to-text step, and Hindi or Kannada is understood as it was said.
2. **Playbooks skip the AI.** Common requests are done by the box itself, checked on the phone, with no step-by-step AI:
   - **Alarms, reminders, timers:** set in one step by the helper app through the Clock's own "set alarm" / "set timer" intents (without the helper, the box opens the right Clock screen).
   - **Calls:** the box looks the person up in the phone's contacts itself (the list never goes to Gemini), asks once with the exact name and number ("Call Ravi Kumar on +91 98450 12345?"), starts the call and checks the phone is calling. Several people with that name: it asks about each in turn. Numbers Android won't call directly (emergency numbers) are put on the dialer, ready for the green button.
   - **Messages:** the WhatsApp or SMS chat opens with the text already typed; the box asks "Send “…” to Asha Rao on SMS?" and only then taps Send, and checks it went. Without WhatsApp it uses SMS and says so.
   - **YouTube, directions:** YouTube's own "play from search"; Google Maps with the route drawn (Start is never pressed). If the app says it must be updated first, the box says so instead of getting lost.
   - **Volume, battery:** ring, notification, media and call volume up, down (never silent) or to max, with the volume bar shown; the battery level is read and said without a question, since nothing changes.
   - **Web search, allowed links, opening an app:** jump straight to the right screen (a search waits until the results are there), then the operator takes over; for a question its last message is the answer itself.
3. **A few actions per call.** The operator returns up to 5 actions, each with the text it expects to see afterwards. The box re-reads the screen after each action and checks that text itself, and asks Gemini again only when the batch is used up or something unexpected appears.
4. **Numbers, not pixels.** The screen goes to Gemini as a numbered element list. The box maps `[n]` back to the element and, after the screen moves, finds it again by its label.
5. **Pictures only when needed.** A screenshot is sent on the first look, on sparse screens, after something unexpected, or when the brain asks. Never on screens with password fields or in payment apps.

The box wakes a sleeping screen itself (a sleeping phone ignores every tap) and asks the user to unlock a PIN lock screen. Safety never depends on the model: taps that order, pay, send, call, book, delete or install, accept terms or allow permissions always ask first (a number pad's backspace and "End call" don't); passwords, PINs, OTPs and payment apps are handed to the user; links outside an allowlist are blocked; an action that changes nothing is reported to the brain with what the screen shows, and the third time the box stops; going round in circles stops it too.

Every run leaves a trace on the box (`~/.nextstep-box/runs/*.jsonl`: plan, each screen as the brain saw it, each action and result) for debugging. It never leaves the box.

## The Android helper app

Plain ADB has hard limits: `uiautomator dump` starts a new process for every look (~1.1 s), `input text` types English only, the adb shell may not set alarms, and it can only change the volume with key presses. (It can read contacts, place calls and open SMS drafts by itself, so those need no helper and no extra permissions.) So the box installs a 17 KB helper app (`helper/`) over the cable and talks to it while plugged in.

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
| iPhone | a real iPhone through macOS iPhone Mirroring ✅; Xcode iOS Simulator + [idb](https://fbidb.io) (not yet run) |
| Linux box (Pi Zero 2 W / Radxa Zero 3W) | the same Python code on a Mac, or a Docker container |
| ESP32 / Pico firmware | [Wokwi](https://wokwi.com) simulator (USB HID to a phone needs a real board) |

## Running it, in full

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q        # no key or phone needed: fake Gemini + scripted phone
helper/build.sh                      # Android helper app (needs JDK 17+ and the Android SDK)
```

The box needs one model key of its own. Keys stay in `~/.nextstep-box/` and never go into the repo.

| Option | Cost | Get the key | Save it (after copying the key) |
|---|---|---|---|
| **Vercel AI Gateway** | $5 free credit every 30 days (accounts that haven't paid) | vercel.com → AI Gateway → API Keys → Create key | `pbpaste > ~/.nextstep-box/ai-gateway.key && chmod 600 ~/.nextstep-box/ai-gateway.key` |
| **Gemini direct** | Google AI Studio free tier / billing | aistudio.google.com → Get API key → Create API key in new project | `pbpaste > ~/.nextstep-box/gemini.key && chmod 600 ~/.nextstep-box/gemini.key` |

If both are present the box uses Gemini direct (one network hop fewer); `NEXTSTEP_BOX_LLM=gateway` or `=gemini` picks one. Google's free tier may use what it is sent to improve its products, so it suits testing on an emulator, not a real person's screens (the paid tier and Vercel don't). Environment variables `NEXTSTEP_BOX_AI_GATEWAY_KEY` / `NEXTSTEP_BOX_GEMINI_KEY` work too. Then, with an Android emulator or a phone with USB debugging on (`adb devices` shows it):

```bash
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"
```

`--yes` approves every question automatically (testing only); `--yes-plan` approves only the plan and says no to every other question (for trying things on a real phone); `--quiet` turns speech off. `NEXTSTEP_LANG` picks the language (`en-IN`, `hi-IN`, `kn-IN`), `NEXTSTEP_BOX_COUNTRY_CODE` is added to numbers saved without one for WhatsApp (default `91`), and `NEXTSTEP_BOX_PLANNER_MODELS` / `NEXTSTEP_BOX_OPERATOR_MODELS` override the model lists (comma-separated, first one tried first).
