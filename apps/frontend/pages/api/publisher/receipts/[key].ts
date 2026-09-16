import type { NextApiRequest, NextApiResponse } from "next";
import { apiError, publisherRequest } from "../../../../lib/publisher";
import { requireApiSession } from "../../../../lib/session";
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "GET") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireApiSession(req, res)) return;
  const key = typeof req.query.key === "string" ? req.query.key.trim() : "";
  if (!key || key.length > 200) return res.status(422).json({ error: "invalid_receipt_key" });
  try { return res.status(200).json(await publisherRequest(`/receipts/${encodeURIComponent(key)}`)); }
  catch (error) { const failure = apiError(error); return res.status(failure.status).json(failure.body); }
}
