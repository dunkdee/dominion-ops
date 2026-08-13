# WORK ORDER 03 — KDP AGENT QUARANTINE & SECRETS REMEDIATION
*Executed 2026-08-13. Claude Code on Dell laptop. Founder order.*
*Filed to governance so it stops living only in a chat window.*
*Execute under DOMINION_BINDING_BRIEFING.md. Truth state on every claim.*

---

## TRIGGER
Two untracked, uncommitted files found in `buddy_core/agents/`:
- `kdp_publisher_agent.py` — browser automation that writes to live KDP account
- `kdp_agent.py` — LLM listing generator with no manuscript access (fabrication by design)

Neither had ever been committed. No git history. No execution log.

---

## VIOLATIONS FOUND

| # | File | Violation |
|---|---|---|
| 1 | `kdp_publisher_agent.py` | CLAUDE.md §5.4 — sovereign-citizen framing in `BOOK` dict ("living man/woman", UCC 1-308). Settled and closed. |
| 2 | `kdp_publisher_agent.py` | Plaintext `AMAZON_EMAIL` and `AMAZON_PASSWORD` read from `.env`. Password found in `.env` line 59. |
| 3 | `kdp_publisher_agent.py` | Unattended publish action to live third-party account. Clicks Publish without Founder GO. |
| 4 | `kdp_agent.py` | Generates listing copy via LLM with no access to source manuscripts. Fabrication by design. |
| 5 | `kdp_listings.json` | Output of `kdp_agent.py`. Generated 2026-04-22. Timestamp suspicious (exact midnight). VOID. |

---

## STEPS EXECUTED

### Step 1 — Create quarantine directory
```
mkdir buddy_core/quarantine/
```
**Status:** VERIFIED

### Step 2 — Quarantine kdp_publisher_agent.py
Prepend header verbatim, move from `agents/` to `quarantine/`:
```
# QUARANTINED 2026-08-13 — Founder order.
# Reasons: (1) CLAUDE.md §5.4 violation — sovereign-citizen framing in BOOK dict.
# (2) Plaintext AMAZON_EMAIL / AMAZON_PASSWORD read from .env.
# (3) Unattended publish action to a live third-party account.
# Never executed (no kdp_publish_log.json). Retained as evidence.
# DO NOT EXECUTE. Founder GO required to lift.
```
**Status:** VERIFIED

### Step 3 — Quarantine kdp_agent.py
Prepend header verbatim, move from `agents/` to `quarantine/`:
```
# QUARANTINED 2026-08-13 — Founder order.
# Reason: generates listing copy via LLM with no access to source manuscripts.
# Fabrication by design. Output kdp_listings.json is VOID.
# DO NOT EXECUTE. Founder GO required to lift.
```
**Status:** VERIFIED

### Step 4 — Mark kdp_listings.json VOID
Prepended to the JSON array:
```json
{"_status": "VOID — unverified generated content, do not use. Quarantine order 2026-08-13."}
```
Do not delete. Retained as evidence.
**Status:** VERIFIED

### Step 5 — Commit to git
```
git add quarantine/kdp_publisher_agent.py quarantine/kdp_agent.py kdp_listings.json
git commit -m "quarantine: move kdp_publisher_agent and kdp_agent per Founder order 2026-08-13"
```
Commit: `f493b89`
**Status:** VERIFIED

### Step 6 — Secrets remediation

**Git history scan:**
- `git log --all --full-history -- .env` → empty. `.env` never committed. VERIFIED.
- `git log -S "AMAZON_PASSWORD" --all` → one hit: commit `f493b89` (quarantine commit). Contains `os.getenv("AMAZON_PASSWORD", "")` as Python source code string — the variable name, not the value. Actual credential value never entered git. VERIFIED.

**.gitignore:**
- `.env`, `.env.*`, `*.env` all present. VERIFIED.

**Credential removal from .env:**
- Lines 58–59 (`AMAZON_EMAIL` and `AMAZON_PASSWORD`) deleted from `buddy_core/.env`.
- Zero matches confirmed after removal. VERIFIED.
- **Password value was found in plaintext. Rotation required — Founder action, still today.**

**Browser profile deletion:**
- `buddy_core/browser_profile/kdp/` deleted in full. VERIFIED.
- Remaining profiles: instagram, tiktok, youtube, linkedin, suno, others — not touched.

### Step 7 — git status audit (read-only)
- Total untracked files: **478**
- 22 files flagged by name as credential readers or third-party write agents (INFERRED — not read)
- See session record for full list

---

## STILL OPEN — REQUIRES FOUNDER ACTION

| Item | Priority |
|---|---|
| **Password rotation** for the exposed credential — today | CRITICAL |
| **2FA audit** on Amazon KDP account | CRITICAL |
| Read and assess the 22 flagged untracked agent files | HIGH |
| Determine disposition of 478 untracked files (commit, quarantine, or gitignore) | MEDIUM |
| `kdp_cover_generator.py` and `kdp_pdf_formatter.py` — not yet read; data origin unknown | MEDIUM |
| `dominion-kdp.service` found in `agents/` — service unit file, disposition unknown | MEDIUM |

---

## STANDING RULE (added to prevent recurrence)
Any agent file that:
- reads credentials from `.env` AND
- performs an unattended write to a live third-party account

...must be quarantined pending review, regardless of whether it has ever been executed. Discovery of such a file is sufficient grounds. No execution required to trigger quarantine.

---
*Filed: 2026-08-13 | Work Order 03 | Executor: Claude Code (laptop session)*
*Companion to: DOMINION_BINDING_BRIEFING.md, WORK_ORDER_02_RATIFY_AND_ACTIVATE.md*
