from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class HoldingsInstrumentResult(Generic[T]):
    instrument_id: int
    values: tuple[T, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class BuybackEvent:
    event_date: date
    change_shares: int
    change_pct_raw: float
    reported_price: float
    currency: str | None
    treasury_shares: int
    treasury_shares_pct_raw: float
    raw_payload: dict


@dataclass(frozen=True)
class ShortInterestSnapshot:
    instrument_id: int
    short_pct_raw: float | None
    reported_holder_count: float | None
    average_short_pct_raw: float | None
    short_value_millions_raw: float | None
    average_short_value_millions_raw: float | None
    last_transaction_date: date | None
    days_to_cover_sum: float | None
    days_to_cover_average: float | None
    trend_1w: float | None
    trend_1m: float | None
    trend_3m: float | None
    trend_6m: float | None
    error: str | None
    raw_payload: dict


@dataclass(frozen=True)
class StoredBuybackEvent:
    company_id: int
    event_date: date
    change_shares: int
    change_pct_raw: float | None
    reported_price: float | None
    currency: str | None
    treasury_shares: int | None
    treasury_shares_pct_raw: float | None
    source: str
    raw_payload: dict


@dataclass(frozen=True)
class StoredShortInterestSnapshot:
    company_id: int
    observation_date: date
    short_pct_raw: float | None
    reported_holder_count: float | None
    average_short_pct_raw: float | None
    short_value_millions_raw: float | None
    average_short_value_millions_raw: float | None
    last_transaction_date: date | None
    days_to_cover_sum: float | None
    days_to_cover_average: float | None
    trend_1w: float | None
    trend_1m: float | None
    trend_3m: float | None
    trend_6m: float | None
    source: str
    raw_payload: dict
