from pathlib import Path
from kncompanyscraper.logger import get_logger

logger = get_logger("cli.sync")


def register(subparsers):
    import_watchlist_parser = subparsers.add_parser(
        "import-watchlist", help="Import companies from a CSV file"
    )
    import_watchlist_parser.add_argument("--csv", required=True, type=Path)
    import_watchlist_parser.set_defaults(func=_cmd_import_watchlist)

    subparsers.add_parser(
        "map-borsdata", help="Map companies to Börsdata instruments"
    )
    subparsers.add_parser("sync-borsdata", help="Fetch and persist Börsdata inputs")
    subparsers.add_parser(
        "sync-fundamental-history", help="Backfill historical ROIC and net debt/EBITDA"
    )
    subparsers.add_parser(
        "sync-borsdata-insiders", help="Sync insider transactions from Börsdata"
    )
    subparsers.add_parser(
        "sync-borsdata-dividends", help="Sync dividend calendar from Börsdata"
    )

    import_benchmark_parser = subparsers.add_parser(
        "import-benchmark-prices", help="Manual fallback for Nasdaq CSV export"
    )
    import_benchmark_parser.add_argument("--csv", required=True, type=Path)
    import_benchmark_parser.add_argument("--series-code", default="OMXS30GI")
    import_benchmark_parser.add_argument("--return-basis", default="gross_total_return")
    import_benchmark_parser.add_argument("--source", default="Manual CSV import")
    import_benchmark_parser.set_defaults(func=_cmd_import_benchmark_prices)

    sync_omx_parser = subparsers.add_parser(
        "sync-omxs30gi", help="Sync OMXS30GI history from Nasdaq"
    )
    sync_omx_parser.add_argument("--start-date", help="YYYY-MM-DD")
    sync_omx_parser.add_argument("--end-date", help="YYYY-MM-DD")
    sync_omx_parser.set_defaults(func=_cmd_sync_omxs30gi)


def _cmd_import_watchlist(args):
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.watchlist_import import WatchlistImportService

    try:
        result = WatchlistImportService(CompanyRepository()).import_file(args.csv)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"Imported {result.imported} watchlist companies "
        f"({result.created} created, {result.updated} updated)."
    )


def _cmd_map_borsdata(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.instrument_mapping import (
        BorsdataInstrumentMappingService,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository

    company_repo = CompanyRepository()
    companies = company_repo.get_active_companies()
    result = BorsdataInstrumentMappingService(BorsdataClient(), company_repo).map_companies(
        companies
    )

    print(f"Mapped {result.mapped} companies to Börsdata instruments.")
    if result.unresolved:
        print(f"Unresolved: {', '.join(result.unresolved)}")


def _cmd_sync_borsdata(args):
    from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    BorsdataIngestionService(
        BorsdataClient(),
        CompanyRepository(),
        FinancialRepository(),
        ValuationRepository(),
        JobRepository(),
    ).sync_all()


def _cmd_sync_fundamental_history(args):
    from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    service = BorsdataIngestionService(
        BorsdataClient(),
        CompanyRepository(),
        FinancialRepository(),
        ValuationRepository(),
        JobRepository(),
    )
    companies = CompanyRepository().get_active_companies()
    synced = 0
    failures = []
    for company in companies:
        try:
            service.sync_fundamental_history(company)
            synced += 1
        except Exception as exc:
            failures.append(f"{company.id} {company.ticker}: {exc}")
    print(
        f"Fundamental KPI history sync: {synced} synced, "
        f"{len(failures)} failed, {len(companies)} attempted."
    )
    for failure in failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_insiders(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_insider_job import BorsdataInsiderJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    companies = CompanyRepository().get_active_companies()
    result = BorsdataInsiderJob(
        BorsdataClient(),
        InsiderRepository(),
        JobRepository(),
    ).run(companies)
    print(
        f"Börsdata insider sync complete: {result.synced} synced, "
        f"{result.failed} failed, {result.inserted} transactions inserted."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_dividends(args):
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_dividend_job import BorsdataDividendJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    result = BorsdataDividendJob(
        BorsdataClient(),
        DividendRepository(),
        ValuationRepository(),
    ).run(CompanyRepository().get_active_companies())
    print(
        f"Börsdata dividend sync complete: {result.synced} synced, "
        f"{result.failed} failed."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_import_benchmark_prices(args):
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository

    BenchmarkRepository().import_prices_csv(
        args.csv, args.series_code, args.return_basis, args.source
    )


def _cmd_sync_omxs30gi(args):
    from datetime import date
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository

    start = date.fromisoformat(args.start_date) if args.start_date else None
    end = date.fromisoformat(args.end_date) if args.end_date else None

    # Nasdaq sync uses the Börsdata client for the underlying HTTP session/backoff logic
    BenchmarkRepository().sync_omxs30gi(BorsdataClient(), start_date=start, end_date=end)
