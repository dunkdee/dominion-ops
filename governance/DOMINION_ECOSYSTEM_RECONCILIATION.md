# DOMINION ECOSYSTEM RECONCILIATION
**Date:** 2026-07-29
**Author:** Claude Code — Lead Engineer
**Authority:** Dewayne Singleton (Founder, final authority)
**Branch:** audit/ecosystem-reconciliation-20260729
**Methodology:** Snapshot-assisted reconciliation. VM state was provided by Founder-supplied
terminal output captured on 2026-07-29, not a live Claude SSH session. All VM observations carry
the timestamp of the supplied output and may not reflect current runtime state.

---

## 1. Executive Summary

Snapshot-assisted reconciliation performed 2026-07-29. The VM is 11 commits behind GitHub main.
The laptop had no local clone of `dominion-ops` — cloned fresh to `C:\Users\Dell\dominion-ops`
at current main (`a2f28b22`). One candidate code correction implemented locally: wix-agent Docker
healthcheck probe changed from `/ready` to `/health`. The healthcheck fix is implemented and
contract-tested (27/27 tests pass); it is pending CodeRabbit review, Founder approval, merge,
VM deployment, and runtime verification. The exact wix-agent readiness blocker is not proven
from the snapshot — log inspection is required. Disk at 87% is a capacity warning with limited
remaining headroom; inventory must be completed before any cleanup action. No verified revenue
closed loop exists for any vertical. Two PRs are open: #83 (Video Studio preflight) and #50
(CodeRabbit configuration). The preflight script has been created and syntax-validated;
Foundation VM execution is pending.

---

## 2. SHA Reconciliation

| Environment | SHA | Source | Notes |
|---|---|---|---|
| Laptop HEAD | `a2f28b22` | Live `git rev-parse HEAD` | Freshly cloned from origin/main |
| GitHub origin/main | `a2f28b22` | `gh api` live query | Canonical |
| VM production | `5d37fb5a` | Founder-supplied terminal output | Detached HEAD — 11 commits behind |

**Drift — commits on main not present on VM (oldest → newest):**

| SHA | Message |
|---|---|
| `fbe0162c` | Add governed Nemotron intelligence provider |
| `20f41317` | Route Command Center through Nemotron with memory capture |
| `98b4762a` | Configure Nemotron worker and persistent Dominion memory |
| `d0ad73bc` | Document Dominion Intelligence closed-loop architecture |
| `59407f5d` | Add governed digital-product revenue loop |
| `bd76f7cb` | Expose governed revenue state and funnel telemetry |
| `7ea2d96`  | Add governed checkout and delivery configuration |
| `3c9635df` | Document first revenue vertical activation gates |
| `81893205` | Fix baby-api ownership checks |
| `b3e8b73`  | Fix Command Center deployment and runtime config |
| `a2f28b22` | Add safe Command Center runtime configuration template |

**Detached HEAD on VM:** Consistent with governed deployment pattern. The VM deployment target
must be the SHA produced by merging the current PR through the governed Foundation VM deployment
workflow — not manually pinned to `a2f28b22` before review and merge complete.

---

## 3. Open Pull Requests (GitHub — confirmed by live query)

| PR | Branch | Title |
|---|---|---|
| #83 | agent/video-studio-production-execution | Run governed Video Studio end-to-end preflight |
| #50 | agent/coderabbit-pro-setup | Configure CodeRabbit Pro for Dominion reviews |

30 total branches were returned by the branch query. Exact stale/unmerged branch count still
requires branch-to-PR reconciliation.

---

## 4. Active Service Registry

### Docker Containers (VM — Founder snapshot Jul 29)

| Container | Port | Host Binding | Status |
|---|---|---|---|
| baby-api | 8080 | 0.0.0.0 — host-bound; external exposure unverified | health observed |
| baby-logger | — | — | runtime observed |
| browser-agents | 8081 | 0.0.0.0 — host-bound; external exposure unverified | health observed |
| dominion-web | 8090 | 0.0.0.0 — host-bound; external exposure unverified | runtime observed |
| wix-agent | 8082 | 127.0.0.1 loopback only | **UNHEALTHY** in snapshot |
| obsidian-remote | 8083 | 127.0.0.1 loopback only | health observed |
| movie-generator | 8001 | 0.0.0.0 — host-bound; external exposure unverified | runtime observed |
| dominion-seo | — | — | runtime observed |
| dominion-n8n | 5678 | 0.0.0.0 — host-bound; external exposure unverified | runtime observed |
| dominion-db | 5432 | 127.0.0.1 loopback only | runtime observed |

