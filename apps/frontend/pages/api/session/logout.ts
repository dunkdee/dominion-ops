import type { NextApiRequest, NextApiResponse } from "next";
import { clearSessionCookie, requireSameOrigin } from "../../../lib/session";
export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireSameOrigin(req, res)) return;
  res.setHeader("Set-Cookie", clearSessionCookie());
  return res.status(200).json({ status: "signed_out" });
}
