# Wix Agent

The Wix agent audits the VoltEdge Wix catalog, reads unfulfilled orders, and records fulfillment state before orders are submitted to Zendrop.

## Required configuration

- `WIX_API_KEY`: site-level Wix API key with the minimum permissions needed for products, inventory, and orders.
- `WIX_SITE_ID`: Wix site ID.
- `WIX_AGENT_OPERATOR_TOKEN`: long random token required in the `X-Operator-Token` header for every route except `/health` and `/ready`.
- `ZENDROP_API_KEY`: required before automated fulfillment can be ready.
- `WIX_AGENT_DB`: SQLite file path. Production uses `/data/wix_agent.db` on the `wix_agent_data` Docker volume.
- `N8N_WEBHOOK_URL`: optional event notification webhook.

Never commit real values. Store them in the production secret store or the VM's mode-`600` environment file.

## Operational endpoints

- `GET /health`: process health plus dependency status. It may report `degraded` while returning HTTP 200.
- `GET /ready`: returns HTTP 200 only when the database and required integrations are configured; otherwise HTTP 503.
- `GET /audit`: read-only inventory audit; operator token required.
- `POST /sync`: starts a read-only inventory audit. It does not change inventory.
- `POST /sync/fix`: applies only explicitly supplied product IDs. `dry_run` defaults to `true`.
- `POST /fulfill`: starts fulfillment and requires both the operator token and Zendrop configuration.

Bulk store setup is intentionally disabled. Generated product copy and policy text must be reviewed before any publication because supplier facts, warranties, shipping promises, and legal policies cannot be safely inferred by code.

## Verification

```bash
python -m unittest discover -s apps/wix-agent/tests -v
docker build -t dominion/wix-agent:local apps/wix-agent
```

After deployment, verify `/ready`, then perform a Wix test purchase through the payment sandbox/test mode and confirm that a single fulfillment record is created. Do not use a live customer order as the first deployment test.
