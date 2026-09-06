from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class LiquidityEvidence:
    status: str
    currency: str | None
    adtv_20: float | None
    adtv_60: float | None
    adtv_120: float | None
    observed_days_20: int
    observed_days_60: int
    observed_days_120: int
    zero_volume_days_120: int
    calculation_method: str = "close_times_volume_proxy"


@dataclass(frozen=True)
class OwnershipLiquidityEvidence:
    as_of: str
    status: str
    listing: dict
    liquidity: LiquidityEvidence
    flow_signals: dict = field(default_factory=dict)
    ownership: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    source_ids_by_measure: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class OwnershipLiquidityEvidenceBuilder:
    WINDOWS = (20, 60, 120)

    def __init__(
        self,
        company_repository,
        valuation_repository,
        ownership_flow_repository=None,
        minimum_observations: dict[int, int] | None = None,
        short_stale_after_days: int = 7,
    ):
        self.company_repository = company_repository
        self.valuation_repository = valuation_repository
        self.ownership_flow_repository = ownership_flow_repository
        self.short_stale_after_days = short_stale_after_days
        self.minimum_observations = minimum_observations or {
            window: window for window in self.WINDOWS
        }

    def build(
        self,
        company_id: int,
        as_of: date,
        filter_ids: set[str] | None = None,
    ) -> OwnershipLiquidityEvidence:
        listing = self.company_repository.get_listing_identity(company_id) or {}
        prices = self.valuation_repository.get_liquidity_prices_as_of(
            company_id, as_of, limit=max(self.WINDOWS)
        )
        currency = next((price.currency for price in prices if price.currency), None)
        limitations = [
            "Free-float and holder ownership coverage are unavailable"
        ]
        values = {}
        observed = {}
        source_ids = []
        source_ids_by_measure = {}
        for window in self.WINDOWS:
            window_prices = prices[:window]
            observed[window] = len(window_prices)
            if len(window_prices) < self.minimum_observations[window]:
                values[window] = None
                limitations.append(
                    f"ADTV {window}-day proxy requires "
                    f"{self.minimum_observations[window]} observations; "
                    f"{len(window_prices)} are stored by {as_of.isoformat()}"
                )
                continue
            values[window] = round(
                sum(price.close * price.volume for price in window_prices) / len(window_prices),
                2,
            )
            liquidity_source_id = (
                f"liquidity:borsdata:{company_id}:"
                f"{window_prices[0].date.isoformat()}:{window}d"
            )
            if filter_ids is None or liquidity_source_id in filter_ids:
                source_ids.append(liquidity_source_id)
                source_ids_by_measure[f"adtv_{window}"] = [liquidity_source_id]
                source_ids_by_measure[f"observed_days_{window}"] = [liquidity_source_id]
                if window == 120:
                    source_ids_by_measure["zero_volume_days_120"] = [liquidity_source_id]
            else:
                values[window] = None
                observed[window] = 0

        has_listing = any(
            listing.get(field) is not None
            for field in ("market_id", "venue", "listing_date")
        )
        listing_payload = {
            "status": "available" if has_listing else "unavailable",
            "market_id": listing.get("market_id"),
            "venue": listing.get("venue"),
            "listing_date": (
                listing["listing_date"].isoformat()
                if listing.get("listing_date")
                else None
            ),
        }
        listing_source_id = f"listing:borsdata:{company_id}"
        if has_listing:
            if filter_ids is None or listing_source_id in filter_ids:
                source_ids.append(listing_source_id)
                for measure in ("market_id", "venue", "listing_date"):
                    if listing_payload[measure] is not None:
                        source_ids_by_measure[measure] = [listing_source_id]
            else:
                listing_payload = {
                    "status": "unavailable",
                    "market_id": None,
                    "venue": None,
                    "listing_date": None,
                }
        flow_signals = self._flow_signals(
            company_id, as_of, limitations, source_ids, filter_ids,
            source_ids_by_measure,
        )
        liquidity_values = tuple(values.values())
        if all(value is not None for value in liquidity_values):
            liquidity_status = "available"
        elif any(value is not None for value in liquidity_values):
            liquidity_status = "partial"
        else:
            liquidity_status = "unavailable"
        subsection_statuses = (
            listing_payload["status"],
            liquidity_status,
            flow_signals["buybacks"]["status"],
            flow_signals["shorts"]["status"],
            "unavailable",
        )
        status = (
            "unavailable"
            if set(subsection_statuses) == {"unavailable"}
            else "stale"
            if set(subsection_statuses) <= {"stale", "unavailable"}
            else "available"
            if set(subsection_statuses) == {"available"}
            else "partial"
        )
        return OwnershipLiquidityEvidence(
            as_of=as_of.isoformat(),
            status=status,
            listing=listing_payload,
            liquidity=LiquidityEvidence(
                status=liquidity_status,
                currency=currency,
                adtv_20=values[20],
                adtv_60=values[60],
                adtv_120=values[120],
                observed_days_20=observed[20],
                observed_days_60=observed[60],
                observed_days_120=observed[120],
                zero_volume_days_120=sum(price.volume == 0 for price in prices[:120]),
            ),
            flow_signals=flow_signals,
            ownership={"status": "unavailable", "source_ids": []},
            limitations=limitations,
            source_ids=source_ids,
            source_ids_by_measure=source_ids_by_measure,
        )

    def _flow_signals(
        self,
        company_id: int,
        as_of: date,
        limitations: list[str],
        source_ids: list[str],
        filter_ids: set[str] | None,
        source_ids_by_measure: dict,
    ) -> dict:
        if self.ownership_flow_repository is None:
            limitations.extend(
                [
                    "Executed buyback evidence is unavailable",
                    "Short-interest evidence is unavailable",
                ]
            )
            return {
                "buybacks": {"status": "unavailable", "source_ids": []},
                "shorts": {"status": "unavailable", "source_ids": []},
            }

        coverage = self.ownership_flow_repository.get_latest_sync_coverage(company_id)
        events = self.ownership_flow_repository.list_buybacks_as_of(company_id, as_of)
        event_pairs = [
            (event, f"buyback:{event.source}:{company_id}:{event.event_date.isoformat()}")
            for event in events
        ]
        if filter_ids is not None:
            event_pairs = [pair for pair in event_pairs if pair[1] in filter_ids]
        elif event_pairs:
            cutoff_12m = _subtract_months(as_of, 12)
            latest_pair = event_pairs[0]
            event_pairs = [
                pair
                for pair in event_pairs
                if pair == latest_pair or pair[0].event_date >= cutoff_12m
            ]
        buyback_ids = [source_id for _, source_id in event_pairs]
        source_ids.extend(buyback_ids)
        for measure in (
            "latest_event_date", "trailing_3_month_change_shares_raw",
            "trailing_12_month_change_shares_raw", "latest_treasury_shares",
            "latest_treasury_shares_pct_raw",
        ):
            if buyback_ids:
                source_ids_by_measure[measure] = list(buyback_ids)
        if event_pairs:
            latest = event_pairs[0][0]
            cutoff_3m = _subtract_months(as_of, 3)
            cutoff_12m = _subtract_months(as_of, 12)
            buybacks = {
                "status": "available",
                "latest_event_date": latest.event_date.isoformat(),
                "trailing_3_month_change_shares_raw": sum(
                    event.change_shares
                    for event, _ in event_pairs
                    if event.event_date >= cutoff_3m
                ),
                "trailing_12_month_change_shares_raw": sum(
                    event.change_shares
                    for event, _ in event_pairs
                    if event.event_date >= cutoff_12m
                ),
                "latest_treasury_shares": latest.treasury_shares,
                "latest_treasury_shares_pct_raw": latest.treasury_shares_pct_raw,
                "source_ids": buyback_ids,
            }
        else:
            buyback_status = coverage.get("buybacks", "unavailable")
            buybacks = {"status": buyback_status, "source_ids": []}
            limitations.append(
                f"Executed buyback evidence is {buyback_status} as of {as_of.isoformat()}"
            )

        snapshot = self.ownership_flow_repository.get_latest_short_as_of(company_id, as_of)
        short_id = (
            f"short:{snapshot.source}:{company_id}:{snapshot.observation_date.isoformat()}"
            if snapshot
            else None
        )
        if filter_ids is not None and short_id not in filter_ids:
            snapshot = None
            short_id = None
        if snapshot is None:
            short_status = coverage.get("shorts", "unavailable")
            shorts = {"status": short_status, "source_ids": []}
            limitations.append(
                f"Short-interest evidence is {short_status} as of {as_of.isoformat()}"
            )
        else:
            age_days = (as_of - snapshot.observation_date).days
            short_status = (
                "stale" if age_days > self.short_stale_after_days else "available"
            )
            shorts = {
                "status": short_status,
                "observation_date": snapshot.observation_date.isoformat(),
                "snapshot_age_days": age_days,
                "short_pct_raw": snapshot.short_pct_raw,
                "reported_holder_count_raw": snapshot.reported_holder_count,
                "average_short_pct_raw": snapshot.average_short_pct_raw,
                "short_value_millions_raw": snapshot.short_value_millions_raw,
                "average_short_value_millions_raw": (
                    snapshot.average_short_value_millions_raw
                ),
                "last_transaction_date": (
                    snapshot.last_transaction_date.isoformat()
                    if snapshot.last_transaction_date
                    else None
                ),
                "days_to_cover_sum_raw": snapshot.days_to_cover_sum,
                "days_to_cover_average_raw": snapshot.days_to_cover_average,
                "trend_1w_raw": snapshot.trend_1w,
                "trend_1m_raw": snapshot.trend_1m,
                "trend_3m_raw": snapshot.trend_3m,
                "trend_6m_raw": snapshot.trend_6m,
                "source_ids": [short_id],
            }
            source_ids.append(short_id)
            for measure in (
                "observation_date", "snapshot_age_days", "short_pct_raw",
                "reported_holder_count_raw", "average_short_pct_raw",
                "short_value_millions_raw",
            ):
                source_ids_by_measure[measure] = [short_id]
            if short_status == "stale":
                limitations.append(
                    f"Short-interest snapshot is stale at {age_days} days old"
                )

        if event_pairs or snapshot:
            limitations.append(
                "Börsdata buyback percentage and short-interest value, percentage, "
                "holder, days-to-cover, and trend fields have unverified semantics "
                "and are supplied only as raw values"
            )
        return {"buybacks": buybacks, "shorts": shorts}


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    month_lengths = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30,
                     31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
