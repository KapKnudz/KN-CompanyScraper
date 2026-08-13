import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
from tests.test_agent_result_boundary import valid_result


def test_save_stock_analysis_persists_canonical_json_and_returns_id():
    cursor = MagicMock()
    cursor.fetchone.return_value = (123,)
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

    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO analysis" in sql
    assert params[0] == 42
    assert json.loads(params[1]) == result.to_dict()
    assert params[2] == "test-model"
    assert params[3].adapted == {"prompt_version": 1}
    assert analysis_id == 123


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
