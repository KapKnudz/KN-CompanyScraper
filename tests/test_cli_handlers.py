from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kncompanyscraper import main
from kncompanyscraper.cli import agent, backtest, dividend, portfolio
from kncompanyscraper.main import build_parser
from kncompanyscraper.constants import BORSDATA_DIVIDEND_SOURCE
from kncompanyscraper.models.enums import RankingModel


def test_every_restored_command_has_a_callable_dispatch_handler():
    parser = main.build_parser()
    commands = {
        "backtest",
        "calibrate-weights",
        "analyze-scoring-audit",
        "evaluate-ranking-performance",
        "report-ranking-performance",
        "evaluate-ranking-challengers",
        "report-ranking-challengers",
        "audit-dividends",
        "review-dividends",
        "select-portfolio",
        "export-thesis-summaries",
        "sync-borsdata-reports",
    }

    for command in commands:
        subparser = parser._subparsers._group_actions[0].choices[command]
        args = [command]
        if command == "calibrate-weights":
            args += ["--attribution-csv", "attribution.csv"]
        elif command == "analyze-scoring-audit":
            args += ["--scoring-audit-csv", "audit.csv"]
        elif command == "audit-dividends":
            args += ["--company-id", "1", "--after", "2025-01-01", "--through", "2025-12-31"]
        elif command == "review-dividends":
            args += [
                "--company-id", "1", "--after", "2025-01-01", "--through", "2025-12-31",
                "--status", "approved", "--reason", "verified",
            ]
        elif command == "export-thesis-summaries":
            args += ["--output", "thesis-summaries.json"]
        assert callable(getattr(parser.parse_args(args), "func", None)), command


def test_calibration_handler_uses_requested_model_and_horizon(capsys):
    report = SimpleNamespace(
        ranking_model=RankingModel.GENERAL,
        horizon_months=12,
        frozen_weights={"quality": 0.4},
        candidate_weights={"quality": 0.5},
        recommendation_ready=True,
        readiness_reasons=["enough observations"],
    )
    with patch(
        "kncompanyscraper.analysis.backtesting.weight_calibration.load_attribution_rows",
        return_value=["row"],
    ) as load, patch(
        "kncompanyscraper.analysis.backtesting.weight_calibration.calibrate_weights",
        return_value=report,
    ) as calibrate:
        backtest._cmd_calibrate_weights(
            SimpleNamespace(
                attribution_csv="attribution.csv",
                ranking_model="general",
                horizon_months=12,
            )
        )

    load.assert_called_once_with("attribution.csv", RankingModel.GENERAL, 12)
    calibrate.assert_called_once_with(["row"], RankingModel.GENERAL, 12)
    assert "Recommendation ready: True" in capsys.readouterr().out


def test_backtest_command_wires_return_repositories():
    engine = MagicMock()
    engine.run.return_value = []
    with (
        patch(
            "kncompanyscraper.analysis.backtesting.backtest_engine.BacktestEngine",
            return_value=engine,
        ) as backtest_engine,
        patch("kncompanyscraper.repositories.company_repository.CompanyRepository") as company,
        patch("kncompanyscraper.repositories.financial_repository.FinancialRepository") as financial,
        patch("kncompanyscraper.repositories.valuation_repository.ValuationRepository") as valuation,
        patch("kncompanyscraper.repositories.dividend_repository.DividendRepository") as dividends,
        patch("kncompanyscraper.repositories.benchmark_repository.BenchmarkRepository") as benchmark,
    ):
        main.run_backtest_command(24)

    backtest_engine.assert_called_once_with(
        company.return_value,
        financial.return_value,
        valuation.return_value,
        dividends.return_value,
        benchmark.return_value,
    )
    engine.run.assert_called_once_with(num_periods=24)


