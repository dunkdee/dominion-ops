// VoltEdge global site code (masterPage.js)
// Deterministically binds a Dominion click to Wix Cart V2 purchaseFlowId.
// No prices, products, payments, buyer PII, or checkout state are mutated.

import { currentCartV2 } from "@wix/ecom";
import { location, queryParams } from "@wix/site-location";
import { session } from "wix-storage-frontend";

const BRIDGE_ORIGIN = "https://dominionhealing.org";
const SESSION_KEY = "dominion_revenue_bridge_v1";
const MAX_ATTEMPTS = 15;
const RETRY_MS = 2000;

function validExperiment(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{3,120}$/.test(value);
}

async function captureBridgeState() {
  const query = await location.query();
  const token = typeof query.dr_token === "string" ? query.dr_token : "";
  const experiment = typeof query.utm_campaign === "string" ? query.utm_campaign : "";
  if (!token || !validExperiment(experiment)) return;

  await session.setItem(SESSION_KEY, JSON.stringify({ token, experiment }));
  // Keep campaign UTM values visible, but remove the one-time credential from the URL.
  await queryParams().remove(["dr_token"]);
}

async function pendingBridgeState() {
  const raw = await session.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed.token || !validExperiment(parsed.experiment)) return null;
    return parsed;
  } catch (_) {
    await session.removeItem(SESSION_KEY);
    return null;
  }
}

async function bindCurrentFlow() {
  const state = await pendingBridgeState();
  if (!state) return true;

  let response;
  try {
    response = await currentCartV2.getCurrentCart();
  } catch (_) {
    return false;
  }
  const purchaseFlowId = response?.cart?.purchaseFlowId || "";
  if (!purchaseFlowId) return false;

  try {
    const bridgeResponse = await fetch(
      `${BRIDGE_ORIGIN}/r/${encodeURIComponent(state.experiment)}/bridge`,
      {
        method: "POST",
        mode: "cors",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: state.token,
          purchase_flow_id: purchaseFlowId,
        }),
      },
    );
    if (bridgeResponse.ok) {
      await session.removeItem(SESSION_KEY);
      return true;
    }
    // 4xx means the token is invalid, expired, replayed, or mismatched. Do not retry it.
    if (bridgeResponse.status >= 400 && bridgeResponse.status < 500) {
      await session.removeItem(SESSION_KEY);
      return true;
    }
  } catch (_) {
    // Network/runtime failures keep the token in session for the next page/navigation retry.
  }
  return false;
}

async function bindWithBoundedRetry(attempt = 0) {
  const done = await bindCurrentFlow();
  if (done || attempt >= MAX_ATTEMPTS - 1) return;
  setTimeout(() => bindWithBoundedRetry(attempt + 1), RETRY_MS);
}

$w.onReady(async function () {
  await captureBridgeState();
  await bindWithBoundedRetry();
});
