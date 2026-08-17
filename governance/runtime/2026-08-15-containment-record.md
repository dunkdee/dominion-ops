# Runtime Recovery Containment Record — 2026-08-15

**State:** RECOVERY HOLD  
**Scope:** Foundation VM and GitHub deployment control plane  
**Source:** Direct runtime inspection and post-change verification.  
**This record supersedes conflicting claims in older runtime documents.** It does not authorize reactivation.

## Verified containment

| Item | Verified state | Acceptance evidence |
|---|---|---|
| Nemotron | Stopped and disabled | `dominion-nemotron.service` inactive/disabled; no listener on TCP 11435 |
| Email monitor | Stopped and disabled | `dominion-email-monitor.service` inactive/disabled |
| Affiliate, scout, wholesale timers | Stopped and disabled | Each timer inactive/disabled |
| Raw ops dashboard ingress | Closed | GCP rule `allow-ops-dashboard` deleted; local service remained healthy |
| Raw Twilio ingress | Closed | GCP rule `allow-twilio-router` deleted; router remains reachable only locally |
| Twilio router candidate | Not deployed | Candidate test suite passed 13/13 in isolation; live router was not replaced or restarted |

## Explicit holds

- No old “full build” workflow may apply VM changes.
- No service above may be re-enabled without a written work order, a reviewed change, and fresh acceptance evidence.
- External publishing, outreach, surplus-recovery contact, payments, and live trading remain outside this authorization.
- Obsidian stores remain unreconciled; no synchronization or merge is authorized.
- Twilio remains paused. Its stored API credentials returned authentication failure; callback URLs and a valid primary Auth Token must be confirmed outside GitHub before deployment or firewall reopening.

## Recovery sequence

1. Reconcile the service inventory against live VM evidence.
2. Replace the deprecated deployment workflow with a reviewed, least-privilege recovery workflow.
3. For every proposed activation, prove source, owner, process, bind, route, health, logs, persistence, restart behavior, and rollback.
4. Open ingress only after the service passes its signed/authorized external acceptance check.
5. Record the actual result in this repository before declaring a component online.

## Non-goals

This record is not proof that any remaining service is healthy, production-ready, secure, or authorized. It is a containment checkpoint and a handoff baseline.
