# WORK ORDER 05 — KDP PUBLISH PACKET GENERATOR

**Issued:** August 15, 2026  
**Authority:** Dewayne Singleton, Founder, Dominion Ascendant  
**Supersedes:** the quarantined `kdp_publisher_agent.py` approach

## Purpose

Produce a complete human-ready publish packet for each KDP title. The human performs upload and publication inside KDP. No agent authenticates to Amazon, stores Amazon credentials, or drives a browser session against Amazon.

## Non-negotiable constraints

- No Amazon credentials in code, `.env`, a secret store reachable by an agent, logs, or packet inputs.
- No browser automation against Amazon or KDP.
- No TOTP seed storage.
- No cron, systemd, unattended trigger, or autonomous publishing.
- The existing title-rights review, Founder approval, and Five Council final-release requirements remain in force.

## Merit Gate

Before any packet exists, the title must receive `GO` on all five checks:

1. Named comparables with observed BSR and source evidence.
2. A specific sentence explaining the title's differentiation.
3. Whole-book content-integrity verification evidence, including every puzzle/answer key where relevant.
4. Clearance for title collision, ownership/originality, public-domain or scraped material, prohibited health/legal/income claims, and CLAUDE.md §5.4.
5. A documented AI-content disclosure determination and rationale.

`NO-GO` writes only `MERIT_GATE.md` with blocking reasons. No partial packet is created.

## GO packet

`publishing/packets/{slug}/` contains:

- supplied print-ready interior and cover assets, preserved with SHA-256 evidence;
- `interior_spec.txt`;
- `listing.html` and `listing.json` with title, author once, seven keyword slots, and three category paths;
- `commercials.json` with actual supplied print-cost evidence and computed royalty per unit;
- AI-disclosure record and KDP Select recommendation;
- `PUBLISH_STEPS.md`, a human click path with each field value.

The generator is offline and preparation-only. It cannot access, upload to, or publish through KDP.

## Acceptance

A valid, evidenced title produces a complete packet. A deficient title fails closed with recorded reasons. The publisher needs only to follow the supplied upload steps after the existing approval gates clear.
