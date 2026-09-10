# Deep Research Fabric v1 — Governed Work Order

**Authority:** Founder-directed under RADAH MEMSHALAH
**State:** DRAFT / NOT DEPLOYED
**Base production SHA:** `d950babb3ddd297bb48e469a27a4a834def264f3`
**Primary mission:** expand market/traffic intelligence without creating a second source of truth or bypassing access controls.

## 1. Objective

Build an isolated research fabric that combines DeepSeek Harness, browser automation, public/authorized research sources, and existing Dominion evidence systems. The fabric is a **research scout**, not a governing brain.

Canonical flow:

`Founder / Obsidian -> Dominion control plane -> Deep Research Fabric -> evidence sources -> normalized receipts -> Nemotron/Dominion validation -> ranked opportunity -> approved traffic/content action -> receipt -> Obsidian`

## 2. Non-negotiable boundaries

1. **No authority bypass.** No CAPTCHA bypass, credential bypass, subscription bypass, rate-limit evasion, or access-control circumvention.
2. **No production secrets in DeepSeek Harness.** Production credentials remain in existing governed secret stores only.
3. **Read-only launch posture.** Initial connectors may research and collect evidence but may not publish, spend, change prices, modify provider accounts, contact customers, execute trades, or mutate production systems.
4. **Loopback/private binding only.** Research services must not be exposed directly to the public internet.
5. **Default deny.** Every connector is explicitly registered and allowlisted; arbitrary shell commands, arbitrary URLs, and arbitrary file reads are prohibited.
6. **Receipts required.** Every research mission records source, timestamp, query/objective, connector ID, result hash, confidence, and evidence references. Secret response bodies are never persisted.
7. **Canonical truth stays Dominion.** Obsidian is the operating mirror; provider-native evidence and governed runtime state remain authoritative.
8. **Founder gate remains binding** for consequential external actions.

## 3. Components

### A. DeepSeek Harness scout
- Official source: `deepseek-ai/deepseek-harness`.
- Treat as developer-preview software.
- Run isolated from production workloads.
- Pin exact package/source version before deployment.
- Disable or omit any plugin not explicitly reviewed.

### B. Browser research connector
- Prefer official Microsoft Playwright MCP / Playwright tooling.
- Persistent authenticated sessions may be used only for accounts the Founder is authorized to access.
- Session material must remain outside logs, receipts, prompts, and Obsidian.
- Initial posture: read-only research/navigation/export.

### C. Research source adapters
Launch adapters should be limited to:
- public web research,
- public GitHub repositories,
- competitor websites,
- YouTube/social public discovery,
- VibeSEO/Able SEO evidence already available to Dominion,
- Similarweb pages/data available through the Founder's legitimate account/session,
- Meta AI outputs supplied by the Founder or available through authorized interfaces.

Future adapters require separate review.

### D. Evidence normalizer
Every source result becomes a bounded normalized record:

```json
{
  "mission_id": "uuid",
  "source": "similarweb|vibeseo|web|github|youtube|meta|other",
  "connector_id": "registered-id",
  "observed_at": "ISO-8601",
  "objective": "string",
  "query_hash": "sha256",
  "result_hash": "sha256",
  "confidence": "HIGH|MEDIUM|LOW",
  "evidence_refs": [],
  "sanitized": true
}
```

### E. Dominion validator
- Nemotron/Dominion compares cross-source evidence.
- A traffic opportunity cannot be promoted because one model says so.
- Promotion requires evidence overlap, source quality, commercial relevance, and a measurable destination.

## 4. First production research mission — VoltEdge Traffic

Target: identify **10 high-intent traffic opportunities** for VoltEdge and promote the strongest **3** into governed content/distribution experiments.

Inputs:
- current VoltEdge catalog,
- current VibeSEO site/audit evidence,
- Similarweb competitor/channel evidence,
- public search demand,
- public competitor content and landing pages,
- current Dominion revenue/traffic runtime state.

