from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "publishing"))
import kdp_packet_generator as generator  # noqa: E402


def valid_manifest() -> dict:
    return {
        "slug": "calm-word-search",
        "title": "Calm Word Search",
        "subtitle": "Large Print Puzzles",
        "author": "Dewayne Singleton",
        "demand_evidence": {"comparables": [{"title": "Example Puzzle Book", "observed_bsr": 12000, "source_url": "https://example.test/book", "observed_at": "2026-08-15"}]},
        "differentiation": "Large-print, fully machine-verified puzzles with a lower count-to-price ratio than the documented comparables.",
        "content_integrity": {"status": "VERIFIED", "evidence": "all 50 grids and answer keys validated by deterministic checker v1"},
        "policy_clearance": {"title_collision": "CLEARED", "rights_and_originality": "CLEARED", "public_domain_or_scraped": "CLEARED", "medical_legal_income_claims": "CLEARED", "claude_5_4": "CLEARED"},
        "ai_disclosure": {"determination": "AI_ASSISTED", "rationale": "Human authored the content; AI was used only for proofreading and layout checks."},
        "interior_spec": {"trim": "8.5 x 11 in", "page_count": 100, "ink": "black", "paper": "white", "bleed": False},
        "assets": {"interior_pdf": "assets/interior.pdf", "full_wrap_cover": "assets/wrap.pdf", "front_cover": "assets/front.jpg"},
        "listing": {"description_html": "<p>A clear description.</p>", "keywords": ["relaxing activities", "easy activities", "mindful games", "adult recreation", "senior activity book", "quiet pastime", "easy-to-read games"], "categories": ["Books > Games > Word Search", "Books > Puzzles", "Books > Activities"]},
        "commercials": {"marketplace": "Amazon.com", "print_list_price": "9.99", "printing_cost": "2.50", "royalty_rate": "0.60", "printing_cost_evidence": "KDP calculator result captured 2026-08-15"},
        "kdp_select_recommendation": {"recommendation": "NO", "reason": "Paperback-only title."},
    }


class PacketGeneratorTests(unittest.TestCase):
    def make_manifest(self, directory: Path, payload: dict) -> Path:
        assets = directory / "assets"
        assets.mkdir()
        for name in ("interior.pdf", "wrap.pdf", "front.jpg"):
            (assets / name).write_bytes(b"test asset")
        path = directory / "title.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_go_creates_complete_packet(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = self.make_manifest(root, valid_manifest())
            result = generator.build_packet(manifest, root / "packets")
            packet = root / "packets" / "calm-word-search"
            self.assertEqual(result, 0)
            self.assertEqual(json.loads((packet / "packet_manifest.json").read_text())["status"], "GO")
            self.assertTrue((packet / "PUBLISH_STEPS.md").is_file())
            self.assertTrue((packet / "interior.pdf").is_file())
            self.assertEqual(json.loads((packet / "commercials.json").read_text())["royalty_per_unit"], "3.49")

    def test_no_go_writes_reasons_and_no_partial_packet(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = valid_manifest()
            payload["demand_evidence"] = {"comparables": []}
            manifest = self.make_manifest(root, payload)
            result = generator.build_packet(manifest, root / "packets")
            packet = root / "packets" / "calm-word-search"
            self.assertEqual(result, 2)
            self.assertIn("demand evidence", (packet / "MERIT_GATE.md").read_text())
            self.assertFalse((packet / "PUBLISH_STEPS.md").exists())

    def test_rejects_amazon_credential_field(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = valid_manifest()
            payload["amazon_password"] = "never"
            manifest = self.make_manifest(root, payload)
            self.assertEqual(generator.build_packet(manifest, root / "packets"), 2)
            report = (root / "packets" / "calm-word-search" / "MERIT_GATE.md").read_text()
            self.assertIn("forbidden credential-like", report)


if __name__ == "__main__":
    unittest.main()
