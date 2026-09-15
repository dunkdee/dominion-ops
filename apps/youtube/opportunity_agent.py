"""Governed YouTube opportunity scoring for Dominion traffic/revenue campaigns.

This module consumes permitted/public metadata that has already been collected
(e.g. YouTube Data API exports, platform analytics, approved research tools,
manual research). It does not scrape YouTube or copy protected creative assets.

The output is a ranked opportunity queue plus original-content briefs. Competitive
videos are treated as evidence of demand and abstract pattern signals only.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class VideoSignal:
    video_id: str
    title: str
    channel: str
    published_at: str
    views: int
    likes: int = 0
    comments: int = 0
    duration_seconds: int = 0
    topic: str = ""
    source_url: str = ""
    channel_median_views: int = 0
    monetization_fit: float = 0.5
    brand_fit: float = 0.5
    buyer_intent: float = 0.5


@dataclass(frozen=True)
class Opportunity:
    video_id: str
    source_url: str
    source_title: str
    channel: str
    topic: str
    score: float
    views_per_day: float
    engagement_rate: float
    outlier_ratio: float
    freshness_days: float
    monetization_fit: float
    brand_fit: float
    buyer_intent: float
    original_brief: dict


def _parse_dt(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _log_norm(value: float, ceiling: float) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(max(1.0, ceiling)))


def _original_brief(signal: VideoSignal, score: float) -> dict:
    topic = signal.topic or signal.title
    return {
        "thesis": f"Create an original Dominion treatment of the demand behind: {topic}",
        "research_question": f"What audience problem or curiosity made '{signal.title}' perform, and what materially different value can Dominion add?",
        "required_differences": [
            "new script and wording",
            "new title and thumbnail concept",
            "new examples, structure, and point of view",
            "owned/licensed/public-domain visuals and audio only",
            "Dominion-specific CTA tied to a measurable offer",
        ],
        "recommended_formats": ["youtube_long", "youtube_short", "tiktok", "instagram_reel"],
        "conversion_design": {
            "destination_required": True,
            "tracking_required": True,
            "offer_required": True,
            "primary_metric": "qualified_revenue_per_campaign",
        },
        "governance": {
            "copy_source_script": False,
            "copy_source_thumbnail": False,
            "reuse_source_footage": False,
            "human_approval_before_publish": True,
            "asset_provenance_required": True,
        },
        "evidence_score": round(score, 4),
    }


def score_signal(signal: VideoSignal, now: datetime | None = None) -> Opportunity:
    now = now or datetime.now(timezone.utc)
    published = _parse_dt(signal.published_at)
    age_days = max(1.0, (now - published).total_seconds() / 86400.0)
    views_per_day = signal.views / age_days
    engagement_rate = (signal.likes + signal.comments) / max(1, signal.views)
    outlier_ratio = (
        signal.views / signal.channel_median_views
        if signal.channel_median_views > 0
        else 1.0
    )

    velocity = _log_norm(views_per_day, 1_000_000)
    engagement = min(1.0, engagement_rate / 0.10)
    outlier = min(1.0, outlier_ratio / 10.0)
    freshness = max(0.0, 1.0 - min(age_days, 365.0) / 365.0)
    monetization = _clamp01(signal.monetization_fit)
    brand = _clamp01(signal.brand_fit)
    intent = _clamp01(signal.buyer_intent)

    # Demand evidence is intentionally weighted above raw virality. A huge video
    # with poor monetization/brand fit should not automatically outrank a smaller
    # but commercially aligned opportunity.
    score = 100.0 * (
        0.24 * velocity
        + 0.14 * engagement
        + 0.14 * outlier
        + 0.08 * freshness
        + 0.16 * monetization
        + 0.10 * brand
        + 0.14 * intent
    )

    return Opportunity(
        video_id=signal.video_id,
        source_url=signal.source_url,
        source_title=signal.title,
        channel=signal.channel,
        topic=signal.topic,
        score=round(score, 4),
        views_per_day=round(views_per_day, 4),
        engagement_rate=round(engagement_rate, 6),
        outlier_ratio=round(outlier_ratio, 4),
        freshness_days=round(age_days, 2),
        monetization_fit=monetization,
        brand_fit=brand,
        buyer_intent=intent,
        original_brief=_original_brief(signal, score),
    )


def rank_opportunities(signals: Iterable[VideoSignal], now: datetime | None = None) -> list[Opportunity]:
    ranked = [score_signal(signal, now=now) for signal in signals]
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def load_signals(path: Path) -> list[VideoSignal]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("videos", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Input must be a JSON list or an object containing a 'videos' list")
    return [VideoSignal(**row) for row in rows]


def build_report(signals: list[VideoSignal], top_n: int = 20) -> dict:
    ranked = rank_opportunities(signals)[: max(1, top_n)]
    return {
        "schema": "dominion-youtube-opportunity-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": "permitted_public_metadata_only_no_scraping_no_creative_copying",
        "primary_scale_metric": "qualified_revenue_per_campaign",
        "opportunities": [asdict(item) for item in ranked],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank YouTube demand signals for original Dominion campaigns")
    parser.add_argument("input", type=Path, help="JSON file containing permitted/public video metadata")
    parser.add_argument("--output", type=Path, default=Path("runtime/private/youtube/opportunity_queue.json"))
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    signals = load_signals(args.input)
    report = build_report(signals, top_n=args.top)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "count": len(report["opportunities"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