GCP firewall rules and Caddy routing were not inspected in this snapshot. External Internet
exposure of host-bound ports is not proven.

### Systemd Services (VM — Founder snapshot Jul 29, all observed running except logrotate)

ascendant-store (5090) · auric-edge · buddy-bridge (5052) · caddy · conductor-api (5051) ·
conductor-scheduler · conductor-worker · covenant-watchdog · dominion-3d-dashboard (8200) ·
dominion-alchemist · dominion-alpha · dominion-buddy-web (5070) · dominion-command-deck (5110) ·
dominion-conductor · dominion-dashboard (3000) · dominion-email-drip · dominion-email-monitor ·
dominion-gatekeeper (5000) · dominion-guardian · dominion-juris (5055) · dominion-monitor ·
dominion-n8n-watchdog · dominion-ops-dashboard (5100) · dominion-proposal-queue ·
dominion-report (5095) · dominion-review-queue · dominion-sentinel · dominion-store (5080) ·
dominion-surplus-dashboard · dominion-tiktok (5120) · dominion-twilio-router (5102) ·
gemini-server · ollama

**Failed systemd unit:** logrotate.service failed; log rotation effectiveness and current log
growth require inspection.

---

## 5. P0 / P1 / P2 Findings

### P0 — Blocks safe deployment or revenue

| ID | Finding | Evidence | Action |
|---|---|---|---|
| P0-1 | VM 11 commits behind GitHub main | SHA comparison — confirmed | Deploy merged-PR SHA via governed Foundation VM workflow after Founder approval |
| P0-2 | wix-agent unhealthy in VM snapshot | `docker ps -a` snapshot; healthcheck calls `/ready` which returns non-2xx on degraded state; `urlopen` raises on non-2xx; exact blocker not proven — requires `docker logs wix-agent` | Candidate healthcheck correction implemented locally; implementation team to inspect logs and confirm blocker before merge |
| P0-3 | No verified revenue closed loop for any vertical | No CHECKOUT_* or DELIVERY_* env vars confirmed; no test purchase on record | Implementation team prepares checkout config, delivery handler, env var templates, validation tests, and deployment changes; Founder approves and authorizes payment account access |

### P1 — Blocks autonomous operation

| ID | Finding | Evidence | Action |
|---|---|---|---|
| P1-1 | Disk at 87% (41G / 49G / 6.5G free) | `df -h` in Founder snapshot | 87% disk usage is a capacity warning with limited remaining headroom. Implementation team runs read-only inventory and prepares cleanup recommendations; Founder approves retention decisions |
| P1-2 | Command Center not deployed on VM | VM at pre-Command-Center SHA | Deploy via governed workflow after PR merge |
| P1-3 | Nemotron not deployed on VM | Same as P1-2 | Same |
| P1-4 | TikTok OAuth token status unknown | Last known: IN REVIEW Jun 25 — 34 days elapsed | Founder checks TikTok developer portal; implementation team prepares token-save flow if approved |
| P1-5 | Trading bot 90-day report status unknown | Target was Jul 23; not in snapshot | Implementation team runs `python live_tracker.py status` on VM and reviews output |
| P1-6 | logrotate.service failed | `systemctl --failed` in Founder snapshot | Implementation team inspects with `journalctl -u logrotate -n 50`; repairs without deleting diagnostic logs |
| P1-7 | Preflight script created and syntax-validated; governed Foundation VM execution pending | `bash -n` passed on laptop; ShellCheck unavailable; Linux runtime tools (ss, systemctl, Docker daemon) not present on laptop — VM execution required for full signal | Run `scripts/runtime/dominion_ecosystem_preflight.sh` on Foundation VM after governed deployment |
| P1-8 | Seller response detection not built | Prior session memory | Build email-monitor → SMS alert for wholesale lane |
| P1-9 | Host-bound port Internet exposure unverified | GCP firewall and Caddy not inspected | Implementation team inspects GCP firewall rules and Caddy routing; documents findings; Founder approves any production routing changes |

