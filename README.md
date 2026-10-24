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
  voice.py             the box's ears (Mac microphone via ffmpeg) and voice (Indian macOS voices); spoken yes/no
  serve.py             plug in and talk: waits for the phone, says hello, listens, does it, listens again
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
    iphone_mirroring.py         a real iPhone through macOS iPhone Mirroring (picture + mouse and keyboard)
    iphone_mirroring_helper.swift  its Mac side: window, clicks, keys, text recognition (built on first use)
    ios_sim.py         iPhone stand-in via Xcode's iOS Simulator + idb (needs Xcode; not yet run)
helper/                the Android helper app (one Java file, no Gradle): build.sh → helper/build/*.apk
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

If both are present the box uses Gemini direct (one network hop fewer); `NEXTSTEP_BOX_LLM=gateway` or `=gemini` picks one. Google's free tier may use what it is sent to improve its products, so it suits testing on an emulator, not a real person's screens (the paid tier and Vercel don't). Environment variables `NEXTSTEP_BOX_AI_GATEWAY_KEY` / `NEXTSTEP_BOX_GEMINI_KEY` work too. Then, with an Android emulator or a phone with USB debugging on (`adb devices` shows it):

```bash
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"
```

`--yes` approves every question automatically (testing only); `--yes-plan` approves only the plan and says no to every other question (for trying things on a real phone); `--quiet` turns speech off. `NEXTSTEP_LANG` picks the language (`en-IN`, `hi-IN`, `kn-IN`), `NEXTSTEP_BOX_COUNTRY_CODE` is added to numbers saved without one for WhatsApp (default `91`), and `NEXTSTEP_BOX_PLANNER_MODELS` / `NEXTSTEP_BOX_OPERATOR_MODELS` override the model lists (comma-separated, first one tried first).

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

## Plug in and talk

```bash
NEXTSTEP_BOX_LLM=gateway .venv/bin/python -m box --serve --phone android
```

The box waits for a phone. When one is plugged in (`adb` sees it; on first use it asks the person to tap Allow for USB debugging) it says hello and listens. The person just speaks; the box asks its one question ("Shall I start a timer for 2 minutes?"), hears "yes" / "haan" / "houdu" / "no" (or "done" after a private step), does it, says what happened, and listens again. Unplugging the phone ends the session. `--hear request.wav` does one spoken request from a recording, for testing without a microphone.

- **Ears:** the Mac's microphone (the real box: a small mic). Whether someone is speaking is decided on the box from loudness alone (a quiet room measures ~80, speech 2,700–5,700), recording runs from just before the first word to a second of quiet, and nothing is sent while it is quiet.
- **Understanding:** the recording goes to Gemini with the planning prompt; talk that isn't a request (a TV, people talking) is not acted on ("Sorry, I didn't catch that"). Spoken yes/no answers are one small call each.
- **Voice:** macOS `say` with Indian voices, Rishi (English) and Lekha (Hindi); macOS has no Kannada voice yet. The box finishes speaking before it listens, so it doesn't hear itself.
- **Needs:** Microphone access for the app that runs the box. Use Vercel (or a paid Google key) for a real person's voice, not the free Google key. Through Vercel a recording goes as a file (its OpenAI-style `input_audio` is refused).

| Spoken request (Android 10 emulator, Vercel, `--yes`) | Time | Result |
|---|---|---|
| "Set an alarm for seven in the morning" (recording, Rishi voice) | 5.8 s | heard right, 1 Gemini call, alarm set |
| "सुबह सात बजे का अलार्म लगा दो" (recording, Lekha voice, box in Hindi) | 5.2 s | heard right, asked and answered in Hindi, alarm set |
| `--serve`: "Start a timer for two minutes" said aloud near the Mac | ready 3.7 s after start; timer running 10.2 s after the speaking began | ~2 s speech + 1 s quiet + 6.3 s to plan and set it; checked on screen |

## A real iPhone through iPhone Mirroring

The box will see an iPhone only as a picture and work it as a mouse and keyboard. macOS iPhone Mirroring (macOS 15+, iOS 18+, same Apple ID, no cable needed) gives a Mac exactly that, so the same brain runs on a real iPhone today:

```bash
NEXTSTEP_BOX_LLM=gateway .venv/bin/python -m box --phone iphone-mirroring --yes-plan "Which iOS version is my phone on?"
```

- **Eyes:** the iPhone Mirroring window is captured (0.07–0.11 s) and Apple's text recognition on the Mac finds its words and where they are; a look takes ~0.2 s. The screenshot goes with every look, because many iPhone buttons are icons without words. The Mac reads English and other Latin-script text, not Hindi or Kannada (the brain reads those from the screenshot).
- **Hands:** clicks and drags into the window are taps and swipes; ⌘1 Home, ⌘2 app switcher, ⌘3 Spotlight (apps open through Spotlight, 4–7 s); typing is key codes (~40 ms a character). Found by trying: iPhone Mirroring's own shortcuts need ⌘ as a flag, while ⌘ and Shift for the iPhone must be pressed as keys of their own; typed characters and pasting don't reach the iPhone, so only text a US keyboard can type works for now. On the home screen an app's name can't be tapped, only its icon.
- **Safety, without app names or field information:** a screen showing "UPI" counts as a payment app, and on a screen that mentions a password, PIN or OTP no screenshot goes to the brain and any typing is the user's. The capture never stays on the Mac's disk.
- **Needs:** iPhone Mirroring open, and Screen Recording and Accessibility allowed for the app that runs the box (System Settings → Privacy & Security). The Mac's pointer is the box's while it works. For a real person's screens use Vercel (or a paid Google key), not the free Google key.

Live on an iPhone 15 (iOS 26.2.1), Vercel free tier, `--yes-plan`:

| Request | Time | Result |
|---|---|---|
| "Open the Clock app" | 10.5–30.8 s | Clock open (Spotlight sometimes needs a second try) |
| "What's the weather in Bengaluru today?" | 25.2 s | "21°C and raining, feels like 24°C; today 27°C / 20°C", from Google in Safari, 1 brain turn |
| "Which iOS version is my phone on?" | 22.1 s | "26.2.1", 1 brain turn |

Vercel's free tier allows 5 requests a minute, so step-by-step tasks hit the limit; the box now waits as long as it is told (here ~12 s) and tries once more instead of giving up. That wait is most of the planning time above (11–14 s instead of 3–4 s).

## Testing without hardware

| Part | Simulator |
|---|---|
| Android phone | Android emulator (ADB, exactly like a real phone) |
| iPhone | a real iPhone through macOS iPhone Mirroring ✅; Xcode iOS Simulator + [idb](https://fbidb.io) (not yet run) |
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

Step-by-step tasks are limited by the model: Gemini 2.5 Flash takes ~2–8 s per turn with a screenshot (one turn took 23 s) and misread the Clock's timer keypad several times; "minimal" thinking was faster but once claimed success on a paused timer, so the box stays on "low". All Vercel tests so far cost about $0.16 of the free $5.

### Gemini direct (free Google AI Studio key) vs Vercel (free tier)

Which models a free AI Studio key may use (checked 24 Oct 2026 with one tiny request each):

| Answers in ~2 s | Busy or timing out | Not for this key |
|---|---|---|
| 3.6 Flash, 3.5 Flash, 3 Flash Preview, 3.1 Flash-Lite | 3.8 Flash (503 after 8 s, 504 after 29 s), 3.7 Flash (504 after 29 s), flash-latest | 2.5 Flash / Flash-Lite / Pro ("no longer available to new users"), every Pro model and gemini-4-argon (no free quota) |

It also allows only about 5 requests a minute per model (the 6th within a minute was refused; a minute later it worked again), and some models only 20 a day (3 Flash Preview ran out the same day; the box then leaves it out until it restarts). The box copes: a model that is refused is never tried again, a busy or slow one rests for 5 minutes and is tried after the others, and only quick failures are retried. The free Vercel tier is the opposite: only 2.5 Flash / Flash-Lite.

Same screens, same prompts, one call at a time (planning: alarm / call / weather; one operator step on the Clock's timer screen):

| Model (route) | Planning | Operator step |
|---|---|---|
| 3 Flash Preview (direct) | 1.8 / 1.3 / 1.4 s | 1.9 s, 2.6 s with screenshot |
| 3.6 Flash (direct) | 5.2 / 2.0 / 9.5 s | 8.4 s |
| 3.1 Flash-Lite (direct) | 15.8 / 4.1 / 3.2 s | 2.1 s but wrong (a 5-second timer); 504 after 29 s with screenshot |
| 2.5 Flash (Vercel) | 2.9 / 2.2 / 2.0 s | 6.0 s, 3.8 s with screenshot |
| 2.5 Flash-Lite (Vercel) | 2.7 / 1.4 / 2.5 s | 3.7 s, 2.8 s with screenshot |

On the emulator (direct = models 3 Flash Preview, then 3.6 Flash, then 3.5 Flash):

| Request | Direct | Vercel (2.5 Flash) |
|---|---|---|
| "Set an alarm for 7:30 in the morning" | **1.7 s** | 3.6 s |
| "Call Ravi Kumar" | **2.8 s** | 3.4 s |
| "What's the weather in Bengaluru today?" | **5.4 s** | 7.7 s |
| "Start a 5 minute timer", step by step (no helper app, screen asleep at the start) | **done in 3 turns** (50 s and 76 s; one answer took 28 s) | stuck after 6 turns (66 s), nothing set |

Gemini 3.x reads the timer keypad right where 2.5 Flash keeps failing. Without the helper app most of the step-by-step time is Android itself: reading the screen of a running timer takes plain ADB ~10 s.

So the box now tries **3 Flash Preview, 3.6 Flash, 3.5 Flash, then 2.5 Flash** by default (`NEXTSTEP_BOX_PLANNER_MODELS` / `NEXTSTEP_BOX_OPERATOR_MODELS` change it, e.g. to put 3.8 Flash first on a paid key). On Vercel's free tier the three 3.x models are refused in ~0.2 s each, once per run, and 2.5 Flash answers. The free Google tier's speed varies: in a later run with this order the same alarm request took 11.6 s to plan instead of 1.7 s.

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · a real iPhone through iPhone Mirroring ✅ (typing English only) · iOS Simulator (after Xcode is installed)
2. Speed: box brain with batches + on-box checks ✅ · playbooks ✅ · faster settle ✅ · Android helper app (screen in 20 ms, any-language typing, one-step alarms) ✅ · one-step calls, messages, directions, volume, battery ✅ · voice: plug in and talk ✅ · streaming voice
3. Hardware: Pi Zero 2 W / Radxa Zero 3W as USB mouse/keyboard + AirPlay receiver; mic, speaker, big button
4. Cheaper dongle (ESP32-S3 / P4) with the brain running on a phone or a small hub
