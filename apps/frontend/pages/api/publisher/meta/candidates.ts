import type { NextApiRequest, NextApiResponse } from "next";
import { apiError, publisherRequest } from "../../../../lib/publisher";
import { requireApiSession } from "../../../../lib/session";
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "GET") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireApiSession(req, res)) return;
  try { return res.status(200).json(await publisherRequest("/oauth/meta/candidates")); }
  catch (error) { const failure = apiError(error); return res.status(failure.status).json(failure.body); }
}
