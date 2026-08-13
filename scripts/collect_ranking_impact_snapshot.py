"""Collect a read-only ranking snapshot for cross-version impact analysis."""

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path

from kncompanyscraper.main import _build_watchlist_analysis_service
from kncompanyscraper.repositories.company_repository import CompanyRepository
from kncompanyscraper.repositories.financial_repository import FinancialRepository


def _json_value(value):
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def collect() -> dict:
    company_repository = CompanyRepository()
    financial_repository = FinancialRepository()
    companies = company_repository.get_active_companies()
    companies_by_id = {company.id: company for company in companies}

    service = _build_watchlist_analysis_service()
    service.ranking_engine.ranking_repository = None
    run = service.analyze_watchlist()

    ranking = {
        score.company_id: {"rank": rank, **score.to_dict()}
        for rank, score in enumerate(run.ranking.scores, 1)
    }
    records = []
    for company_id, result in run.results_by_company.items():
        company = companies_by_id[company_id]
        annuals = financial_repository._get_reports(company_id, "year")
        current = (
            financial_repository.get_latest_report(company_id, "r12")
            or financial_repository.get_latest_report(company_id, "year")
        )
        records.append(
            {
                "company": _json_value(company),
                "ranking": ranking[company_id],
                "reverse_dcf": _json_value(result["reverse_dcf"]),
                "current_report": (
                    {
                        "period_end": _json_value(current.period_end),
                        "revenue": current.revenue,
                        "ebit": current.ebit,
                        "free_cash_flow": current.free_cash_flow,
                        "shares_outstanding": current.shares_outstanding,
                        "net_debt": current.total_debt,
                        "currency": current.currency,
                    }
                    if current is not None
                    else None
                ),
                "annuals": [
                    {
                        "year": report.year,
                        "period_end": _json_value(report.period_end),
                        "revenue": report.revenue,
                        "ebit": report.ebit,
                        "free_cash_flow": report.free_cash_flow,
                        "operating_cash_flow": report.operating_cash_flow,
                        "investing_cash_flow": (report.raw_payload or {}).get(
                            "cash_Flow_From_Investing_Activities"
                        ),
                    }
                    for report in annuals
                ],
            }
        )
    return {"generated_at": datetime.now().isoformat(), "companies": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
