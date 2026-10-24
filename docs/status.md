# Status (25 October 2026)

The box's software works; the physical box isn't built yet. In every test a Mac played the box.

| | Box + Android | Box + iPhone |
|---|---|---|
| Tested on | Android 10 emulator | a real iPhone 15 (iOS 26.2.1), through iPhone Mirroring |
| Plug in → hello → speak → done | ✅ | ✅ the voice part is the same box |
| Understands and speaks English, Hindi, Kannada | ✅ | ✅ |
| Asks before order / send / pay / call; leaves PINs and OTPs to the person | ✅ | ✅ |
| Opening apps, web search, reading the screen, step-by-step tasks | ✅ | ✅ tested: opened Clock, read the weather in Safari, found the iOS version in Settings |
| One step: alarms, timers, calls, messages, volume, battery | ✅ | not yet (planned: links in Safari, the status bar, Control Center) |
| Explain my screen, scam check, learned routines, pop-up rules | ✅ | same code, not tested on iPhone yet |
| What did I miss? Phone off silent | ✅ | not yet (planned: read them from the screen) |
| Medicine label and grocery list from the camera | ✅ | the camera can't be used during iPhone Mirroring (workaround: read a photo from Photos) |
| Typing Hindi and Kannada into apps | ✅ | English for now |
| Speed of a simple task | 4–7 s | about 10–30 s |

Compared with the NextStep app: the box does what the app does on Android except the family's live timeline
(it needs a server) and the floating on-screen bubble (the box has no screen of its own). Blinkit and Uber orders work
step by step but haven't been tested (they aren't on the emulator).

## Next

1. Build the Raspberry Pi box ([HARDWARE.md](../HARDWARE.md)) and test it with a real Android phone.
2. iPhone: the same features as Android, through iPhone Mirroring first, then on the Pi (USB keyboard and mouse,
   AirPlay to see the screen).
3. The Gemini live voice agent: connect it to the box's brain; switch it on once paid credits are added.

## Roadmap

1. **Milestone 1** (now): box software + Android emulator ✅ · NextStep's features in the box ✅ · a real iPhone through iPhone Mirroring ✅ (typing English only) · a real Android phone · iOS Simulator (after Xcode is installed)
2. Speed: box brain with batches + on-box checks ✅ · playbooks ✅ · faster settle ✅ · Android helper app (screen in 20 ms, any-language typing, one-step alarms) ✅ · one-step calls, messages, directions, volume, battery ✅ · voice: plug in and talk ✅ · Gemini live voice agent (prototype ✅; connect to the brain; needs credits)
3. Hardware: the first box on a Raspberry Pi Zero 2 W, Android first (parts, wiring and setup: [HARDWARE.md](../HARDWARE.md)); then iPhone (USB mouse/keyboard + AirPlay receiver)
4. Cheaper dongle (ESP32-S3 / P4) with the brain running on a phone or a small hub
