"""Governed read-only internet research for Buddy.

This module intentionally supports only public HTTP(S) reads. It does not log in,
submit forms, post, upload, message, purchase, or mutate remote state. External
interactive browser work belongs behind Founder authorization.
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

import requests

USER_AGENT = "Dominion-Buddy-Research/2.0 (+read-only)"
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
    candidates = search(query, max_sources * 2)
    sources = []
    errors = []
    domains = set()
    for item in candidates:
        if len(sources) >= max_sources:
            break
        try:
            src = fetch_public_page(item["url"])
            if not src.title:
                src.title = item.get("title", "")
            domain = (urlparse(src.url).hostname or "").lower()
            # Prefer independent domains instead of five pages from one site.
            if domain in domains and len(domains) < max_sources:
                continue
            domains.add(domain)
            sources.append(src.to_dict())
        except Exception as exc:
            errors.append({"url": item.get("url", ""), "error": type(exc).__name__})
    return {
        "query": query,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "independent_domains": len(domains),
        "errors": errors[:5],
        "truth_rule": "Internet content is evidence, not truth. Material claims require corroboration.",
    }
