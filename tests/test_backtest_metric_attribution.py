from datetime import date
from types import SimpleNamespace

from kncompanyscraper.analysis.backtesting.backtest_engine import BacktestEngine
from kncompanyscraper.models.company import Company


def test_metric_attributions_use_scoring_audit_component_schema():
    score = SimpleNamespace(
        company_id=1,
        ranking_model="general",
        scoring_audit={
            "valuation": {
                "production_score": 60.0,
                "reconstruction_error": 0.0,
                "total_category_weight": 0.3,
                "components": [
                    {
                        "name": "dividend_yield",
                        "raw_value": 4.0,
                        "score": 50.0,
                        "weight": 0.1,
                        "effective_weight": 0.1,
                        "category_contribution": 5.0,
                        "total_contribution": 1.5,
                        "available": True,
                        "transformation": "linear[0,8.0]",
                        "dependencies": ("dividends", "market_cap"),
                        "cross_category_dependencies": (),
                        "provenance": "report_reconstructed",
                    }
                ],
            }
        },
    )
    company = Company(1, "Test Co", "TST", None, None, None)

    rows = BacktestEngine._build_metric_attributions(
        date(2025, 1, 31),
        [score],
        {1: company},
    )

    assert rows[0].normalized_score == 50.0
    assert rows[0].configured_weight == 0.1
