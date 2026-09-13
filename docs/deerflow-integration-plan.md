# DeerFlow integration

DeerFlow runs beneath existing Dominion / RADAH MEMSHALAH governance. Dominion remains the authority; DeerFlow is a governed long-running execution coordinator.

## Production pin

Production is pinned to upstream `bytedance/deer-flow` tag `v2.0.0`.

The v2.0.0 backend root project exposes `postgres` and `discord` optional extras, while Ollama support is exposed by the local `deerflow-harness[ollama]` package. The governed deployment therefore patches only the pinned checkout during image build so the root backend depends on `deerflow-harness[ollama]`, then restores the upstream file automatically after the deployment command exits.

The pinned v2.0.0 tree does not contain `deerflow.community.browser_automation`. Browser automation is therefore intentionally disabled for this production pin instead of advertising an unavailable capability. A future browser-capable upgrade must use a separately reviewed exact upstream pin and pass the same governance, regression, rollback, and receipt requirements before production adoption.

## Required production proof

A deployment is not accepted until the workflow records `DEERFLOW_RUNTIME_HEALTH=PASS` from the Foundation VM. Runtime health alone does not close the full Dominion acceptance contract; persistence, initiative, governance, rollback, regression, and receipt-chain tests still follow before DeerFlow is classified as fully closed.