### P2 — Cleanup / optimization

| ID | Finding |
|---|---|
| P2-1 | 30 branches returned by query; stale/unmerged count requires branch-to-PR reconciliation |
| P2-2 | Duplicate repo dirs on VM: ~/dominion, ~/dominion-ops, ~/dominion-ascendant, ~/dominion-healing-site, ~/dominion-strategizer |
| P2-3 | Ollama has only llama3.2:3b |
| P2-4 | Root-owned files in home dir: content_engine.py.bak, multi_content.py.bak |
| P2-5 | dominion-proposal-queue service name references removed PPH vertical |

---

## 6. Disk Assessment — Inventory Required Before Any Cleanup

**87% disk usage is a capacity warning with limited remaining headroom.**

Implementation team runs these read-only commands on the VM, then prepares a categorized
cleanup recommendation. No deletions until the recommendation is reviewed and Founder approves
retention decisions for each category.

```bash
# Media outputs (regeneratable vs archived)
du -sh ~/tiktok_videos ~/tiktok_audio ~/youtube_videos ~/youtube_audio ~/media_output

# Python virtual environments (rebuildable)
du -sh ~/dominion_env ~/conductor/venv

# Node modules (rebuildable)
du -sh ~/dominion_3d_dashboard/node_modules/ 2>/dev/null

# Release artifacts
du -sh ~/releases/*

# Docker layers and volumes
docker system df

# Journal logs
sudo journalctl --disk-usage

# System logs
sudo du -sh /var/log/*

# Duplicate project directories
du -sh ~/dominion ~/dominion-ops ~/dominion-ascendant ~/dominion-strategizer

# Stale top-level files
ls -lh ~/*.log ~/*.bak ~/*.b64 ~/*.save 2>/dev/null
```

---

## 7. Security Exposure (Unverified — Requires Live Inspection)

| Item | Observation | Status |
|---|---|---|
| Ports 8080, 8081, 8001, 8090, 5678 | Bound to 0.0.0.0 in Docker | Host-bound; Internet exposure depends on GCP firewall and Caddy routing — NOT proven |
| Ports 8082, 8083, 5432 | Loopback only | Internal only — correct |
| .env file | mode 600, owner malachisingleton8 | Correct — contents not inspected |
| wix-agent | read_only filesystem + cap_drop ALL + no-new-privileges | Strong hardening — correct |
| Secrets in compose | All ${VAR} references — no literal values in file | Correct |

---

## 8. Nemotron Status

| Dimension | Status |
|---|---|
| Repository implementation | YES — commits on GitHub main |
| Runtime configuration | UNKNOWN — env vars presence not confirmed |
| Deployed to VM | NO — VM is at pre-Nemotron SHA |
| Endpoint connected and responding | NOT PROVEN |

---

## 9. Revenue Readiness

**Digital products is the leading candidate for first revenue closed loop.** Not confirmed as
the fastest lane until the following are verified:

- Exact product asset and suitability for delivery (product.pdf on VM — identity UNKNOWN;
  "The Art of True Healing" final delivery file not proven by supplied find output)
- Payment link creation (Stripe or Gumroad)
- Delivery mechanism (email, secure download, or n8n workflow)
- Published refund and support terms
- Funnel telemetry endpoint active

No offer is revenue-ready until all gates in `governance/DIGITAL_PRODUCTS_REVENUE_LOOP.md` pass.

**Activation ownership:**
- Implementation team: prepares checkout configuration, delivery handler, env var templates,
  validation tests, and deployment changes
- Founder: supplies payment account access, approves test purchase, authorizes go-live

---

## 10. Changes in This PR

| File | Change | Status |
|---|---|---|
| `docker-compose.yml` | wix-agent healthcheck: `/ready` → `/health` | DONE — implemented and tested; pending CodeRabbit review, Founder approval, merge, VM deployment, and runtime verification |
| `apps/wix-agent/tests/test_wix_agent.py` | Added `HealthProbeContractTests` and `ComposeHealthcheckContractTests` | DONE — `py_compile` passed; 27/27 tests passed |
| `scripts/runtime/dominion_ecosystem_preflight.sh` | Read-only runtime preflight check | DONE — `bash -n` passed; ShellCheck unavailable on laptop; Foundation VM execution pending |
| `governance/DOMINION_ECOSYSTEM_RECONCILIATION.md` | This document | CREATED |

