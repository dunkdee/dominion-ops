import type { NextApiRequest, NextApiResponse } from "next";
import { apiError, publisherRequest } from "../../../../lib/publisher";
import { requireApiSession, requireSameOrigin } from "../../../../lib/session";
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireApiSession(req, res) || !requireSameOrigin(req, res)) return;
  const pageId = typeof req.body?.page_id === "string" ? req.body.page_id.trim() : "";
  const approvedBy = typeof req.body?.approved_by === "string" ? req.body.approved_by.trim() : "";
  if (!pageId || !approvedBy || req.body?.human_approval !== "APPROVED") return res.status(422).json({ error: "explicit_human_approval_required" });
  try {
    return res.status(200).json(await publisherRequest("/oauth/meta/bind", { method: "POST", headers: { "X-Human-Approval": "APPROVED" }, body: JSON.stringify({ page_id: pageId, approved_by: approvedBy }) }));
  } catch (error) { const failure = apiError(error); return res.status(failure.status).json(failure.body); }
}
