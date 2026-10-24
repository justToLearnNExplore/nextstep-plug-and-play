# Features from NextStep

Rebuilt inside the box from the NextStep app's design (its public repo was only read, never changed or
called), with the box's own brain:

| Feature | How it works on the box | Live (Android 10 emulator, Vercel) |
|---|---|---|
| **Explain my screen** | says what the screen is and whether it's safe; offers to go back from a risky one | scam SMS: "a common scam message and not from your bank", offered back, 9.5 s |
| **What did I miss?** | missed calls (helper, call-log permission granted over adb), SMS, WhatsApp and other message notifications of the last hour, summarised aloud; 4–8 digit codes are blanked on the box first | missed call + SMS from "Ravi Kumar" and "a verification code", 7.4 s |
| **Phone on silent** | "louder" also turns Do Not Disturb off (permission granted over adb) and the ringer back on; from near-silent to at least 70 % | DND off, ring 7/7: "Your phone was on silent. It will ring again now.", 4.3 s |
| **Scam check** | fixed rules (look-alike bank domains, urgency, OTP/PIN requests, prize bait) + the AI, the more cautious wins; offers only the official site (or the cyber-crime portal); `.bank.in` and `.gov.in` count as official; links inside messages are never tapped unless official | fake SBI KYC SMS: warning, offered and opened onlinesbi.sbi, 8.8 s |
| **Pop-up rules** | "Rate us", "Update available", "Turn on notifications"… closed with "Not now" / "Skip" / "Close", no AI | (tests) |
| **Learned routines** | a step-by-step task that worked is kept by button names, details as slots ("type {item}", "ADD next to 'Amul {item} 1 L'"); replayed through the safety gates, the AI takes over at the first mismatch and checks the result | "Turn on the dark theme": 3 of 3 steps replayed, 2 AI turns instead of 4 |
| **Camera help** | opens the phone's camera, says where to hold it, reads the live view (nothing saved): a medicine's name, ingredient and expiry (never dosage advice; can be sent to a contact, asking first), or a written grocery list, then "Shall I add these to your Blinkit cart? I won't place the order" | drawn label: "Dolo-650 (Paracetamol 650 mg), expires February 2028"; drawn list: 5 items, "प्याज़" → onions, crossed-out item skipped; camera steps on the emulator. Android only |

Not brought over: the family's live timeline (needs a server), the floating bubble (the box has no
screen of its own), Uber and Blinkit ordering are possible step by step but untested (not on the emulator).
