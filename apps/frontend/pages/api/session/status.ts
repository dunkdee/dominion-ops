import type { NextApiRequest, NextApiResponse } from "next";
import { hasValidSession } from "../../../lib/session";
export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "GET") return res.status(405).json({ error: "method_not_allowed" });
  return res.status(200).json({ authenticated: hasValidSession(req) });
}
