import type { NextApiRequest, NextApiResponse } from "next";
import { makeSessionCookie, requireSameOrigin, verifyAccessKey } from "../../../lib/session";

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).json({ error: "method_not_allowed" });
  if (!requireSameOrigin(req, res)) return;
  const accessKey = typeof req.body?.accessKey === "string" ? req.body.accessKey : "";
  if (!verifyAccessKey(accessKey)) return res.status(401).json({ error: "invalid_credentials" });
  try {
    res.setHeader("Set-Cookie", makeSessionCookie());
    return res.status(200).json({ status: "authenticated" });
  } catch { return res.status(503).json({ error: "session_not_configured" }); }
}
