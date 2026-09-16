import type { NextApiRequest, NextApiResponse } from "next";
import { apiError, publisherRequest } from "../../../../lib/publisher";
import { requireApiSession, requireSameOrigin } from "../../../../lib/session";

const SHA256 = /^[a-f0-9]{64}$/i;
const PLATFORMS = new Set(["facebook", "instagram"]);

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireApiSession(req, res) || !requireSameOrigin(req, res)) return;

  const body = req.body || {};
  for (const key of ["campaign_id", "platform", "account_id", "caption", "destination_url"]) {
    if (typeof body[key] !== "string" || !body[key].trim()) {
      return res.status(422).json({ error: `missing_${key}` });
    }
  }
  if (!PLATFORMS.has(body.platform)) return res.status(422).json({ error: "unsupported_platform" });
  if (typeof body.approved_by !== "string" || !body.approved_by.trim() || body.human_approval !== "APPROVED") {
    return res.status(422).json({ error: "explicit_queue_approval_required" });
  }
  try {
    const destination = new URL(body.destination_url);
    if (destination.protocol !== "http:" && destination.protocol !== "https:") throw new Error("bad protocol");
  } catch {
    return res.status(422).json({ error: "invalid_destination_url" });
  }

  const assets = Array.isArray(body.assets) ? body.assets : [];
  if (assets.length > 8) return res.status(422).json({ error: "too_many_assets" });
  for (const asset of assets) {
    if (!asset || typeof asset.uri !== "string" || typeof asset.sha256 !== "string" || typeof asset.provenance !== "string") {
      return res.status(422).json({ error: "invalid_asset" });
    }
    if (!SHA256.test(asset.sha256)) return res.status(422).json({ error: "invalid_asset_sha256" });
  }

  const payload = {
    campaign_id: body.campaign_id.trim(),
    platform: body.platform,
    account_id: body.account_id.trim(),
    caption: body.caption,
    destination_url: body.destination_url.trim(),
    assets,
    approved_by: body.approved_by.trim(),
    approved_at: new Date().toISOString(),
    scheduled_at: typeof body.scheduled_at === "string" && body.scheduled_at ? body.scheduled_at : null,
    metadata: { source: "dominion-frontend", governance: "RESTRICTED_HOLD" },
  };

  try {
    return res.status(200).json(await publisherRequest("/jobs/queue", { method: "POST", body: JSON.stringify(payload) }));
  } catch (error) {
    const failure = apiError(error);
    return res.status(failure.status).json(failure.body);
  }
}
