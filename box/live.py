"""Prototype: the box's voice as a Gemini live voice agent (two-way, natural voice, can be interrupted).

Test only, with the Google key (Vercel's free tier refuses live models; they come with paid credits).
The box's current voice (voice.py + speech.py) stays the default until then.

The agent hears the microphone all the time and answers aloud, in the language it is spoken to
(English, Hindi, Kannada). When the person asks for something to be done on the phone, it calls the
box's tool do_task(request); in this prototype that tool is a stand-in that only reports the request
(step 2 connects it to the box's brain, shortcuts and safety questions).

    python -m box.live                        # talk to it: Mac microphone and speakers
    python -m box.live --headphones           # the same, and you can interrupt it while it talks
    python -m box.live --hear request.wav     # one recorded request: times the reply and saves it as a WAV

Through loudspeakers the microphone pauses while the agent talks, so it doesn't hear itself; with
headphones it keeps listening, so the person can cut in.
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

from .brain.llm import read_key
from .config import Config

MODEL = os.getenv("NEXTSTEP_BOX_LIVE_MODEL", "gemini-3.8-live")
VOICE = os.getenv("NEXTSTEP_BOX_LIVE_VOICE", "Sulafat")  # warm; others: Kore, Achird, Charon...
IN_RATE, OUT_RATE = 16000, 24000
CHUNK_S = 0.04
LANGUAGES = {"en-IN": "Indian English", "hi-IN": "Hindi", "kn-IN": "Kannada"}

SYSTEM = """
You are NextStep, the voice of a small box that helps an older adult in India use their phone.
Speak warmly, simply and a little slowly, in short sentences. Answer in the language they speak to
you (English, Hindi or Kannada); if unsure, use {language}.
It is now {now}.
When they ask for something to be done on the phone (call or message someone, an alarm, a timer,
ordering, opening an app, reading or checking something on the screen, the volume...), call do_task
once with their request in their own words, straight away: don't ask them to confirm first (the box asks
itself when something needs a yes). Then tell them in one sentence exactly what its result says
happened, nothing more: if it says nothing was done, say that. Never say you are doing or have done
something that do_task did not report. The box itself asks before anything that sends, buys, pays,
books or calls. Never ask for or repeat an OTP, PIN or password. If they only chat, answer kindly and
briefly.
""".strip()

DO_TASK = types.FunctionDeclaration(
    name="do_task",
    description="Do something on the person's phone for them; returns what happened.",
    parameters=types.Schema(type="OBJECT", properties={
        "request": types.Schema(type="STRING", description="What they asked for, in their own words and language."),
    }, required=["request"]),
)


def stand_in_task(request: str) -> str:
    """Prototype only: the phone part isn't connected yet."""
    return (f"Nothing was done: this is a test and the phone is not connected yet. The request was: {request}. "
            "Tell the person exactly that nothing was done because this is a test, and repeat their request "
            "back in a few words so they know you understood.")


def live_config(language: str) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        system_instruction=types.Content(parts=[types.Part(text=SYSTEM.format(
            language=LANGUAGES.get(language, language), now=time.strftime("%A, %d %B %Y, %H:%M")))]),
        tools=[types.Tool(function_declarations=[DO_TASK])],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


def mic_command() -> list[str]:
    from .voice import find_microphone
    device = find_microphone()
    if sys.platform == "darwin":
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation", "-i", f":{device}",
                "-ac", "1", "-ar", str(IN_RATE), "-f", "s16le", "-"]
    return ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(IN_RATE), "-c", "1", "-t", "raw"]


def player_command() -> list[str]:
    if shutil.which("aplay") and sys.platform != "darwin":
        return ["aplay", "-q", "-r", str(OUT_RATE), "-f", "S16_LE", "-c", "1", "-t", "raw", "-"]
    return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-f", "s16le", "-ar", str(OUT_RATE),
            "-ch_layout", "mono", "-i", "-"]


