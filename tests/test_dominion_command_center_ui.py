from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSIDIAN = ROOT / "obsidian"
HOME = OBSIDIAN / "command-center" / "00-HOME.md"
PRODUCTION = OBSIDIAN / "command-center" / "16-Production-Matrix.md"
MCP = OBSIDIAN / "command-center" / "17-MCP-CLI-Connector.md"
ROOT_NOTE = OBSIDIAN / "00-DOMINION-COMMAND-CENTER.md"
CSS = OBSIDIAN / "dominion.css"
MOTION_CSS = OBSIDIAN / "dominion-motion.css"
GOLDEN_CSS = OBSIDIAN / "dominion-golden-ratio.css"
WEB_INDEX = ROOT / "apps" / "command-center" / "index.html"
DEPLOY_UI = ROOT / "scripts" / "deploy_dominion_command_center.sh"


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


def parse_page(path: Path) -> tuple[str, DashboardParser]:
    text = path.read_text(encoding="utf-8")
    parser = DashboardParser()
    parser.feed(text)
    return text, parser


def load_dashboard() -> tuple[str, str, str, DashboardParser]:
    home, parser = parse_page(HOME)
    css = CSS.read_text(encoding="utf-8")
    motion = MOTION_CSS.read_text(encoding="utf-8")
    return home, css, motion, parser


def test_dashboard_structure_and_visual_contract() -> None:
    home, _, _, parser = load_dashboard()
    assert "cssclasses:" in home
    required_classes = {
        "dominion-shell",
        "dominion-hero",
        "dominion-status-row",
        "dominion-metric-grid",
        "dominion-card-grid",
        "dominion-boundary",
        "dominion-mobile-dock",
        "dominion-card--active",
        "dominion-flow",
    }
    assert required_classes <= parser.classes
    assert len(parser.internal_targets) >= 19
    assert len(parser.nav_labels) >= 4
    assert "RADAH MEMSHALAH" in home
    assert "Production Matrix" in home
    assert "Dominion-Command-Center/16-Production-Matrix" in home
    assert "MCP CLI Connector Fabric" in home
    assert "Dominion-Command-Center/17-MCP-CLI-Connector" in home
    assert "Current production state requires timestamped runtime receipts." in home
    assert "they do not invent status or grant authority" in home


def test_every_dashboard_link_resolves() -> None:
    _, _, _, parser = load_dashboard()
    prefix = "Dominion-Command-Center/"
    for target in parser.internal_targets:
        assert target.startswith(prefix)
        relative = target.removeprefix(prefix)
        assert (OBSIDIAN / "command-center" / f"{relative}.md").is_file(), target


def test_production_matrix_covers_every_governed_lane() -> None:
    production, parser = parse_page(PRODUCTION)
    assert "All-Lane Production Matrix" in production
    assert "External Action Holds" in production
    assert "Motion indicates intended production state, not proof of runtime activity." in production
    required_lanes = (
        "Commerce",
        "KDP Publishing",
        "Analytics Services",
        "Digital Products",
        "Service Leads",
        "Content & Traffic",
        "Surplus",
        "Trading",
        "Orchestration",
        "Governance & Legal",
        "Infrastructure",
    )
    for lane in required_lanes:
        assert lane in production
    assert "dominion-card--productive" in parser.classes
    assert "dominion-flow" in parser.classes


def test_mcp_connector_page_is_full_visual_canopy_not_plain_shell() -> None:
    text, parser = parse_page(MCP)
    for marker in (
        "RADAH MEMSHALAH · CONNECTOR FABRIC",
        "MCP CLI Server",
        "MCP 2026-07-28",
        "DEFAULT DENY",
        "LOOPBACK ONLY",
        "Registered Connectors",
        "How “Connects to Anything” Works",
        "arbitrary shell commands or arbitrary target URLs",
    ):
        assert marker.lower() in text.lower(), marker
    required_classes = {"dominion-shell", "dominion-hero", "dominion-metric-grid", "dominion-card-grid", "dominion-flow", "dominion-mobile-dock"}
    assert required_classes <= parser.classes
    assert len(parser.internal_targets) >= 10


def test_css_is_phone_first_accessible_offline_motion_safe_and_phi_governed() -> None:
    _, css, motion, _ = load_dashboard()
    golden = GOLDEN_CSS.read_text(encoding="utf-8")
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
    motion_required = (
        "@keyframes dominion-ambient-drift",
        "@keyframes dominion-orbit",
        "@keyframes dominion-status-breathe",
        "@keyframes dominion-production-sweep",
        "@keyframes dominion-flow-pass",
        "@media (prefers-reduced-motion: reduce)",
        ".dominion-card--active",
        ".dominion-card--productive",
    )
    for marker in motion_required:
        assert marker in motion
    golden_required = (
        "--dominion-phi: 1.61803398875",
        "--dominion-invphi: 0.61803398875",
        "--dominion-s1: 8px",
        "--dominion-s9: 377px",
        "--dominion-radius: 0px",
        ".dominion-metric-grid",
        ".dominion-card-grid",
        "min-height: 52px",
    )
    for marker in golden_required:
        assert marker in golden
    deploy = DEPLOY_UI.read_text(encoding="utf-8")
    expected_concat = 'cat "$asset_root/obsidian/dominion.css" "$asset_root/obsidian/dominion-motion.css" "$asset_root/obsidian/dominion-golden-ratio.css" > "$snippet"'
    assert expected_concat in deploy
    assert "golden_ratio=locked" in deploy
    combined = css + "\n" + motion + "\n" + golden
    assert "@import" not in combined
    assert "url(http" not in combined
    assert "javascript:" not in combined.lower()


def test_web_command_center_is_reference_locked_to_golden_ratio() -> None:
    web = WEB_INDEX.read_text(encoding="utf-8")
    for marker in (
        "--phi:1.61803398875",
        "--invphi:.61803398875",
        "--s1:8px",
        "--s2:13px",
        "--s3:21px",
        "--s4:34px",
        "--s5:55px",
        "--s6:89px",
        "--s7:144px",
        "--s8:233px",
        "--s9:377px",
        "grid-template-columns:minmax(0,1.618fr) minmax(320px,1fr)",
        "grid-template-columns:1fr 1fr 1.618fr",
        "width:var(--s7);height:var(--s7)",
        "width:var(--s6);height:var(--s6)",
        "RADAH MEMSHALAH",
        "GOLDEN RATIO GOVERNANCE",
        "AGENTS NETWORK / GOVERNED OPERATORS",
    ):
        assert marker in web, marker
    assert "border-radius:18px" not in web
    assert "rounded" not in web.lower()


def test_root_note_is_a_clean_styled_entrypoint() -> None:
    root = ROOT_NOTE.read_text(encoding="utf-8")
    assert "dominion-command-center-root" in root
    assert "![[Dominion-Command-Center/00-HOME]]" in root
    assert "# Dominion Command Center" not in root


def main() -> int:
    test_dashboard_structure_and_visual_contract()
    test_every_dashboard_link_resolves()
    test_production_matrix_covers_every_governed_lane()
    test_mcp_connector_page_is_full_visual_canopy_not_plain_shell()
    test_css_is_phone_first_accessible_offline_motion_safe_and_phi_governed()
    test_web_command_center_is_reference_locked_to_golden_ratio()
    test_root_note_is_a_clean_styled_entrypoint()
    print("DOMINION_UI_V5_TESTS=PASS production_matrix=11_lanes golden_ratio=locked web_and_obsidian=true mcp_canopy=full motion=natural accessibility=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())