# Wix Production Cutover Report

- Generated: 2026-07-20T22:35:55.515829+00:00
- Customer/order data: **EXCLUDED**
- API keys and secret values: **EXCLUDED**
- Workflow cutover outcome: **FAILURE**
- Cutover state: **FAILED_BEFORE_CUTOVER**
- Failure stage: **INITIALIZING**
- Expected release: **4e7dc60b0730165989c666947c460c00907c1a6d**
- Running image matches release: **False**

## Production verification

| Gate | Status |
|---|---:|
| Production container running | PASS |
| Release image active | BLOCKED |
| Localhost-only port binding | BLOCKED |
| Persistent /data mount | BLOCKED |
| Persistent /app/logs mount | PASS |
| Readiness HTTP 200 | BLOCKED |
| Wix catalog V3 | BLOCKED |
| Record-only fulfillment | BLOCKED |
| Zendrop credential withheld | PASS |
| Operator token configured | BLOCKED |
| Secret files mode 600 | PASS |
| Read-only root filesystem | BLOCKED |
| Linux capabilities dropped | BLOCKED |
| No-new-privileges enforced | BLOCKED |
| Safe restart policy | PASS |
| Docker healthcheck configured | PASS |
| Non-root runtime user | BLOCKED |
| CPU, memory, and PID limits | BLOCKED |
| Hardened temporary filesystem | BLOCKED |
| Compose contract matches release | BLOCKED |
| Compose preserves active image and volumes | BLOCKED |
| Zendrop supplier submission | REVIEW |

## Recovery evidence

- Existing database result: **NOT_CHECKED**
- Backup artifact: **NONE**
- Verified backup retained: **BLOCKED**
- Rollback container retained: **NONE**
- Rollback container stopped and retained: **BLOCKED**
- Previous Compose file retained: **NONE**
- New data volume: **wix_agent_data_4e7dc60b0730-29784447103-1**
- Database mount type: **MISSING**

## Remaining launch controls

- Automated Zendrop submission remains disabled pending exact variant mapping and separate approval.
- A Wix owner checkout/payment/customer-journey test is still required before public launch certification.
