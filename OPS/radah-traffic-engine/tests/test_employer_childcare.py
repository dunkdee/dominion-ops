import os
from datetime import date

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("AUDIT_HMAC_KEY", "test-audit-key")
os.environ.setdefault("RADAH_SHARED_SECRET", "test-radah-key")
os.environ.setdefault("REQUIRE_RADAH_SIGNATURE", "false")

from app.lanes.employer_childcare import (
    EmployerChildcareEstimateIn,
    estimate_federal_45f,
    estimate_local_programs,
)


def sample(**overrides):
    data = dict(
        tax_year=2026,
        average_annual_gross_receipts=5_000_000,
        qualified_childcare_expenditures=36_000,
        qualified_resource_referral_expenditures=0,
        state="TX",
        county="Dallas",
        eligible_children=10,
        annual_employer_contribution_per_child=3_000,
    )
    data.update(overrides)
    return EmployerChildcareEstimateIn(**data)


def test_small_business_2026_rate_and_credit():
    r = estimate_federal_45f(sample())
    assert r.possible_small_business_threshold_met is True
    assert r.childcare_expenditure_rate == 0.50
    assert r.estimated_federal_credit_usd == 18_000
    assert r.illustrative_employer_cost_after_estimated_credit_usd == 18_000


def test_non_small_business_rate():
    r = estimate_federal_45f(sample(average_annual_gross_receipts=40_000_000))
    assert r.possible_small_business_threshold_met is False
    assert r.childcare_expenditure_rate == 0.40
    assert r.annual_credit_cap_usd == 500_000


def test_resource_referral_rate_and_cap():
    r = estimate_federal_45f(sample(
        qualified_childcare_expenditures=2_000_000,
        qualified_resource_referral_expenditures=100_000,
    ))
    assert r.estimated_credit_before_cap_usd == 1_010_000
    assert r.estimated_federal_credit_usd == 600_000


def test_dallas_match_current_as_of_verification_window():
    programs = estimate_local_programs(sample(), as_of=date(2026, 8, 25))
    assert len(programs) == 1
    p = programs[0]
    assert p.status == "CURRENTLY_VERIFIED_OPEN_FIRST_COME_FIRST_SERVED"
    assert p.potential_match_usd == 30_000
    assert p.employee_benefit_pool_usd == 60_000


def test_dallas_match_fails_closed_when_stale():
    programs = estimate_local_programs(sample(), as_of=date(2026, 10, 1))
    assert programs[0].status == "REVERIFY_REQUIRED"
    assert programs[0].potential_match_usd == 0
