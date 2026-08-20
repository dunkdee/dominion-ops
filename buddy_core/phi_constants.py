# ============================================================
# phi_constants.py  —  THE GOLDEN ARCHITECTURE
# φ = 1.618033988749895  embedded at every layer of Dominion
#
# This is not decorative. These constants govern:
#   - Agent timing intervals
#   - Pricing tiers
#   - Database schema partitioning
#   - Content cadence
#   - Email drip sequences
#   - Token emission (Phase 3)
#
# Pioneer claim: First autonomous AI ecosystem governed by φ
# at the infrastructure level. Version-controlled. Provable.
# ============================================================

PHI  = 1.618033988749895   # The golden ratio
PHI2 = PHI ** 2            # 2.618033988749895
PHI3 = PHI ** 3            # 4.23606797749979
PHI4 = PHI ** 4            # 6.854101966249685
PHI5 = PHI ** 5            # 11.09016994374948

INV_PHI  = 1 / PHI         # 0.6180339887498949  (φ⁻¹)
INV_PHI2 = 1 / PHI2        # 0.3819660112501051

# ── Agent Hierarchy Weights ───────────────────────────────────
# DominionBrain governs Conductor at 1.618:1 priority weighting
AGENT_WEIGHTS = {
    # Governance layer
    "dominion_brain":  1.000,        # Master intelligence — φ⁰
    "conductor":       INV_PHI,      # 0.618 — orchestrator
    # Revenue agents — descending φ priority
    "scout":           INV_PHI2,     # 0.382 — lead discovery (highest revenue impact)
    "pitch":           0.236,        # strategy — converts leads to pitches
    "email":           0.236,        # execution — sends pitches
    "followup":        0.146,        # nurture — day 2/5 sequences
    "reply":           0.236,        # closing — inbound reply handler (same priority as pitch)
    "alchemist":       0.146,        # nurture — 21-day drip
    "intel":           0.146,        # research — world intelligence
    "social":          INV_PHI2,     # 0.382 — social posting (6 browser sessions need ~370s)
    "jurs":            0.090,        # specialized — legal/sovereign
    "content":         0.090,        # content generation
    "monetization":    0.056,        # monetization/affiliate
}

# ── Timing Intervals ──────────────────────────────────────────
PROPOSAL_INTERVAL_HOURS   = PHI          # 1.618 hours between proposal checks
PROPOSAL_INTERVAL_MINUTES = PHI * 60     # 97.08 minutes
CONTENT_BUILD_MINUTES     = PHI * 10     # 16.18 min build window
CONTENT_DIST_MINUTES      = PHI2 * 10   # 26.18 min distribute window
VALIDATION_LOOP_SECONDS   = PHI2         # 2.618 second checks

# Scout runs daily at 6:18 AM
SCOUT_CRON                = "18 6 * * *"

# World intel at 4:18 PM (16:18)
INTEL_CRON                = "18 16 * * *"

# Proposal engine every 97 minutes (≈ φ hours)
# Cloud Scheduler runs at: 00,37 14,51 05,42 19,56 ...
PROPOSAL_CRON             = "0,37 */2 * * *"  # Approximation

# Full pipeline daily at 9:00 AM
PIPELINE_CRON             = "0 9 * * *"

# Vault backup daily at 2:00 AM
BACKUP_CRON               = "0 2 * * *"

# ── Revenue Tier Pricing (φ multiples, USD cents) ─────────────
PRICE_TIER_1   = 9700    # $97.00 — base
PRICE_TIER_2   = 15700   # $157.00 → $97 × φ ≈ $156.95
PRICE_TIER_3   = 25400   # $254.00 → $97 × φ² ≈ $253.87
PRICE_TIER_4   = 41100   # $411.00 → $97 × φ³ ≈ $410.47
PRICE_TIER_5   = 66500   # $665.00 → $97 × φ⁴ ≈ $664.85

# Entry products (existing)
PRICE_BOOK_1   = 1700    # $17.00 — Art of Healing
PRICE_BOOK_2   = 1900    # $19.00 — Divine Sovereignty

# ── Layout Proportions (golden split) ────────────────────────
LAYOUT_MAJOR   = 61.8    # % — dominant column
LAYOUT_MINOR   = 38.2    # % — secondary column

# Typography scale (px, each a φ multiple of previous)
TYPE_XS        = 10.0
TYPE_SM        = round(10 * PHI, 2)    # 16.18
TYPE_MD        = round(10 * PHI2, 2)   # 26.18
TYPE_LG        = round(10 * PHI3, 2)   # 42.36
TYPE_XL        = round(10 * PHI4, 2)   # 68.54

# ── Database / BigQuery Schema Intervals ─────────────────────
BQ_PARTITION_DAYS   = 16           # φ×10 ≈ 16.18 → 16 days
BQ_RETENTION_1      = 26           # Fibonacci/φ sequence
BQ_RETENTION_2      = 42           # 26 × φ ≈ 42.07
BQ_RETENTION_3      = 68           # 42 × φ ≈ 67.97
BQ_ARCHIVE_MULTIPLIER = PHI        # Archive triggers at 1.618× data threshold

# ── Email Drip Sequence (Alchemist — φ-interval days) ────────
EMAIL_DAY_0    = 0                 # Immediate — lead magnet delivery
EMAIL_DAY_1    = round(PHI, 1)    # Day 1.6 — welcome + story
EMAIL_DAY_2    = round(PHI2, 1)   # Day 2.6 — value content
EMAIL_DAY_3    = round(PHI3, 1)   # Day 4.2 — case study
EMAIL_DAY_4    = round(PHI4, 1)   # Day 6.9 — soft pitch
EMAIL_DAY_5    = round(PHI5, 1)   # Day 11.1 — hard offer
EMAIL_DAY_6    = 14               # Day 14 — urgency
EMAIL_DAY_7    = 21               # Day 21 — final close

DRIP_DAYS = [EMAIL_DAY_0, EMAIL_DAY_1, EMAIL_DAY_2, EMAIL_DAY_3,
             EMAIL_DAY_4, EMAIL_DAY_5, EMAIL_DAY_6, EMAIL_DAY_7]

# ── Token Model (Phase 3) ────────────────────────────────────
TOKEN_EMISSION_REDUCTION = INV_PHI  # Supply × φ⁻¹ reduction per epoch
STAKING_WINDOW_1 = 6.18            # days
STAKING_WINDOW_2 = 16.18           # days
STAKING_WINDOW_3 = 61.8            # days

# ── Scoring Thresholds ────────────────────────────────────────
PROPOSAL_SCORE_THRESHOLD = 72      # Gemini score ≥ 72 → auto-submit proposal
LEAD_SCORE_HOT           = 80      # Hot lead — immediate follow-up
LEAD_SCORE_WARM          = 50      # Warm — standard sequence
LEAD_SCORE_COLD          = 30      # Cold — long nurture

# ── Google Cloud ──────────────────────────────────────────────
GCP_PROJECT   = "dominion-ascendant"
GCP_REGION    = "us-central1"
BQ_DATASET    = "dominion_core"
GEMINI_MODEL  = "gemini-2.5-flash"   # Free tier, fast
GEMINI_PRO    = "gemini-2.5-pro"     # For deep tasks

# ── Pioneer Claim ────────────────────────────────────────────
PIONEER_CLAIM = {
    "builder": "DeWayne Singleton",
    "trust": "Primal Dominion Legacy Trust",
    "claim": "First autonomous AI ecosystem governed by φ at infrastructure level",
    "phi": PHI,
    "date": "April 2026",
    "proof": "Version-controlled config files, agent timing, pricing, schema — all documented",
}
