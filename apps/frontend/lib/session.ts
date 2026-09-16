import crypto from "node:crypto";
import type { IncomingMessage } from "node:http";
import type { NextApiRequest, NextApiResponse } from "next";

const COOKIE_NAME = "dominion_session";
const SESSION_SECONDS = 8 * 60 * 60;

function env(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

function equalText(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

export function verifyAccessKey(candidate: string): boolean {
  try { return equalText(candidate, env("DOMINION_FRONTEND_ACCESS_KEY")); }
  catch { return false; }
}

function sign(payload: string): string {
  return crypto.createHmac("sha256", env("DOMINION_FRONTEND_SESSION_SECRET")).update(payload).digest("base64url");
}

export function makeSessionCookie(): string {
  const expires = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  const nonce = crypto.randomBytes(18).toString("base64url");
  const payload = `v1.${expires}.${nonce}`;
  return `${COOKIE_NAME}=${payload}.${sign(payload)}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_SECONDS}`;
}

export function clearSessionCookie(): string {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
}

function cookieValue(req: IncomingMessage): string | null {
  const raw = req.headers.cookie || "";
  for (const part of raw.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === COOKIE_NAME) return rest.join("=");
  }
  return null;
}

export function hasValidSession(req: IncomingMessage): boolean {
  const value = cookieValue(req);
  if (!value) return false;
  const parts = value.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") return false;
  const [version, expiresRaw, nonce, signature] = parts;
  const expires = Number(expiresRaw);
  if (!Number.isFinite(expires) || expires <= Math.floor(Date.now() / 1000)) return false;
  const payload = `${version}.${expiresRaw}.${nonce}`;
  try { return equalText(signature, sign(payload)); }
  catch { return false; }
}

export function requireApiSession(req: NextApiRequest, res: NextApiResponse): boolean {
  if (!hasValidSession(req)) {
    res.status(401).json({ error: "authentication_required" });
    return false;
  }
  return true;
}

function effectiveHost(req: NextApiRequest): string {
  const forwarded = req.headers["x-forwarded-host"];
  const host = Array.isArray(forwarded) ? forwarded[0] : forwarded || req.headers.host || "";
  return host.split(",")[0].trim().toLowerCase();
}

export function requireSameOrigin(req: NextApiRequest, res: NextApiResponse): boolean {
  const origin = req.headers.origin;
  if (!origin) {
    res.status(403).json({ error: "origin_required" });
    return false;
  }
  try {
    if (new URL(origin).host.toLowerCase() !== effectiveHost(req)) {
      res.status(403).json({ error: "origin_rejected" });
      return false;
    }
  } catch {
    res.status(403).json({ error: "origin_rejected" });
    return false;
  }
  return true;
}
