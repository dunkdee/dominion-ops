-- Migration 001: orders attribution columns + stripe_events live schema alignment
-- Apply once: psql -U dominion -d dominion -f migration_001_orders_attribution.sql
-- MIGRATION_APPLIED=NO

BEGIN;

-- orders: post-migration columns (idempotent)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_session_id      TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_payment_intent  TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email         TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id             TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_name           TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount_cents           INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS currency               TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS utm_source             TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS utm_medium             TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS utm_campaign           TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS utm_content            TEXT;

-- Partial unique index so ON CONFLICT clause works; safe to re-run
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_stripe_session_id
    ON orders (stripe_session_id)
    WHERE stripe_session_id IS NOT NULL;

COMMIT;
