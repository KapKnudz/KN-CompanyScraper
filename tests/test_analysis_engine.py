from unittest.mock import MagicMock

from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine


def test_analysis_engine_runs_each_skill_once_and_keys_results_by_name():
    first = MagicMock(name="first")
    first.name = "financial"
    first.run.return_value = {"score": 1}
    second = MagicMock(name="second")
    second.name = "valuation"
    second.run.return_value = {"score": 2}

    result = AnalysisEngine([first, second]).analyze("company")

    assert result == {"financial": {"score": 1}, "valuation": {"score": 2}}
    first.run.assert_called_once_with("company")
    second.run.assert_called_once_with("company")


def test_analysis_engine_analyzes_only_explicit_companies():
    skill = MagicMock()
    skill.name = "financial"
    skill.run.side_effect = lambda company: {"company_id": company.id}
    company_two = MagicMock(id=2)

    result = AnalysisEngine([skill]).analyze_companies([company_two])

    assert result == {2: {"financial": {"company_id": 2}}}
    skill.run.assert_called_once_with(company_two)
