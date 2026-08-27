import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE = (ROOT / "apps/command-center/intelligence.py").read_text(encoding="utf-8")
APP = (ROOT / "apps/command-center/app.py").read_text(encoding="utf-8")


class BuddyVoiceContractTests(unittest.TestCase):
    def test_buddy_persona_is_governed_and_non_caricatured(self):
        self.assertIn("You are Buddy: the Founder's personal AI operator", INTELLIGENCE)
        self.assertIn("not a generic assistant", INTELLIGENCE)
        self.assertIn("Black American conversational register", INTELLIGENCE)
        self.assertIn("Never force slang", INTELLIGENCE)
        self.assertIn("Never fabricate completion", INTELLIGENCE)
        self.assertIn("Do not pretend to remember", INTELLIGENCE)
        self.assertIn("return call_conductor(message, context)", INTELLIGENCE)

    def test_buddy_voice_surface_is_present_and_default_on(self):
        self.assertIn("BUDDY_VOICE_SCRIPT", APP)
        self.assertIn("window.speechSynthesis", APP)
        self.assertIn("dominion.buddy.voice.enabled", APP)
        self.assertIn("BUDDY VOICE:", APP)
        self.assertIn("utterance.rate = 0.96", APP)
        self.assertIn("utterance.pitch = 0.82", APP)
        self.assertIn('"voice_default": "on"', APP)

    def test_voice_script_is_injected_without_replacing_truth_ui(self):
        self.assertIn('html = html.replace("</body>", BUDDY_VOICE_SCRIPT + "\\n</body>", 1)', APP)
        self.assertIn("Current production state requires timestamped runtime receipts.", APP)


if __name__ == "__main__":
    unittest.main()
