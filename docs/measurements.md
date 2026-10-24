# Measurements

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
