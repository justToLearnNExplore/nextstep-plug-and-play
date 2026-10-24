# Voice

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

## Gemini live voice agent (prototype)

```bash
.venv/bin/python -m box.live                 # talk to it (Mac microphone and speakers); --headphones to interrupt it
.venv/bin/python -m box.live --hear req.wav  # one recorded request: timing, transcript, reply saved with --save
```

The plan for the box's voice: one two-way Gemini live session (`gemini-3.8-live`, the warm "Sulafat" voice) that
listens all the time, answers in the language it is spoken to, can be interrupted, and hands every request to the box
through a `do_task` tool (in the prototype a stand-in that does nothing yet, so the box's brain, shortcuts and safety
questions stay in charge). It knows the date and reports only what `do_task` says happened. Through loudspeakers the
microphone pauses while it talks; with headphones the person can cut in.

| Recorded request | Heard | First sound after the request ended |
|---|---|---|
| "Please call my son Ravi." | right | 2.0 s |
| "आज कौन सा दिन है? और रवि बेटे को फ़ोन लगाओ।" | "रविवार बेटे" (Ravi misheard as Sunday, after a question about the day; synthetic voice) | 2.4 s |
| "ನನ್ನ ಮಗ ರವಿಗೆ ಕರೆ ಮಾಡಿ." | right (transcript in Latin letters), answered in Kannada | 1.5 s |

It needs the Google key (test only: the free tier may use what it hears to improve Google's products) or, for real
seniors, paid credits; Vercel's free tier refuses live and voice models, and its speech endpoint can't stream. Until
then the box keeps its own voice. Gemini's one-shot voice (`gemini-3.8-flash-tts`) was also tried: natural in all three
languages, but 5.5–6.6 s before it speaks unless streamed (first sound 1.4 s).
