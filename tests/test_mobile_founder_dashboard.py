from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSIDIAN = ROOT / "obsidian" / "command-center"
MOBILE = OBSIDIAN / "18-Mobile-Founder-Dashboard.md"


class MobileDashboardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.internal_targets: list[str] = []
        self.classes: set[str] = set()
        self.nav_labels: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.classes.update((values.get("class") or "").split())
        if tag == "a" and "internal-link" in (values.get("class") or "").split():
            target = values.get("data-href")
            assert target
            self.internal_targets.append(target)
        if tag == "nav":
            label = values.get("aria-label")
            assert label
            self.nav_labels.append(label)


def test_mobile_founder_dashboard_contract() -> None:
    text = MOBILE.read_text(encoding="utf-8")
    parser = MobileDashboardParser()
    parser.feed(text)

    for marker in (
        "RADAH MEMSHALAH · PHONE FIRST",
        "Founder Mobile Dashboard",
        "Revenue",
        "Traffic & Production",
        "Active Missions",
        "Blockers & Incidents",
        "Founder Action Needed",
        "Latest Receipts",
        "Agents",
        "MOBILE TRUTH BOUNDARY",
        "does not create a second source of truth",
    ):
        assert marker in text

    required_classes = {
        "dominion-shell",
        "dominion-hero",
        "dominion-status-row",
        "dominion-card-grid",
        "dominion-card",
        "dominion-boundary",
        "dominion-mobile-dock",
    }
    assert required_classes <= parser.classes
    assert "Mobile founder controls" in parser.nav_labels
    assert "Mobile founder quick navigation" in parser.nav_labels
    assert len(parser.internal_targets) >= 11


def test_mobile_founder_dashboard_links_resolve() -> None:
    text = MOBILE.read_text(encoding="utf-8")
    parser = MobileDashboardParser()
    parser.feed(text)
    prefix = "Dominion-Command-Center/"
    for target in parser.internal_targets:
        assert target.startswith(prefix)
        relative = target.removeprefix(prefix)
        assert (OBSIDIAN / f"{relative}.md").is_file(), target


def test_mobile_dashboard_remains_non_consequential_control_surface() -> None:
    text = MOBILE.read_text(encoding="utf-8")
    assert "does not grant new authority" in text
    assert "Founder-gated" in text
    assert "exact-release governed" in text
    assert "password" not in text.lower()
    assert "token=" not in text.lower()
    assert "api_key" not in text.lower()
