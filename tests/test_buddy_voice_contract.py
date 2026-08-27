from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE = (ROOT / "apps/command-center/intelligence.py").read_text(encoding="utf-8")
APP = (ROOT / "apps/command-center/app.py").read_text(encoding="utf-8")


def test_buddy_persona_is_governed_and_non_caricatured():
    assert "You are Buddy, Dominion Intelligence" in INTELLIGENCE
    assert "Black American conversational register" in INTELLIGENCE
    assert "Never force slang" in INTELLIGENCE
    assert "Never fabricate completion" in INTELLIGENCE
    assert "return call_conductor(message, context)" in INTELLIGENCE


def test_buddy_voice_surface_is_present_and_default_on():
    assert "BUDDY_VOICE_SCRIPT" in APP
    assert "window.speechSynthesis" in APP
    assert "dominion.buddy.voice.enabled" in APP
    assert "BUDDY VOICE:" in APP
    assert "utterance.rate = 0.96" in APP
    assert "utterance.pitch = 0.82" in APP
    assert '"voice_default": "on"' in APP


def test_voice_script_is_injected_without_replacing_truth_ui():
    assert 'html = html.replace("</body>", BUDDY_VOICE_SCRIPT + "\\n</body>", 1)' in APP
    assert "Current production state requires timestamped runtime receipts." in APP
