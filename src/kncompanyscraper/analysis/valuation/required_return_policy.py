"""Deterministic required-return components for the reverse DCF."""

from dataclasses import dataclass
from datetime import date
from typing import Literal


RiskProfile = Literal[
    "noncyclical_recurring",
    "slightly_cyclical",
    "cyclical_or_other_risk",
]


@dataclass(frozen=True)
class RiskFreeRateSnapshot:
    effective_date: date
    rate: float
    source: str


@dataclass(frozen=True)
class DiscountRateProfile:
    profile: RiskProfile
    label: str
    business_risk_adjustment: float
    discount_rate: float


@dataclass(frozen=True)
class RequiredReturnDecision:
    available: bool
    policy_version: str
    risk_free_rate: float | None
    risk_free_rate_date: str | None
    risk_free_rate_source: str | None
    equity_risk_premium: float
    market_cap: float | None
    size_bucket: str | None
    size_adjustment: float | None
    baseline_profile: RiskProfile
    profiles: dict[RiskProfile, DiscountRateProfile]
    missing_information: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class RequiredReturnPolicy:
    """Build a dated required return without beta or company-specific WACC."""

    VERSION = "required-return-v1"
    SUPPORTED_CURRENCY = "SEK"
    EQUITY_RISK_PREMIUM = 0.05
    BASELINE_PROFILE: RiskProfile = "slightly_cyclical"
    RISK_FREE_RATE_SNAPSHOTS = (
        RiskFreeRateSnapshot(
            effective_date=date(1900, 1, 1),
            rate=0.03,
            source="legacy normalized Swedish risk-free proxy for historical backtests",
        ),
        RiskFreeRateSnapshot(
            effective_date=date(2026, 7, 24),
            rate=0.028,
            source=(
                "Swedish National Debt Office state-loan reference rate effective "
                "2026-07-24; https://www.riksgalden.se/var-verksamhet/statslanerantan/"
            ),
        ),
    )
    BUSINESS_RISK_PROFILES = (
        ("noncyclical_recurring", "high-quality noncyclical recurring", 0.02),
        ("slightly_cyclical", "high-quality slightly cyclical", 0.04),
        ("cyclical_or_other_risk", "cyclical or other material risk", 0.07),
    )
    SIZE_BUCKETS = (
        (1_000_000_000.0, "micro", 0.02),
        (5_000_000_000.0, "small", 0.015),
        (20_000_000_000.0, "lower_mid", 0.01),
        (100_000_000_000.0, "upper_mid", 0.005),
        (float("inf"), "large", 0.0),
    )

    def build(
        self,
        *,
        as_of: date,
        currency: str | None,
        market_cap: float | None,
    ) -> RequiredReturnDecision:
        normalized_currency = (currency or self.SUPPORTED_CURRENCY).upper()
        if normalized_currency != self.SUPPORTED_CURRENCY:
            return RequiredReturnDecision(
                available=False,
                policy_version=self.VERSION,
                risk_free_rate=None,
                risk_free_rate_date=None,
                risk_free_rate_source=None,
                equity_risk_premium=self.EQUITY_RISK_PREMIUM,
                market_cap=market_cap,
                size_bucket=None,
                size_adjustment=None,
                baseline_profile=self.BASELINE_PROFILE,
                profiles={},
                missing_information=(
                    f"currency-matched risk-free rate unavailable for {normalized_currency}",
                ),
            )

        eligible_snapshots = (
            item
            for item in self.RISK_FREE_RATE_SNAPSHOTS
            if item.effective_date <= as_of
        )
        snapshot = max(eligible_snapshots, key=lambda item: item.effective_date)
        size_bucket, size_adjustment, size_warning = self._size_adjustment(market_cap)
        warnings = [size_warning] if size_warning else []
        if snapshot.effective_date == date(1900, 1, 1):
            warnings.append(
                "dated Swedish risk-free history unavailable; using legacy 3% backtest proxy"
            )
        profiles = {
            profile: DiscountRateProfile(
                profile=profile,
                label=label,
                business_risk_adjustment=business_adjustment,
                discount_rate=(
                    snapshot.rate
                    + self.EQUITY_RISK_PREMIUM
                    + size_adjustment
                    + business_adjustment
                ),
            )
            for profile, label, business_adjustment in self.BUSINESS_RISK_PROFILES
        }
        return RequiredReturnDecision(
            available=True,
            policy_version=self.VERSION,
            risk_free_rate=snapshot.rate,
            risk_free_rate_date=snapshot.effective_date.isoformat(),
            risk_free_rate_source=snapshot.source,
            equity_risk_premium=self.EQUITY_RISK_PREMIUM,
            market_cap=market_cap,
            size_bucket=size_bucket,
            size_adjustment=size_adjustment,
            baseline_profile=self.BASELINE_PROFILE,
            profiles=profiles,
            warnings=tuple(warnings),
        )

    @classmethod
    def _size_adjustment(
        cls,
        market_cap: float | None,
    ) -> tuple[str, float, str | None]:
        if market_cap is None or market_cap <= 0:
            return "unknown", 0.0, "market capitalization unavailable; size adjustment set to 0%"
        for upper_bound, bucket, adjustment in cls.SIZE_BUCKETS:
            if market_cap < upper_bound:
                return bucket, adjustment, None
        raise RuntimeError("size bucket policy is incomplete")
