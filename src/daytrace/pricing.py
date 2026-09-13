from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from daytrace.models import SummaryPlan


PRICING_AS_OF = date(2026, 9, 13)
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/compare"
TOKENS_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal


@dataclass(frozen=True, slots=True)
class CostEstimate:
    input_tokens: int
    output_tokens: int
    usd: Decimal


_SOL_PRICE = ModelPrice(Decimal("4"), Decimal("0.4"), Decimal("20"))
MODEL_PRICES = {
    "gpt-5.6-luna": ModelPrice(Decimal("0.2"), Decimal("0.02"), Decimal("1.2")),
    "gpt-5.6-terra": ModelPrice(Decimal("2"), Decimal("0.2"), Decimal("12")),
    "gpt-5.6-sol": _SOL_PRICE,
    "gpt-5.6": _SOL_PRICE,
    "gpt-6-astra": ModelPrice(Decimal("10"), Decimal("1"), Decimal("50")),
}


def estimate_usage_cost(
    model: str, input_tokens: int, output_tokens: int
) -> CostEstimate | None:
    price = MODEL_PRICES.get(model)
    if price is None:
        return None
    usd = (
        Decimal(input_tokens) * price.input_per_million
        + Decimal(output_tokens) * price.output_per_million
    ) / TOKENS_PER_MILLION
    return CostEstimate(input_tokens=input_tokens, output_tokens=output_tokens, usd=usd)


def estimate_plan_cost(model: str, plan: SummaryPlan) -> CostEstimate | None:
    # Four characters per token with 40% allowance for instructions and schema.
    input_tokens = (plan.input_character_count * 7 + 19) // 20
    output_tokens = max(600, plan.episode_count * 60)
    if plan.planned_request_count > len(plan.requests):
        # A merge consumes the provisional summary, then emits a much smaller grouping.
        input_tokens += output_tokens
        output_tokens += max(250, plan.episode_count * 10)
    return estimate_usage_cost(model, input_tokens, output_tokens)