def test_audit_dividends_prints_review_status(capsys):
    event = SimpleNamespace(
        ex_date=date(2025, 3, 20), amount=2.5, currency="SEK", dividend_type=1
    )
    review = SimpleNamespace(status="approved")
    repository = MagicMock()
    repository.get_dividends.return_value = [event]
    repository.get_reviews.return_value = {"key": review}
    repository.review_key.return_value = "key"

    with patch(
        "kncompanyscraper.repositories.dividend_repository.DividendRepository",
        return_value=repository,
    ):
        dividend._cmd_audit_dividends(
            SimpleNamespace(company_id=7, after="2025-01-01", through="2025-12-31")
        )

    repository.get_dividends.assert_called_once_with(
        7, after_date=date(2025, 1, 1), through_date=date(2025, 12, 31)
    )
    assert "2025-03-20 2.5 SEK approved" in capsys.readouterr().out


def test_review_dividends_passes_decision_to_repository(capsys):
    repository = MagicMock()
    repository.review_events.return_value = 2

    with patch(
        "kncompanyscraper.repositories.dividend_repository.DividendRepository",
        return_value=repository,
    ):
        dividend._cmd_review_dividends(
            SimpleNamespace(
                company_id=7,
                after="2025-01-01",
                through="2025-12-31",
                status="excluded",
                reason="duplicate source",
                evidence_url="https://example.test/evidence",
            )
        )

    repository.review_events.assert_called_once_with(
        7,
        after_date=date(2025, 1, 1),
        through_date=date(2025, 12, 31),
        status="excluded",
        reason="duplicate source",
        evidence_url="https://example.test/evidence",
            source=BORSDATA_DIVIDEND_SOURCE,
    )
    assert "Reviewed 2 dividend events" in capsys.readouterr().out


def test_select_portfolio_persists_and_optionally_exports_selection(tmp_path):
    ranking = {"scores": []}
    selection = SimpleNamespace(to_dict=lambda: {"status": "not_ready", "selected": []})
    ranking_repository = MagicMock()
    ranking_repository.get_latest_monthly_run_before.return_value = ranking
    portfolio_repository = MagicMock()
    output = tmp_path / "portfolio.json"

    with (
        patch(
            "kncompanyscraper.repositories.ranking_repository.RankingRepository",
            return_value=ranking_repository,
        ),
        patch(
            "kncompanyscraper.repositories.analysis_repository.AnalysisRepository"
        ) as analysis_repository,
        patch(
            "kncompanyscraper.repositories.portfolio_repository.PortfolioRepository",
            return_value=portfolio_repository,
        ),
        patch("kncompanyscraper.analysis.portfolio_selection.PortfolioSelectionService") as service,
    ):
        # The handler imports RankingRepository inside the function, so patch its
        # defining module and provide the result there.
        service.return_value.select.return_value = selection
        analysis_repository.return_value.get_latest_validated_stock_analyses.return_value = {}
        portfolio._cmd_select_portfolio(SimpleNamespace(target_size=3, output=output))

    portfolio_repository.save_run.assert_called_once_with({"status": "not_ready", "selected": []})
    assert '"status": "not_ready"' in output.read_text(encoding="utf-8")


def test_export_thesis_summaries_exports_only_enriched_v2_analyses(tmp_path, capsys):
    from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION
    from kncompanyscraper.models.stored_analysis import StoredAnalysisDocument

    current = StoredAnalysisDocument(
        {
            "analysis_id": 7,
            "content": {
                "thesis_card_version": "individual-thesis-card-v2",
                "verdict": "watch",
                "confidence": "medium",
                "one_sentence_thesis": "The evidence remains incomplete.",
                "reverse_dcf_expectation_assessment": "unassessable",
                "thesis_break_conditions": [],
                "missing_information": [],
                "scenario_bundles": [
                    {"case": "bear"},
                    {"case": "base"},
                    {"case": "bull"},
                ],
                "forward_scenario_analysis": {
                    "status": "available",
                    "policy_version": FORWARD_SCENARIO_POLICY_VERSION,
                    "bands": [
                        {
                            "case": case,
                            "low_price": 1,
                            "high_price": 2,
                            "low_annualized_return": 0.01,
                            "high_annualized_return": 0.02,
                        }
                        for case in ("bear", "base", "bull")
                    ],
                },
            },
            "metadata": {},
        }
    )
    legacy = StoredAnalysisDocument(
        {
            "analysis_id": 8,
            "content": {"thesis_card_version": "individual-thesis-card-v1"},
            "metadata": {},
        }
    )
    output = tmp_path / "thesis-summaries.json"

    with patch(
        "kncompanyscraper.repositories.analysis_repository.AnalysisRepository"
    ) as repository:
        repository.return_value.get_latest_validated_stock_analyses.return_value = {
            42: current,
            43: legacy,
        }
        agent._cmd_export_thesis_summaries(SimpleNamespace(output=output))

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert list(exported) == ["42"]
    assert exported["42"]["one_sentence_thesis"] == current.thesis_summary[
        "one_sentence_thesis"
    ]
    assert "validated v2 thesis summaries" in capsys.readouterr().out


