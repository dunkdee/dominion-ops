import socket

import pytest

from buddy_core.core import web_research


def _addr(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


def test_rejects_localhost(monkeypatch):
    with pytest.raises(ValueError):
        web_research._public_host("http://localhost/admin")


def test_rejects_private_resolved_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("10.0.0.5"))
    with pytest.raises(ValueError):
        web_research._public_host("https://internal.example")


def test_rejects_link_local_cloud_metadata(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("169.254.169.254"))
    with pytest.raises(ValueError):
        web_research._public_host("http://metadata.example/latest")


def test_rejects_credentials_in_url(monkeypatch):
    with pytest.raises(ValueError):
        web_research._public_host("https://user:pass@example.com/")


def test_allows_public_https(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("93.184.216.34"))
    web_research._public_host("https://example.com/research")


def test_search_transport_is_get_only_by_construction():
    # The research module exports no submit/post helper. Remote interaction is
    # deliberately limited to search/fetch reads; interactive browser work is
    # represented as a separate external capability in the operator registry.
    assert hasattr(web_research, "search")
    assert hasattr(web_research, "fetch_public_page")
    assert not hasattr(web_research, "post")
    assert not hasattr(web_research, "submit")
