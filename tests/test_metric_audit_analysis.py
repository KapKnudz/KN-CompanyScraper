from datetime import date

import pytest

from kncompanyscraper.analysis.backtesting.metric_audit_analysis import (
    MetricRow,
    analyze_metric_audit,
    load_metric_rows,
)


def _rows():
    rows = []
    for month in range(1, 5):
        for company_id in range(1, 11):
            good = company_id * 10.0
            bad = 100.0 - good
            for metric, score in (("good", good), ("bad", bad)):
                rows.append(
                    MetricRow(
                        observation_date=date(2024, month, 28),
                        company_id=company_id,
                        category="quality",
                        metric=metric,
                        raw_value=score,
                        normalized_score=score,
                        configured_weight=0.5,
                        effective_weight=0.5,
                        category_score=50.0,
                        total_category_weight=1.0,
                        available=True,
                        transformation="linear[0,100]",
                        dependencies=("earnings",),
                        cross_category_dependencies=(),
                        realized_return=company_id / 100.0,
                        benchmark_return=0.05,
                    )
                )
    return rows


def test_leave_one_out_separates_harmful_metric_on_holdout():
    report = analyze_metric_audit(_rows())
    diagnostics = {item.key: item for item in report.diagnostics}

    assert diagnostics["quality.bad"].holdout_spread_delta == pytest.approx(0.18)
    assert diagnostics["quality.bad"].score_return_correlation == pytest.approx(-1.0)
    assert diagnostics["quality.good"].score_return_correlation == pytest.approx(1.0)
    assert report.redundant_pairs[0].correlation == pytest.approx(-1.0)
    assert report.shared_dependencies == {
        "earnings": ("quality.bad", "quality.good")
    }


def test_multiple_metric_ablation_uses_one_reconstructed_category():
    from kncompanyscraper.analysis.backtesting.metric_audit_analysis import (
        evaluate_metric_policy,
    )

    result = evaluate_metric_policy(
        _rows(),
        ablated_metrics=frozenset({"quality.bad"}),
    )

    assert result.top_bottom_spread == pytest.approx(0.09)


def test_metric_audit_reports_bounded_weight_and_threshold_sensitivity():
    report = analyze_metric_audit(_rows())
    weights = {
        (item.key, item.variant): item for item in report.weight_sensitivities
    }
    thresholds = {
        (item.key, item.variant): item
        for item in report.threshold_sensitivities
    }

    assert weights[("quality.good", "weight_2x")].holdout_spread_delta > 0
    assert weights[("quality.bad", "weight_0.5x")].holdout_spread_delta > 0
    assert ("quality.good", "threshold_0.8x") in thresholds
    assert ("quality.good", "threshold_1.2x") in thresholds


def test_loader_rejects_pre_return_audit_schema(tmp_path):
    path = tmp_path / "audit.csv"
    path.write_text("observation_date,company_id,metric\n")

    with pytest.raises(ValueError, match="benchmark_12m_return"):
        load_metric_rows(path)
