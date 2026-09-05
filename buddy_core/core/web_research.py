"""Governed read-only internet research for Buddy.

This module supports only public-web retrieval. It does not log in, submit forms,
post, upload, message, purchase, or mutate remote target state. Some read-only
provider APIs use POST as their transport; that does not authorize browser or
external side effects. External interactive work remains behind Founder
authorization.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import json
import os
import requests

try:
    from . import scrapegraph_provider
except ImportError:  # standalone core runtime
    import scrapegraph_provider

USER_AGENT = "Dominion-Buddy-Research/2.1 (+read-only)"
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 4


@dataclass
class Source:
    url: str
    title: str = ""
    excerpt: str = ""
    fetched_at: str = ""
    status: int = 0
    quality: float = 0.0

    def to_dict(self):
        return asdict(self)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.title = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        self.text.append(clean)
        if self._in_title:
            self.title.append(clean)


class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._href = attrs.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            href = self._href
            if "uddg=" in href:
                try:
                    href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
                except Exception:
                    pass
            title = html.unescape(" ".join(self._text)).strip()
            if href.startswith("http") and title:
                self.results.append((href, title))
            self._href = None
            self._text = []


def _public_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("research permits only http/https")
    if parsed.username or parsed.password:
        raise ValueError("credentials in URLs are forbidden")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("local/private hosts are forbidden")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("host resolution failed") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("private/reserved/link-local targets are forbidden")


def _quality(url: str) -> float:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    score = 0.45
    if p.scheme == "https":
        score += 0.1
    if host.endswith((".gov", ".edu")):
        score += 0.25
    if any(x in host for x in ("reuters.com", "apnews.com", "sec.gov", "nih.gov", "who.int")):
        score += 0.15
    return round(min(score, 1.0), 2)


def _get(url: str, timeout: int = 12) -> requests.Response:
    current = url
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5"}
    for _ in range(MAX_REDIRECTS + 1):
        _public_host(current)
        response = session.get(current, headers=headers, timeout=timeout, allow_redirects=False, stream=True)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("redirect without location")
            current = urljoin(current, location)
            continue
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_BYTES:
                response.close()
                raise ValueError("response exceeds research byte limit")
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response._content_consumed = True
        response.url = current
        return response
    raise ValueError("too many redirects")


def search(query: str, limit: int = 6) -> list[dict]:
    """Search the public web using DuckDuckGo's HTML result page (GET only)."""
    if not query or not query.strip():
        return []
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query.strip())
    response = _get(url)
    response.raise_for_status()
    parser = _DDGParser()
    parser.feed(response.text)
    out = []
    seen = set()
    for href, title in parser.results:
        if href in seen:
            continue
        try:
            _public_host(href)
        except ValueError:
            continue
        seen.add(href)
        out.append({"url": href, "title": title})
        if len(out) >= max(1, min(limit, 10)):
            break
    return out


