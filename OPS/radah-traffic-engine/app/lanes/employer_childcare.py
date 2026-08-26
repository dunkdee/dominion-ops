from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from ..models import RadahEnvelope


IRS_SOURCE = {
    "name": "IRS — Employer-provided child care credit: Tax year 2026 and later",
    "url": "https://www.irs.gov/businesses/small-businesses-self-employed/employer-provided-child-care-credit-tax-year-2026-and-later",
    "verified_at": "2026-08-25",
}

DALLAS_SOURCE = {
    "name": "Dallas County / TOOTRiS Employer Match Child Care Program",
    "url": "https://tootris.com/edu/blog/news/dallas-county-partners-with-tootris-to-launch-texas-first-employer-match-child-care-program/",
    "verified_at": "2026-08-25",
    "refresh_after": "2026-09-24",
}

TOOTRIS_REFERRAL_SOURCE = {
    "name": "TOOTRiS Employer Referral",
    "url": "https://go.tootris.com/refer",
    "verified_at": "2026-08-25",
    "published_reward_usd": 250,
    "trigger": "referred employer creates a partnership with TOOTRiS",
    "refresh_after": "2026-09-24",
}


class EmployerChildcareEstimateIn(BaseModel):
    tax_year: int = Field(default=2026, ge=2026, le=2030)
    average_annual_gross_receipts: float = Field(
        ge=0,
        le=100_000_000_000,
        description="Average annual gross receipts over the relevant preceding period; 2026 small-business threshold screening only.",
    )
    qualified_childcare_expenditures: float = Field(default=0, ge=0, le=100_000_000)
    qualified_resource_referral_expenditures: float = Field(default=0, ge=0, le=100_000_000)
    state: str = Field(min_length=2, max_length=2)
    county: Optional[str] = Field(default=None, max_length=100)
    eligible_children: int = Field(default=0, ge=0, le=100_000)
    annual_employer_contribution_per_child: float = Field(default=0, ge=0, le=100_000)

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("county")
    @classmethod
    def normalize_county(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


class EmployerChildcareLeadIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=2, max_length=160)
    work_email: EmailStr
    state: str = Field(min_length=2, max_length=2)
    county: Optional[str] = Field(default=None, max_length=100)
    employee_count: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    estimated_annual_childcare_budget: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    company_website: Optional[str] = Field(default=None, max_length=500)
    consent_to_contact_and_share: bool
    website_honeypot: Optional[str] = Field(default=None, max_length=200)

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("business_name", "contact_name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split())


class GovernedChildcareLeadStatus(BaseModel):
    radah: "RadahEnvelope"
    status: str = Field(pattern=r"^(REFERRED|CLOSED)$")
    provider: Optional[str] = Field(default=None, max_length=160)
    receipt_id: Optional[str] = Field(default=None, max_length=160)


class Federal45FResult(BaseModel):
    screening_status: str
    possible_small_business_threshold_met: bool
    small_business_threshold_usd: float
    childcare_expenditure_rate: float
    resource_referral_rate: float
    annual_credit_cap_usd: float
    gross_qualified_spend_usd: float
    estimated_credit_before_cap_usd: float
    estimated_federal_credit_usd: float
    illustrative_employer_cost_after_estimated_credit_usd: float


class LocalProgramResult(BaseModel):
    program: str
    status: str
    potential_match_usd: float
    employer_contribution_counted_usd: float
    employee_benefit_pool_usd: float
    source: dict
    note: str


def estimate_federal_45f(data: EmployerChildcareEstimateIn) -> Federal45FResult:
    if data.tax_year != 2026:
        # This lane only contains verified 2026 parameters. Refuse to silently
        # apply them to later tax years.
        raise ValueError("Only tax year 2026 is currently verified for this calculator.")

    # IRS states that for tax years beginning in 2026, the Section 448(c)
    # gross-receipts threshold used for this credit is generally $32 million.
    # This is only a screening indicator; aggregation and other tax rules can
    # change the final determination.
    threshold = 32_000_000.0
    possible_small = data.average_annual_gross_receipts <= threshold

    childcare_rate = 0.50 if possible_small else 0.40
    referral_rate = 0.10
    cap = 600_000.0 if possible_small else 500_000.0

    gross_spend = (
        data.qualified_childcare_expenditures
        + data.qualified_resource_referral_expenditures
    )
    before_cap = (
        data.qualified_childcare_expenditures * childcare_rate
        + data.qualified_resource_referral_expenditures * referral_rate
    )
    credit = min(before_cap, cap)
    after_credit = max(0.0, gross_spend - credit)

    return Federal45FResult(
        screening_status="ESTIMATE_NOT_TAX_DETERMINATION",
        possible_small_business_threshold_met=possible_small,
        small_business_threshold_usd=threshold,
        childcare_expenditure_rate=childcare_rate,
        resource_referral_rate=referral_rate,
        annual_credit_cap_usd=cap,
        gross_qualified_spend_usd=round(gross_spend, 2),
        estimated_credit_before_cap_usd=round(before_cap, 2),
        estimated_federal_credit_usd=round(credit, 2),
        illustrative_employer_cost_after_estimated_credit_usd=round(after_credit, 2),
    )


def _dallas_program_is_fresh(as_of: date) -> bool:
    return as_of <= date.fromisoformat(DALLAS_SOURCE["refresh_after"])


def estimate_local_programs(
    data: EmployerChildcareEstimateIn,
    *,
    as_of: Optional[date] = None,
) -> list[LocalProgramResult]:
    as_of = as_of or date.today()
    results: list[LocalProgramResult] = []

    if data.state == "TX" and (data.county or "").strip().lower() in {
        "dallas", "dallas county"
    }:
        fresh = _dallas_program_is_fresh(as_of)
        if not fresh:
            results.append(LocalProgramResult(
                program="Dallas County Employer Match Child Care Program",
                status="REVERIFY_REQUIRED",
                potential_match_usd=0.0,
                employer_contribution_counted_usd=0.0,
                employee_benefit_pool_usd=0.0,
                source=DALLAS_SOURCE,
                note=(
                    "The last verified program data is past its refresh date. "
                    "RADAH should reverify current enrollment/funding before this incentive is used."
                ),
            ))
            return results

        per_child_counted = min(data.annual_employer_contribution_per_child, 3_000.0)
        employer_counted = per_child_counted * data.eligible_children
        county_match = employer_counted  # published dollar-for-dollar match
        benefit_pool = employer_counted + county_match

        results.append(LocalProgramResult(
            program="Dallas County Employer Match Child Care Program",
            status="CURRENTLY_VERIFIED_OPEN_FIRST_COME_FIRST_SERVED",
            potential_match_usd=round(county_match, 2),
            employer_contribution_counted_usd=round(employer_counted, 2),
            employee_benefit_pool_usd=round(benefit_pool, 2),
            source=DALLAS_SOURCE,
            note=(
                "Published program terms state a dollar-for-dollar Dallas County match, "
                "up to $3,000 per child annually. The county match increases employee "
                "benefit value; it is not subtracted from the federal-credit estimate here."
            ),
        ))

    return results


def build_estimate(data: EmployerChildcareEstimateIn, *, as_of: Optional[date] = None) -> dict:
    federal = estimate_federal_45f(data)
    local = estimate_local_programs(data, as_of=as_of)

    return {
        "lane": "employer-childcare-net-cost",
        "tax_year": data.tax_year,
        "federal": federal.model_dump(),
        "local_programs": [item.model_dump() for item in local],
        "monetization": {
            "published_employer_referral_reward_usd": TOOTRIS_REFERRAL_SOURCE["published_reward_usd"],
            "reward_trigger": TOOTRIS_REFERRAL_SOURCE["trigger"],
            "execution_authorized": False,
            "note": (
                "Referral terms are evidence for lane economics only. A lead must not be "
                "transmitted externally until the provider terms are current, consent is "
                "recorded, and a separate RADAH-authorized executor performs the handoff."
            ),
        },
        "sources": [IRS_SOURCE, DALLAS_SOURCE, TOOTRIS_REFERRAL_SOURCE],
        "legal_notice": (
            "This is an informational screening estimate, not tax, legal, accounting, or benefits advice. "
            "Section 45F eligibility, aggregation rules, qualified expenditures, general-business-credit "
            "limitations, recapture, and no-double-benefit rules can change the amount actually claimable. "
            "A qualified tax professional should determine final eligibility and filing treatment."
        ),
    }