def test_sync_agent_evidence_handles_companies_without_explicit_mfn_slug(capsys):
    shortlist = SimpleNamespace(company_id=153)
    service = MagicMock()
    run = MagicMock()
    service.analyze_watchlist.return_value = run
    run.ranking.shortlist_for_agent.return_value = [shortlist]
    company = SimpleNamespace(id=153, name="Avtech", mfn_slug=None)
    ingestion = MagicMock()
    ingestion.sync_company.return_value = SimpleNamespace(
        releases_added=1, documents_added=2
    )

    with (
        patch(
            "kncompanyscraper.repositories.company_repository.CompanyRepository"
        ) as company_repository,
        patch(
            "kncompanyscraper.repositories.news_repository.NewsRepository"
        ),
        patch(
            "kncompanyscraper.repositories.research_document_repository.ResearchDocumentRepository"
        ),
        patch(
            "kncompanyscraper.analysis.agent.research_document_ingestion.ResearchDocumentIngestionService",
            return_value=ingestion,
        ),
        patch(
            "kncompanyscraper.composition.build_watchlist_analysis_service",
            return_value=service,
        ),
    ):
        company_repository.return_value.get_by_id.return_value = company
        agent._cmd_sync_agent_evidence(SimpleNamespace(max_candidates=1))

    ingestion.sync_company.assert_called_once_with(company)
    run.ranking.shortlist_for_agent.assert_called_once_with(top_n=1, max_total=1)
    assert "1 releases, 2 report PDFs added" in capsys.readouterr().out


def test_analyze_shortlist_defaults_to_local_provider():
    args = build_parser().parse_args(["analyze-shortlist"])

    assert args.provider == "local"


def test_audit_thesis_calibration_exports_flags_and_reads_history(tmp_path, capsys):
    output = tmp_path / "calibration.json"
    repository = MagicMock()
    repository.get_latest_validated_stock_analyses.return_value = {}
    repository.get_validated_stock_analysis_revisions.return_value = {}

    with patch(
        "kncompanyscraper.repositories.analysis_repository.AnalysisRepository",
        return_value=repository,
    ):
        agent._cmd_audit_thesis_calibration(SimpleNamespace(output=output))

    assert json.loads(output.read_text(encoding="utf-8"))["diagnostic_only"] is True
    repository.get_validated_stock_analysis_revisions.assert_called_once_with()
    assert "diagnostic thesis calibration audit" in capsys.readouterr().out


def test_audit_thesis_contract_coverage_exports_latest_validated_cards(
    tmp_path, capsys
):
    output = tmp_path / "contract-coverage.json"
    repository = MagicMock()
    repository.get_latest_validated_stock_analyses.return_value = {}

    with patch(
        "kncompanyscraper.repositories.analysis_repository.AnalysisRepository",
        return_value=repository,
    ):
        agent._cmd_audit_thesis_contract_coverage(SimpleNamespace(output=output))

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert exported["measurement_version"] == "thesis-contract-coverage-v2"
    assert exported["coverage_rate"] is None
    repository.get_latest_validated_stock_analyses.assert_called_once_with()
    assert "0 complete (n/a)" in capsys.readouterr().out


def test_audit_thesis_contract_coverage_command_is_registered():
    args = build_parser().parse_args(
        ["audit-thesis-contract-coverage", "--output", "coverage.json"]
    )

    assert args.func is agent._cmd_audit_thesis_contract_coverage


