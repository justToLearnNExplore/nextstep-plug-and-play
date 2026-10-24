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
    llm.py             picks the model route from the keys on the box
    gemini.py          Gemini direct (Google AI Studio key): retry once, then fall back to the next model
    gateway.py         Gemini via Vercel AI Gateway (OpenAI-compatible API, strict JSON schema), same fallback
    schemas.py         Plan / Turn / Action: small structured answers (fewer tokens = faster)
    brain.py           planner + operator prompts; screen sent as a numbered element list
    safety.py          gates: auto / confirm (irreversible) / private (passwords, OTPs, payment apps) / blocked
    playbooks.py       shortcuts that skip step-by-step AI (alarm, timer, call, message, YouTube, directions,
                       volume, battery, web search, allowed links, open app)
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

The box needs one model key of its own. Keys stay in `~/.nextstep-box/` and never go into the repo.

| Option | Cost | Get the key | Save it (after copying the key) |
|---|---|---|---|
| **Vercel AI Gateway** | $5 free credit every 30 days (accounts that haven't paid) | vercel.com → AI Gateway → API Keys → Create key | `pbpaste > ~/.nextstep-box/ai-gateway.key && chmod 600 ~/.nextstep-box/ai-gateway.key` |
| **Gemini direct** | Google AI Studio free tier / billing | aistudio.google.com → Get API key → Create API key in new project | `pbpaste > ~/.nextstep-box/gemini.key && chmod 600 ~/.nextstep-box/gemini.key` |

If both are present the box uses Gemini direct (one network hop fewer); `NEXTSTEP_BOX_LLM=gateway` or `=gemini` picks one. Environment variables `NEXTSTEP_BOX_AI_GATEWAY_KEY` / `NEXTSTEP_BOX_GEMINI_KEY` work too. Then, with an Android emulator or a phone with USB debugging on (`adb devices` shows it):

```bash
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"
```

`--yes` approves every question automatically (testing only), and `--quiet` turns speech off. `NEXTSTEP_LANG` picks the language (`en-IN`, `hi-IN`, `kn-IN`), `NEXTSTEP_BOX_COUNTRY_CODE` is added to numbers saved without one for WhatsApp (default `91`), and `NEXTSTEP_BOX_PLANNER_MODELS` / `NEXTSTEP_BOX_OPERATOR_MODELS` override the model lists (comma-separated, first one tried first).

## How the brain stays fast

1. **Plan once.** One Gemini call turns the request into a yes/no question and a precise goal, and picks a playbook if one fits.
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

Safety never depends on the model: taps that order, pay, send, call, book, delete or install, accept terms or allow permissions always ask first (a number pad's backspace and "End call" don't); passwords, PINs, OTPs and payment apps are handed to the user; links outside an allowlist are blocked; an action that changes nothing is reported to the brain with what the screen shows, and the third time the box stops; going round in circles stops it too.

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

### Live runs (Vercel AI Gateway free tier, Android 10 emulator, `--yes`)

On the free tier only Gemini 2.5 Flash / Flash-Lite are allowed; the box notices the refusal for 3.x models once and uses 2.5 Flash from then on.

| Request | Before | Now | How |
|---|---|---|---|
| "Set an alarm for 7:30 in the morning" | 45 s | **3.2 s** | 1 Gemini call (plan) + alarm playbook |
| "Remind me to take my tablets at 9 pm" | — | **3.5 s** | alarm labelled "Tablets" |
| "Start a 5 minute timer" | 91.6 s (12 brain turns) | **3.7 s** | timer playbook |
| "Call Ravi Kumar" | — | **3.9 s** | contact found on the box, one question, call started (in-call screen checked) |
| "Send an SMS to Asha saying I will be late for lunch" | — | **5.4 s** | SMS draft with the text, one question, Send tapped and checked |
| "WhatsApp Ravi Sharma: जन्मदिन मुबारक हो बेटा" | — | **6.3 s** | no WhatsApp on the emulator: sent as SMS, and the question said so |
| "How much battery is left on my phone?" | — | **4.3 s** | read and said, no question |
| "My phone is too quiet, I can't hear it ring" | — | **3.7 s** | ring, notifications, media, calls to max (volume playbook itself ~0.1 s) |
| "How do I get to Lalbagh in Bangalore?" | — | **6.4 s** | Maps opens with the route drawn |
| "What's the weather in Bengaluru today?" | 17.4 s (2 brain turns, retyped the search) | **6.5 s** | search waits for the results; 1 turn; says "It is 22°C and cloudy, up to 27°C" |

Most of each time is the one planning call (2.6–4.3 s). In Hindi ("रवि बेटा को फ़ोन लगाओ") the box found the contact saved in Devanagari and asked in Hindi. Not checked live: YouTube playing (the emulator's 2020 YouTube app insists on an update first; the box says so in 3.8 s) and WhatsApp (needs a real account); both are covered by the automated tests.

Step-by-step tasks are limited by the model: Gemini 2.5 Flash takes ~2–8 s per turn with a screenshot (one turn took 23 s) and misread the Clock's timer keypad several times; "minimal" thinking was faster but once claimed success on a paused timer, so the box stays on "low". Gemini 3.x Flash (paid credits or a Google AI Studio key) should do better; to be measured. All tests so far cost about $0.12 of the free $5.

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · iOS Simulator (after Xcode is installed)
2. Speed: box brain with batches + on-box checks ✅ · playbooks ✅ · faster settle ✅ · Android helper app (screen in 20 ms, any-language typing, one-step alarms) ✅ · one-step calls, messages, directions, volume, battery ✅ · streaming voice
3. Hardware: Pi Zero 2 W / Radxa Zero 3W as USB mouse/keyboard + AirPlay receiver; mic, speaker, big button
4. Cheaper dongle (ESP32-S3 / P4) with the brain running on a phone or a small hub
