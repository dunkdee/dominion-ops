#!/usr/bin/env python3
"""Fail-closed, offline KDP publish-packet generator.

This program never reads credentials, opens a browser, calls Amazon, or publishes.
It only converts a fully evidenced title manifest and supplied local assets into a
human-ready packet.  A deficient manifest produces only a NO-GO record.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


FORBIDDEN_KEY_RE = re.compile(r"(amazon|kdp).*(credential|password|secret|token)|(?:credential|password|secret|token).*(amazon|kdp)", re.I)
POLICY_CHECKS = ("title_collision", "rights_and_originality", "public_domain_or_scraped", "medical_legal_income_claims", "claude_5_4")
ALLOWED_ASSET_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}


class PacketError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PacketError(f"manifest cannot be read as JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PacketError("manifest root must be a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def deep_forbidden_key(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{prefix}.{key}" if prefix else str(key)
            if FORBIDDEN_KEY_RE.search(str(key)):
                found.append(here)
            found.extend(deep_forbidden_key(child, here))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(deep_forbidden_key(child, f"{prefix}[{index}]"))
    return found


def resolved_asset(manifest_path: Path, raw: Any, label: str, reasons: list[str]) -> Path | None:
    if not nonempty(raw):
        reasons.append(f"required asset missing: {label}")
        return None
    path = (manifest_path.parent / str(raw)).resolve()
    if path.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
        reasons.append(f"asset type is not allowed for {label}: {path.suffix or 'none'}")
    elif not path.is_file():
        reasons.append(f"asset does not exist: {label}")
    return path


def merit_reasons(manifest: dict[str, Any], manifest_path: Path) -> tuple[list[str], dict[str, Path]]:
    reasons: list[str] = []
    assets: dict[str, Path] = {}
    forbidden = deep_forbidden_key(manifest)
    if forbidden:
        reasons.append("forbidden credential-like manifest keys: " + ", ".join(forbidden))

    for field in ("slug", "title", "author"):
        if not nonempty(manifest.get(field)):
            reasons.append(f"required title field missing: {field}")

    demand = manifest.get("demand_evidence")
    comparables = demand.get("comparables") if isinstance(demand, dict) else None
    if not isinstance(comparables, list) or not comparables:
        reasons.append("demand evidence requires at least one named comparable")
    else:
        for index, comparable in enumerate(comparables, 1):
            if not isinstance(comparable, dict) or not nonempty(comparable.get("title")) or not isinstance(comparable.get("observed_bsr"), int) or comparable["observed_bsr"] <= 0 or not nonempty(comparable.get("source_url")):
                reasons.append(f"demand comparable {index} requires title, positive observed_bsr, and source_url")

    if not nonempty(manifest.get("differentiation")) or len(str(manifest.get("differentiation", "")).strip()) < 20:
        reasons.append("differentiation must be a specific, non-generic sentence")

    integrity = manifest.get("content_integrity")
    if not isinstance(integrity, dict) or integrity.get("status") != "VERIFIED" or not nonempty(integrity.get("evidence")):
        reasons.append("content integrity must be VERIFIED with machine-verification evidence")

    policy = manifest.get("policy_clearance")
    if not isinstance(policy, dict):
        reasons.append("policy clearance record is missing")
    else:
        for check in POLICY_CHECKS:
            if policy.get(check) != "CLEARED":
                reasons.append(f"policy clearance not CLEARED: {check}")

    disclosure = manifest.get("ai_disclosure")
    if not isinstance(disclosure, dict) or disclosure.get("determination") not in {"AI_GENERATED", "AI_ASSISTED", "HUMAN_CREATED"} or not nonempty(disclosure.get("rationale")):
        reasons.append("AI disclosure needs a valid determination and rationale")

    spec = manifest.get("interior_spec")
    if not isinstance(spec, dict) or not nonempty(spec.get("trim")) or not isinstance(spec.get("page_count"), int) or spec["page_count"] < 24 or not nonempty(spec.get("ink")) or not nonempty(spec.get("paper")) or "bleed" not in spec:
        reasons.append("interior spec must state trim, page_count (>=24), ink, paper, and bleed")

    asset_map = manifest.get("assets")
    if not isinstance(asset_map, dict):
        reasons.append("asset map is missing")
    else:
        for label, key in (("interior PDF", "interior_pdf"), ("full wrap cover", "full_wrap_cover"), ("front cover", "front_cover")):
            path = resolved_asset(manifest_path, asset_map.get(key), label, reasons)
            if path:
                assets[key] = path
        if manifest.get("ebook") is not None:
            path = resolved_asset(manifest_path, asset_map.get("kindle_cover"), "Kindle cover", reasons)
            if path:
                assets["kindle_cover"] = path

    listing = manifest.get("listing")
    if not isinstance(listing, dict) or not nonempty(listing.get("description_html")):
        reasons.append("listing requires KDP HTML description")
    else:
        keywords = listing.get("keywords")
        categories = listing.get("categories")
        if not isinstance(keywords, list) or len(keywords) != 7 or not all(nonempty(x) for x in keywords):
            reasons.append("listing requires exactly seven nonempty keyword slots")
        elif title_words_repeated(manifest, keywords):
            reasons.append("keyword slots repeat words already in title or subtitle")
        if not isinstance(categories, list) or len(categories) != 3 or not all(nonempty(x) for x in categories):
            reasons.append("listing requires exactly three category paths")

    commercials = manifest.get("commercials")
    if not isinstance(commercials, dict):
        reasons.append("commercials record is missing")
    else:
        for key in ("marketplace", "print_list_price", "printing_cost", "royalty_rate", "printing_cost_evidence"):
            if key not in commercials or not nonempty(str(commercials[key])):
                reasons.append(f"commercials field missing: {key}")
    return reasons, assets


def title_words_repeated(manifest: dict[str, Any], keywords: list[Any]) -> bool:
    title_text = f"{manifest.get('title', '')} {manifest.get('subtitle', '')}".lower()
    title_words = set(re.findall(r"[a-z0-9]+", title_text))
    return any(title_words.intersection(re.findall(r"[a-z0-9]+", str(slot).lower())) for slot in keywords)


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise PacketError(f"invalid monetary value: {value!r}") from exc


def ensure_commercials(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest["commercials"]
    price, cost = money(raw["print_list_price"]), money(raw["printing_cost"])
    try:
        rate = Decimal(str(raw["royalty_rate"]))
    except Exception as exc:
        raise PacketError("invalid royalty_rate") from exc
    if price <= 0 or cost < 0 or rate <= 0 or rate > 1:
        raise PacketError("commercial values must be positive; royalty_rate must be in (0, 1]")
    royalty = (price * rate - cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if royalty <= 0:
        raise PacketError("commercials fail: computed print royalty is not positive")
    result: dict[str, Any] = {"marketplace": raw["marketplace"], "print_list_price": f"{price:.2f}", "printing_cost": f"{cost:.2f}", "royalty_rate": str(rate), "royalty_per_unit": f"{royalty:.2f}", "printing_cost_evidence": raw["printing_cost_evidence"]}
    ebook = manifest.get("ebook")
    if ebook is not None:
        ebook_price, print_price = money(ebook["price"]), price
        within_rule = ebook_price <= (print_price * Decimal("0.80")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not within_rule:
            raise PacketError("ebook price fails required 20%-below-print rule")
        result["ebook"] = {"price": f"{ebook_price:.2f}", "twenty_percent_below_print_verified": True}
    return result


def write_no_go(target: Path, reasons: list[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise PacketError(f"refusing to overwrite existing packet directory: {target}")
    lines = ["# KDP Merit Gate — NO-GO", "", f"Generated: {utc_now()}", "", "No publish packet was generated.", "", "## Blocking reasons", ""]
    lines.extend(f"- {reason}" for reason in reasons)
    (target / "MERIT_GATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_asset(source: Path, destination: Path) -> dict[str, str]:
    shutil.copy2(source, destination)
    return {"file": destination.name, "sha256": sha256(destination), "bytes": str(destination.stat().st_size)}


def render_steps(manifest: dict[str, Any], commercial: dict[str, Any]) -> str:
    listing = manifest["listing"]
    disclosure = manifest["ai_disclosure"]
    spec = manifest["interior_spec"]
    lines = ["# KDP Publish Steps", "", "This packet does not authenticate to, access, or publish on KDP.", "", "1. Open KDP in your own browser and sign in yourself.", "2. Select **Create paperback**.", f"3. Enter title: `{manifest['title']}`."]
    if manifest.get("subtitle"):
        lines.append(f"4. Enter subtitle: `{manifest['subtitle']}`.")
    lines.extend([f"5. Enter author exactly once: `{manifest['author']}`.", f"6. Paste description from `listing.html`.", f"7. Enter the seven keyword slots from `listing.json` in order.", f"8. Select the three category paths from `listing.json`.", f"9. Answer the AI-content question: `{disclosure['determination']}`. Reason: {disclosure['rationale']}", f"10. Upload `interior{Path(manifest['assets']['interior_pdf']).suffix.lower()}` and `full_wrap_cover{Path(manifest['assets']['full_wrap_cover']).suffix.lower()}`.", f"11. Confirm trim `{spec['trim']}`, {spec['page_count']} pages, {spec['ink']} ink, {spec['paper']} paper, bleed `{spec['bleed']}`.", f"12. Set paperback list price to `{commercial['print_list_price']}` in `{commercial['marketplace']}`; expected royalty per unit: `{commercial['royalty_per_unit']}`.", "13. Use Print Previewer. Stop for any layout, margin, font, or cover-spine error.", "14. Publish only after the recorded Founder approval and final Five Council release are present."])
    if "ebook" in commercial:
        lines.append(f"15. Create Kindle only if approved; use `kindle_cover{Path(manifest['assets']['kindle_cover']).suffix.lower()}` and price `{commercial['ebook']['price']}`.")
    return "\n".join(lines) + "\n"


def build_packet(manifest_path: Path, output_root: Path) -> int:
    manifest = load_json(manifest_path)
    slug = str(manifest.get("slug", "invalid-slug"))
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise PacketError("slug must contain lowercase letters, digits, and single hyphens only")
    target = output_root / slug
    reasons, assets = merit_reasons(manifest, manifest_path)
    if reasons:
        write_no_go(target, reasons)
        print(f"NO-GO: {target}")
        return 2
    commercial = ensure_commercials(manifest)
    if target.exists():
        raise PacketError(f"refusing to overwrite existing packet directory: {target}")
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{slug}.", dir=output_root) as raw_tmp:
        packet = Path(raw_tmp)
        copied = {
            "interior": copy_asset(assets["interior_pdf"], packet / f"interior{assets['interior_pdf'].suffix.lower()}"),
            "full_wrap_cover": copy_asset(assets["full_wrap_cover"], packet / f"full_wrap_cover{assets['full_wrap_cover'].suffix.lower()}"),
            "front_cover": copy_asset(assets["front_cover"], packet / f"front_cover{assets['front_cover'].suffix.lower()}"),
        }
        if "kindle_cover" in assets:
            copied["kindle_cover"] = copy_asset(assets["kindle_cover"], packet / f"kindle_cover{assets['kindle_cover'].suffix.lower()}")
        spec = manifest["interior_spec"]
        (packet / "MERIT_GATE.md").write_text("# KDP Merit Gate — GO\n\nAll five required checks passed from supplied evidence.\n", encoding="utf-8")
        (packet / "interior_spec.txt").write_text(f"trim={spec['trim']}\npage_count={spec['page_count']}\nink={spec['ink']}\npaper={spec['paper']}\nbleed={spec['bleed']}\n", encoding="utf-8")
        (packet / "listing.html").write_text(str(manifest["listing"]["description_html"]).strip() + "\n", encoding="utf-8")
        (packet / "listing.json").write_text(json.dumps({"title": manifest["title"], "subtitle": manifest.get("subtitle", ""), "author": manifest["author"], "keywords": manifest["listing"]["keywords"], "categories": manifest["listing"]["categories"]}, indent=2) + "\n", encoding="utf-8")
        (packet / "commercials.json").write_text(json.dumps(commercial, indent=2) + "\n", encoding="utf-8")
        (packet / "PUBLISH_STEPS.md").write_text(render_steps(manifest, commercial), encoding="utf-8")
        packet_manifest = {"schema_version": 1, "generated_at": utc_now(), "status": "GO", "source_manifest_sha256": sha256(manifest_path), "assets": copied, "ai_disclosure": manifest["ai_disclosure"], "kdp_select_recommendation": manifest.get("kdp_select_recommendation", {"recommendation": "REVIEW_REQUIRED", "reason": "No determination supplied."}), "non_capabilities": ["no_amazon_credentials", "no_kdp_browser_automation", "no_totp_storage", "no_unattended_trigger", "no_publish_action"]}
        (packet / "packet_manifest.json").write_text(json.dumps(packet_manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(packet, target)
    print(f"GO: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a governed, offline KDP publish packet.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("publishing/packets"))
    args = parser.parse_args(argv)
    try:
        return build_packet(args.manifest.resolve(), args.output_root.resolve())
    except PacketError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