def _serpapi_search(query: str, limit: int = 6) -> list:
    """SerpAPI is discovery only; its credential never enters generic fetches."""
    key = os.environ.get("SERPAPI_KEY", "")
    if not key or not query.strip():
        return []

    endpoint = "https://serpapi.com/search.json"

    try:
        _public_host(endpoint)
        response = requests.get(
            endpoint,
            params={
                "q": query.strip(),
                "api_key": key,
                "engine": "google",
                "num": max(1, min(limit * 2, 20)),
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            timeout=10,
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            response.close()
            return []
        response.raise_for_status()

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_BYTES:
                response.close()
                return []
            chunks.append(chunk)

        body = b"".join(chunks)
        data = json.loads(body.decode("utf-8", errors="replace"))
        discovered = []
        for item in data.get("organic_results", []):
            candidate_url = item.get("link", "")
            if not isinstance(candidate_url, str):
                continue
            if not candidate_url.startswith(("http://", "https://")):
                continue
            try:
                _public_host(candidate_url)
            except ValueError:
                continue
            discovered.append({
                "url": candidate_url,
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            })
            if len(discovered) >= limit:
                break
        return discovered
    except Exception:
        return []


def _ddg_json_search(query: str, limit: int = 6) -> list:
    """DuckDuckGo Instant Answer JSON fallback; metadata only, never HEALTHY."""
    try:
        url = (
            "https://api.duckduckgo.com/?q="
            + quote_plus(query.strip())
            + "&format=json&no_html=1&skip_disambig=1"
        )
        resp = _get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        out = []
        for item in data.get("RelatedTopics", []):
            href = item.get("FirstURL", "")
            text = item.get("Text", "")
            if not (href and href.startswith("http")):
                continue
            try:
                _public_host(href)
                out.append({"url": href, "title": text[:200]})
                if len(out) >= limit:
                    break
            except ValueError:
                continue
        return out
    except Exception:
        return []


def fetch_public_page(url: str) -> Source:
    response = _get(url)
    content_type = response.headers.get("content-type", "").lower()
    if "text" not in content_type and "json" not in content_type and "html" not in content_type:
        raise ValueError("research fetch accepts text/html/json only")
    if "html" in content_type:
        parser = _TextParser()
        parser.feed(response.text)
        text = " ".join(parser.text)
        title = " ".join(parser.title)
    else:
        text = response.text
        title = ""
    text = re.sub(r"\s+", " ", text).strip()[:12000]
    return Source(
        url=response.url,
        title=title[:300],
        excerpt=text,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        status=response.status_code,
        quality=_quality(response.url),
    )


def research(query: str, max_sources: int = 5) -> dict:
    """Search with governed provider fallback.

    Provider order:
      A. ScrapeGraphAI V2 search/extraction when SGAI_API_KEY is configured.
      B. SerpAPI discovery followed by Dominion's governed page fetch.
      C. DuckDuckGo HTML discovery followed by governed page fetch.
      D. DuckDuckGo Instant Answer JSON metadata only (DEGRADED).
      E. UNAVAILABLE.

    backend_status values:
      HEALTHY     - at least one public source has retrieved page content
      DEGRADED    - only DDG Instant Answer JSON metadata; no page content
      UNAVAILABLE - no usable sources from any provider
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    errors: list = []
    sources: list = []
    domains: set = set()
    backend_status = "UNAVAILABLE"

    # Provider A: ScrapeGraphAI V2. The provider performs read-only retrieval and
    # returns page content plus source URLs. Every returned URL is independently
    # checked against Dominion's public-host boundary before it becomes evidence.
    if os.environ.get("SGAI_API_KEY", ""):
        try:
            sgai = scrapegraph_provider.search(query, max_sources * 2)
        except Exception as exc:
            sgai = {
                "status": "ERROR",
                "reason": type(exc).__name__,
            }
        if sgai.get("status") == "HEALTHY":
            for item in sgai.get("results", []):
                if len(sources) >= max_sources:
                    break
                item_url = item.get("url", "")
                content = item.get("content", "")
                if not isinstance(item_url, str) or not isinstance(content, str) or not content.strip():
                    continue
                try:
                    _public_host(item_url)
                except ValueError:
                    errors.append({"provider": "scrapegraphai", "url": item_url, "error": "PublicHostRejected"})
                    continue
                domain = (urlparse(item_url).hostname or "").lower()
                if domain in domains and len(domains) < max_sources:
                    continue
                domains.add(domain)
                sources.append({
                    "url": item_url,
                    "title": str(item.get("title", "") or "")[:300],
                    "excerpt": content.strip()[:12000],
                    "fetched_at": item.get("fetched_at") or sgai.get("observed_at") or fetched_at,
                    "status": 0,
                    "quality": _quality(item_url),
                    "provider": "scrapegraphai",
                    "content_sha256": item.get("content_sha256"),
                })
            if sources:
                backend_status = "HEALTHY"
        elif sgai.get("status") == "ERROR":
            errors.append({
                "provider": "scrapegraphai",
                "error": str(sgai.get("reason") or "PROVIDER_ERROR")[:100],
            })

    # Provider B: SerpAPI discovery -> governed page fetch.
    serpapi_candidates: list = []
    if backend_status != "HEALTHY" and os.environ.get("SERPAPI_KEY", ""):
        serpapi_candidates = _serpapi_search(query, max_sources * 2)

    if backend_status != "HEALTHY" and serpapi_candidates:
        for item in serpapi_candidates:
            if len(sources) >= max_sources:
                break
            item_url = item.get("url", "")
            try:
                src = fetch_public_page(item_url)
                domain = (urlparse(src.url).hostname or "").lower()
                if domain in domains and len(domains) < max_sources:
                    continue
                domains.add(domain)
                sources.append(src.to_dict())
                backend_status = "HEALTHY"
            except Exception as exc:
                errors.append({"url": item_url, "error": type(exc).__name__})

    # Provider C: DDG HTML discovery -> governed page fetch.
    if backend_status != "HEALTHY":
        ddg_candidates: list = []
        try:
            ddg_candidates = search(query, max_sources * 2)
        except Exception as exc:
            errors.append({"provider": "ddg_html", "error": type(exc).__name__})

        for item in ddg_candidates:
            if len(sources) >= max_sources:
                break
            item_url = item.get("url", "")
            try:
                src = fetch_public_page(item_url)
                if not src.title:
                    src.title = item.get("title", "")
                domain = (urlparse(src.url).hostname or "").lower()
                if domain in domains and len(domains) < max_sources:
                    continue
                domains.add(domain)
                sources.append(src.to_dict())
                backend_status = "HEALTHY"
            except Exception as exc:
                errors.append({"url": item_url, "error": type(exc).__name__})

    # Provider D: DDG JSON — DEGRADED only, no page fetch, never HEALTHY.
    if backend_status == "UNAVAILABLE":
        ddg_json = _ddg_json_search(query, max_sources * 2)
        if ddg_json:
            backend_status = "DEGRADED"
            for item in ddg_json:
                if len(sources) >= max_sources:
                    break
                url = item.get("url", "")
                domain = (urlparse(url).hostname or "").lower()
                if domain in domains:
                    continue
                domains.add(domain)
                sources.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "excerpt": "",
                    "fetched_at": fetched_at,
                    "status": 0,
                    "quality": 0.0,
                })

    return {
        "query": query,
        "fetched_at": fetched_at,
        "sources": sources,
        "independent_domains": len(domains),
        "errors": errors[:5],
        "truth_rule": "Internet content is evidence, not truth. Material claims require corroboration.",
        "backend_status": backend_status,
    }
