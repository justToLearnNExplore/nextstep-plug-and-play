"""The live voice agent prototype's setup (no network)."""

import time

from box.live import live_config, stand_in_task


def test_the_agent_knows_the_date_its_tool_and_to_report_truthfully():
    cfg = live_config("kn-IN")
    prompt = cfg.system_instruction.parts[0].text
    assert time.strftime("%A") in prompt and "Kannada" in prompt
    assert "exactly what its result says" in prompt and "don't ask them to confirm first" in prompt
    assert [f.name for f in cfg.tools[0].function_declarations] == ["do_task"]
    assert cfg.input_audio_transcription is not None and cfg.output_audio_transcription is not None


def test_the_stand_in_never_pretends_to_have_done_anything():
    assert stand_in_task("call Ravi").startswith("Nothing was done")
