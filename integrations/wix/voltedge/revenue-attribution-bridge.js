// VoltEdge embedded attribution bridge for the existing Dominion Attribution Wix app.
// Binds the one-time Dominion click token to Wix-native checkout/order identity.
// No product, price, cart, payment, refund, or buyer data is mutated.

import { analytics } from "@wix/site";

const BRIDGE_ORIGIN = "https://dominionhealing.org";
const SESSION_KEY = "dominion_revenue_bridge_v2";
const EXPERIMENT_RE = /^[A-Za-z0-9_-]{3,120}$/;
let bindingInFlight = false;

function captureState() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("dr_token") || "";
  const experiment = params.get("utm_campaign") || "";
  if (
    token.length >= 32 &&
    token.length <= 256 &&
    EXPERIMENT_RE.test(experiment)
  ) {
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token, experiment }),
    );
  }
}

function loadState() {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (
      typeof value?.token !== "string" ||
      value.token.length < 32 ||
      value.token.length > 256 ||
      !EXPERIMENT_RE.test(value?.experiment || "")
    ) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return value;
  } catch (_) {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

async function bindNativeIdentity({ checkoutId = "", orderId = "" } = {}) {
  if (bindingInFlight) return;
  const state = loadState();
  if (!state) return;

  const checkout = typeof checkoutId === "string" ? checkoutId : "";
  const order = typeof orderId === "string" ? orderId : "";
  if (!checkout && !order) return;

  const payload = { token: state.token };
  if (checkout) payload.checkout_id = checkout;
  if (order) payload.order_id = order;

  bindingInFlight = true;
  try {
    const response = await fetch(
      `${BRIDGE_ORIGIN}/r/${encodeURIComponent(state.experiment)}/bridge`,
      {
        method: "POST",
        mode: "cors",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );

    if (response.ok || (response.status >= 400 && response.status < 500)) {
      sessionStorage.removeItem(SESSION_KEY);
    }
  } catch (_) {
    // Preserve the token for a later Wix event if the network path is transiently unavailable.
  } finally {
    bindingInFlight = false;
  }
}

captureState();

analytics.registerEventListener((eventName, eventData) => {
  if (eventName === "InitiateCheckout") {
    void bindNativeIdentity({ checkoutId: eventData?.checkoutId || "" });
    return;
  }
  if (eventName === "Purchase") {
    void bindNativeIdentity({ orderId: eventData?.orderId || "" });
  }
});
