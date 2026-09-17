import pytest

from apps.revenue_runtime.core import RevenueRuntimeError, deterministic_variant


def test_zero_percent_routes_every_visitor_to_control():
    visitors = ["visitor-a", "visitor-b", "visitor-c", "visitor-d"]
    assert all(deterministic_variant("gate-e", visitor, 0) == "control" for visitor in visitors)


def test_hundred_percent_routes_every_visitor_to_treatment():
    visitors = ["visitor-a", "visitor-b", "visitor-c", "visitor-d"]
    assert all(deterministic_variant("gate-e", visitor, 100) == "treatment" for visitor in visitors)


def test_out_of_range_percentages_remain_fail_closed():
    with pytest.raises(RevenueRuntimeError):
        deterministic_variant("gate-e", "visitor-a", -1)
    with pytest.raises(RevenueRuntimeError):
        deterministic_variant("gate-e", "visitor-a", 101)
