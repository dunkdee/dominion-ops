import type { NextApiRequest, NextApiResponse } from "next";
import { apiError, publisherRequest } from "../../../../lib/publisher";
import { requireApiSession, requireSameOrigin } from "../../../../lib/session";
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireApiSession(req, res) || !requireSameOrigin(req, res)) return;
  try { return res.status(200).json(await publisherRequest("/oauth/meta/start", { method: "POST", body: "{}" })); }
  catch (error) { const failure = apiError(error); return res.status(failure.status).json(failure.body); }
}