def test_analyze_company_parses_one_selector_form_or_resume():
    args = build_parser().parse_args(["analyze-company", "--tickers", "MSAB B", "AVT B"])

    assert args.tickers == ["MSAB B", "AVT B"]
    assert args.company_ids is None
    assert args.resume_job_id is None

    resumed = build_parser().parse_args(
        ["analyze-company", "--resume-job-id", "1234"]
    )
    assert resumed.resume_job_id == 1234


def test_repair_agent_report_parses_authoritative_source_fields():
    args = build_parser().parse_args(
        [
            "repair-agent-report",
            "--company-id",
            "153",
            "--title",
            "AVTECH Annual Report 2024",
            "--url",
            "https://storage.mfn.se/avtech-annual-report-2024.pdf",
            "--published-at",
            "2025-04-11T08:30:00+02:00",
            "--document-type",
            "annual_report",
        ]
    )

    assert args.company_id == 153
    assert args.document_type == "annual_report"
    assert args.func is agent._cmd_repair_agent_report


def test_analyze_company_summary_distinguishes_all_outcomes(capsys):
    outcomes = [
        SimpleNamespace(ticker="A", status="accepted", job_id=1, resume_command="resume 1"),
        SimpleNamespace(
            ticker="B", status="blocked-before-model", job_id=2, resume_command="resume 2"
        ),
        SimpleNamespace(ticker="C", status="failed", job_id=3, resume_command="resume 3"),
        SimpleNamespace(ticker="D", status="resumable", job_id=4, resume_command="resume 4"),
        SimpleNamespace(
            ticker="E", status="already-completed", job_id=5, resume_command="resume 5"
        ),
    ]
    pipeline = MagicMock()
    pipeline.resolve_companies.return_value = [SimpleNamespace(id=1)]
    pipeline.run.return_value = outcomes

    with (
        patch(
            "kncompanyscraper.composition.build_agent_model_adapter",
            return_value=MagicMock(),
        ),
        patch(
            "kncompanyscraper.composition.build_company_analysis_pipeline",
            return_value=pipeline,
        ),
    ):
        agent._cmd_analyze_company(
            SimpleNamespace(
                company_ids=[1],
                tickers=None,
                resume_job_id=None,
                provider=None,
                model=None,
                reasoning_effort=None,
            )
        )

    output = capsys.readouterr().out
    assert "A: accepted" in output
    assert "B: blocked-before-model" in output
    assert "C: failed" in output
    assert "D: resumable" in output
    assert "E: already-completed" in output
    assert "Resume: resume 4" in output
    assert (
        "Summary: accepted=1, blocked-before-model=1, failed=1, "
        "resumable=1, already-completed=1"
    ) in output


def test_analyze_company_does_not_enter_ranking_or_monthly_cohort_workflows():
    pipeline = MagicMock()
    pipeline.resolve_companies.return_value = [SimpleNamespace(id=114)]
    pipeline.run.return_value = []
    adapter = SimpleNamespace(model="gpt-5.6-luna", reasoning_effort="high")

    with (
        patch(
            "kncompanyscraper.composition.build_agent_model_adapter",
            return_value=adapter,
        ),
        patch(
            "kncompanyscraper.composition.build_company_analysis_pipeline",
            return_value=pipeline,
        ),
        patch(
            "kncompanyscraper.composition.build_watchlist_analysis_service",
            side_effect=AssertionError("exact-company analysis entered ranking"),
        ),
        patch(
            "kncompanyscraper.composition.refresh_agent_cohort_snapshot",
            side_effect=AssertionError("exact-company analysis entered cohort"),
        ),
    ):
        agent._cmd_analyze_company(
            SimpleNamespace(
                company_ids=[114],
                tickers=None,
                resume_job_id=None,
                provider=None,
                model=None,
                reasoning_effort=None,
            )
        )

    pipeline.run.assert_called_once()
    assert pipeline.run.call_args.kwargs["settings"] == {
        "provider": "local",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
    }
