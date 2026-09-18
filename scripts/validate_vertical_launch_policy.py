#!/usr/bin/env python3
import json
from pathlib import Path

POLICY = Path("governance/vertical_launch_policy.json")
SYSTEM = Path("governance/system_components.json")
ATTRIBUTION = Path("governance/traffic_attribution_contract.json")

REQUIRED_VERTICALS = [
    "voltedge_commerce",
    "publisher_meta",
    "content_traffic",
    "orion_alpha",
]
REQUIRED_FUNNEL_STAGES = [
    "traffic_source",
    "content_or_ad",
    "tracked_link",
    "landing_or_product_page",
    "offer",
    "checkout_or_lead_capture",
    "follow_up",
    "sale_or_goal_event",
    "receipt",
    "attribution",
    "refinement",
]
REQUIRED_UTM_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
}
REQUIRED_ATTRIBUTION_RECEIPTS = {
    "campaign_id",
    "asset_id_or_hash",
    "platform",
    "publication_receipt",
    "tracked_destination_url",
    "landing_session",
    "cart_or_lead_event",
    "checkout_event",
    "order_or_goal_event",
    "revenue_amount_when_applicable",
    "refund_or_failure_event_when_applicable",
}


def fail(message: str) -> None:
    raise SystemExit(f"VERTICAL_LAUNCH_POLICY=FAIL reason={message}")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid_json:{path}:{exc.__class__.__name__}")


def validate_attribution(attribution: dict) -> None:
    if attribution.get("authority_model") != "RADAH_MEMSHALAH":
        fail("attribution_authority_model")
    if attribution.get("canonical_destination_domain") != "www.voltedgegoods.com":
        fail("attribution_destination_domain")

    identity = attribution.get("campaign_identity") or {}
    if identity.get("required") is not True:
        fail("campaign_identity_required")
    if identity.get("immutable_after_first_publish") is not True:
        fail("campaign_identity_immutable")
    if not identity.get("format"):
        fail("campaign_identity_format")

    tracked = attribution.get("tracked_link") or {}
    if set(tracked.get("required_query_parameters") or []) != REQUIRED_UTM_PARAMETERS:
        fail("utm_parameter_contract")
    rules = tracked.get("rules") or {}
    for key in (
        "no_untracked_campaign_links",
        "no_credentials_or_personal_data_in_query_parameters",
        "utm_campaign_must_equal_campaign_id",
        "utm_content_must_identify_asset_or_variant",
        "destination_must_be_registered_before_publish",
    ):
        if rules.get(key) is not True:
            fail(f"attribution_rule:{key}")

    receipts = set(attribution.get("receipt_chain") or [])
    if not REQUIRED_ATTRIBUTION_RECEIPTS.issubset(receipts):
        fail("attribution_receipt_chain")

    source_truth = attribution.get("source_of_truth") or {}
    if source_truth.get("campaign_definition") != "github":
        fail("attribution_campaign_source_truth")
    if source_truth.get("conflict_state") != "HOLD":
        fail("attribution_conflict_state")

    fail_closed = set(attribution.get("fail_closed") or [])
    for required in (
        "missing_campaign_id",
        "missing_tracked_link",
        "missing_publication_receipt",
        "source_truth_conflict",
        "claimed_revenue_without_order_or_provider_receipt",
    ):
        if required not in fail_closed:
            fail(f"attribution_fail_closed:{required}")

    privacy = attribution.get("privacy") or {}
    if privacy.get("forbid_pii_in_utm_values") is not True:
        fail("attribution_pii_guard")
    if privacy.get("forbid_credentials_in_urls") is not True:
        fail("attribution_credential_guard")


def main() -> None:
    policy = load(POLICY)
    system = load(SYSTEM)
    attribution = load(ATTRIBUTION)

    if policy.get("authority_model") != "RADAH_MEMSHALAH":
        fail("authority_model")
    if policy.get("source_of_truth_precedence") != system.get("source_of_truth_precedence"):
        fail("source_of_truth_precedence_drift")

    rules = policy.get("activation_rules") or {}
    for key in (
        "new_verticals_activate_sequentially",
        "proven_verticals_may_run_concurrently",
        "external_effects_require_explicit_authorization",
        "external_effects_require_runtime_receipt",
        "missing_or_stale_evidence_fails_closed",
        "next_vertical_requires_current_vertical_launch_receipt",
    ):
        if rules.get(key) is not True:
            fail(f"activation_rule:{key}")

    windows = policy.get("windows") or {}
    if windows.get("burn_in_hours") != 72:
        fail("burn_in_hours")
    if windows.get("proof_window_hours") != 168:
        fail("proof_window_hours")

    stages = (policy.get("funnel_contract") or {}).get("required_stages")
    if stages != REQUIRED_FUNNEL_STAGES:
        fail("funnel_contract")

    components = {row.get("id") for row in system.get("components", [])}
    pipelines = {row.get("id") for row in system.get("mission_pipelines", [])}
    verticals = policy.get("verticals") or []
    ids = [row.get("id") for row in verticals]
    if ids != REQUIRED_VERTICALS:
        fail("vertical_order_or_membership")

    orders = [row.get("order") for row in verticals]
    if orders != [1, 2, 3, 4]:
        fail("vertical_order")

    for vertical in verticals:
        owner = vertical.get("owner")
        pipeline = vertical.get("mission_pipeline")
        if owner not in components:
            fail(f"unknown_owner:{owner}")
        if pipeline not in pipelines:
            fail(f"unknown_pipeline:{pipeline}")
        receipts = vertical.get("required_receipts")
        if not isinstance(receipts, list) or not receipts:
            fail(f"missing_receipts:{vertical.get('id')}")
        if not vertical.get("activation_gate"):
            fail(f"missing_activation_gate:{vertical.get('id')}")

    voltedge = next((row for row in verticals if row.get("id") == "voltedge_commerce"), None)
    if not voltedge or voltedge.get("order") != 1:
        fail("voltedge_must_launch_first")
    required_store_receipts = {
        "storefront_health",
        "catalog_nonempty",
        "store_policies_verified",
        "checkout_path_verified",
        "attribution_record",
    }
    if not required_store_receipts.issubset(set(voltedge.get("required_receipts") or [])):
        fail("voltedge_pretraffic_receipts")

    orion = next((row for row in verticals if row.get("id") == "orion_alpha"), None)
    if not orion:
        fail("orion_missing")
    if orion.get("live_money_permitted") is not False:
        fail("orion_live_money_must_be_false")
    if orion.get("external_effect_class") != "paper_only":
        fail("orion_external_effect_class")

    factory = policy.get("store_factory") or {}
    if factory.get("independent_authority") is not False:
        fail("store_factory_parallel_authority")
    if factory.get("owner") != "voltedge_wix":
        fail("store_factory_owner")

    validate_attribution(attribution)

    print(f"VERTICAL_LAUNCH_POLICY=PASS verticals={len(verticals)} burn_in=72h proof_window=168h")
    print("VOLTEDGE_FIRST=PASS")
    print("RADAH_MEMSHALAH=PASS")
    print("FUNNEL_CONTRACT=PASS")
    print("ATTRIBUTION_CONTRACT=PASS")
    print("STORE_FACTORY_GOVERNANCE=PASS")


if __name__ == "__main__":
    main()
