from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSIDIAN = ROOT / "obsidian"
HOME = OBSIDIAN / "command-center" / "00-HOME.md"
ROOT_NOTE = OBSIDIAN / "00-DOMINION-COMMAND-CENTER.md"
CSS = OBSIDIAN / "dominion.css"


class DashboardParser(HTMLParser):
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


def load_dashboard() -> tuple[str, str, DashboardParser]:
    home = HOME.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    parser = DashboardParser()
    parser.feed(home)
    return home, css, parser


def test_dashboard_structure_and_visual_contract() -> None:
    home, _, parser = load_dashboard()
    assert "cssclasses:" in home
    required_classes = {
        "dominion-shell",
        "dominion-hero",
        "dominion-status-row",
        "dominion-metric-grid",
        "dominion-card-grid",
        "dominion-boundary",
        "dominion-mobile-dock",
    }
    assert required_classes <= parser.classes
    assert len(parser.internal_targets) >= 17
    assert len(parser.nav_labels) >= 4
    assert "RADAH MEMSHALAH" in home
    assert "This is deployment evidence, not live business telemetry." in home
    assert "This surface grants no authority and invents no status." in home


def test_every_dashboard_link_resolves() -> None:
    _, _, parser = load_dashboard()
    prefix = "Dominion-Command-Center/"
    for target in parser.internal_targets:
        assert target.startswith(prefix)
        relative = target.removeprefix(prefix)
        assert (OBSIDIAN / "command-center" / f"{relative}.md").is_file(), target


def test_css_is_phone_first_accessible_and_offline() -> None:
    _, css, _ = load_dashboard()
    required = (
        ".dominion-shell",
        ".dominion-hero",
        ".dominion-card-grid",
        ".dominion-mobile-dock",
        "@media (max-width: 720px)",
        "@media (prefers-reduced-motion: reduce)",
        ":focus-visible",
        "min-height: 52px",
    )
    for marker in required:
        assert marker in css
    assert "@import" not in css
    assert "url(http" not in css
    assert "javascript:" not in css.lower()


def test_root_note_is_a_clean_styled_entrypoint() -> None:
    root = ROOT_NOTE.read_text(encoding="utf-8")
    assert "dominion-command-center-root" in root
    assert "![[Dominion-Command-Center/00-HOME]]" in root
    assert "# Dominion Command Center" not in root


def main() -> int:
    test_dashboard_structure_and_visual_contract()
    test_every_dashboard_link_resolves()
    test_css_is_phone_first_accessible_and_offline()
    test_root_note_is_a_clean_styled_entrypoint()
    print("DOMINION_UI_V2_TESTS=PASS cards=17 mobile=pass accessibility=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
