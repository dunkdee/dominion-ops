# Wix Production Cutover Report

- Generated: 2026-07-20T22:48:06.126614+00:00
- Customer/order data: **EXCLUDED**
- API keys and secret values: **EXCLUDED**
- Workflow cutover outcome: **SUCCESS**
- Cutover state: **SUCCESS**
- Failure stage: **NONE**
- Expected release: **a33ce2044d95d1aa63a9429ee4be532f457952bf**
- Running image matches release: **True**

## Production verification

| Gate | Status |
|---|---:|
| Production container running | PASS |
| Release image active | PASS |
| Localhost-only port binding | PASS |
| Persistent /data mount | PASS |
| Persistent /app/logs mount | PASS |
| Readiness HTTP 200 | PASS |
| Wix catalog V3 | PASS |
| Record-only fulfillment | PASS |
| Zendrop credential withheld | PASS |
| Operator token configured | PASS |
| Secret files mode 600 | PASS |
| Read-only root filesystem | PASS |
| Linux capabilities dropped | PASS |
| No-new-privileges enforced | PASS |
| Safe restart policy | PASS |
| Docker healthcheck configured | PASS |
| Non-root runtime user | PASS |
| CPU, memory, and PID limits | PASS |
| Hardened temporary filesystem | PASS |
| Compose contract matches release | PASS |
| Compose preserves active image and volumes | PASS |
| Zendrop supplier submission | DISABLED |

## Recovery evidence

- Existing database result: **NO_EXISTING_SQLITE_DATABASE**
- Backup artifact: **NONE**
- Verified backup retained: **PASS**
- Rollback container retained: **wix-agent-rollback-20260720T224801Z**
- Rollback container stopped and retained: **PASS**
- Previous Compose file retained: **docker-compose_20260720T224759Z.yml**
- New data volume: **wix_agent_data_a33ce2044d95-29785123140-1**
- Database mount type: **volume**

## Remaining launch controls

- Automated Zendrop submission remains disabled pending exact variant mapping and separate approval.
- A Wix owner checkout/payment/customer-journey test is still required before public launch certification.
