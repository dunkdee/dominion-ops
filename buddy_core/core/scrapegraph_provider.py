"""Governed optional ScrapeGraphAI V2 adapter.

This module is a provider boundary, not an authority boundary. It may retrieve
public-web evidence through ScrapeGraphAI, but it cannot publish, submit forms,
log in, spend money, change credentials, or mutate target sites.

Security invariants:
- SGAI_API_KEY is read from the environment only and is never returned;
- credential-bearing requests never follow redirects;
- the provider endpoint must resolve to globally routable HTTPS addresses;
- extract targets must be public HTTP(S) URLs (no private/link-local targets);
- response bodies are bounded before JSON parsing;
- provider errors are reduced to stable codes rather than raw response bodies;
- returned content is untrusted evidence and is SHA-256 fingerprinted.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_API_URL = "https://v2-api.scrapegraphai.com/api"
MAX_RESPONSE_BYTES = 1_000_000
MAX_RESULT_CHARS = 12_000
MAX_QUERY_CHARS = 4_000
MAX_PROMPT_CHARS = 8_000
MAX_SCHEMA_BYTES = 32_000


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _public_network_url(url: str, *, require_https: bool = False) -> str:
    parsed = urlparse(url)
    allowed = {"https"} if require_https else {"http", "https"}
    if parsed.scheme not in allowed:
        raise ValueError("unsupported_scheme")
    if parsed.username or parsed.password:
        raise ValueError("credentials_in_url_forbidden")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("private_host_forbidden")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("host_resolution_failed") from exc
    if not infos:
        raise ValueError("host_resolution_failed")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError("private_address_forbidden")
    return url


def _api_url(path: str) -> str:
    base = (os.environ.get("SGAI_API_URL") or DEFAULT_API_URL).strip().rstrip("/")
    endpoint = f"{base}/{path.lstrip('/')}"
    return _public_network_url(endpoint, require_https=True)


def _timeout() -> int:
    raw = (os.environ.get("SGAI_TIMEOUT") or "30").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 30
    return max(5, min(value, 60))


def _read_json_response(response: requests.Response) -> dict:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65_536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            response.close()
            raise ValueError("response_too_large")
        chunks.append(chunk)
    payload = b"".join(chunks)
    parsed = json.loads(payload.decode("utf-8", errors="strict"))
    if not isinstance(parsed, dict):
        raise ValueError("response_not_object")
    return parsed


def _request(path: str, payload: dict) -> dict:
    api_key = (os.environ.get("SGAI_API_KEY") or "").strip()
    if not api_key:
        return {
            "status": "UNAVAILABLE",
            "provider": "scrapegraphai",
            "reason": "MISSING_API_KEY",
        }

    try:
        endpoint = _api_url(path)
        response = requests.post(
            endpoint,
            json=payload,
            headers={
                "SGAI-APIKEY": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Dominion-Buddy-Research/2.1 (+read-only-provider)",
            },
            timeout=_timeout(),
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            response.close()
            return {
                "status": "ERROR",
                "provider": "scrapegraphai",
                "reason": "CREDENTIAL_REDIRECT_BLOCKED",
            }
        if not (200 <= int(response.status_code) < 300):
            code = int(response.status_code)
            response.close()
            return {
                "status": "ERROR",
                "provider": "scrapegraphai",
                "reason": f"PROVIDER_HTTP_{code}",
            }
        data = _read_json_response(response)
    except requests.Timeout:
        return {
            "status": "ERROR",
            "provider": "scrapegraphai",
            "reason": "PROVIDER_TIMEOUT",
        }
    except requests.RequestException:
        return {
            "status": "ERROR",
            "provider": "scrapegraphai",
            "reason": "PROVIDER_NETWORK_ERROR",
        }
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {
            "status": "ERROR",
            "provider": "scrapegraphai",
            "reason": "PROVIDER_RESPONSE_REJECTED",
        }

    return {
        "status": "HEALTHY",
        "provider": "scrapegraphai",
        "observed_at": _utc(),
        "data": data,
        "response_sha256": _sha256_json(data),
    }


def search(query: str, limit: int = 6) -> dict:
    """Search public web through ScrapeGraphAI V2 and return bounded evidence.

    Official V2 search uses POST /search for a read-only retrieval operation.
    This function does not expose monitor/crawl job creation or browser actions.
    """
    query = (query or "").strip()
    if not query:
        return {"status": "UNAVAILABLE", "provider": "scrapegraphai", "reason": "EMPTY_QUERY"}
    if len(query) > MAX_QUERY_CHARS:
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": "QUERY_TOO_LARGE"}

    requested = max(3, min(int(limit or 6), 20))
    response = _request(
        "/search",
        {
            "query": query,
            "numResults": requested,
            "format": "markdown",
            "mode": "reader",
        },
    )
    if response.get("status") != "HEALTHY":
        return response

    raw = response.get("data") or {}
    rows = raw.get("results")
    if not isinstance(rows, list):
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": "RESULTS_MISSING"}

    observed_at = response.get("observed_at") or _utc()
    results: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        title = row.get("title")
        content = row.get("content")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        bounded = content.strip()[:MAX_RESULT_CHARS]
        results.append(
            {
                "url": url,
                "title": title if isinstance(title, str) else "",
                "content": bounded,
                "fetched_at": observed_at,
                "content_sha256": hashlib.sha256(bounded.encode("utf-8")).hexdigest(),
            }
        )
        if len(results) >= requested:
            break

    if not results:
        return {"status": "UNAVAILABLE", "provider": "scrapegraphai", "reason": "NO_USABLE_RESULTS"}

    return {
        "status": "HEALTHY",
        "provider": "scrapegraphai",
        "provider_api": "v2/search",
        "observed_at": observed_at,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "response_sha256": response.get("response_sha256"),
        "results": results,
    }


def extract(url: str, prompt: str, *, schema: dict | None = None) -> dict:
    """Perform governed structured extraction from one public URL.

    The extracted object remains untrusted evidence. This helper is deliberately
    not wired to external browser automation, monitor creation, or target-site
    mutation.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": "EMPTY_PROMPT"}
    if len(prompt) > MAX_PROMPT_CHARS:
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": "PROMPT_TOO_LARGE"}
    try:
        target = _public_network_url((url or "").strip(), require_https=False)
    except ValueError as exc:
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": str(exc)}

    payload: dict[str, Any] = {"url": target, "prompt": prompt}
    if schema is not None:
        try:
            encoded_schema = json.dumps(schema, ensure_ascii=True, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return {"status": "ERROR", "provider": "scrapegraphai", "reason": "INVALID_SCHEMA"}
        if len(encoded_schema) > MAX_SCHEMA_BYTES:
            return {"status": "ERROR", "provider": "scrapegraphai", "reason": "SCHEMA_TOO_LARGE"}
        payload["schema"] = schema

    response = _request("/extract", payload)
    if response.get("status") != "HEALTHY":
        return response

    raw = response.get("data") or {}
    extracted: Any = raw.get("json")
    if extracted is None:
        extracted = raw.get("raw")
    if extracted is None:
        return {"status": "UNAVAILABLE", "provider": "scrapegraphai", "reason": "NO_EXTRACTED_DATA"}

    try:
        output_sha = _sha256_json(extracted)
    except (TypeError, ValueError, OverflowError):
        return {"status": "ERROR", "provider": "scrapegraphai", "reason": "EXTRACT_NOT_JSON_SAFE"}

    return {
        "status": "HEALTHY",
        "provider": "scrapegraphai",
        "provider_api": "v2/extract",
        "observed_at": response.get("observed_at") or _utc(),
        "url": target,
        "input_sha256": _sha256_json({"url": target, "prompt": prompt, "schema": schema}),
        "output_sha256": output_sha,
        "response_sha256": response.get("response_sha256"),
        "data": extracted,
        "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
    }
