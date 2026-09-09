-- Ascendant Digital base schema.
--
-- migration_001 only ALTERs `orders`, so it assumes tables that were never
-- created anywhere in this repository. This file is the missing bootstrap and
-- is safe to run repeatedly: every statement is IF NOT EXISTS.
--
-- Apply:  psql -U dominion -d dominion -f schema.sql
--   then: psql -U dominion -d dominion -f migration_001_orders_attribution.sql

BEGIN;

-- Stripe webhook idempotency. The webhook inserts here first and relies on
-- ON CONFLICT DO NOTHING to make replayed events harmless.
CREATE TABLE IF NOT EXISTS stripe_events (
    id               BIGSERIAL PRIMARY KEY,
    stripe_event_id  TEXT NOT NULL UNIQUE,
    event_type       TEXT NOT NULL,
    payload_json     TEXT,
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Completed orders, with the UTM attribution the checkout flow captures.
CREATE TABLE IF NOT EXISTS orders (
    id                     BIGSERIAL PRIMARY KEY,
    stripe_session_id      TEXT,
    stripe_payment_intent  TEXT,
    customer_email         TEXT,
    product_id             TEXT,
    product_name           TEXT,
    amount_cents           INTEGER,
    currency               TEXT DEFAULT 'usd',
    utm_source             TEXT,
    utm_medium             TEXT,
    utm_campaign           TEXT,
    utm_content            TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Required by the webhook's ON CONFLICT target.
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_stripe_session_id
    ON orders (stripe_session_id)
    WHERE stripe_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_utm_source ON orders (utm_source);

COMMIT;
