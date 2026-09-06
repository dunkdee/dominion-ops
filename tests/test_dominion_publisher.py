from __future__ import annotations

from dataclasses import replace

import pytest

from apps.dominion_publisher.adapters.meta import MetaFacebookAdapter, MetaInstagramAdapter
from apps.dominion_publisher.core import PublisherCore, PublisherStore
from apps.dominion_publisher.models import Asset, PublishJob, PublishStatus, utc_now


class FakeAdapter:
    platform = "instagram"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def validate_credentials(self, account_id: str) -> None:
        assert account_id == "acct-1"

    def validate_job(self, job: PublishJob) -> None:
        assert job.caption

    def publish(self, job: PublishJob) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return "provider-post-1"


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._data


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url: str, data: dict, timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return self.responses.pop(0)


def approved_job(platform: str = "instagram") -> PublishJob:
    return PublishJob(
        campaign_id="voltedge-launch-001",
        platform=platform,
        account_id="acct-1",
        caption="Reliable everyday tech.",
        destination_url="https://www.voltedgegoods.com/product/demo?ref=existing",
        assets=[
            Asset(
                uri="https://cdn.example.com/product.jpg",
                sha256="a" * 64,
                provenance="owned-product-catalog",
                media_type="image/jpeg",
            )
        ],
        approved_by="founder",
        approved_at=utc_now(),
    )


def test_queue_blocks_unapproved_job(tmp_path):
    core = PublisherCore(PublisherStore(tmp_path / "publisher.db"))
    job = replace(approved_job(), approved_by=None, approved_at=None)
    with pytest.raises(PermissionError):
        core.queue(job)


def test_asset_requires_provenance(tmp_path):
    core = PublisherCore(PublisherStore(tmp_path / "publisher.db"))
    job = approved_job()
    job.assets = [replace(job.assets[0], provenance="")]
    with pytest.raises(ValueError, match="provenance"):
        core.queue(job)


def test_attribution_preserves_existing_query_and_adds_campaign_tags():
    url = approved_job().attributed_url()
    assert "ref=existing" in url
    assert "utm_source=instagram" in url
    assert "utm_medium=social" in url
    assert "utm_campaign=voltedge-launch-001" in url


def test_publish_is_idempotent_and_records_receipts(tmp_path):
    store = PublisherStore(tmp_path / "publisher.db")
    adapter = FakeAdapter()
    core = PublisherCore(store, {"instagram": adapter})
    job = approved_job()

    first = core.publish(job)
    second = core.publish(job)

    assert first.status == PublishStatus.PUBLISHED
    assert first.provider_post_id == "provider-post-1"
    assert second.status == PublishStatus.PUBLISHED
    assert second.error == "duplicate suppressed"
    assert adapter.calls == 1
    receipts = store.receipts_for(job.idempotency_key)
    assert len(receipts) == 2


def test_provider_failure_is_fail_closed_and_receipted(tmp_path):
    store = PublisherStore(tmp_path / "publisher.db")
    core = PublisherCore(store, {"instagram": FakeAdapter(fail=True)})
    job = approved_job()

    receipt = core.publish(job)

    assert receipt.status == PublishStatus.FAILED
    assert "provider unavailable" in (receipt.error or "")
    assert store.status_for(job.idempotency_key) == PublishStatus.FAILED
    assert len(store.receipts_for(job.idempotency_key)) == 1


def test_missing_adapter_is_blocked(tmp_path):
    store = PublisherStore(tmp_path / "publisher.db")
    core = PublisherCore(store)
    job = approved_job("linkedin")

    receipt = core.publish(job)

    assert receipt.status == PublishStatus.BLOCKED
    assert receipt.error == "platform adapter is not registered"


def test_instagram_adapter_uses_container_then_publish():
    session = FakeSession([FakeResponse({"id": "container-1"}), FakeResponse({"id": "ig-post-1"})])
    adapter = MetaInstagramAdapter(access_token="secret", graph_version="v99.0", session=session)

    post_id = adapter.publish(approved_job("instagram"))

    assert post_id == "ig-post-1"
    assert session.calls[0]["url"].endswith("/acct-1/media")
    assert session.calls[1]["url"].endswith("/acct-1/media_publish")
    assert session.calls[0]["data"]["access_token"] == "secret"
    assert "utm_campaign=voltedge-launch-001" in session.calls[0]["data"]["caption"]


def test_facebook_adapter_publishes_page_photo():
    session = FakeSession([FakeResponse({"post_id": "fb-post-1"})])
    adapter = MetaFacebookAdapter(access_token="secret", graph_version="v99.0", session=session)
    job = approved_job("facebook")

    post_id = adapter.publish(job)

    assert post_id == "fb-post-1"
    assert session.calls[0]["url"].endswith("/acct-1/photos")
    assert "utm_source=facebook" in session.calls[0]["data"]["caption"]


def test_meta_adapter_requires_runtime_credentials():
    adapter = MetaInstagramAdapter(access_token="", graph_version="")
    with pytest.raises(RuntimeError, match="META_ACCESS_TOKEN"):
        adapter.validate_credentials("acct-1")