Required output per opportunity:
- buyer intent,
- target keyword/topic,
- evidence sources,
- competitor/channel proof,
- recommended content format,
- destination URL / offer route,
- expected measurable event,
- risk/compliance notes,
- confidence,
- next reversible action.

Promotion rule: top 3 only after validation; no fabricated search volume or traffic claims.

## 5. Implementation phases

### Phase 0 — Inventory / collision check
- Confirm Node.js/npm/pnpm availability and versions on the target host.
- Check all existing listeners/services and choose a proven-free loopback port.
- Confirm CPU/RAM/disk headroom.
- Confirm no existing DeepSeek Harness or Playwright service is already deployed.
- Record rollback target and exact production SHA.

### Phase 1 — Isolated local harness
- Pin an exact DeepSeek Harness version/commit.
- Install in a dedicated path/service account or container.
- Bind loopback only.
- No production secrets mounted.
- Health/start/stop/restart contracts documented.

### Phase 2 — Governed connector registry
- Add explicit connector IDs and allowlisted targets.
- Start with read-only public web/GitHub/browser research.
- Reject arbitrary URL, arbitrary shell, and arbitrary path access.
- Hash and sanitize every invocation receipt.

### Phase 3 — Playwright research adapter
- Add official Playwright MCP/CLI integration.
- Separate browser profile from production services.
- Authentication performed only through Founder-authorized sessions.
- No password/token values written to repo, logs, prompts, or receipts.

### Phase 4 — Evidence + Obsidian bridge
- Normalize research receipts.
- Feed sanitized summaries into existing Obsidian/Command Center evidence paths rather than creating a parallel truth store.
- Preserve source URLs/refs and timestamps.

### Phase 5 — VoltEdge mission canary
- Run one public-web/GitHub-only research mission first.
- Then run one Founder-authorized Similarweb read-only mission.
- Compare with VibeSEO evidence.
- Produce ranked 10-opportunity report.
- Promote only the top 3 after Dominion validation.

## 6. Acceptance gates

All must pass before production classification:

- `DRF_INSTALL_PINNED=PASS`
- `DRF_LOOPBACK_ONLY=PASS`
- `DRF_NO_PRODUCTION_SECRETS=PASS`
- `DRF_DEFAULT_DENY=PASS`
- `DRF_ARBITRARY_SHELL_BLOCKED=PASS`
- `DRF_ARBITRARY_URL_BLOCKED=PASS`
- `DRF_PLAYWRIGHT_READ_ONLY_CANARY=PASS`
- `DRF_RECEIPT_SANITIZATION=PASS`
- `DRF_OBSIDIAN_BRIDGE=PASS`
- `DRF_CROSS_SOURCE_VALIDATION=PASS`
- `DRF_VOLTEDGE_TOP10_REPORT=PASS`
- `DRF_TOP3_PROMOTION_PACKET=PASS`
- `SYSTEM_INTEGRITY=PASS`
- `ROLLBACK_PROVEN=PASS`

## 7. Explicitly out of scope for v1

- bypassing ChatGPT Work limits,
- bypassing Similarweb/Meta/provider controls,
- automated paid ad spend,
- autonomous purchasing or money movement,
- live trading,
- automatic customer outreach,
- credential/IAM mutation,
- arbitrary browser automation across unapproved sites,
- making DeepSeek Harness the constitutional/governance authority.

## 8. Rollback

The v1 release must be removable without impacting Dominion production:
- stop/disable the isolated research service,
- remove its connector registration,
- preserve sanitized receipts,
- restore the prior connector registry/configuration,
- verify Command Center, Nemotron, Revenue Runtime, Obsidian, and system integrity remain healthy.

## 9. Release rule

This work order authorizes **design, branch implementation, tests, and non-consequential read-only canaries only**. Production deployment or any expansion into consequential external actions requires the repository's normal exact-SHA Founder authorization and Five Council release process.
