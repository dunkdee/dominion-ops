"""Canonical URL attribution helper for Dominion revenue tracking.

Rules
-----
- Accepts both https:// scheme and schemeless Dominion URLs.
- Preserves scheme, host, path, all existing query params, fragments.
- Merges UTM params using urllib.parse — no raw string manipulation.
- Overwrites any existing UTM keys with caller's values (caller wins).
- Non-Dominion URLs returned unchanged.
- Non-URL strings returned unchanged.
- Empty / non-string input returned unchanged.
- utm_content accepted but callers must only supply it when a real variant exists.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DOMINION_HOSTS: frozenset[str] = frozenset(
    {
        "dominionhealing.org",
        "www.dominionhealing.org",
        "shop.dominionhealing.org",
        "store.dominionhealing.org",
        "ascendantdigital.store",
    }
)

# Pre-build alternation pattern longest-first to avoid partial matches
_HOSTS_ALT = "|".join(
    re.escape(h) for h in sorted(DOMINION_HOSTS, key=len, reverse=True)
)

# Matches either:
#   • a scheemed Dominion URL:   https://dominionhealing.org/path?q#frag
#   • a schemeless Dominion URL: dominionhealing.org/path  (not preceded by / @ or \w)
_URL_RE = re.compile(
    r"https?://(?:" + _HOSTS_ALT + r")(?:[/?#][^\s<>\"']*)?"
    r"|"
    r"(?<![/@\w])(?:" + _HOSTS_ALT + r")(?:[/?#][^\s<>\"']*)?"
)

_UTM_KEYS: frozenset[str] = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_content"}
)


def build_tracked_url(
    url: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    utm_content: str | None = None,
) -> str:
    """Return *url* with UTM params merged in.

    Returns *url* unchanged when:
    - it is empty or not a string,
    - it does not parse as an absolute URL (http/https),
    - its hostname is not in DOMINION_HOSTS.

    Schemeless Dominion URLs (e.g. ``dominionhealing.org/store``) are normalised
    to ``https://`` and returned with the scheme present.
    """
    if not url or not isinstance(url, str):
        return url

    raw = url.strip()

    # Normalise schemeless Dominion URLs
    if not raw.startswith(("http://", "https://")):
        matched = any(
            raw == h
            or raw.startswith(h + "/")
            or raw.startswith(h + "?")
            or raw.startswith(h + "#")
            for h in DOMINION_HOSTS
        )
        if not matched:
            return url
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)
    except Exception:
        return url

    if parsed.scheme not in ("http", "https"):
        return url

    hostname = (parsed.hostname or "").lower()
    if hostname not in DOMINION_HOSTS:
        return url

    # Preserve all existing params; overwrite UTM keys so caller wins
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in existing if k not in _UTM_KEYS]

    filtered.append(("utm_source", utm_source))
    filtered.append(("utm_medium", utm_medium))
    filtered.append(("utm_campaign", utm_campaign))
    if utm_content is not None:
        filtered.append(("utm_content", utm_content))

    new_query = urlencode(filtered)
    return urlunparse(parsed._replace(query=new_query))


def _cta_with_utm(cta: str, content_id: str) -> str:
    """Apply UTM params to any Dominion URL found in a plain-text CTA string.

    Non-URL CTAs pass through unchanged.
    External URLs pass through unchanged.
    utm_content is intentionally omitted — no variant exists at generation time.
    """

    def _replace(m: re.Match) -> str:
        return build_tracked_url(
            m.group(0),
            utm_source="social",
            utm_medium="organic",
            utm_campaign=content_id,
        )

    return _URL_RE.sub(_replace, cta)
