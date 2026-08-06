import json
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