class Speaker:
    """Plays the agent's audio as it arrives; can be cut off (when the person interrupts)."""

    def __init__(self, enabled: bool = True):
        self.enabled, self.proc = enabled, None
        self.last_audio = 0.0  # when the latest audio chunk arrived

    def play(self, pcm: bytes) -> None:
        self.last_audio = time.monotonic()
        if not self.enabled:
            return
        if self.proc is None or self.proc.poll() is not None:
            self.proc = subprocess.Popen(player_command(), stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            self.proc.stdin.write(pcm)  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except BrokenPipeError:
            self.proc = None

    def busy(self, tail_s: float = 0.6) -> bool:
        """Still talking: audio arrived recently (ffplay keeps playing what it already has)."""
        return time.monotonic() - self.last_audio < tail_s

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


class LiveAgent:
    def __init__(self, language: str, key: str, task=stand_in_task, speaker: Speaker | None = None):
        self.client = genai.Client(api_key=key)
        self.language, self.task = language, task
        self.speaker = speaker or Speaker()
        self.out_pcm = bytearray()  # everything the agent said (for --hear)
        self.first_audio_at: float | None = None
        self.heard, self.said = [], []
        self.speech_ended_at: float | None = None
        self.replies = 0  # finished turns in which the agent spoke

    async def _receive(self, session) -> None:
        while True:
            async for msg in session.receive():
                if msg.tool_call:
                    responses = []
                    for fc in msg.tool_call.function_calls or []:
                        request = (fc.args or {}).get("request", "")
                        print(f"   🛠  do_task({request!r})", flush=True)
                        result = await asyncio.to_thread(self.task, request)
                        responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result}))
                    await session.send_tool_response(function_responses=responses)
                sc = msg.server_content
                if not sc:
                    continue
                if sc.input_transcription and sc.input_transcription.text:
                    self.heard.append(sc.input_transcription.text)
                if sc.output_transcription and sc.output_transcription.text:
                    self.said.append(sc.output_transcription.text)
                if sc.interrupted:
                    self.speaker.stop()
                    print("   ✋ interrupted", flush=True)
                for part in (sc.model_turn.parts if sc.model_turn else []) or []:
                    if part.inline_data and part.inline_data.data:
                        if self.first_audio_at is None:
                            self.first_audio_at = time.monotonic()
                        self.out_pcm += part.inline_data.data
                        self.speaker.play(part.inline_data.data)
                if sc.turn_complete:
                    if self.first_audio_at:
                        self.replies += 1
                    if self.heard:
                        print(f"   🎤 {''.join(self.heard).strip()}", flush=True)
                    if self.said:
                        print(f"   🔈 {''.join(self.said).strip()}", flush=True)
                    self.heard, self.said = [], []

    async def talk(self, headphones: bool) -> None:
        """Live conversation through the microphone, until Ctrl+C."""
        async with self.client.aio.live.connect(model=MODEL, config=live_config(self.language)) as session:
            print(f"Talk to NextStep ({MODEL}, voice {VOICE}). Ctrl+C to stop.", flush=True)
            receiver = asyncio.create_task(self._receive(session))
            mic = await asyncio.create_subprocess_exec(*mic_command(), stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.DEVNULL)
            silence = bytes(int(IN_RATE * CHUNK_S) * 2)
            try:
                while True:
                    chunk = await mic.stdout.readexactly(int(IN_RATE * CHUNK_S) * 2)  # type: ignore[union-attr]
                    if not headphones and self.speaker.busy():
                        chunk = silence  # loudspeakers: don't let it hear itself
                    await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={IN_RATE}"))
            finally:
                mic.kill()
                receiver.cancel()

    async def hear(self, pcm: bytes, wait_s: float = 25.0) -> None:
        """One recorded request, sent at speaking pace, then quiet; returns when the reply has ended."""
        async with self.client.aio.live.connect(model=MODEL, config=live_config(self.language)) as session:
            receiver = asyncio.create_task(self._receive(session))
            step = int(IN_RATE * CHUNK_S) * 2
            for i in range(0, len(pcm), step):
                await session.send_realtime_input(audio=types.Blob(data=pcm[i:i + step], mime_type=f"audio/pcm;rate={IN_RATE}"))
                await asyncio.sleep(CHUNK_S)
            self.speech_ended_at = time.monotonic()
            quiet = bytes(step)
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:  # keep the line open with quiet until the reply is over
                await session.send_realtime_input(audio=types.Blob(data=quiet, mime_type=f"audio/pcm;rate={IN_RATE}"))
                await asyncio.sleep(CHUNK_S)
                if self.replies and not self.speaker.busy(1.0):
                    break
            receiver.cancel()


def pcm_from(path: str) -> bytes:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(IN_RATE),
                        "-f", "s16le", "-"], capture_output=True)
    if r.returncode != 0:
        sys.exit(f"could not read {path}")
    return r.stdout


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m box.live", description="Prototype: Gemini live voice agent (test only).")
    p.add_argument("--headphones", action="store_true", help="keep listening while it talks, so you can interrupt")
    p.add_argument("--hear", metavar="AUDIO", help="one recorded request instead of the microphone")
    p.add_argument("--save", metavar="WAV", help="with --hear: save the agent's reply here")
    a = p.parse_args()
    key = read_key("NEXTSTEP_BOX_GEMINI_KEY", "gemini.key")
    if not key:
        sys.exit("The live voice prototype needs a Google AI Studio key in ~/.nextstep-box/gemini.key.")
    agent = LiveAgent(Config().language, key, speaker=Speaker(enabled=not a.save))
    if not a.hear:
        try:
            asyncio.run(agent.talk(a.headphones))
        except KeyboardInterrupt:
            agent.speaker.stop()
        return
    t0 = time.monotonic()
    asyncio.run(agent.hear(pcm_from(a.hear)))
    if agent.first_audio_at and agent.speech_ended_at:
        print(f"   ⏱ first sound {agent.first_audio_at - agent.speech_ended_at:.1f} s after the request ended; "
              f"reply {len(agent.out_pcm) / 2 / OUT_RATE:.1f} s long; whole exchange {time.monotonic() - t0:.1f} s")
    if a.save and agent.out_pcm:
        with wave.open(a.save, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(OUT_RATE)
            w.writeframes(bytes(agent.out_pcm))
        print(f"   saved {Path(a.save).name}")


if __name__ == "__main__":
    main()
