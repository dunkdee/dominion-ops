import http from "node:http";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const operatorToken = "smoke-operator-token";
const accessKey = "smoke-access-key";
const sessionSecret = "smoke-session-secret-that-is-long-enough-123456789";
let bindApprovals = 0;
let queued = 0;

const mock = http.createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString();
  const json = (code, payload) => {
    res.writeHead(code, { "content-type": "application/json" });
    res.end(JSON.stringify(payload));
  };

  if (req.headers["x-operator-token"] !== operatorToken) return json(401, { detail: "bad token" });
  if (req.url === "/health") return json(200, { status: "ok", service: "dominion-publisher", meta_app_configured: true, meta_bound_counts: { facebook: 1, instagram: 1 } });
  if (req.url === "/accounts") return json(200, { app_configured: true, bound_accounts: { facebook: [{ account_id: "page-1", label: "Dominion" }], instagram: [{ account_id: "ig-1", label: "Dominion" }] } });
  if (req.url === "/oauth/meta/candidates") return json(200, { candidates: [{ page_id: "page-1", page_name: "Dominion", instagram_account_id: "ig-1", tasks: ["CREATE_CONTENT"] }] });
  if (req.url === "/oauth/meta/start" && req.method === "POST") return json(200, { authorization_url: "https://example.com/oauth", scopes: [], expires_in_seconds: 600 });
  if (req.url === "/oauth/meta/bind" && req.method === "POST") {
    if (req.headers["x-human-approval"] !== "APPROVED") return json(403, { detail: "approval required" });
    bindApprovals++;
    return json(200, { status: "BOUND", binding: { facebook: { account_id: "page-1" } } });
  }
  if (req.url === "/jobs/queue" && req.method === "POST") {
    const payload = JSON.parse(body);
    if (!payload.approved_by || !payload.approved_at || Number.isNaN(Date.parse(payload.approved_at))) {
      return json(422, { detail: "explicit approval is required before queueing" });
    }
    queued++;
    return json(200, { receipt_id: "r1", idempotency_key: "idem-1", status: "QUEUED", destination_url: payload.destination_url });
  }
  if (req.url === "/receipts/idem-1") return json(200, { idempotency_key: "idem-1", receipts: [{ status: "QUEUED" }] });
  return json(404, { detail: "not found" });
});

await new Promise((resolve) => mock.listen(5112, "127.0.0.1", resolve));
const app = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-p", "3100"], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    DOMINION_FRONTEND_ACCESS_KEY: accessKey,
    DOMINION_FRONTEND_SESSION_SECRET: sessionSecret,
    DOMINION_PUBLISHER_BASE_URL: "http://127.0.0.1:5112",
    DOMINION_PUBLISHER_OPERATOR_TOKEN: operatorToken,
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let logs = "";
app.stdout.on("data", (data) => logs += data);
app.stderr.on("data", (data) => logs += data);
const origin = "http://127.0.0.1:3100";

try {
  for (let i = 0; i < 60; i++) {
    try {
      const response = await fetch(`${origin}/login`);
      if (response.ok) break;
    } catch {}
    await sleep(250);
    if (i === 59) throw new Error(`app failed to start\n${logs}`);
  }

  const bad = await fetch(`${origin}/api/session/login`, {
    method: "POST",
    headers: { "content-type": "application/json", origin },
    body: JSON.stringify({ accessKey: "wrong" }),
  });
  if (bad.status !== 401) throw new Error("bad login did not fail closed");

  const login = await fetch(`${origin}/api/session/login`, {
    method: "POST",
    headers: { "content-type": "application/json", origin },
    body: JSON.stringify({ accessKey }),
  });
  if (!login.ok) throw new Error("login failed");
  const cookie = (login.headers.get("set-cookie") || "").split(";")[0];
  if (!cookie.includes("dominion_session=")) throw new Error("secure session cookie missing");
  const auth = { cookie };

  const status = await fetch(`${origin}/api/publisher/status`, { headers: auth });
  const statusText = await status.text();
  if (!status.ok || statusText.includes(operatorToken)) throw new Error("status proxy failed or leaked operator token");

  const rejected = await fetch(`${origin}/api/publisher/meta/bind`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json", origin },
    body: JSON.stringify({ page_id: "page-1", approved_by: "smoke" }),
  });
  if (rejected.status !== 422 || bindApprovals !== 0) throw new Error("binding did not fail closed without explicit approval");

  const bound = await fetch(`${origin}/api/publisher/meta/bind`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json", origin },
    body: JSON.stringify({ page_id: "page-1", approved_by: "smoke", human_approval: "APPROVED" }),
  });
  if (!bound.ok || bindApprovals !== 1) throw new Error("approved binding failed");

  const queueRejected = await fetch(`${origin}/api/publisher/jobs/queue`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json", origin },
    body: JSON.stringify({ campaign_id: "smoke", platform: "facebook", account_id: "page-1", caption: "Smoke", destination_url: "https://example.com", assets: [] }),
  });
  if (queueRejected.status !== 422 || queued !== 0) throw new Error("queue did not fail closed without explicit approval");

  const queuedResp = await fetch(`${origin}/api/publisher/jobs/queue`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json", origin },
    body: JSON.stringify({
      campaign_id: "smoke",
      platform: "facebook",
      account_id: "page-1",
      caption: "Smoke",
      destination_url: "https://example.com",
      assets: [],
      approved_by: "smoke",
      human_approval: "APPROVED",
    }),
  });
  if (!queuedResp.ok || queued !== 1) throw new Error("approved queue path failed");
  const queuedBody = await queuedResp.json();

  const receipt = await fetch(`${origin}/api/publisher/receipts/${queuedBody.idempotency_key}`, { headers: auth });
  if (!receipt.ok) throw new Error("receipt path failed");

  const publishProbe = await fetch(`${origin}/api/publisher/jobs/publish`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json", origin },
    body: "{}",
  });
  if (publishProbe.status !== 404) throw new Error("frontend unexpectedly exposes live publish endpoint");

  console.log("SMOKE PASS: auth, secret isolation, explicit bind approval, explicit queue approval, queue, receipt, live-publish hold");
} finally {
  app.kill("SIGTERM");
  mock.close();
}
