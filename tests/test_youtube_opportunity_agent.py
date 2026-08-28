from datetime import datetime, timezone

from apps.youtube.opportunity_agent import VideoSignal, rank_opportunities, score_signal


def test_high_value_aligned_video_scores_above_viral_low_fit_video():
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    aligned = VideoSignal(
        video_id="aligned",
        title="High intent buyer topic",
        channel="A",
        published_at="2026-08-20T00:00:00Z",
        views=120_000,
        likes=8_000,
        comments=900,
        channel_median_views=25_000,
        monetization_fit=0.95,
        brand_fit=0.95,
        buyer_intent=0.95,
    )
    viral_low_fit = VideoSignal(
        video_id="viral",
        title="Huge but unrelated trend",
        channel="B",
        published_at="2026-08-20T00:00:00Z",
        views=800_000,
        likes=20_000,
        comments=1_000,
        channel_median_views=100_000,
        monetization_fit=0.05,
        brand_fit=0.05,
        buyer_intent=0.05,
    )

    ranked = rank_opportunities([viral_low_fit, aligned], now=now)
    assert ranked[0].video_id == "aligned"


def test_outlier_ratio_uses_channel_baseline_when_available():
    signal = VideoSignal(
        video_id="x",
        title="Outlier",
        channel="C",
        published_at="2026-08-27T00:00:00Z",
        views=100_000,
        channel_median_views=10_000,
    )
    opportunity = score_signal(signal, now=datetime(2026, 8, 28, tzinfo=timezone.utc))
    assert opportunity.outlier_ratio == 10.0


def test_original_brief_forbids_copying_source_creative():
    signal = VideoSignal(
        video_id="x",
        title="Source idea",
        channel="C",
        published_at="2026-08-27T00:00:00Z",
        views=1_000,
    )
    opportunity = score_signal(signal, now=datetime(2026, 8, 28, tzinfo=timezone.utc))
    governance = opportunity.original_brief["governance"]
    assert governance["copy_source_script"] is False
    assert governance["copy_source_thumbnail"] is False
    assert governance["reuse_source_footage"] is False
    assert governance["human_approval_before_publish"] is True
