from dataclasses import asdict, dataclass
from datetime import date, datetime


DOMAINS = ("liquidity", "buybacks", "shorts")
STATES = (
    "available",
    "confirmed_empty",
    "omitted",
    "unknown",
    "failed",
    "stale",
)


@dataclass(frozen=True)
class OwnershipLiquidityOperationalCoverage:
    as_of: str
    stale_after_days: int
    counts: dict
    observation_ranges: dict
    companies: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class OwnershipLiquidityCoverageReport:
    def __init__(self, repository, stale_after_days: int = 7):
        if stale_after_days < 0:
            raise ValueError("stale_after_days must be non-negative")
        self.repository = repository
        self.stale_after_days = stale_after_days

    def build(
        self, companies: list, as_of: date | None = None
    ) -> OwnershipLiquidityOperationalCoverage:
        as_of = as_of or date.today()
        company_ids = [company.id for company in companies if company.id is not None]
        rows = self.repository.get_operational_coverage(company_ids)
        company_results = [self._company_result(row, as_of) for row in rows]
        counts = {
            domain: {
                "requested": len(company_ids),
                **{
                    state: sum(
                        item[domain]["status"] == state for item in company_results
                    )
                    for state in STATES
                },
            }
            for domain in DOMAINS
        }
        ranges = {
            "liquidity": self._range(rows, "price_oldest", "price_newest"),
            "buybacks": self._range(rows, "buyback_oldest", "buyback_newest"),
            "shorts": self._range(rows, "short_oldest", "short_newest"),
        }
        return OwnershipLiquidityOperationalCoverage(
            as_of=as_of.isoformat(),
            stale_after_days=self.stale_after_days,
            counts=counts,
            observation_ranges=ranges,
            companies=company_results,
        )

    def _company_result(self, row: dict, as_of: date) -> dict:
        coverage = row.get("holdings_coverage") or {}
        liquidity_status = self._fresh_status(
            self._liquidity_status(row), row.get("price_newest"), as_of
        )
        buyback_base = self._normalize_status(coverage.get("buybacks"))
        if buyback_base == "unknown" and row.get("buyback_newest") is not None:
            buyback_base = "available"
        buyback_collection = (
            row.get("holdings_completed_at")
            if buyback_base in {"available", "confirmed_empty"}
            else row.get("buyback_collected_at")
        )
        buyback_status = self._fresh_status(
            buyback_base, self._as_date(buyback_collection), as_of
        )

        short_base = self._normalize_status(coverage.get("shorts"), short_domain=True)
        if short_base == "unknown" and row.get("short_newest") is not None:
            short_base = "available"
        short_status = self._fresh_status(
            short_base, row.get("short_newest"), as_of
        )
        errors = []
        if row.get("liquidity_error"):
            errors.append(f"liquidity: {row['liquidity_error']}")
        if row.get("holdings_error"):
            errors.append(f"holdings: {row['holdings_error']}")
        return {
            "company_id": row["company_id"],
            "name": row["name"],
            "ticker": row["ticker"],
            "liquidity": self._domain_result(
                liquidity_status,
                row.get("price_collected_at"),
                row.get("price_newest"),
                as_of,
            ),
            "buybacks": self._domain_result(
                buyback_status,
                buyback_collection,
                row.get("buyback_newest"),
                as_of,
            ),
            "shorts": self._domain_result(
                short_status,
                row.get("short_collected_at"),
                row.get("short_newest"),
                as_of,
            ),
            "errors": errors,
        }

    def _domain_result(
        self,
        status: str,
        collected_at: datetime | None,
        observation_date: date | None,
        as_of: date,
    ) -> dict:
        collection_date = self._as_date(collected_at)
        return {
            "status": status,
            "latest_successful_collection_time": (
                collected_at.isoformat() if collected_at else None
            ),
            "latest_observation_date": (
                observation_date.isoformat() if observation_date else None
            ),
            "snapshot_age_days": (
                (as_of - observation_date).days if observation_date else None
            ),
            "collection_age_days": (
                (as_of - collection_date).days if collection_date else None
            ),
        }

    def _liquidity_status(self, row: dict) -> str:
        if row.get("price_newest") is not None:
            return "available"
        if row.get("liquidity_job_status") == "failed":
            return "failed"
        return "unknown"

    def _fresh_status(self, status: str, observed_on: date | None, as_of: date) -> str:
        if (
            status in {"available", "confirmed_empty"}
            and observed_on is not None
            and (as_of - observed_on).days > self.stale_after_days
        ):
            return "stale"
        return status

    @staticmethod
    def _normalize_status(value: str | None, short_domain: bool = False) -> str:
        if value == "empty":
            return "confirmed_empty"
        if value in {"failed", "rejected"}:
            return "failed"
        if value == "omitted" and short_domain:
            return "unknown"
        if value in STATES:
            return value
        return "unknown"

    @staticmethod
    def _as_date(value: date | datetime | None) -> date | None:
        return value.date() if isinstance(value, datetime) else value

    @staticmethod
    def _range(rows: list[dict], oldest_key: str, newest_key: str) -> dict:
        oldest = [row[oldest_key] for row in rows if row.get(oldest_key) is not None]
        newest = [row[newest_key] for row in rows if row.get(newest_key) is not None]
        return {
            "oldest": min(oldest).isoformat() if oldest else None,
            "newest": max(newest).isoformat() if newest else None,
        }
