import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from kncompanyscraper.analysis.agent.output_schema import CompanyFact
from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
from tests.test_agent_result_boundary import valid_result


def test_save_stock_analysis_persists_canonical_json_and_returns_id():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(123,), None, (456,)]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    result = valid_result()

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        analysis_id = AnalysisRepository().save_stock_analysis(
            result,
            created_by="test-model",
            metadata={"prompt_version": 1},
        )

    sql, params = cursor.execute.call_args_list[1].args
    assert "INSERT INTO analysis" in sql
    assert params[0] == 42
    assert json.loads(params[1]) == result.to_dict()
    assert params[2] == "test-model"
    assert params[3].adapted == {"prompt_version": 1}
    assert analysis_id == 123
    thesis_sql, thesis_params = cursor.execute.call_args_list[3].args
    assert "INSERT INTO company_thesis_revisions" in thesis_sql
    assert thesis_params[1:5] == (1, None, 123, "initial")


def test_save_stock_analysis_persists_structured_facts_on_next_revision():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(123,), (456, 2), (457,)]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    result = valid_result()
    result.company_fact_ledger.revenue_drivers = [
        CompanyFact(
            statement="Subscription revenue grew.",
            evidence_kind="fact",
            source_ids=["news:21"],
            source_date="2026-08-01",
            reporting_period="2026-Q2",
        )
    ]

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        analysis_id = AnalysisRepository().save_stock_analysis(
            result,
            created_by="test-model",
            metadata={"evidence_as_of": "2026-08-16"},
        )

    assert analysis_id == 123
    thesis_params = cursor.execute.call_args_list[3].args[1]
    assert thesis_params[1:5] == (3, 456, 123, "full_reassessment")
    assert cursor.executemany.call_args.args[1] == [
        (
            42,
            457,
            "revenue_drivers",
            "Subscription revenue grew.",
            "fact",
            ["news:21"],
            "2026-08-01",
            "2026-Q2",
        )
    ]


def test_save_stock_analysis_marks_incremental_revision():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(123,), (456, 2), (457,)]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        AnalysisRepository().save_stock_analysis(
            valid_result(),
            created_by="test-model",
            metadata={"thesis_revision_type": "incremental_update"},
        )

    thesis_params = cursor.execute.call_args_list[3].args[1]
    assert thesis_params[4] == "incremental_update"


def test_save_and_update_raw_stock_analysis():
    cursor = MagicMock()
    cursor.fetchone.return_value = (77,)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        repository = AnalysisRepository()
        analysis_id = repository.save_stock_analysis_raw(
            42,
            '{"raw": true}',
            "test-model",
            {"model_response_id": "resp_123"},
        )
        repository.update_raw_validation(analysis_id, "rejected", "bad citation")

    assert analysis_id == 77
    insert_params = cursor.execute.call_args_list[0].args[1]
    assert insert_params[0:3] == (42, '{"raw": true}', "test-model")
    assert insert_params[3].adapted == {
        "validation_status": "pending",
        "model_response_id": "resp_123",
    }
    update_params = cursor.execute.call_args_list[1].args[1]
    assert "metadata - 'validation_error'" in cursor.execute.call_args_list[1].args[0]
    assert update_params[0].adapted == {
        "validation_status": "rejected",
        "validation_error": "bad citation",
    }


def test_get_latest_validated_stock_analyses_parses_content():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 7,
            "company_id": 42,
            "content": json.dumps(valid_result().to_dict()),
            "created_by": "test-model",
            "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
            "metadata": {"validation_status": "accepted"},
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        analyses = AnalysisRepository().get_latest_validated_stock_analyses()

    assert analyses[42]["analysis_id"] == 7
    assert analyses[42]["content"]["company_id"] == 42
    sql = cursor.execute.call_args[0][0]
    assert "validation_status" in sql


def test_get_latest_rejected_incremental_updates_filters_candidates():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 11,
            "company_id": 42,
            "content": '{"impact":"thesis_strengthened"}',
            "created_by": "test-model",
            "metadata": {"validation_status": "rejected"},
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        rows = AnalysisRepository().get_latest_rejected_incremental_updates([42, 7])

    assert rows[42]["id"] == 11
    assert cursor.execute.call_args.args[1] == ([42, 7],)


def test_get_latest_rejected_initial_analyses_filters_candidates():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "id": 12,
            "company_id": 42,
            "content": '{"company_id":42}',
            "created_by": "test-model",
            "metadata": {"validation_status": "rejected"},
        }
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch(
        "kncompanyscraper.repositories.analysis_repository.get_connection",
        return_value=connection,
    ):
        rows = AnalysisRepository().get_latest_rejected_initial_analyses([42, 7])

    assert rows[42]["id"] == 12
    assert cursor.execute.call_args.args[1] == ([42, 7],)
    assert "COALESCE(metadata->>'analysis_mode', 'initial') = 'initial'" in (
        cursor.execute.call_args.args[0]
    )
