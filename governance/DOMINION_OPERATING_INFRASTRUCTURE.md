# DOMINION OPERATING INFRASTRUCTURE — AMENDMENT 04
*The unglamorous systems that decide whether an ecosystem survives its own success.*
*Status: DRAFT — Founder GO required. Completes Amendments 01–03.*

---

## §0 — WHY THIS IS THE LAST GAP
Amendments 01–03 cover revenue, leverage, and compounding. Every one assumes an operating substrate that does not yet exist in verified form. These systems are invisible while nothing is happening and decisive the moment something is. Each is listed with what breaks without it and the minimum viable version — not an enterprise build, the smallest thing that actually holds.

---

## §1 — FINANCIAL INFRASTRUCTURE
**Breaks:** first real revenue. Cannot separate trust from operating funds, cannot compute the tax reserve, cannot prove unit economics to anyone, cannot pass diligence at Stage 4.
**Minimum viable:**
- Chart of accounts, per lane, revenue and cost segregated
- Bookkeeping system reconciled monthly against every provider payout
- Clear separation of Dominion Legacy Trust funds from operating funds — **UNKNOWN:** current banking and account structure; must be VERIFIED, not assumed
- Tax reserve mechanism funded at every payout, not at year end (§6 reserve in Amendment 03 is the source)
- Cash position and runway reported weekly
**Gate:** must exist before the first payout is received, not after.

---

## §2 — LEGAL AND IP FOUNDATION
**Breaks:** first dispute, first chargeback, and all of Amendment 02 Stage 4.
**Minimum viable:**
- Terms of service, privacy policy, refund/return policy, shipping policy — live on every commercial property before paid traffic
- Written IP assignment from operating entities to Dominion Legacy Trust covering PhiMemory, the governance corpus, agent implementations, and published works
- Confirmation the trust can license and receive royalty as Stage 4 assumes
**Truth state:** currently UNKNOWN. Requires qualified legal review. No agent may assert IP position.

---

## §3 — IDENTITY AND ACCESS CONTROL
**Breaks:** silently, then catastrophically. This is the highest-severity unaddressed item.
**Minimum viable:**
- Single access register: every human and agent, every system, every permission level, with a named owner
- Credential inventory by reference and hash only — never values
- Rotation schedule and a documented rotation procedure
- Offboarding procedure for a retired or suspended agent, including revocation
- Least privilege enforced — no shared root-equivalent credentials across agents

---

## §4 — BUSINESS CONTINUITY
**Breaks:** on the day you need it, which is the only day it matters.
**Minimum viable:**
- **A tested restore.** A 1.7G backup that has never been restored is UNKNOWN, not a backup. Restore to a scratch environment and record the result.
- Documented recovery-time and recovery-point objectives per service
- Off-VM, off-laptop copy of governance corpus, Command Vault, and credentials-by-reference
- Restore test repeated quarterly with evidence

---

## §5 — CUSTOMER OPERATIONS
**Breaks:** before your tenth sale. An unanswered angry customer becomes a chargeback, a public review, and a processor risk flag.
**Minimum viable:**
- Monitored support inbox with a stated response-time target
- Written refund, replacement, and dispute procedures — decided before the first case, not during it
- Chargeback response process and evidence pack
- Every case logged; recurring causes routed into the learning loop (Amendment 03 §3)
**Note:** payment-processor standing depends on dispute rate. This protects the revenue rail itself.

---

## §6 — OBSERVABILITY AND ALERTING
**Breaks:** quietly. A down checkout that nobody is paged about is indistinguishable from no demand.
**Minimum viable:**
- Alerting to a human — not a dashboard — on: checkout failure, payment failure, site down, order-to-fulfillment stall, spend anomaly, dispute-rate threshold, agent error spike
- Defined severity levels and who is notified at each
- Weekly review of what alerted, what was noise, what was missed

---

## §7 — DATA GOVERNANCE AND PRIVACY
**Breaks:** into legal exposure, and it is the most under-considered item in the corpus.
**Minimum viable:**
- Data inventory: what personal data is collected, where it lives, who can reach it, how long it is kept
- **Surplus lane is the sharpest risk** — case research involves identifiable individuals who never opted in. Retention limits, access controls, and no processing beyond documented prep purpose.
- Customer PII: minimum necessary, encrypted at rest, never in logs, prompts, commits, or screenshots
- Deletion-request procedure
- Vendor data-handling review before any new provider touches customer data

---

## §8 — VENDOR AND PLATFORM DEPENDENCY
**Breaks:** without warning and without appeal. Meta's restriction already proved this.
**Minimum viable:**
- Dependency register: Wix, Zendrop, GCP, payment providers, email, each rated by revenue exposure and switching difficulty
- Documented contingency for every single point of failure with high exposure
- Owned assets (list, content, domain, data) held independent of any platform — a platform loss must never be a data loss
- No lane may reach `REVENUE: PROVEN` while depending on a single unreplaceable vendor without a written contingency

---

## §9 — SUCCESSION AND KNOWLEDGE CONTINUITY
**This is the gap that ends everything else if left open.**

Dominion is a legacy structure held in trust, and it currently runs on one person's undocumented context. Not the documents — the judgment: why lanes were sequenced this way, why Buddy was removed, what the φ constant governs and what it doesn't, which decisions are settled and which are open. If that context is lost, the corpus becomes archaeology and the ecosystem stops.

**Minimum viable:**
- **Founder Context Record** — the decisions and the reasoning behind them, maintained as a living document. Not status; judgment.
- **Successor Brief** — what a new operator, human or agent, must read in order, to take command without rediscovering the whole system.
- **Emergency access and authority procedure** — who holds authority if the Founder is unavailable, how it is proven, what it may and may not authorize. **UNKNOWN:** whether the trust instrument already specifies this. Verify with counsel; do not draft governance around an assumed answer.
- **Named owner for every service** — Amendment 01's audit surfaces the unowned ones. Unowned infrastructure is orphaned infrastructure.
- **Documented before deployed** — Engineering Standard v1.0 §10 already requires it. Enforce it: no service enters production without purpose, operation, deployment, debugging, owner, and compliance status recorded.

**The test:** could a competent successor with no prior contact read the corpus and run Dominion correctly within a week? Today the honest answer is no. That is the last open loop.

---

## §10 — SEQUENCING (nothing here delays the sprint)
All of §1–§9 is Tier B. None blocks Tier C. Ordered by what breaks first:

**Before the first paid traffic dollar:** §2 policies live, §6 alerting on checkout and payment, §5 support inbox and refund procedure.
**Before the first payout is received:** §1 accounts, reserve, and reconciliation.
**Within the 14-day sprint:** §3 access register, §4 tested restore, §8 dependency register.
**Within 30 days:** §7 data inventory, §9 Founder Context Record and Successor Brief begun.
**Before Amendment 02 Stage 2:** §2 legal review complete, §9 succession procedure verified.

---

## §11 — CLOSING RULING
An ecosystem does not fail at the ambitious layer. It fails because nobody tested the restore, nobody answered the support email, nobody separated the trust funds, and nobody wrote down why the decisions were made. Amendments 01–03 build the engine. This one keeps it running when the founder is unavailable, the vendor changes terms, and the first ten customers all arrive on the same day.

**Founder GO required on:** the sequencing in §10, and authorization to begin §9 with qualified legal review of the trust's succession and authority provisions.

---
*Filed: 2026-08-13 | Document 05 of 11 | Amendment 04*
