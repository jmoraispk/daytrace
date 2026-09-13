from dataclasses import replace
from decimal import Decimal

import pytest

from daytrace.pricing import estimate_plan_cost, estimate_usage_cost


@pytest.mark.parametrize(
    ("model", "expected_usd"),
    [
        ("gpt-5.6-luna", Decimal("0.032")),
        ("gpt-5.6-terra", Decimal("0.32")),
        ("gpt-5.6-sol", Decimal("0.6")),
        ("gpt-5.6", Decimal("0.6")),
        ("gpt-6-astra", Decimal("1.5")),
    ],
)
def test_usage_cost_uses_official_standard_rates(model, expected_usd) -> None:
    estimate = estimate_usage_cost(model, input_tokens=100_000, output_tokens=10_000)

    assert estimate is not None
    assert estimate.usd == expected_usd
    assert estimate.input_tokens == 100_000
    assert estimate.output_tokens == 10_000


def test_unknown_model_cost_is_unavailable(make_summary_plan) -> None:
    assert estimate_usage_cost("private-model", 100, 50) is None
    assert estimate_plan_cost("private-model", make_summary_plan()) is None


def test_preflight_cost_includes_prompt_overhead_and_expected_output(
    make_summary_plan,
) -> None:
    base = make_summary_plan(episode_count=10)
    plan = replace(base, input_character_count=10_000)

    estimate = estimate_plan_cost("gpt-5.6-terra", plan)

    assert estimate is not None
    assert estimate.input_tokens == 3_500
    assert estimate.output_tokens == 600
    assert estimate.usd == Decimal("0.0142")


def test_preflight_cost_accounts_for_merge_input_and_output(make_summary_plan) -> None:
    base = make_summary_plan(chunk_count=2, episode_count=10)
    plan = replace(base, input_character_count=10_000)

    estimate = estimate_plan_cost("gpt-5.6-terra", plan)

    assert estimate is not None
    assert estimate.input_tokens == 4_100
    assert estimate.output_tokens == 850
    assert estimate.usd == Decimal("0.0184")