**Validation evidence (laptop — 2026-07-29):**

| Check | Result | Notes |
|---|---|---|
| `python -m py_compile` (wix-agent tests) | PASS | No syntax errors |
| Wix-agent test suite | 27/27 PASS | `HealthProbeContractTests` (5) + `ComposeHealthcheckContractTests` (2) + prior suite (20) |
| `docker compose config` | PASS | Compose file validates; expected warnings for unset env vars on laptop |
| `bash -n` (preflight script) | PASS | No syntax errors |
| ShellCheck | NOT AVAILABLE | Not installed on laptop |
| Laptop preflight execution | Exit 1 | Expected: Docker daemon unavailable; `ss`, `systemctl` absent on Windows/Git Bash; disk percentage output not valid Linux evidence |
| Foundation VM preflight | PENDING | Requires governed VM deployment of merged PR SHA |

---

## 11. Deployment Plan

**Requires Founder approval. VM must be updated to the merged-PR SHA via the governed Foundation
VM deployment workflow — not to `a2f28b22` directly before this branch is reviewed and merged.**

1. PR opens → CodeRabbit reviews → Founder approves
2. PR merges to main → new canonical SHA produced
3. Foundation VM governed deployment workflow runs against merged SHA
4. Post-deploy verification (implementation team):
   ```bash
   docker inspect wix-agent --format '{{.State.Health.Status}}'
   # Expected: healthy (within 90s of container restart)
   docker ps -a  # confirm no other containers regressed
   ```

---

## 12. Rollback Plan

If the wix-agent change causes regression, use the governed rollback procedure with the
previously deployed SHA (`5d37fb5a`). Do not assume any backup directory path is valid —
use the governed deployment workflow with the verified prior SHA.

---

## 13. Inputs Required

| Item | Owner |
|---|---|
| Approve PR and governed VM deployment | Founder |
| Check TikTok developer portal — app approval status | Founder |
| Supply payment account access for first offer checkout link | Founder |
| Approve test purchase for revenue verification | Founder |
| Approve retention and cleanup decisions | Founder |
| Approve any firewall or production routing changes | Founder |
| Run read-only VM disk inventory and prepare cleanup recommendations | Implementation team |
| Inspect GCP firewall rules and Caddy routing; document exposure findings | Implementation team |
| Inspect `docker logs wix-agent` and confirm exact readiness blocker | Implementation team |
| Run `python live_tracker.py status`; report trading bot results | Implementation team |

---

## 14. Truth Table

| Component | BUILT | CONFIGURED | DEPLOYED | PROCESS HEALTH | READINESS | E2E VERIFIED | REVENUE VERIFIED |
|---|---|---|---|---|---|---|---|
| baby-api | YES | YES | YES | health observed | UNKNOWN | UNKNOWN | NO |
| baby-logger | YES | YES | YES | runtime observed | N/A | UNKNOWN | NO |
| browser-agents | YES | YES | YES | health observed | UNKNOWN | UNKNOWN | NO |
| dominion-web | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| wix-agent | YES | PARTIAL | YES | UNHEALTHY in supplied VM snapshot; candidate healthcheck correction pending verification | UNKNOWN — blocker not proven from snapshot | UNKNOWN | NO |
| obsidian-remote | YES | YES | YES | health observed | UNKNOWN | UNKNOWN | NO |
| movie-generator | YES | UNKNOWN | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| dominion-n8n | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| dominion-db | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| Nemotron | YES | UNKNOWN | NO | — | — | UNKNOWN | NO |
| Command Center | YES | PARTIAL — template exists; VM runtime config UNKNOWN | NO | — | — | UNKNOWN | NO |
| Digital product revenue loop | YES | NO | NO | — | — | UNKNOWN | NO |
| KDP pipeline | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | UNKNOWN |
| YouTube pipeline | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| Surplus recovery | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | UNKNOWN |
| Wholesale scout | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | UNKNOWN |
| Email drip | YES | PARTIAL | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| TikTok OAuth | YES | PARTIAL | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| Sentinel | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| Juris | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
| Alpha Engine | YES | YES | YES | runtime observed | UNKNOWN | UNKNOWN | NO |
