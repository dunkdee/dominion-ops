# DeerFlow integration

DeerFlow runs beneath existing Dominion / RADAH MEMSHALAH governance. Dominion remains the authority; DeerFlow is a governed long-running execution coordinator, not a second control plane or source of truth.

## Production pin

Production is pinned to the stable upstream `bytedance/deer-flow` tag `v2.0.0`.

The v2.0.0 backend root project exposes `postgres` and `discord` optional extras, while Ollama support is exposed by the local `deerflow-harness[ollama]` package. The governed deployment patches only the pinned checkout during image build so the root backend depends on `deerflow-harness[ollama]`, then restores the upstream file automatically after the deployment command exits.

The pinned v2.0.0 tree does not contain `deerflow.community.browser_automation`. Browser automation is therefore intentionally disabled instead of advertising an unavailable capability. A future browser-capable upgrade requires a separately reviewed exact upstream pin plus governance, regression, rollback, and receipt proof.

## Governed production capability contract

The Dominion profile enables the stable v2.0.0 capabilities that are appropriate for a single-node governed production coordinator:

- local Ollama through the native `langchain_ollama:ChatOllama` provider using the already-governed `nemotron-3-nano:4b` model
- no deployment-time model pull; model inventory is a prerequisite and a missing governed model fails closed
- persistent single-node SQLite execution state under the mounted `DEER_FLOW_HOME`
- database-backed run events so messages and execution traces survive restart
- per-user DeerFlow memory for execution continuity, explicitly non-canonical relative to Dominion truth
- subagent delegation with bounded time and turn limits
- the stable DeerFlow skills system mounted read-only into the gateway
- DuckDuckGo web search, Jina page fetch, DuckDuckGo image search, and bounded file list/search/read/write/replace tools
- native pre-tool guardrails enabled fail-closed with host bash denied
- circuit-breaker, loop-detection, token-usage, and tool-output budget protections
- a governed `SOUL.md` declaring DeerFlow subordinate to RADAH MEMSHALAH, Council, and Gatekeeper
- custom-agent management API disabled
- agent-managed skill evolution disabled
- user-owned IM channel connections disabled until separately governed and bound

The local SQLite database and DeerFlow memory are runtime continuity mechanisms only. They do not supersede Dominion's canonical operational records, governance, receipts, or approved data stores.

## Scheduling and initiative boundary

The stable v2.0.0 pin supplies persistent runs, memory, subagents, skills, and long-running execution, but Dominion does not rely on an unverified native scheduler or browser feature. Deterministic recurrence and external-event triggers remain with governed n8n / Dominion orchestration. DeerFlow receives authorized missions, continues them within its runtime boundaries, and returns verified outcomes and receipts.

## Required production proof

A deployment is not accepted merely because containers start or because Ollama's model-list endpoint responds. The deployment workflow must record all three:

- `DEERFLOW_INFERENCE_PROOF=PASS model=nemotron-3-nano:4b` proving the gateway performed a real `ChatOllama` inference against the configured governed model through the bounded Docker bridge
- `DEERFLOW_CAPABILITY_PROOF=PASS` proving the loaded production configuration, persistent database, memory, guardrails, skills, subagents, approved tool set, governed identity, configured model, and model inventory
- `DEERFLOW_RUNTIME_HEALTH=PASS` proving the Foundation VM runtime is reachable after startup

Runtime proof still does not close the full Dominion acceptance contract. Before DeerFlow is classified as fully closed, Dominion must additionally prove mission persistence/recovery, bounded initiative, governance denial behavior, rollback/stop behavior, existing-service regression safety, end-to-end receipt lineage, and one real bounded long-running synchronization mission.
