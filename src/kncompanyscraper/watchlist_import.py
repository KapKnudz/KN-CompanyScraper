import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WatchlistCompany:
    borsdata_id: int
    name: str
    ticker: str


@dataclass(frozen=True)
class WatchlistImportResult:
    created: int
    updated: int

    @property
    def imported(self) -> int:
        return self.created + self.updated


class WatchlistImportService:
    REQUIRED_COLUMNS = ("Id", "Name", "Ticker")
    MAX_TICKER_LENGTH = 20

    def __init__(self, company_repository):
        self.company_repository = company_repository

    def import_file(self, path: Path) -> WatchlistImportResult:
        companies = self._read_csv(path)
        created, updated = self.company_repository.upsert_watchlist_companies(companies)
        return WatchlistImportResult(created=created, updated=updated)

    def _read_csv(self, path: Path) -> list[WatchlistCompany]:
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, delimiter=";")
            if tuple(reader.fieldnames or ()) != self.REQUIRED_COLUMNS:
                expected = ";".join(self.REQUIRED_COLUMNS)
                raise ValueError(f"CSV header must be: {expected}")

            companies: list[WatchlistCompany] = []
            seen_ids: set[int] = set()
            seen_tickers: set[str] = set()

            for line_number, row in enumerate(reader, start=2):
                if None in row or any(row[column] is None for column in self.REQUIRED_COLUMNS):
                    raise ValueError(f"CSV line {line_number} must contain exactly 3 columns")
                name = row["Name"].strip()
                ticker = row["Ticker"].strip()
                raw_id = row["Id"].strip()

                if not raw_id or not name or not ticker:
                    raise ValueError(f"CSV line {line_number} contains an empty required value")
                try:
                    borsdata_id = int(raw_id)
                except ValueError as exc:
                    raise ValueError(
                        f"CSV line {line_number} has an invalid Börsdata ID: {raw_id}"
                    ) from exc
                if borsdata_id < 1:
                    raise ValueError(
                        f"CSV line {line_number} has an invalid Börsdata ID: {raw_id}"
                    )
                if len(ticker) > self.MAX_TICKER_LENGTH:
                    raise ValueError(
                        f"CSV line {line_number} ticker exceeds "
                        f"{self.MAX_TICKER_LENGTH} characters: {ticker}"
                    )
                if borsdata_id in seen_ids:
                    raise ValueError(
                        f"CSV line {line_number} duplicates Börsdata ID {borsdata_id}"
                    )
                normalized_ticker = ticker.casefold()
                if normalized_ticker in seen_tickers:
                    raise ValueError(f"CSV line {line_number} duplicates ticker {ticker}")

                seen_ids.add(borsdata_id)
                seen_tickers.add(normalized_ticker)
                companies.append(WatchlistCompany(borsdata_id, name, ticker))

        if not companies:
            raise ValueError("CSV contains no companies")
        return companies
