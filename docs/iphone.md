# A real iPhone through iPhone Mirroring

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
