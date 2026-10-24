"""Everything the box says on its own (not written by Gemini), in each supported language."""

PHRASES = {
    "en-IN": {
        "thinking": "Let me think about that…",
        "confirm": "Shall I go ahead?",
        "private": "This step is private. Please do it yourself, then press the button.",
        "payment": "This is a payment app. Please finish it yourself.",
        "blocked": "I won't open that link. It may not be safe.",
        "declined": "Okay, I won't do it.",
        "stopped": "Okay, I stopped. Nothing was ordered or sent.",
        "done": "Done.",
        "not_finished": "I couldn't finish that. Nothing was ordered or sent.",
        "too_long": "This is taking too long, so I stopped. Nothing was ordered or sent.",
        "stuck": "I got stuck, so I stopped. Nothing was ordered or sent.",
        "no_brain": "Sorry, I can't reach the internet right now. Please try again in a little while.",
    },
    "hi-IN": {
        "thinking": "एक पल, सोच रहा हूँ…",
        "confirm": "क्या मैं आगे बढ़ूँ?",
        "private": "यह कदम निजी है। कृपया इसे ख़ुद करें, फिर बटन दबाएँ।",
        "payment": "यह पेमेंट ऐप है। कृपया इसे ख़ुद पूरा करें।",
        "blocked": "मैं यह लिंक नहीं खोलूँगा। यह सुरक्षित नहीं हो सकता।",
        "declined": "ठीक है, मैं यह नहीं करूँगा।",
        "stopped": "ठीक है, मैंने रोक दिया। कुछ भी ऑर्डर या भेजा नहीं गया।",
        "done": "हो गया।",
        "not_finished": "मैं यह पूरा नहीं कर पाया। कुछ भी ऑर्डर या भेजा नहीं गया।",
        "too_long": "इसमें बहुत समय लग रहा था, इसलिए मैंने रोक दिया। कुछ भी ऑर्डर या भेजा नहीं गया।",
        "stuck": "मैं अटक गया, इसलिए रुक गया। कुछ भी ऑर्डर या भेजा नहीं गया।",
        "no_brain": "माफ़ कीजिए, अभी इंटरनेट से नहीं जुड़ पा रहा। थोड़ी देर बाद फिर कोशिश करें।",
    },
    "kn-IN": {
        "thinking": "ಒಂದು ಕ್ಷಣ, ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ…",
        "confirm": "ಮುಂದುವರಿಯಲೇ?",
        "private": "ಈ ಹಂತ ಖಾಸಗಿ. ದಯವಿಟ್ಟು ನೀವೇ ಮಾಡಿ, ನಂತರ ಬಟನ್ ಒತ್ತಿ.",
        "payment": "ಇದು ಪಾವತಿ ಆ್ಯಪ್. ದಯವಿಟ್ಟು ನೀವೇ ಪೂರ್ಣಗೊಳಿಸಿ.",
        "blocked": "ಈ ಲಿಂಕ್ ತೆರೆಯುವುದಿಲ್ಲ. ಇದು ಸುರಕ್ಷಿತವಲ್ಲದಿರಬಹುದು.",
        "declined": "ಸರಿ, ನಾನು ಅದನ್ನು ಮಾಡುವುದಿಲ್ಲ.",
        "stopped": "ಸರಿ, ನಿಲ್ಲಿಸಿದೆ. ಏನನ್ನೂ ಆರ್ಡರ್ ಮಾಡಿಲ್ಲ ಅಥವಾ ಕಳುಹಿಸಿಲ್ಲ.",
        "done": "ಆಯಿತು.",
        "not_finished": "ಅದನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು ಆಗಲಿಲ್ಲ. ಏನನ್ನೂ ಆರ್ಡರ್ ಮಾಡಿಲ್ಲ ಅಥವಾ ಕಳುಹಿಸಿಲ್ಲ.",
        "too_long": "ತುಂಬಾ ಸಮಯ ಆಗುತ್ತಿತ್ತು, ಹಾಗಾಗಿ ನಿಲ್ಲಿಸಿದೆ. ಏನನ್ನೂ ಆರ್ಡರ್ ಮಾಡಿಲ್ಲ ಅಥವಾ ಕಳುಹಿಸಿಲ್ಲ.",
        "stuck": "ನಾನು ಸಿಕ್ಕಿಹಾಕಿಕೊಂಡೆ, ಹಾಗಾಗಿ ನಿಲ್ಲಿಸಿದೆ. ಏನನ್ನೂ ಆರ್ಡರ್ ಮಾಡಿಲ್ಲ ಅಥವಾ ಕಳುಹಿಸಿಲ್ಲ.",
        "no_brain": "ಕ್ಷಮಿಸಿ, ಈಗ ಇಂಟರ್ನೆಟ್‌ಗೆ ಸಂಪರ್ಕವಾಗುತ್ತಿಲ್ಲ. ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    },
}


def phrase(lang: str, key: str) -> str:
    return PHRASES.get(lang, PHRASES["en-IN"])[key]
