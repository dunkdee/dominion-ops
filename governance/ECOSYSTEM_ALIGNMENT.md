# Dominion Ascendant — Ecosystem Alignment

## Authority

Dewayne Singleton is the final human authority. Agents may observe, analyze, draft, route, test, and recommend. They may not override a vertical gate, sign, file, publish sensitive claims, spend funds, activate live trading, or disclose protected information without explicit human approval.

The machine-readable source of truth is [`verticals.json`](./verticals.json). Changes to vertical duties, order, modes, dependencies, or approval gates must pass `scripts/validate_ecosystem_alignment.py`.

## Operating order

1. **Cash flow** — produce a verified customer transaction or qualified service opportunity.
2. **Systems** — make the proven revenue path repeatable, observable, and recoverable.
3. **Scale** — increase volume only after the lane has evidence, controls, and a rollback path.

No new vertical is promoted because its code exists. Promotion requires its declared exit gate to be proven with real output.

## Vertical command order

| Priority | Vertical | Current mode | Current status | Primary duty | Promotion gate |
|---:|---|---|---|---|---|
| 1 | Digital products | Assisted | Blocked | Publish and deliver owned products | File attached, product visibly published, checkout and delivery verified |
| 2 | Commerce and fulfillment | Record only | Guarded | Audit Wix and record order state | `/ready` passes and one sandbox order creates one record |
| 3 | Services and lead generation | Assisted | Unverified | Produce qualified leads and reviewable proposals | Controlled dry run yields one qualified lead without submission |
| 4 | Content and traffic | Draft only | Unverified | Produce approved traffic-driving content | OAuth verified and one private/unlisted end-to-end publish test passes |
| 5 | Surplus | Research only | Incomplete | Qualify lawful opportunities and prepare case records | Jurisdiction workflow reviewed and synthetic case passes end to end |
| 6 | Trading | Paper | Paper only | Simulate governed strategies and measure risk | Documented sample size, drawdown, profit factor, and recovery thresholds pass |
| 7 | Intelligence and orchestration | Observe and route | Incomplete | Route tasks, enforce contracts, log outcomes, escalate failures | Every active vertical has input/output contracts, health, failure queue, and escalation |
| 8 | Governance and legal | Review and veto | Foundational | Enforce authority, auditability, privacy, and legal boundaries | All active verticals pass automated alignment validation |
| 9 | Infrastructure | Production support | Partially verified | Provide deployment, secrets, networking, persistence, monitoring, backup, and rollback | VM health, secrets, backup, rollback, and runtime inventory are verified |

## Present alignment finding

The ecosystem is **not yet production-aligned as one end-to-end system**.

The repository contains substantial working components, but the current Docker Compose runtime only declares the API, browser agents, website, Wix agent, and Obsidian. Jarvis, n8n, the content workers, surplus processing, and the Alpha Engine are not presently represented as one governed production runtime. This means they cannot yet be treated as continuously supervised verticals.

The current state record also identifies unresolved operational gates: Gumroad file attachment/publishing, stale or unknown secrets, unverified production health, untested TikTok OAuth, untested trading paper-mode integration, and an incomplete frontend.

## Non-negotiable boundaries

- **Trading remains paper-only.** No exchange execution is permitted by this registry.
- **Wix remains record-only by default.** Supplier submission and bulk mutation require explicit approval.
- **Content remains draft-only until OAuth and private/unlisted testing pass.**
- **Surplus remains research-only.** No claimant contact, filing, signature, or sensitive identity collection is autonomous.
- **Legal and trust documents are drafts until independently reviewed and deliberately executed.**
- **Secrets belong in the production secret store, never repository files or logs.**
- **A heartbeat is not proof of duty completion.** Each vertical must produce a defined output and a logged result.

## Closure sequence

### Gate A — Revenue proof

1. Complete and verify the digital-product checkout and delivery path.
2. Run a Wix sandbox purchase and confirm exactly one fulfillment record.
3. Run a services dry test that creates a qualified lead and reviewable proposal.

Only lanes that pass these tests stay in the immediate execution queue.

### Gate B — Runtime alignment

1. Inventory the live VM and compare it with `docker-compose.yml` and `verticals.json`.
2. Assign one health endpoint, persistent store, failure queue, and rollback method to each active vertical.
3. Bring Jarvis/n8n routing under explicit contracts rather than informal heartbeat loops.
4. Remove or quarantine obsolete workflows and duplicate deployment paths.

### Gate C — Controlled activation

1. Verify content OAuth and run private/unlisted publishing tests.
2. Complete a synthetic surplus case under jurisdiction-specific legal review.
3. Run trading paper benchmarks and publish metrics; do not enable live execution.
4. Promote only the verticals whose exit gates are evidenced.

## Definition of aligned

The ecosystem is aligned only when all of the following are true:

- every active vertical appears in the registry and the runtime inventory;
- every vertical has one operator, one duty, one mode, dependencies, approval gates, and an exit gate;
- automated validation passes on every relevant change;
- production secrets and health are verified without exposing credentials;
- failures enter a visible queue and escalate to a human;
- rollback and persistent-data recovery are tested;
- no vertical operates beyond its authorized mode;
- revenue-producing lanes receive priority over expansion work.
