"""Voice: hearing one utterance, spoken yes/no answers, spoken requests, and the plug-in-and-talk loop."""

import io
import math
import struct

import pytest
from test_brain import HOME, FakeConsole, FakeGemini, FakePhone, plan

from box.brain.brain import Brain
from box.brain.llm import Audio
from box.config import Config
from box.runner import Runner
from box.serve import serve
from box.voice import RATE, Ears, VoiceConsole


def pcm(seconds: float, amplitude: int) -> bytes:
    n = int(seconds * RATE)
    return struct.pack(f"<{n}h", *(int(amplitude * math.sin(2 * math.pi * 300 * i / RATE)) for i in range(n)))


def test_one_utterance_is_cut_from_first_word_to_a_second_of_quiet():
    stream = io.BytesIO(pcm(0.5, 30) + pcm(1.0, 6000) + pcm(1.5, 30) + pcm(2.0, 6000))
    wav = Ears._utterance(stream, wait_s=5, max_s=15, quiet_s=1.0)
    seconds = (len(wav) - 44) / 2 / RATE
    assert 1.9 < seconds < 2.4  # 0.3 s before the first word + the speech + 1 s of quiet; not the second burst


def test_nobody_speaking_gives_nothing():
    assert Ears._utterance(io.BytesIO(pcm(2.0, 30)), wait_s=0, max_s=15, quiet_s=1.0) is None
    assert Ears._utterance(io.BytesIO(b""), wait_s=5, max_s=15, quiet_s=1.0) is None


class FakeEars:
    def __init__(self, *heard):
        self.heard = list(heard)

    def listen(self, wait_s=8.0, max_s=15.0, quiet_s=1.0, pressed=None):
        return self.heard.pop(0) if self.heard else None


def voice_ui(ears, answers):
    asked = []

    def understand(wav_b64, question):
        asked.append(question)
        return answers.pop(0)
    return VoiceConsole(ears, understand, "en-IN", speak=False), asked


def test_spoken_answers():
    ui, _ = voice_ui(FakeEars(b"RIFF1"), ["yes"])
    assert ui.ask("Shall I call Ravi?") is True
    ui, asked = voice_ui(FakeEars(b"RIFF1", b"RIFF2"), ["unclear", "no"])
    assert ui.ask("Send this to Asha?") is False and len(asked) == 2
    ui, _ = voice_ui(FakeEars(), [])
    assert ui.ask("Shall I?") is False  # silence twice is not a yes


def test_a_spoken_request_is_heard_by_the_planner_itself():
    p = plan("set_alarm", [("hour", "7")]).model_copy(update={"heard": "सुबह सात बजे का अलार्म लगा दो"})
    g = FakeGemini(p)
    report = Runner(Config(), Brain(g), FakePhone(HOME), FakeConsole(), trace=False).run(speech_wav_b64="UklGRg==")
    assert report.outcome == "done" and report.goal == "सुबह सात बजे का अलार्म लगा दो"
    assert any(isinstance(part, Audio) for part in g.calls[0][1])


def test_talk_that_is_not_a_request_is_not_acted_on():
    g = FakeGemini(plan(goal="").model_copy(update={"heard": ""}))
    con = FakeConsole()
    report = Runner(Config(), Brain(g), FakePhone(HOME), con, trace=False).run(speech_wav_b64="UklGRg==")
    assert report.outcome == "not_understood" and con.asked == [] and "say it again" in con.said[-1]


class Stop(Exception):
    pass


def test_plug_in_and_talk():
    states = iter(["absent", "unauthorized", "ready", "ready", "ready", "absent"])

    def state(kind, serial):
        try:
            return next(states)
        except StopIteration:
            raise Stop from None

    phones = []

    def make_phone(kind, serial):
        phones.append(FakePhone(HOME))
        return phones[-1]

    said = []
    ui = VoiceConsole(FakeEars(), lambda w, q: "yes", "en-IN", speak=False, auto_yes=True)
    ui.say = said.append
    ui.speak_now = said.append
    g = FakeGemini(plan("set_alarm", [("hour", "7")]).model_copy(update={"heard": "alarm at 7"}))
    with pytest.raises(Stop):
        serve(Config(), Brain(g), "android", None, make_phone, ui, FakeEars(b"RIFF"), state=state, sleep=lambda s: None)
    assert said[0] == "Please tap Allow on the phone's screen."
    assert said[1] == "Hello! I'm ready. Tell me what you need."
    assert phones[0].alarms == [(7, 0, "")]  # what was heard got done
    assert said[-1] == "The phone is unplugged. Goodbye!"


def test_the_button_says_yes():
    ui, asked = voice_ui(FakeEars(b""), [])
    assert ui.ask("Send this to Asha?") is True and asked == []  # no AI needed for a press


def test_pressing_the_button_while_waiting_means_listen_now():
    states = iter(["ready", "ready", "absent"])

    def state(kind, serial):
        try:
            return next(states)
        except StopIteration:
            raise Stop from None

    said = []
    ui = VoiceConsole(FakeEars(), lambda w, q: "yes", "en-IN", speak=False, auto_yes=True)
    ui.say = ui.speak_now = said.append
    g = FakeGemini(plan("set_alarm", [("hour", "6")]).model_copy(update={"heard": "alarm at 6"}))
    phone = FakePhone(HOME)
    with pytest.raises(Stop):
        serve(Config(), Brain(g), "android", None, lambda k, s: phone, ui, FakeEars(b"", b"RIFF"), state=state,
              sleep=lambda s: None)
    assert "Yes? Tell me." in said and phone.alarms == [(6, 0, "")]


def test_voices_and_microphone_on_a_pi(monkeypatch):
    from box import speech, voice
    monkeypatch.setattr(speech.sys, "platform", "linux")
    monkeypatch.setattr(speech.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "espeak-ng" else None)
    assert speech.voice_for("kn-IN") == "espeak:kn" and speech.voice_for("hi-IN") == "espeak:hi"
    assert speech.speech_argv("ನಮಸ್ಕಾರ", "espeak:kn") == ["espeak-ng", "-v", "kn", "-s", "150", "ನಮಸ್ಕಾರ"]
    piper = speech.speech_argv("Hello; rm -rf /", "piper:/v/en.onnx")
    assert piper[0] == "sh" and piper[-2:] == ["Hello; rm -rf /", "/v/en.onnx"]  # text is an argument, not shell code
    assert speech.speech_argv("Hi", "say:Rishi") == ["say", "-r", "185", "-v", "Rishi", "Hi"]
    monkeypatch.setattr(voice.sys, "platform", "linux")
    assert Ears("plughw:1,0").command()[:4] == ["arecord", "-q", "-D", "plughw:1,0"]
