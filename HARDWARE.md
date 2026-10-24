# The first real box (Raspberry Pi)

The first box runs the same Python code as the Mac: it listens, thinks with Gemini over Wi‑Fi, and
works an **Android** phone through one USB cable. iPhone support on the Pi comes second, after
testing (see the end). An ESP32 alone can't be this box: it can't see the phone's screen or run the
brain.

## Parts (about ₹2,700–4,000 in all)

Prices are rough estimates, except the Pi's (₹1,500–2,000 at Indian shops in 2026). Check Robu,
Robocraze or similar.

| # | Part | For | Rough price |
|---|---|---|---|
| 1 | **Raspberry Pi Zero 2 WH** ("H" = pins already soldered) | the box's computer | ₹1,500–2,000 |
| 2 | **INMP441** I2S microphone module | ears | ₹150–300 |
| 3 | **MAX98357A** I2S amplifier module | voice | ₹200–350 |
| 4 | Small speaker, 3 W, 4 Ω (or 8 Ω) | voice | ₹80–150 |
| 5 | Push button (a big arcade button is easiest for older hands) | press to talk / "yes" / "done" | ₹30–150 |
| 6 | One LED + 330 Ω resistor (or a button with a built-in LED) | shows listening / thinking / done | ₹10–30 |
| 7 | Female–female jumper wires (one pack) | connecting 2, 3, 5, 6 to the Pi | ₹60–100 |
| 8 | microSD card, 32 GB, A1 / Class 10 | the Pi's disk | ₹300–400 |
| 9 | 5 V 2.5 A micro‑USB charger (a good one: weak ones cause restarts) | power | ₹300–500 |
| 10 | Micro‑USB **OTG** adapter (male micro‑B → female USB‑A) | the Pi's USB port to the phone's own USB cable | ₹80–150 |
| 11 | A small case or project box | | — |

The microphone and amplifier modules usually come with loose header pins that need soldering (or
buy them pre-soldered). No screen or keyboard is needed: the Pi is set up from the Mac over Wi‑Fi.

## Wiring (Pi Zero 2 W pin numbers)

The microphone and amplifier share one I2S sound bus; Linux sees them as one sound card
(`dtoverlay=googlevoicehat-soundcard`, to be confirmed on first boot with `arecord -l` / `aplay -l`).

| Module pin | Pi pin |
|---|---|
| INMP441 VDD | 1 (3.3 V) |
| INMP441 GND, L/R | 6 (GND) — L/R to GND = left channel |
| INMP441 SCK | 12 (GPIO18, bit clock) |
| INMP441 WS | 35 (GPIO19, word select) |
| INMP441 SD | 38 (GPIO20, data in) |
| MAX98357A Vin | 2 (5 V) |
| MAX98357A GND | 9 (GND) |
| MAX98357A BCLK | 12 (GPIO18, shared) |
| MAX98357A LRC | 35 (GPIO19, shared) |
| MAX98357A DIN | 40 (GPIO21, data out) |
| MAX98357A + / − | the speaker |
| Button | 16 (GPIO23) and 14 (GND) |
| LED (long leg via 330 Ω) | 18 (GPIO24); short leg to 20 (GND) |

## Setting it up (when the parts arrive)

1. On the Mac, Raspberry Pi Imager → Raspberry Pi OS Lite (64-bit) → in its settings: host name
   `nextstep-box`, a user, Wi‑Fi, and SSH on. Write the card, put it in the Pi, power on.
2. From the Mac, in this repo: `./pi/install-from-mac.sh <user>@nextstep-box.local`. It copies the
   repo, the Android helper app and the box's key (to `~/.nextstep-box/` on the Pi, chmod 600), then
   runs `pi/setup.sh` on the Pi: Python, ADB, sound tools, espeak-ng, the I2S sound card, and a
   service that starts the box at every power-on. Reboot once when it says so.
3. Plug in an Android phone with USB debugging on, tap **Allow** once (the box asks), and talk.
   The box's log: `journalctl -u nextstep-box -f`. If it doesn't hear you, check the microphone with
   `arecord -l`; `NEXTSTEP_BOX_MIC_MIN` (default 400) is the quietest sound it counts as speech.

## What changes in the software for the Pi

| Piece | On the Mac today | On the Pi |
|---|---|---|
| Start | `python -m box --serve` by hand | `pi/nextstep-box.service`: at power-on, restarted if it stops ✅ |
| Ears | MacBook mic via ffmpeg | INMP441 via ALSA `arecord` (same speech detection) ✅ |
| Voice | macOS `say` (Rishi, Lekha) | espeak-ng offline for English, Hindi **and Kannada** ✅; Piper for a more natural English voice if installed (`NEXTSTEP_BOX_PIPER_MODEL`); a cloud voice for Hindi and Kannada is a later choice |
| Button / light | Enter key, terminal lines | GPIO23 button: "listen now", "yes" / "done" ✅; GPIO24 LED: on = listening, fast blink = working, slow blink = asking ✅ |
| Keys, helper app | `~/.nextstep-box/`, built on the Mac | copied by `pi/install-from-mac.sh` (no Android SDK on the Pi) ✅ |
| Internet | the Mac's | home Wi‑Fi, set once on the card (later perhaps the phone's own data) |

✅ = written and tested on the Mac (unit tests); not yet run on a real Pi.

## iPhone on the Pi (second step, to be tested)

- **Hands:** the Pi's USB port can act as a keyboard and mouse ([zero-hid](https://github.com/thewh1teagle/zero-hid));
  an iPhone takes a mouse through AssistiveTouch. Unproven: exact pointing.
- **Eyes:** AirPlay to the Pi ([UxPlay](https://github.com/antimof/Uxplay), tested on the Pi Zero 2 W); the
  iPhone has to start Screen Mirroring itself.
- **Reading words:** Apple's text recognition is Mac-only; on the Pi, another engine or Gemini reading the screenshot.
- **Typing:** English only, as through iPhone Mirroring.
