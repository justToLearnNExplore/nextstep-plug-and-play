# NextStep Box

**A small box an older person plugs into their phone, Android or iPhone. They just speak; the box does it on
the phone and asks before anything risky.** Inspired by [NextStep](https://github.com/justToLearnNExplore/nextstep)
(Team Northstar), but a separate project with its own brain (Gemini): no shared server, account or database.

## Status

The software works; the physical box isn't built yet. A Mac plays the box.

- **Android** (emulator): plug in → hello → speak → done, in English, Hindi or Kannada. Calls, messages, alarms,
  timers, YouTube, directions, volume, battery, explain my screen, what did I miss, scam check, medicine and grocery
  lists from the camera, learned routines.
- **iPhone** (a real iPhone 15, through iPhone Mirroring on the Mac): the talking is the same; opening apps, searching,
  reading the screen and step-by-step tasks work. One-step calls, messages and alarms, "what did I miss?" and Hindi or
  Kannada typing are next.

Feature by feature: [docs/status.md](docs/status.md).

## Next

1. **Build the Raspberry Pi box**: what to buy, wiring and setup in [HARDWARE.md](HARDWARE.md).
2. **iPhone**: the same features as Android.
3. **A real Android phone**, and Blinkit / Uber orders.
4. **Gemini live voice**: prototype ready ([docs/voice.md](docs/voice.md)); needs paid credits.

## Try it

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q                                   # no key or phone needed
helper/build.sh                                                 # the Android helper app (JDK 17 + Android SDK)
.venv/bin/python -m box --phone android "Set an alarm for 7 AM"  # one request, typed
.venv/bin/python -m box --serve --phone android                  # plug in and talk
.venv/bin/python -m box --phone iphone-mirroring --yes-plan "Open the Clock app"
```

The box needs one AI key in `~/.nextstep-box/` (never in the repo): a Vercel AI Gateway key in `ai-gateway.key`
($5 free credit a month) or a Google AI Studio key in `gemini.key`. Save it after copying it, e.g.
`pbpaste > ~/.nextstep-box/ai-gateway.key && chmod 600 ~/.nextstep-box/ai-gateway.key`. Use Vercel (or a paid
Google key) for real people: Google's free tier may use what it is sent to improve its products.

`--yes` answers every question with yes (testing only); `--yes-plan` says yes to the plan and no to everything else
(for a real phone); `NEXTSTEP_LANG` = `en-IN`, `hi-IN` or `kn-IN`.

## Safety

- Taps that order, pay, send, call, book, delete, install, accept terms or allow permissions always ask first.
- Passwords, PINs, OTPs and payment apps are left to the person; codes are blanked before anything goes to the AI.
- Links outside a short list (and links inside messages, unless official) are never opened.
- Every run is logged on the box only (`~/.nextstep-box/runs/`).

## More

| | |
|---|---|
| [docs/how-it-works.md](docs/how-it-works.md) | why a box, code layout, how the brain stays fast, the Android helper app |
| [docs/features.md](docs/features.md) | the features rebuilt from NextStep, with live results |
| [docs/voice.md](docs/voice.md) | plug in and talk; the Gemini live voice agent |
| [docs/iphone.md](docs/iphone.md) | a real iPhone through iPhone Mirroring |
| [docs/measurements.md](docs/measurements.md) | speed, models, Gemini vs Vercel |
| [HARDWARE.md](HARDWARE.md) | the Raspberry Pi box: parts, wiring, setup |
